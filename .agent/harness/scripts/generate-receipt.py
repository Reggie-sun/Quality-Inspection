#!/usr/bin/env python3
"""Build task receipts and validate one literal immutable Harness run."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable
from xml.etree import ElementTree

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
MIRROR_PATH = HARNESS / "contracts/p0-contracts.json"
BINDINGS_PATH = HARNESS / "contracts/global-contract-bindings.json"
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
SYMBOL_EVAL_ARTIFACT = "artifacts/visual-symbol-eval.json"
SYMBOL_VERDICT_ARTIFACT = "artifacts/visual-symbol-annotation-verdict.json"
SYMBOL_EVAL_ARTIFACTS = frozenset(
    {SYMBOL_EVAL_ARTIFACT, SYMBOL_VERDICT_ARTIFACT}
)
INPUT_ARTIFACT_PREFIX = "input-artifact:"
PROVIDER_FIXTURE_PREFIX = "provider-fixture:"
PROVIDER_FIXTURE_PATHS = (
    ".agent/harness/fixtures/providers/tencent-ocr/general-accurate-v1.json",
    ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json",
)

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
    "human-verdict.schema.json",
    "live-run-evidence.schema.json",
    "p0-contracts.schema.json",
    "provider-fixture.schema.json",
    "receipt.schema.json",
    "run.schema.json",
    "visual-symbol-annotation-verdict.schema.json",
    "visual-symbol-eval.schema.json",
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


def _live_evidence_policy() -> ModuleType:
    name = "qi_live_evidence_policy"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = HARNESS / "scripts/live_evidence_policy.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared live evidence policy")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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
    *,
    root: Path = ROOT,
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
    if (mode, scope, task_id) == ("fixture", "task", "D2-T2"):
        for relative_path in PROVIDER_FIXTURE_PATHS:
            pairs.append(
                (
                    f"{PROVIDER_FIXTURE_PREFIX}{relative_path}",
                    _read_repository_fixture(root, relative_path),
                )
            )
    artifacts = dict(input_artifacts or {})
    artifact_names = set(artifacts)
    if artifact_names and artifact_names not in (
        {CURRENT_FOUR_ARTIFACT},
        SYMBOL_EVAL_ARTIFACTS,
        {CURRENT_FOUR_ARTIFACT, *SYMBOL_EVAL_ARTIFACTS},
    ):
        raise ValueError("unsupported input artifact set")
    for name, artifact in artifacts.items():
        if not isinstance(artifact, bytes):
            raise ValueError("input artifact content must be bytes")
        pairs.append((f"{INPUT_ARTIFACT_PREFIX}{name}", artifact))
    return _identity_from_pairs(pairs)


def _read_repository_fixture(root: Path, relative_path: str) -> bytes:
    repository = root.absolute()
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("sanitized Provider fixture path is not repository-relative")
    candidate = repository / relative
    current = repository
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(
                f"sanitized Provider fixture path contains a symlink: {relative_path}"
            )
    if not candidate.is_file():
        raise ValueError(f"missing sanitized Provider fixture: {relative_path}")
    try:
        candidate.resolve(strict=True).relative_to(repository.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"sanitized Provider fixture escapes repository root: {relative_path}"
        ) from exc
    return candidate.read_bytes()


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
    name_set = set(names)
    if name_set and name_set not in (
        {CURRENT_FOUR_ARTIFACT},
        SYMBOL_EVAL_ARTIFACTS,
        {CURRENT_FOUR_ARTIFACT, *SYMBOL_EVAL_ARTIFACTS},
    ):
        raise ValueError("unsupported sealed input artifact set")
    if len(names) != len(name_set):
        raise ValueError("duplicate sealed input artifact identity component")
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
        root=root,
    ):
        reasons.append("input_identity_changed")
    if now > valid_until:
        reasons.append("receipt_expired")
    return sorted(reasons)


def _validate_binding_projection(
    mirror: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> None:
    if (
        bindings.get("contract_definition_hash")
        != mirror.get("contract_definition_hash")
    ):
        raise ValueError("typed bindings do not match the P0 contract definition")
    mirror_ids = {
        row["p0_contract_id"]
        for row in mirror.get("contracts", [])
        if isinstance(row, Mapping) and isinstance(row.get("p0_contract_id"), str)
    }
    bound_ids: set[str] = set()
    for binding in bindings.get("bindings", []):
        if not isinstance(binding, Mapping):
            raise ValueError("typed binding must be one object")
        buckets = [set(binding.get(name, [])) for name in BUCKETS]
        if any(
            left & right
            for index, left in enumerate(buckets)
            for right in buckets[index + 1 :]
        ):
            raise ValueError("typed binding collapses primary and related relations")
        for bucket in buckets:
            if not bucket <= mirror_ids:
                raise ValueError("typed binding references an unknown P0 contract")
            bound_ids.update(bucket)
    required_bound_ids = {
        row["p0_contract_id"]
        for row in mirror.get("contracts", [])
        if isinstance(row, Mapping)
        and (
            row.get("global_contract_id") is not None
            or bool(row.get("related_global_contract_ids"))
        )
    }
    if not required_bound_ids <= bound_ids:
        raise ValueError("typed bindings leave a P0 contract relation unbound")


def _run_artifact_path(
    root: Path,
    run: Mapping[str, Any],
    artifact_ref: str,
) -> Path:
    return _live_evidence_policy().run_artifact_path(root, run, artifact_ref)


def validate_final_p0_release(
    root: Path,
    run: Mapping[str, Any],
    result_by_id: Mapping[str, Mapping[str, Any]],
    mirror: Mapping[str, Any],
    bindings: Mapping[str, Any],
    policies: Mapping[str, Mapping[str, Any]],
) -> None:
    _validate_binding_projection(mirror, bindings)
    _live_evidence_policy().validate_final_p0_release(
        root,
        run,
        result_by_id,
        policies,
        schema_validator=validate_schema,
    )


def _junit_failure_evidence(
    path: Path,
) -> tuple[dict[str, int], list[dict[str, str]]]:
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
        summary = {
            name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
            for name in ("tests", "failures", "errors", "skipped")
        }
        cases: list[dict[str, str]] = []
        for test_case in root.findall(".//testcase"):
            properties = {
                str(item.attrib.get("name")): str(item.attrib.get("value"))
                for item in test_case.findall("./properties/property")
            }
            if "failure_point" in properties:
                cases.append(
                    {
                        "test_name": str(test_case.attrib.get("name", "")),
                        **properties,
                    }
                )
        return summary, cases
    except (ElementTree.ParseError, OSError, TypeError, ValueError) as exc:
        raise ValueError("failure proof JUnit evidence is invalid") from exc


def _validate_failure_proof(
    root: Path,
    run: dict[str, Any],
    result_by_id: dict[str, dict[str, Any]],
    contracts_by_id: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> None:
    proof = policy.get("failure_proof")
    if not isinstance(proof, dict):
        raise ValueError("failure severity policy is missing failure_proof")
    target = (proof.get("mode"), proof.get("scope"), proof.get("task_id"))
    current = (run["mode"], run["scope"], run["task_id"])
    task_failure_proof = current == target
    full_p0_failure_proof = current == ("live", "full-p0", None)
    if not task_failure_proof and not full_p0_failure_proof:
        return

    contract_id = proof.get("contract_id")
    if task_failure_proof and run["selected_contract_ids"] != [contract_id]:
        raise ValueError("failure proof must select its one registered contract")
    if full_p0_failure_proof and contract_id not in run["selected_contract_ids"]:
        raise ValueError("full-P0 run must include the registered failure proof")
    result = result_by_id.get(str(contract_id))
    if result is None:
        raise ValueError("failure proof result is missing")
    selector = proof.get("selector")
    if result.get("command") != selector:
        raise ValueError("failure proof result does not use its registered selector")
    severity = contracts_by_id[str(contract_id)]["blocking_level"]
    if severity not in policy.get("formal_success_forbidden_when", []):
        raise ValueError("failure proof contract severity does not veto formal success")

    report_ref = proof.get("report_ref")
    junit_ref = proof.get("junit_ref")
    if not isinstance(report_ref, str) or not isinstance(junit_ref, str):
        raise ValueError("failure proof evidence refs must be strings")
    artifact_refs = set(result.get("artifact_refs", []))
    if report_ref not in artifact_refs:
        raise ValueError("failure proof result is missing its structured report")
    report = _load_json(_run_artifact_path(root, run, report_ref))

    if (
        report.get("schema_version") != "failure-proof/1"
        or report.get("run_id") != run["run_id"]
        or report.get("selector") != selector
        or report.get("result_state") != result["result_state"]
        or report.get("exit_code") != result["exit_code"]
    ):
        raise ValueError("failure proof report identity does not match its result")

    command = report.get("command")
    test_path = proof.get("test_path")
    if (
        not isinstance(command, list)
        or len(command) < 4
        or command[1:3] != ["-m", "pytest"]
        or test_path not in command
        or any(Path(str(token)).name == "run-p0.py" for token in command)
    ):
        raise ValueError("failure proof did not run the registered pytest command")

    if result["result_state"] != "passed":
        validation_errors = report.get("validation_errors")
        if not isinstance(validation_errors, list) or not validation_errors:
            raise ValueError("non-passing failure proof lacks structured error evidence")
        report_junit_ref = report.get("junit_ref")
        if report_junit_ref is not None:
            if report_junit_ref != junit_ref or junit_ref not in artifact_refs:
                raise ValueError("non-passing failure proof JUnit ref is inconsistent")
            _run_artifact_path(root, run, junit_ref)
        return

    if (
        result["exit_code"] != 0
        or report.get("junit_ref") != junit_ref
        or report.get("validation_errors") != []
        or junit_ref not in artifact_refs
    ):
        raise ValueError("passing failure proof lacks complete structured evidence")
    junit_summary, junit_cases = _junit_failure_evidence(
        _run_artifact_path(root, run, junit_ref)
    )
    if (
        junit_summary != report.get("pytest_summary")
        or junit_cases != report.get("cases")
    ):
        raise ValueError("failure proof JUnit evidence does not match its report")

    expected_points = proof.get("failure_points")
    if (
        not isinstance(expected_points, list)
        or report.get("failure_points") != expected_points
        or report.get("pytest_summary")
        != {
            "tests": len(expected_points),
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
    ):
        raise ValueError("failure proof did not cover every registered failure point")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(expected_points):
        raise ValueError("failure proof structured cases are incomplete")
    zero_properties = proof.get("zero_count_properties")
    allowed_severities = proof.get("allowed_error_severities")
    evidence_requirements = proof.get("evidence_requirements")
    if not isinstance(zero_properties, list) or not isinstance(
        allowed_severities, list
    ) or not isinstance(evidence_requirements, dict):
        raise ValueError("failure proof property policy is invalid")
    for point, case in zip(expected_points, cases, strict=True):
        expected_evidence = evidence_requirements.get(point)
        if not isinstance(case, dict) or not isinstance(expected_evidence, dict):
            raise ValueError("failure proof case must be one structured object")
        if (
            case.get("failure_point") != point
            or case.get("test_name")
            != f"test_p0_acc_007_no_silent_success[{point}]"
            or case.get("export_status") != "failed"
            or case.get("error_severity") not in allowed_severities
            or any(case.get(name) != "0" for name in zero_properties)
            or any(
                case.get(name) != str(value)
                for name, value in expected_evidence.items()
            )
        ):
            raise ValueError(f"failure proof case does not veto formal success: {point}")


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

    validate_schema(run, "run.schema.json", root)
    validate_schema(mirror, "p0-contracts.schema.json", root)
    validate_schema(bindings, "global-contract-bindings.schema.json", root)
    for result in results:
        validate_schema(result, "contract-result.schema.json", root)

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

    for p0_id in selected_ids:
        expected_selector = contracts_by_id[p0_id]["verification_selector"]
        if result_by_id[p0_id].get("command") != expected_selector:
            raise ValueError(
                f"contract result command does not match mirror selector: {p0_id}"
            )
    _validate_failure_proof(
        root,
        run,
        result_by_id,
        contracts_by_id,
        policies["failure_severity_policy"],
    )

    result_counts = _empty_counts()
    per_severity_counts = {severity: _empty_counts() for severity in SEVERITIES}
    for p0_id in selected_ids:
        result = result_by_id[p0_id]
        state = result["result_state"]
        severity = contracts_by_id[p0_id]["blocking_level"]
        result_counts[state] += 1
        per_severity_counts[severity][state] += 1

    reasons = _freshness_reasons(
        root,
        run,
        mirror,
        policies,
        current_time,
        valid_until,
    )
    completed_at = _parse_iso(run["completed_at"])
    if generated < completed_at:
        reasons.append("receipt_precedes_run_completion")
    if generated > current_time:
        reasons.append("receipt_generated_in_future")
    reasons = sorted(set(reasons))

    overall = _overall_verdict(result_counts)
    formal_allowed = run["scope"] == policies["harness_policy"]["formal_p0_scope"]
    if formal_allowed and overall == "passed":
        if reasons:
            overall = "blocked"
        else:
            validate_final_p0_release(
                root,
                run,
                result_by_id,
                mirror,
                bindings,
                policies,
            )
    formal_verdict = overall if formal_allowed else None

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

    bootstrap_run = {"run_id": run_id}
    run = _load_json(_run_artifact_path(root, bootstrap_run, "run.json"))
    results_document = _load_json(
        _run_artifact_path(root, bootstrap_run, "contract-results.json")
    )
    receipt = _load_json(
        _run_artifact_path(root, bootstrap_run, "receipt.json")
    )
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
