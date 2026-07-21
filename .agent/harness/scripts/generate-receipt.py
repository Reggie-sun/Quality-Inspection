#!/usr/bin/env python3
"""Build task receipts and validate one literal immutable Harness run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
MIRROR_PATH = HARNESS / "contracts/p0-contracts.json"
BINDINGS_PATH = HARNESS / "contracts/global-contract-bindings.json"
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
INPUT_ARTIFACT_PREFIX = "input-artifact:"

POLICY_FILES = {
    "harness_policy": "harness-policy.yaml",
    "p0_acceptance_policy": "p0-acceptance-policy.yaml",
    "provider_call_policy": "provider-call-policy.yaml",
    "failure_severity_policy": "failure-severity-policy.yaml",
}
RESULT_STATES = ("passed", "failed", "blocked", "not_run")
SEVERITIES = ("fatal", "blocking", "review_required", "warning", "informational")
BUCKETS = (
    "primary_p0_contract_ids",
    "related_business_p0_contract_ids",
    "related_implementation_p0_contract_ids",
)
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
SCHEMA_FILES = (
    "contract-result.schema.json",
    "current-four-manifest.schema.json",
    "global-contract-bindings.schema.json",
    "p0-contracts.schema.json",
    "provider-fixture.schema.json",
    "receipt.schema.json",
    "run.schema.json",
)
CODE_IDENTITY_SOURCE_GLOBS = (
    (".agent/harness/scripts", ("*.py",)),
    ("backend/alembic", ("**/*.py",)),
    ("backend/app", ("**/*.py", "**/*.schema.json")),
    ("backend/tests", ("**/*.py",)),
    (
        "frontend/src",
        (
            "**/*.css",
            "**/*.js",
            "**/*.jsx",
            "**/*.ts",
            "**/*.tsx",
        ),
    ),
    (
        "frontend/e2e",
        ("**/*.css", "**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"),
    ),
)
CODE_IDENTITY_EXPLICIT_FILES = (
    ".env.example",
    "Dockerfile",
    "Makefile",
    "compose.yaml",
    "environment.yml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "backend/Dockerfile",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    "frontend/Dockerfile",
    "frontend/eslint.config.js",
    "frontend/index.html",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/vitest.config.ts",
    *(f".agent/harness/policy/{filename}" for filename in POLICY_FILES.values()),
    *(f".agent/harness/schemas/{filename}" for filename in SCHEMA_FILES),
)
PROVIDER_NETWORK_ENABLED_KEYS = (
    "QI_PROVIDER_NETWORK_ENABLED",
    "PROVIDER_NETWORK_ENABLED",
    "OCR_PROVIDER_NETWORK_ENABLED",
    "VISION_PROVIDER_NETWORK_ENABLED",
)
PROVIDER_MODE_KEYS = (
    "QI_PROVIDER_MODE",
    "PROVIDER_MODE",
    "OCR_PROVIDER_MODE",
    "VISION_PROVIDER_MODE",
    "VISION_LLM_PROVIDER_MODE",
)
TRUTHY_PROVIDER_CONTROLS = {"1", "true", "yes", "on", "enabled", "live"}
OFFLINE_PROVIDER_MODES = {"", "disabled", "fixture", "mock", "none", "offline"}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _identity_from_pairs(pairs: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
    ordered = sorted(pairs, key=lambda pair: pair[0])
    digest = hashlib.sha256()
    components: list[str] = []
    for name, content in ordered:
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        components.append(name)
    return {
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "components": components,
    }


def _is_excluded(path: Path, root: Path) -> bool:
    absolute_root = root.absolute()
    absolute_path = path.absolute()
    relative = absolute_path.relative_to(absolute_root)
    current = absolute_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    if relative == Path(".env.example"):
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    return any(
        part.startswith(".") and not (index == 0 and part == ".agent")
        for index, part in enumerate(relative.parts)
    )


def code_identity(root: Path = ROOT) -> dict[str, Any]:
    """Hash executable/test/Harness/policy/schema/dependency content, not Git state."""
    root = root.absolute()
    candidates: set[Path] = set()
    for relative, patterns in CODE_IDENTITY_SOURCE_GLOBS:
        directory = (root / relative).absolute()
        if not directory.is_dir() or _is_excluded(directory, root):
            continue
        for pattern in patterns:
            for path in directory.glob(pattern):
                candidate = path.absolute()
                if not _is_excluded(candidate, root) and candidate.is_file():
                    candidates.add(candidate)
    for relative in CODE_IDENTITY_EXPLICIT_FILES:
        candidate = (root / relative).absolute()
        if not _is_excluded(candidate, root) and candidate.is_file():
            candidates.add(candidate)

    pairs = [
        (str(path.relative_to(root)), path.read_bytes())
        for path in candidates
    ]
    return _identity_from_pairs(pairs)


def load_policies(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    policies: dict[str, dict[str, Any]] = {}
    for key, filename in POLICY_FILES.items():
        path = root / ".agent/harness/policy" / filename
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("schema_version"), str):
            raise ValueError(f"invalid policy document: {filename}")
        policies[key] = document
    return policies


def policy_versions(policies: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {key: policies[key]["schema_version"] for key in POLICY_FILES}


def _provider_control_values(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if environment is None else environment
    values = {
        key: (
            "enabled"
            if source.get(key, "").strip().lower() in TRUTHY_PROVIDER_CONTROLS
            else "disabled"
        )
        for key in PROVIDER_NETWORK_ENABLED_KEYS
    }
    values.update(
        {
            key: source.get(key, "").strip().lower()
            for key in PROVIDER_MODE_KEYS
        }
    )
    return values


def provider_network_enabled(environment: Mapping[str, str] | None = None) -> bool:
    values = _provider_control_values(environment)
    return any(
        values[key] == "enabled" for key in PROVIDER_NETWORK_ENABLED_KEYS
    ) or any(values[key] not in OFFLINE_PROVIDER_MODES for key in PROVIDER_MODE_KEYS)


def config_identity(
    mode: str,
    scope: str,
    task_id: str | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    pairs: list[tuple[str, bytes]] = []
    for filename in POLICY_FILES.values():
        path = root / ".agent/harness/policy" / filename
        pairs.append((str(path.relative_to(root)), path.read_bytes()))
    pairs.append(
        (
            "run-config",
            _canonical_bytes({"mode": mode, "scope": scope, "task_id": task_id}),
        )
    )
    pairs.extend(
        (f"provider-control:{key}", value.encode("utf-8"))
        for key, value in _provider_control_values().items()
    )
    return _identity_from_pairs(pairs)


def input_identity(
    mode: str,
    scope: str,
    task_id: str | None,
    input_artifacts: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    content = _canonical_bytes(
        {
            "identity_kind": "task-selector-set",
            "mode": mode,
            "scope": scope,
            "task_id": task_id,
        }
    )
    pairs = [("task-selector-set", content)]
    for name, artifact in (input_artifacts or {}).items():
        if name != CURRENT_FOUR_ARTIFACT or not isinstance(artifact, bytes):
            raise ValueError("unsupported current-four-manifest input artifact")
        pairs.append((f"{INPUT_ARTIFACT_PREFIX}{name}", artifact))
    return _identity_from_pairs(pairs)


def input_artifacts_from_run(
    run: Mapping[str, Any],
    run_dir: Path,
) -> dict[str, bytes]:
    components = run.get("input_identity", {}).get("components", [])
    names = [
        component.removeprefix(INPUT_ARTIFACT_PREFIX)
        for component in components
        if isinstance(component, str) and component.startswith(INPUT_ARTIFACT_PREFIX)
    ]
    if any(name != CURRENT_FOUR_ARTIFACT for name in names):
        raise ValueError("unsupported current-four-manifest input artifact")
    artifacts: dict[str, bytes] = {}
    for name in names:
        artifact_path = run_dir / name
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ValueError(f"missing sealed input artifact: {name}")
        artifacts[name] = artifact_path.read_bytes()
    return artifacts


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check_contract_authority(root: Path = ROOT) -> None:
    checker = root / ".agent/harness/scripts/check-contracts.py"
    result = subprocess.run(
        [sys.executable, str(checker)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            f"contract authority preflight failed: {detail or 'checker failed'}"
        )


def validate_schema(instance: Any, schema_name: str, root: Path = ROOT) -> None:
    schema_path = root / ".agent/harness/schemas" / schema_name
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        details = []
        for error in errors:
            location = "/".join(str(part) for part in error.absolute_path) or "<root>"
            details.append(f"{location}: {error.message}")
        raise ValueError(f"{schema_name}: {'; '.join(details)}")


def _empty_counts() -> dict[str, int]:
    return {state: 0 for state in RESULT_STATES}


def _overall_verdict(result_counts: dict[str, int]) -> str:
    if result_counts["failed"]:
        return "failed"
    if result_counts["blocked"] or result_counts["not_run"]:
        return "blocked"
    if result_counts["passed"]:
        return "passed"
    return "blocked"


def _binding_evidence(
    bindings: dict[str, Any], selected_contract_ids: set[str]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for binding in bindings["bindings"]:
        selected = {
            name: sorted(selected_contract_ids & set(binding[name])) for name in BUCKETS
        }
        if not any(selected.values()):
            continue
        evidence.append(
            {
                "global_contract_id": binding["global_contract_id"],
                "direct_enforcement": bool(selected["primary_p0_contract_ids"]),
                **selected,
            }
        )
    return evidence


def _freshness_reasons(
    root: Path,
    run: dict[str, Any],
    mirror: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    now: datetime,
    valid_until: datetime,
) -> list[str]:
    reasons: list[str] = []
    if run["contract_definition_hash"] != mirror["contract_definition_hash"]:
        reasons.append("contract_definition_changed")
    if run["policy_versions"] != policy_versions(policies):
        reasons.append("policy_version_changed")
    if run["code_identity"] != code_identity(root):
        reasons.append("executable_content_changed")
    if run["config_identity"] != config_identity(
        run["mode"], run["scope"], run["task_id"], root
    ):
        reasons.append("config_identity_changed")
    input_artifacts = input_artifacts_from_run(
        run,
        root / ".agent/harness/runs" / run["run_id"],
    )
    if run["input_identity"] != input_identity(
        run["mode"],
        run["scope"],
        run["task_id"],
        input_artifacts,
    ):
        reasons.append("input_identity_changed")
    if now > valid_until:
        reasons.append("receipt_expired")
    return sorted(reasons)


def build_receipt(
    root: Path,
    run: dict[str, Any],
    results: list[dict[str, Any]],
    mirror: dict[str, Any],
    bindings: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    *,
    generated_at: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated = _parse_iso(generated_at) if generated_at else datetime.now(timezone.utc)
    current_time = now or generated
    freshness_hours = int(policies["harness_policy"]["receipt_freshness_hours"])
    valid_until = generated + timedelta(hours=freshness_hours)

    selected_ids = list(run["selected_contract_ids"])
    if selected_ids != sorted(set(selected_ids)):
        raise ValueError("selected_contract_ids must be sorted and unique")

    contracts_by_id = {
        row["p0_contract_id"]: row for row in mirror["contracts"]
    }
    if run["scope"] == "task":
        expected_ids = sorted(
            row["p0_contract_id"]
            for row in mirror["contracts"]
            if row["task_id"] == run["task_id"]
        )
        if not expected_ids or selected_ids != expected_ids:
            raise ValueError(
                "task scope selected_contract_ids must exactly match mirror contracts "
                "for run.task_id"
            )
    elif run["scope"] == "full-p0":
        expected_ids = sorted(contracts_by_id)
        required_count = int(
            policies["p0_acceptance_policy"]["required_contract_count"]
        )
        if len(expected_ids) != required_count:
            raise ValueError(
                "full-p0 mirror contract count must equal "
                "p0_acceptance_policy.required_contract_count"
            )
        if selected_ids != expected_ids:
            raise ValueError(
                "full-p0 selected_contract_ids must exactly match all mirror contracts"
            )
    else:
        raise ValueError(f"unsupported receipt scope: {run['scope']}")

    result_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        if result.get("run_id") != run["run_id"]:
            raise ValueError("contract result run_id must equal run.run_id")
        p0_id = result["p0_contract_id"]
        if p0_id in result_by_id:
            raise ValueError(f"duplicate contract result: {p0_id}")
        result_by_id[p0_id] = result
    if set(result_by_id) != set(selected_ids):
        raise ValueError("contract results do not exactly cover selected_contract_ids")

    if not set(selected_ids) <= set(contracts_by_id):
        raise ValueError("run selects an unknown P0 contract ID")

    result_counts = _empty_counts()
    per_severity_counts = {severity: _empty_counts() for severity in SEVERITIES}
    for p0_id in selected_ids:
        result = result_by_id[p0_id]
        state = result["result_state"]
        severity = contracts_by_id[p0_id]["blocking_level"]
        result_counts[state] += 1
        per_severity_counts[severity][state] += 1

    overall = _overall_verdict(result_counts)
    formal_allowed = run["scope"] == policies["harness_policy"]["formal_p0_scope"]
    if formal_allowed and overall == "passed":
        # D1-T1 does not implement current-four/human-trial formal acceptance.
        overall = "blocked"
    formal_verdict = overall if formal_allowed else None
    reasons = _freshness_reasons(
        root,
        run,
        mirror,
        policies,
        current_time,
        valid_until,
    )

    receipt = {
        "schema_version": "receipt/1",
        "run_id": run["run_id"],
        "receipt_scope": run["scope"],
        "task_id": run["task_id"],
        "policy_versions": policy_versions(policies),
        "contract_definition_hash": run["contract_definition_hash"],
        "status_projection_hash": run["status_projection_hash_at_start"],
        "freshness": {
            "fresh": not reasons,
            "valid_until": _iso(valid_until),
            "receipt_freshness_hours": freshness_hours,
            "reasons": reasons,
        },
        "selected_contract_ids": selected_ids,
        "result_counts": result_counts,
        "per_severity_counts": per_severity_counts,
        "binding_evidence": _binding_evidence(bindings, set(selected_ids)),
        "overall_verdict": overall,
        "formal_p0_verdict_allowed": formal_allowed,
        "formal_p0_verdict": formal_verdict,
        "generated_at": _iso(generated),
    }
    validate_schema(receipt, "receipt.schema.json", root)
    return receipt


def check_run(run_id: str, root: Path = ROOT) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(run_id) or run_id in {"latest", "latest-successful"}:
        raise ValueError("--check-run requires one literal generated run ID")
    check_contract_authority(root)
    run_dir = root / ".agent/harness/runs" / run_id
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ValueError(f"run directory does not exist: {run_id}")

    run = _load_json(run_dir / "run.json")
    results_document = _load_json(run_dir / "contract-results.json")
    receipt = _load_json(run_dir / "receipt.json")
    mirror = _load_json(root / MIRROR_PATH.relative_to(ROOT))
    bindings = _load_json(root / BINDINGS_PATH.relative_to(ROOT))
    policies = load_policies(root)

    if run["run_id"] != run_id or results_document.get("run_id") != run_id:
        raise ValueError("run ID mismatch inside immutable evidence")
    if results_document.get("schema_version") != "contract-results/1":
        raise ValueError("invalid contract-results schema_version")
    results = results_document.get("results")
    if not isinstance(results, list):
        raise ValueError("contract-results.json is missing results")

    validate_schema(run, "run.schema.json", root)
    if run["completed_at"] is None:
        raise ValueError("run is not completed")
    for result in results:
        validate_schema(result, "contract-result.schema.json", root)
    validate_schema(receipt, "receipt.schema.json", root)

    expected = build_receipt(
        root,
        run,
        results,
        mirror,
        bindings,
        policies,
        generated_at=receipt["generated_at"],
        now=datetime.now(timezone.utc),
    )
    if _canonical_bytes(expected) != _canonical_bytes(receipt):
        raise ValueError("receipt does not match current run evidence or is stale")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-run", metavar="RUN_ID", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = check_run(args.check_run)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"generate-receipt: {exc}", file=sys.stderr)
        return 1
    print(
        f"run_id={receipt['run_id']} receipt_valid=1 "
        f"scope={receipt['receipt_scope']} overall_verdict={receipt['overall_verdict']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
