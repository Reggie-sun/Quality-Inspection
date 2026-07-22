#!/usr/bin/env python3
"""Run the literal selectors for one P0 task and seal immutable evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import secrets
import shlex
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping
from urllib.parse import urlsplit
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
MIRROR_PATH = HARNESS / "contracts/p0-contracts.json"
BINDINGS_PATH = HARNESS / "contracts/global-contract-bindings.json"
TASK_RE = re.compile(r"^D[0-9]+-T[0-9]+$")
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<"}
CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
NO_SILENT_SUCCESS_SELECTOR = "phase://failure/no-silent-success"
NO_SILENT_SUCCESS_TEST = "backend/tests/e2e/test_no_silent_success.py"
NO_SILENT_SUCCESS_REPORT = "reports/no-silent-success.json"
NO_SILENT_SUCCESS_JUNIT = "reports/no-silent-success.junit.xml"
NO_SILENT_SUCCESS_POINTS = (
    "provider",
    "storage",
    "template",
    "font",
    "ballooned_pdf",
    "sip_excel",
    "manifest",
)
NO_SILENT_SUCCESS_ZERO_PROPERTIES = (
    "successful_exports",
    "formal_downloads",
    "published_refs",
)
NO_SILENT_SUCCESS_EVIDENCE_PROPERTIES = (
    "evidence_source",
    "status_owner",
    "error_code",
    "recorded_stage",
    "error_severity",
    "severity_source",
)
_ACTIVE_RUN_DIR: Path | None = None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location("qi_generate_receipt", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate-receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else "unavailable"


def _junit_failure_evidence(
    path: Path,
) -> tuple[dict[str, int], list[dict[str, str]]]:
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
        if "failure_point" not in properties:
            continue
        cases.append(
            {
                "test_name": str(test_case.attrib.get("name", "")),
                **properties,
            }
        )
    order = {name: index for index, name in enumerate(NO_SILENT_SUCCESS_POINTS)}
    cases.sort(key=lambda item: order.get(item["failure_point"], len(order)))
    return summary, cases


def _failure_phase_outcome(
    selector: str,
    run_dir: Path,
) -> tuple[int | None, str, str, list[str]]:
    junit_path = run_dir / NO_SILENT_SUCCESS_JUNIT
    report_path = run_dir / NO_SILENT_SUCCESS_REPORT
    argv = [
        sys.executable,
        "-m",
        "pytest",
        NO_SILENT_SUCCESS_TEST,
        "-q",
        "-o",
        "junit_family=legacy",
        f"--junitxml={junit_path}",
    ]
    started_at = _iso_now()
    try:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        completed_at = _iso_now()
        report = {
            "schema_version": "failure-proof/1",
            "run_id": run_dir.name,
            "selector": selector,
            "command": argv,
            "exit_code": None,
            "result_state": "blocked",
            "started_at": started_at,
            "completed_at": completed_at,
            "junit_ref": None,
            "pytest_summary": None,
            "failure_points": [],
            "cases": [],
            "validation_errors": [f"pytest could not start: {exc}"],
        }
        _write_json(report_path, report)
        return None, "blocked", report["validation_errors"][0], [NO_SILENT_SUCCESS_REPORT]

    completed_at = _iso_now()
    validation_errors: list[str] = []
    summary: dict[str, int] | None = None
    cases: list[dict[str, str]] = []
    if junit_path.is_file():
        try:
            summary, cases = _junit_failure_evidence(junit_path)
        except (ElementTree.ParseError, OSError, TypeError, ValueError) as exc:
            validation_errors.append(f"invalid JUnit evidence: {exc}")
    else:
        validation_errors.append("pytest did not create JUnit evidence")

    if result.returncode != 0:
        validation_errors.append(f"pytest exited with code {result.returncode}")

    if summary != {"tests": 7, "failures": 0, "errors": 0, "skipped": 0}:
        validation_errors.append("JUnit summary is not seven passing failure cases")
    if [item.get("failure_point") for item in cases] != list(
        NO_SILENT_SUCCESS_POINTS
    ):
        validation_errors.append("JUnit failure points do not match the registered set")
    for item in cases:
        point = item.get("failure_point", "unknown")
        if item.get("export_status") != "failed":
            validation_errors.append(f"{point} did not record failed export status")
        if any(item.get(name) != "0" for name in NO_SILENT_SUCCESS_ZERO_PROPERTIES):
            validation_errors.append(f"{point} exposed formal success evidence")
        if any(not item.get(name) for name in NO_SILENT_SUCCESS_EVIDENCE_PROPERTIES):
            validation_errors.append(f"{point} did not record direct failure evidence")
        if item.get("error_severity") not in {"fatal", "blocking"}:
            validation_errors.append(f"{point} did not record fatal/blocking severity")

    state = (
        "passed"
        if result.returncode == 0 and not validation_errors
        else "failed"
    )
    report = {
        "schema_version": "failure-proof/1",
        "run_id": run_dir.name,
        "selector": selector,
        "command": argv,
        "exit_code": result.returncode,
        "result_state": state,
        "started_at": started_at,
        "completed_at": completed_at,
        "junit_ref": NO_SILENT_SUCCESS_JUNIT if junit_path.is_file() else None,
        "pytest_summary": summary,
        "failure_points": [item["failure_point"] for item in cases],
        "cases": cases,
        "validation_errors": validation_errors,
    }
    _write_json(report_path, report)
    output = "\n".join(
        (
            f"command={shlex.join(argv)}",
            f"exit_code={result.returncode}",
            f"structured_report={NO_SILENT_SUCCESS_REPORT}",
            f"validation_errors={json.dumps(validation_errors, ensure_ascii=False)}",
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        )
    )
    artifact_refs = [NO_SILENT_SUCCESS_REPORT]
    if junit_path.is_file():
        artifact_refs.append(NO_SILENT_SUCCESS_JUNIT)
    return result.returncode, state, output, artifact_refs


def _phase_outcome(
    selector: str,
    mode: str,
    run_dir: Path,
) -> tuple[int | None, str, str, list[str]]:
    parsed = urlsplit(selector)
    requested_mode = parsed.netloc
    phase = parsed.path.lstrip("/")
    if requested_mode != mode:
        return (
            None,
            "blocked",
            f"phase mode mismatch: runner={mode} selector={requested_mode}",
            [],
        )
    if selector == NO_SILENT_SUCCESS_SELECTOR:
        return _failure_phase_outcome(selector, run_dir)
    return (
        None,
        "blocked",
        f"phase://{requested_mode}/{phase} has no D1-T1 handler; no child run was created",
        [],
    )


def _command_outcome(selector: str) -> tuple[int | None, str, str]:
    try:
        argv = shlex.split(selector)
    except ValueError as exc:
        return None, "blocked", f"invalid selector argv: {exc}"
    if not argv or any(token in SHELL_OPERATORS for token in argv):
        return None, "blocked", "selector is not one exact argv command"
    try:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return None, "blocked", f"selector could not start: {exc}"
    state = "passed" if result.returncode == 0 else "failed"
    output = "\n".join(
        (
            f"command={selector}",
            f"exit_code={result.returncode}",
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        )
    )
    return result.returncode, state, output


def _execute_selector(selector: str, mode: str) -> dict[str, Any]:
    started_at = _iso_now()
    if selector.startswith("phase://"):
        if _ACTIVE_RUN_DIR is None:
            exit_code, state, output, artifact_refs = (
                None,
                "blocked",
                "phase selector has no active open run",
                [],
            )
        else:
            exit_code, state, output, artifact_refs = _phase_outcome(
                selector,
                mode,
                _ACTIVE_RUN_DIR,
            )
    else:
        exit_code, state, output = _command_outcome(selector)
        artifact_refs = []
    return {
        "exit_code": exit_code,
        "result_state": state,
        "started_at": started_at,
        "completed_at": _iso_now(),
        "output": output,
        "artifact_refs": artifact_refs,
    }


def _execute_selector_in_run(
    selector: str,
    mode: str,
    run_dir: Path,
) -> dict[str, Any]:
    global _ACTIVE_RUN_DIR
    if _ACTIVE_RUN_DIR is not None:
        raise RuntimeError("selector execution already owns one open run")
    _ACTIVE_RUN_DIR = run_dir
    try:
        return _execute_selector(selector, mode)
    finally:
        _ACTIVE_RUN_DIR = None


def _seal_run(run_dir: Path) -> None:
    descendants = sorted(
        run_dir.rglob("*"),
        key=lambda path: (len(path.parts), str(path)),
        reverse=True,
    )
    for path in descendants:
        if path.is_symlink():
            raise ValueError("run evidence must not contain symlinks")
        if path.is_dir():
            path.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    run_dir.chmod(
        stat.S_IRUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )


def _validate_input_artifacts(
    input_artifacts: Mapping[str, bytes] | None,
) -> dict[str, bytes]:
    artifacts = dict(input_artifacts or {})
    if set(artifacts) - {CURRENT_FOUR_ARTIFACT}:
        raise ValueError("only artifacts/current-four-manifest.json is accepted")
    if any(not isinstance(content, bytes) for content in artifacts.values()):
        raise TypeError("current-four-manifest input artifact must be bytes")
    return artifacts


def _is_sealed(path: Path) -> bool:
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return not bool(path.stat().st_mode & write_bits)


def _load_current_four_artifact(run_id: str) -> dict[str, bytes]:
    if not RUN_ID_RE.fullmatch(run_id) or run_id in {"latest", "latest-successful"}:
        raise ValueError("--current-four-run requires one literal registration run ID")
    run_dir = RUNS / run_id
    artifact_path = run_dir / CURRENT_FOUR_ARTIFACT
    run_path = run_dir / "run.json"
    receipt_path = run_dir / "receipt.json"
    controlled_paths = (run_dir, artifact_path.parent, artifact_path, run_path, receipt_path)
    if any(path.is_symlink() or not path.exists() for path in controlled_paths):
        raise ValueError("registration run is missing sealed current-four evidence")
    if any(not _is_sealed(path) for path in controlled_paths):
        raise ValueError("registration run must be sealed before reuse")

    run = _load_json(run_path)
    receipt = _load_json(receipt_path)
    if (
        run.get("run_id") != run_id
        or run.get("mode") != "live"
        or run.get("scope") != "task"
        or run.get("task_id") != "D2-T1"
        or not run.get("completed_at")
        or receipt.get("run_id") != run_id
        or receipt.get("overall_verdict") != "passed"
    ):
        raise ValueError("current-four source is not a passed D2-T1 registration run")

    artifact = artifact_path.read_bytes()
    manifest = json.loads(artifact)
    receipt_module = _receipt_module()
    receipt_module.validate_schema(
        manifest,
        "current-four-manifest.schema.json",
        ROOT,
    )
    expected_identity = receipt_module.input_identity(
        "live",
        "task",
        "D2-T1",
        {CURRENT_FOUR_ARTIFACT: artifact},
    )
    if run.get("input_identity") != expected_identity:
        raise ValueError(
            "current-four input identity does not match sealed manifest bytes"
        )
    return {CURRENT_FOUR_ARTIFACT: artifact}


def run_task(
    mode: str,
    scope: str,
    task_id: str,
    *,
    input_artifacts: Mapping[str, bytes] | None = None,
) -> tuple[str, str]:
    if scope != "task":
        raise ValueError("D1-T1 implements task scope only; full-p0 orchestration is not available")
    if not TASK_RE.fullmatch(task_id):
        raise ValueError("--task must be a literal Dn-Tn identifier")

    artifacts = _validate_input_artifacts(input_artifacts)
    if artifacts and (mode not in {"fixture", "live"} or task_id != "D2-T1"):
        raise ValueError(
            "current-four-manifest input is limited to fixture/live D2-T1 task runs"
        )

    receipt_module = _receipt_module()
    if mode == "fixture" and receipt_module.provider_network_enabled():
        raise ValueError("fixture mode rejects network-enabled Provider configuration")
    receipt_module.check_contract_authority(ROOT)

    mirror = _load_json(MIRROR_PATH)
    bindings = _load_json(BINDINGS_PATH)
    policies = receipt_module.load_policies(ROOT)
    receipt_module.validate_schema(mirror, "p0-contracts.schema.json", ROOT)
    receipt_module.validate_schema(bindings, "global-contract-bindings.schema.json", ROOT)
    if artifacts:
        receipt_module.validate_schema(
            json.loads(artifacts[CURRENT_FOUR_ARTIFACT]),
            "current-four-manifest.schema.json",
            ROOT,
        )

    selected = sorted(
        (row for row in mirror["contracts"] if row["task_id"] == task_id),
        key=lambda row: row["p0_contract_id"],
    )
    if not selected:
        raise ValueError(f"no P0 contracts select task {task_id}")

    # The identity and run directory exist before any selector is invoked.
    run_id = _new_run_id()
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started_at = _iso_now()
    run = {
        "schema_version": "run/1",
        "run_id": run_id,
        "mode": mode,
        "scope": scope,
        "task_id": task_id,
        "code_identity": receipt_module.code_identity(ROOT),
        "git_revision_at_start": _git_revision(),
        "config_identity": receipt_module.config_identity(mode, scope, task_id, ROOT),
        "input_identity": receipt_module.input_identity(
            mode,
            scope,
            task_id,
            artifacts,
        ),
        "contract_definition_hash": mirror["contract_definition_hash"],
        "status_projection_hash_at_start": mirror["status_projection_hash"],
        "policy_versions": receipt_module.policy_versions(policies),
        "selected_contract_ids": [row["p0_contract_id"] for row in selected],
        "started_at": started_at,
        "completed_at": None,
    }
    for name in ("logs", "reports", "artifacts"):
        (run_dir / name).mkdir()
    for name, content in artifacts.items():
        (run_dir / name).write_bytes(content)
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)

    # Identical selectors execute once; every selected P0 ID still gets a result.
    outcomes: dict[str, dict[str, Any]] = {}
    log_refs: dict[str, str] = {}
    for index, selector in enumerate(dict.fromkeys(row["verification_selector"] for row in selected), start=1):
        outcome = _execute_selector_in_run(selector, mode, run_dir)
        log_ref = f"logs/selector-{index:03d}.log"
        (run_dir / log_ref).write_text(outcome.pop("output") + "\n", encoding="utf-8")
        outcomes[selector] = outcome
        log_refs[selector] = log_ref

    results: list[dict[str, Any]] = []
    for row in selected:
        selector = row["verification_selector"]
        outcome = outcomes[selector]
        result = {
            "schema_version": "contract-result/1",
            "run_id": run_id,
            "p0_contract_id": row["p0_contract_id"],
            "command": selector,
            "exit_code": outcome["exit_code"],
            "result_state": outcome["result_state"],
            "started_at": outcome["started_at"],
            "completed_at": outcome["completed_at"],
            "artifact_refs": [
                log_refs[selector],
                *outcome.get("artifact_refs", []),
            ],
        }
        receipt_module.validate_schema(result, "contract-result.schema.json", ROOT)
        results.append(result)

    _write_json(
        run_dir / "contract-results.json",
        {
            "schema_version": "contract-results/1",
            "run_id": run_id,
            "results": results,
        },
    )
    run["completed_at"] = _iso_now()
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)
    receipt = receipt_module.build_receipt(
        ROOT,
        run,
        results,
        mirror,
        bindings,
        policies,
    )
    _write_json(run_dir / "receipt.json", receipt)
    _seal_run(run_dir)
    return run_id, receipt["overall_verdict"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fixture", "failure", "live"))
    parser.add_argument("--scope", required=True, choices=("task", "full-p0"))
    parser.add_argument("--task", required=True)
    parser.add_argument("--current-four-run", metavar="RUN_ID")
    args = parser.parse_args(argv)
    try:
        artifacts = (
            _load_current_four_artifact(args.current_four_run)
            if args.current_four_run
            else None
        )
        run_id, verdict = run_task(
            args.mode,
            args.scope,
            args.task,
            input_artifacts=artifacts,
        )
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"run-p0: {exc}", file=sys.stderr)
        return 2
    print(f"run_id={run_id} scope={args.scope} task={args.task} overall_verdict={verdict}")
    return 0 if verdict == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
