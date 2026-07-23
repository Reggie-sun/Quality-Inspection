#!/usr/bin/env python3
"""Run the literal selectors for one P0 task and seal immutable evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
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
LIVE_EVIDENCE_ARTIFACT = "live-run-evidence.json"
HUMAN_VERDICT_ARTIFACT = "artifacts/human-verdict.json"
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
LIVE_PHASES = (
    "process",
    "candidates",
    "review",
    "balloons",
    "export",
    "consistency",
)
LIVE_CREDENTIAL_KEYS = (
    "QI_TENCENT_SECRET_ID",
    "QI_TENCENT_SECRET_KEY",
    "QI_QWEN_API_KEY",
    "QI_QWEN_WORKSPACE_ID",
)
LIVE_PROVIDER_MODE = "QI_PROVIDER_MODE"
LIVE_PROVIDER_NETWORK = "QI_PROVIDER_NETWORK_ENABLED"
SELECTOR_COMPOSE_DATABASE_URL = "postgresql+psycopg://qi:qi@postgres:5432/qi"
LIVE_PAUSE_BARRIER = "first-pdf-balloons"
LIVE_BROWSER = "chrome"
LIVE_VIEWPORT = {"width": 1565, "height": 796}
LIVE_OPERATOR_ENV = "QI_P0_OPERATOR_ID"
LIVE_API_BASE_ENV = "QI_P0_API_BASE"
LIVE_FRONTEND_BASE_ENV = "QI_P0_FRONTEND_BASE"
LIVE_SOURCE_ROOT_ENV = "QI_CURRENT_FOUR_SOURCE_ROOT"
_ACTIVE_RUN_DIR: Path | None = None
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SAFE_BROWSER_ENV_KEYS = {
    "ALL_PROXY",
    "CI",
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NODE_OPTIONS",
    "NO_PROXY",
    "NPM_CONFIG_CACHE",
    "PATH",
    "PLAYWRIGHT_BROWSERS_PATH",
    "SHELL",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "WAYLAND_DISPLAY",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_RUNTIME_DIR",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "npm_config_cache",
}


class LivePreflight(NamedTuple):
    source_root: Path
    source_paths: tuple[Path, ...]
    manifest_bytes: bytes
    mirror: dict[str, Any]
    bindings: dict[str, Any]
    policies: dict[str, dict[str, Any]]
    code_identity: dict[str, Any]
    config_identity: dict[str, Any]
    input_identity: dict[str, Any]


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


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _verified_run_artifact(
    run_dir: Path,
    ref: Any,
    digest: Any,
    *,
    expect_json: bool = False,
    expect_png: bool = False,
) -> tuple[Path, Any]:
    if not isinstance(ref, str) or not ref:
        raise ValueError("evidence ref must be a non-empty relative path")
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != ref:
        raise ValueError(f"evidence ref escapes the run: {ref}")
    path = run_dir / relative
    current = run_dir
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"evidence ref uses a symlink: {ref}")
    if not path.is_file():
        raise ValueError(f"evidence ref is missing: {ref}")
    resolved_run = run_dir.resolve()
    resolved = path.resolve()
    if resolved_run not in resolved.parents:
        raise ValueError(f"evidence ref escapes the run: {ref}")
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if not isinstance(digest, str) or digest != actual:
        raise ValueError(f"evidence identity changed: {ref}")
    if expect_png and not content.startswith(PNG_SIGNATURE):
        raise ValueError(f"evidence is not a PNG: {ref}")
    if not expect_json:
        return path, content
    try:
        document = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"evidence is not valid JSON: {ref}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"evidence JSON must be an object: {ref}")
    return path, document


def _receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location("qi_generate_receipt", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate-receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_module(name: str, filename: str) -> ModuleType:
    path = HARNESS / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
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
            env=_selector_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError, RuntimeError) as exc:
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
    # P0-ACC-007 remains a failure-mode proof, but a full live gate must reuse
    # it inside the already-open run instead of spawning a nested task run.
    if selector == NO_SILENT_SUCCESS_SELECTOR and mode == "live":
        return _failure_phase_outcome(selector, run_dir)
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
    if requested_mode == "live":
        return _live_phase_outcome(selector, run_dir)
    return (
        None,
        "blocked",
        f"phase://{requested_mode}/{phase} has no D1-T1 handler; no child run was created",
        [],
    )


def _compose_service_ip(service: str) -> str:
    container = subprocess.run(
        ["docker", "compose", "ps", "-q", service],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    container_ids = container.stdout.split()
    if container.returncode != 0 or len(container_ids) != 1:
        raise RuntimeError(f"Compose {service} container is unavailable")
    inspection = subprocess.run(
        ["docker", "inspect", container_ids[0]],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        documents = json.loads(inspection.stdout)
        networks = documents[0]["NetworkSettings"]["Networks"]
        addresses = sorted(
            network["IPAddress"]
            for network in networks.values()
            if network.get("IPAddress")
        )
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Compose {service} network is invalid") from exc
    if inspection.returncode != 0 or len(addresses) != 1:
        raise RuntimeError(f"Compose {service} network is unavailable")
    return addresses[0]


def _selector_environment(
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if base_environment is None else base_environment)
    backend_root = str(ROOT / "backend")
    python_paths = [
        path
        for path in environment.get("PYTHONPATH", "").split(os.pathsep)
        if path and path != backend_root
    ]
    environment["PYTHONPATH"] = os.pathsep.join([backend_root, *python_paths])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in (*LIVE_CREDENTIAL_KEYS, LIVE_PROVIDER_MODE, LIVE_PROVIDER_NETWORK):
        environment.pop(key, None)

    database_url = environment.get(
        "QI_DATABASE_URL",
        SELECTOR_COMPOSE_DATABASE_URL,
    )
    if urlsplit(database_url).hostname == "postgres":
        parsed = urlsplit(database_url)
        userinfo = parsed.netloc.rsplit("@", 1)[0] + "@"
        port = f":{parsed.port}" if parsed.port is not None else ""
        environment["QI_DATABASE_URL"] = urlunsplit(
            parsed._replace(
                netloc=f"{userinfo}{_compose_service_ip('postgres')}{port}"
            )
        )
    return environment


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
            env=_selector_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError, RuntimeError) as exc:
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
            path.chmod(
                stat.S_IRUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH
            )
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


def can_resume_live_run(run_dir: Path) -> bool:
    try:
        run = _load_json(run_dir / "run.json")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return bool(
        run.get("mode") == "live"
        and run.get("scope") == "full-p0"
        and run.get("task_id") is None
        and run.get("execution_state") == "visual_qa_pending"
        and run.get("pause_identity")
        and run.get("completed_at") is None
        and not _is_sealed(run_dir / "run.json")
    )


def abort_live_run(
    run_dir: Path,
    *,
    reason: str,
    seal: bool = True,
) -> dict[str, Any]:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("live abort reason must be non-empty")
    run_path = run_dir / "run.json"
    if run_dir.is_symlink() or run_path.is_symlink() or not run_path.is_file():
        raise ValueError("live run identity is unavailable")
    run = _load_json(run_path)
    if (
        run.get("run_id") != run_dir.name
        or run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("execution_state") not in {"running", "visual_qa_pending"}
        or run.get("completed_at") is not None
    ):
        raise ValueError("only one open full-p0 live run can be aborted")
    run["execution_state"] = "failed"
    run["failure_reason"] = clean_reason
    run["completed_at"] = _iso_now()
    receipt_module = _receipt_module()
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_path, run)
    if seal:
        _seal_run(run_dir)
    return run


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


def _require_live_environment(environment: Mapping[str, str]) -> None:
    missing = [
        key
        for key in LIVE_CREDENTIAL_KEYS
        if not environment.get(key, "").strip()
    ]
    if missing:
        raise ValueError(
            "server-only Provider configuration is incomplete: "
            + ", ".join(missing)
        )
    if environment.get(LIVE_PROVIDER_MODE, "").strip().lower() != "live":
        raise ValueError(f"{LIVE_PROVIDER_MODE}=live is required")
    if environment.get(LIVE_PROVIDER_NETWORK, "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
        "live",
    }:
        raise ValueError(f"{LIVE_PROVIDER_NETWORK}=enabled is required")


def _current_live_identity(
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = os.environ if environment is None else environment
    operator_id = current.get(LIVE_OPERATOR_ENV, "").strip()
    if not operator_id:
        raise ValueError(f"{LIVE_OPERATOR_ENV} is required")
    api_base = current.get(LIVE_API_BASE_ENV, "http://localhost:8000").rstrip("/")
    frontend_base = current.get(
        LIVE_FRONTEND_BASE_ENV,
        "http://localhost:3000",
    ).rstrip("/")
    if api_base != "http://localhost:8000":
        raise ValueError(
            f"{LIVE_API_BASE_ENV} must target the verified Compose API topology"
        )
    if frontend_base != "http://localhost:3000":
        raise ValueError(
            f"{LIVE_FRONTEND_BASE_ENV} must target the verified Compose frontend"
        )
    return {
        "operator_id": operator_id,
        "api_base": api_base,
        "frontend_base": frontend_base,
        "browser": _chrome_identity(current),
        "viewport": dict(LIVE_VIEWPORT),
    }


def _validate_live_policy(policies: Mapping[str, Mapping[str, Any]]) -> None:
    live = policies.get("provider_call_policy", {}).get("live")
    if not isinstance(live, Mapping):
        raise ValueError("live Provider call policy is unavailable")
    exact_limits = {
        "explicit_flag_required": True,
        "max_retries_per_call": 2,
        "max_crop_expansions": 1,
        "max_ocr_calls_per_page": 16,
        "max_vision_calls_per_candidate": 2,
        "max_total_estimated_cost_cny": 50,
        "budget_exceeded_result": "blocked",
    }
    if any(live.get(key) != value for key, value in exact_limits.items()):
        raise ValueError("live Provider budget/retry policy changed")


def _validate_export_assets() -> None:
    backend_root = ROOT / "backend"
    backend_text = str(backend_root)
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    from app.capabilities.service import ExportPreflight

    ExportPreflight(
        template_path=backend_root / "assets/templates/sip-v1.xlsx",
        mapping_path=backend_root / "assets/templates/sip-v1.mapping.json",
        font_path=backend_root / "assets/fonts/DejaVuSans.ttf",
        font_license_path=backend_root / "assets/fonts/LICENSE-DejaVu.txt",
    ).check()


def _chrome_identity(environment: Mapping[str, str]) -> dict[str, str]:
    search_path = environment.get("PATH", os.defpath)
    selected = next(
        (
            (name, resolved)
            for name in ("google-chrome", "google-chrome-stable")
            if (resolved := shutil.which(name, path=search_path)) is not None
        ),
        None,
    )
    if selected is None:
        raise ValueError("the user-selected Chrome browser is unavailable")
    name, executable = selected
    resolved = Path(executable).resolve()
    if not resolved.is_file():
        raise ValueError("the user-selected Chrome executable is invalid")
    result = subprocess.run(
        [executable, "--version"],
        env={
            key: environment[key]
            for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE")
            if key in environment
        },
        check=False,
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(
        r"Google Chrome [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+",
        version,
    ):
        raise ValueError("the user-selected Chrome version is unavailable")
    return {
        "name": LIVE_BROWSER,
        "executable": name,
        "version": version,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def preflight_full_p0_live(
    *,
    input_set: str,
    source_root: str | None,
    environment: Mapping[str, str] | None = None,
) -> LivePreflight:
    if input_set != "current-four":
        raise ValueError("full-p0 live requires --input-set current-four")
    current_environment = os.environ if environment is None else environment
    # Credential/control checks intentionally precede source reads, identity
    # hashing, run creation, uploads, and every potentially paid operation.
    _require_live_environment(current_environment)
    _current_live_identity(current_environment)
    if source_root is None or not source_root.strip():
        raise ValueError(f"{LIVE_SOURCE_ROOT_ENV} is required")

    receipt_module = _receipt_module()
    receipt_module.check_contract_authority(ROOT)
    policies = receipt_module.load_policies(ROOT)
    _validate_live_policy(policies)
    if not receipt_module.provider_network_enabled(current_environment):
        raise ValueError("live Provider network control is not enabled")

    mirror = _load_json(MIRROR_PATH)
    bindings = _load_json(BINDINGS_PATH)
    receipt_module.validate_schema(mirror, "p0-contracts.schema.json", ROOT)
    receipt_module.validate_schema(
        bindings,
        "global-contract-bindings.schema.json",
        ROOT,
    )
    selected_ids = sorted(row["p0_contract_id"] for row in mirror["contracts"])
    required_count = int(
        policies["p0_acceptance_policy"]["required_contract_count"]
    )
    if len(selected_ids) != required_count or len(set(selected_ids)) != required_count:
        raise ValueError("full-p0 contract selection is not exactly 111 unique IDs")

    stage_module = _script_module(
        "qi_stage_current_four_for_live_preflight",
        "stage-current-four.py",
    )
    sources = stage_module._resolve_sources(None, source_root)
    stage_module._verify_sources(sources)
    manifest_bytes = stage_module._manifest_bytes(stage_module.FROZEN_DOCUMENTS)
    artifacts = {CURRENT_FOUR_ARTIFACT: manifest_bytes}

    _validate_export_assets()
    return LivePreflight(
        source_root=Path(source_root),
        source_paths=tuple(
            sources[document.basename]
            for document in stage_module.FROZEN_DOCUMENTS
        ),
        manifest_bytes=manifest_bytes,
        mirror=mirror,
        bindings=bindings,
        policies=policies,
        code_identity=receipt_module.code_identity(ROOT),
        config_identity=receipt_module.config_identity(
            "live",
            "full-p0",
            None,
            ROOT,
        ),
        input_identity=receipt_module.input_identity(
            "live",
            "full-p0",
            None,
            artifacts,
            root=ROOT,
        ),
    )


def _atomic_write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _open_live_run(preflight: LivePreflight) -> Path:
    receipt_module = _receipt_module()
    run_id = _new_run_id()
    run_dir = RUNS / run_id
    selected_ids = sorted(
        row["p0_contract_id"] for row in preflight.mirror["contracts"]
    )
    run = {
        "schema_version": "run/1",
        "run_id": run_id,
        "mode": "live",
        "scope": "full-p0",
        "task_id": None,
        "code_identity": preflight.code_identity,
        "git_revision_at_start": _git_revision(),
        "config_identity": preflight.config_identity,
        "input_identity": preflight.input_identity,
        "contract_definition_hash": preflight.mirror["contract_definition_hash"],
        "status_projection_hash_at_start": preflight.mirror[
            "status_projection_hash"
        ],
        "policy_versions": receipt_module.policy_versions(preflight.policies),
        "selected_contract_ids": selected_ids,
        "live_identity": _current_live_identity(),
        "execution_state": "running",
        "pause_identity": None,
        "failure_reason": None,
        "started_at": _iso_now(),
        "completed_at": None,
    }
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    run_dir.mkdir(parents=True, exist_ok=False)
    for name in ("logs", "reports", "artifacts"):
        (run_dir / name).mkdir()
    _write_json(run_dir / "run.json", run)
    stage_module = _script_module(
        "qi_stage_current_four_for_open_live_run",
        "stage-current-four.py",
    )
    stage_module.attach_manifest(run_dir, preflight.manifest_bytes)
    live = {
        "schema_version": "live-run-evidence/1",
        "run_id": run_id,
        "input_set": "current-four",
        "phases": list(LIVE_PHASES),
        "child_run_ids": [],
        "design_qa": None,
        "samples": [],
    }
    receipt_module.validate_schema(
        live,
        "live-run-evidence.schema.json",
        ROOT,
    )
    _write_json(run_dir / LIVE_EVIDENCE_ARTIFACT, live)
    return run_dir


def _http_json(
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    operator_id: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    base = os.environ.get(LIVE_API_BASE_ENV, "http://localhost:8000").rstrip("/")
    payload = None
    headers = {"Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if operator_id is not None:
        headers["X-QI-Operator"] = operator_id
    request = Request(base + path, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"API {method} {path} returned {exc.code}: {detail}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"API {method} {path} is unavailable: {exc}") from exc
    try:
        document = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"API {method} {path} returned non-JSON evidence") from exc
    if not isinstance(document, dict):
        raise RuntimeError(f"API {method} {path} returned a non-object")
    return document


_PREPARE_PROJECT_PROGRAM = r"""
import hashlib
import json
import os
import sys
import uuid

from redis import Redis
from sqlalchemy import select

from app.capabilities.service import ProcessingPreflight
from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.candidates.models import AutomaticResult
from app.processing.pipeline import InventoryPipeline
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile

payload = sys.stdin.buffer.read()
expected = os.environ["QI_P0_SOURCE_SHA256"]
if hashlib.sha256(payload).hexdigest() != expected:
    raise RuntimeError("source identity changed before application upload")
settings = get_settings()
storage = LocalFileStorage(settings.storage_root)
preflight = ProcessingPreflight(
    storage,
    Redis.from_url(settings.redis_url),
    celery_app,
    ocr_configured=all(
        isinstance(value, str) and bool(value.strip())
        for value in (
            settings.tencent_secret_id,
            settings.tencent_secret_key,
            settings.tencent_region,
        )
    ),
    vision_configured=all(
        isinstance(value, str) and bool(value.strip())
        for value in (
            settings.qwen_api_key,
            settings.qwen_workspace_id,
            settings.qwen_model,
        )
    ),
)
preflight.check()
session = SessionLocal()
try:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    stored = storage.write_verified(
        f"projects/{project.id}/source.pdf",
        payload,
        expected,
    )
    source = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    session.add_all([project, source])
    session.commit()
    InventoryPipeline(session, storage, preflight).run(
        str(project.id),
        source.resource_ref,
        "p0-live:" + os.environ["QI_P0_RUN_ID"] + ":" + os.environ["QI_P0_ORDER"],
    )
    raw = session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    if raw is None:
        raise RuntimeError("automatic result was not created")
    working = ReviewService(session, storage=storage).create_from_raw(raw.id)
    inventory = json.loads(storage.read_bytes(raw.inventory_ref))
    pages = inventory.get("pages")
    if not isinstance(pages, list) or not pages:
        raise RuntimeError("stored page inventory is unavailable")

    def physical_page(page):
        width = float(page["width"])
        height = float(page["height"])
        standards = {
            "A3 landscape": (1190.55, 841.89),
            "A4 portrait": (595.28, 841.89),
        }
        matches = [
            name
            for name, (expected_width, expected_height) in standards.items()
            if abs(width - expected_width) <= 18
            and abs(height - expected_height) <= 18
        ]
        if len(matches) != 1:
            raise RuntimeError(f"unsupported live page size: {width}x{height}")
        return matches[0]

    candidate_ids = []
    source_location_ids = set()
    for candidate in raw.candidates:
        candidate_id = candidate.get("candidate_id")
        sources = candidate.get("source_location_ids")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise RuntimeError("automatic candidate identity is incomplete")
        if not isinstance(sources, list) or not sources:
            raise RuntimeError("automatic candidate source relation is incomplete")
        candidate_ids.append(candidate_id)
        source_location_ids.update(str(value) for value in sources)
    coverage_entries = raw.coverage.get("entries")
    if not isinstance(coverage_entries, list):
        raise RuntimeError("coverage evidence is unavailable")
    coverage_by_candidate = {}
    for entry in coverage_entries:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id:
            coverage_by_candidate.setdefault(candidate_id, []).append(entry)
    candidate_records = []
    for candidate in raw.candidates:
        candidate_id = str(candidate["candidate_id"])
        payload = candidate.get("payload")
        coordinates = payload.get("coordinates") if isinstance(payload, dict) else None
        source_evidence = [
            {
                "source_location_id": str(entry["source_location_id"]),
                "coordinates": entry["coordinates"],
                "disposition": entry["disposition"],
            }
            for entry in coverage_by_candidate.get(candidate_id, [])
            if entry.get("disposition") == "candidate"
        ]
        candidate_records.append({
            "candidate_id": candidate_id,
            "coordinates": coordinates,
            "source_location_ids": sorted(
                str(value) for value in candidate.get("source_location_ids", [])
            ),
            "source_evidence": source_evidence,
        })
    print(json.dumps({
        "project_id": str(project.id),
        "working_copy_id": str(working.id),
        "working_version": working.version,
        "process": {
            "source_sha256": source.sha256,
            "actual_page_count": len(pages),
            "actual_physical_pages": sorted({physical_page(page) for page in pages}),
            "automatic_result_id": str(raw.id),
        },
        "candidates": {
            "candidate_count": len(raw.candidates),
            "candidate_ids": sorted(candidate_ids),
            "source_location_ids": sorted(source_location_ids),
            "coverage_checked": raw.coverage.get("coverage_checked") is True,
            "coverage_blocking_count": int(raw.coverage.get("blocking_count", -1)),
            "coverage_disposition_count": sum(
                isinstance(entry.get("disposition"), str)
                and bool(entry["disposition"].strip())
                for entry in coverage_entries
                if isinstance(entry, dict)
            ),
            "candidate_records": sorted(
                candidate_records,
                key=lambda entry: entry["candidate_id"],
            ),
        },
    }, sort_keys=True))
finally:
    session.close()
"""


_REVIEW_EVIDENCE_PROGRAM = r"""
import json
import os
import uuid

from sqlalchemy import select

from app.audit.operations import OperationRecord
from app.balloons.models import Balloon
from app.candidates.models import AutomaticResult
from app.db import SessionLocal
from app.review.models import ReviewWorkingCopy

project_id = uuid.UUID(os.environ["QI_P0_PROJECT_ID"])
require_frozen = os.environ.get("QI_P0_REQUIRE_FROZEN") == "1"
session = SessionLocal()
try:
    working = session.scalar(
        select(ReviewWorkingCopy).where(ReviewWorkingCopy.project_id == project_id)
    )
    if working is None or (require_frozen and working.items_frozen_at is None):
        raise RuntimeError("review working copy is not frozen")
    raw = session.get(AutomaticResult, working.raw_result_id)
    if raw is None:
        raise RuntimeError("automatic result is unavailable")
    operations = list(
        session.scalars(
            select(OperationRecord)
            .where(OperationRecord.project_id == project_id)
            .order_by(OperationRecord.created_at, OperationRecord.id)
        )
    )
    review_command_names = {
        "keep",
        "exclude",
        "edit",
        "add",
        "merge",
        "split",
        "resolve_confirmation",
        "set_balloon_required",
        "set_sip_detail_fields",
        "set_sip_metadata",
    }
    review_operations = [
        operation
        for operation in operations
        if operation.command in review_command_names
    ]
    balloons = list(
        session.scalars(
            select(Balloon)
            .where(Balloon.project_id == project_id, Balloon.status == "active")
            .order_by(Balloon.formal_number, Balloon.id)
        )
    )
    active_item_ids = sorted(
        str(item["item_id"])
        for item in working.items
        if item.get("active", True)
    )
    balloon_required_item_ids = sorted(
        str(item["item_id"])
        for item in working.items
        if item.get("active", True) and item.get("balloon_required") is True
    )
    excluded_item_ids = sorted(
        str(item["item_id"])
        for item in working.items
        if not item.get("active", True)
    )
    formal_numbers = [
        int(balloon.formal_number)
        for balloon in balloons
        if balloon.formal_number is not None
    ]
    item_by_id = {str(item["item_id"]): item for item in working.items}
    candidate_decisions = []
    decision_commands = {
        "keep",
        "exclude",
        "edit",
        "merge",
        "split",
        "resolve_confirmation",
        "set_balloon_required",
        "set_sip_detail_fields",
    }
    for candidate in raw.candidates:
        candidate_id = str(candidate["candidate_id"])
        item = item_by_id.get(candidate_id)
        if item is None:
            raise RuntimeError("automatic candidate disappeared from working copy")
        status = str(item.get("status", ""))
        final_state = (
            "active"
            if item.get("active", True)
            else "superseded"
            if status == "superseded"
            else "excluded"
        )
        commands = sorted({
            operation.command
            for operation in review_operations
            if candidate_id in operation.target_ids
            and operation.command in decision_commands
        })
        candidate_decisions.append({
            "candidate_id": candidate_id,
            "final_state": final_state,
            "commands": commands,
        })
    print(json.dumps({
        "run_id": os.environ["QI_P0_RUN_ID"],
        "order": int(os.environ["QI_P0_ORDER"]),
        "project_id": str(project_id),
        "review": {
            "working_copy_id": str(working.id),
            "frozen_version": (
                int(working.items_frozen_version)
                if working.items_frozen_version is not None
                else None
            ),
            "frozen_by": (
                str(working.items_frozen_by)
                if working.items_frozen_by is not None
                else None
            ),
            "items_frozen_at": (
                working.items_frozen_at.isoformat()
                if working.items_frozen_at is not None
                else None
            ),
            "active_item_ids": active_item_ids,
            "balloon_required_item_ids": balloon_required_item_ids,
            "excluded_item_ids": excluded_item_ids,
            "operation_commands": sorted({
                operation.command for operation in review_operations
            }),
            "operation_operator_ids": sorted({
                operation.operator_id for operation in review_operations
            }),
            "operation_target_ids": sorted({
                target_id
                for operation in review_operations
                for target_id in operation.target_ids
            }),
            "candidate_decisions": sorted(
                candidate_decisions,
                key=lambda entry: entry["candidate_id"],
            ),
        },
        "balloons": {
            "hard_collision_count": sum(len(balloon.collision_flags) for balloon in balloons),
            "unresolved_manual_required_count": sum(
                balloon.placement_status == "manual_required" for balloon in balloons
            ),
            "active_item_ids": sorted(balloon.inspection_item_id for balloon in balloons),
            "formal_numbers": formal_numbers,
        },
    }, sort_keys=True))
finally:
    session.close()
"""


_POST_EXPORT_EVIDENCE_PROGRAM = r"""
import hashlib
import json
import os
import re
import uuid
from io import BytesIO

import fitz
from openpyxl import load_workbook
from sqlalchemy import select

from app.balloons.renderer import BALLOON_RADIUS_PDF
from app.config import get_settings
from app.db import SessionLocal
from app.exports.models import ExportArtifact, ExportJob
from app.exports.service import ExportService, assert_artifact_identity
from app.review.models import ReviewedResult
from app.storage.local import LocalFileStorage

project_id = uuid.UUID(os.environ["QI_P0_PROJECT_ID"])
reviewed_id = uuid.UUID(os.environ["QI_P0_REVIEWED_RESULT_ID"])
export_id = uuid.UUID(os.environ["QI_P0_EXPORT_ID"])
session = SessionLocal()
storage = LocalFileStorage(get_settings().storage_root)
try:
    reviewed = session.get(ReviewedResult, reviewed_id)
    export = session.get(ExportJob, export_id)
    if (
        reviewed is None
        or reviewed.project_id != project_id
        or export is None
        or export.project_id != project_id
        or export.reviewed_result_id != reviewed_id
        or export.status != "success"
    ):
        raise RuntimeError("formal export identity is unavailable")
    service = ExportService(session, storage=storage)
    artifacts = list(
        session.scalars(
            select(ExportArtifact).where(ExportArtifact.export_id == export_id)
        )
    )
    by_kind = {artifact.kind: artifact for artifact in artifacts}
    kinds = ["ballooned_pdf", "sip_excel", "manifest"]
    if set(by_kind) != set(kinds):
        raise RuntimeError("formal export does not contain exactly three artifacts")
    contents = {}
    for kind in kinds:
        artifact = by_kind[kind]
        if artifact.published_ref is None:
            raise RuntimeError("formal artifact is not published")
        content = storage.read_bytes(artifact.published_ref)
        if (
            hashlib.sha256(content).hexdigest() != artifact.sha256
            or len(content) != artifact.size_bytes
            or artifact.reviewed_result_id != reviewed_id
        ):
            raise RuntimeError("formal artifact identity changed after publish")
        contents[kind] = content

    source = service._source_pdf(reviewed)
    registration = service.preflight.check()
    active_balloons = service._active_balloon_snapshots(reviewed.balloons)
    frozen_balloons = service._frozen_balloons(reviewed.balloons)
    excel_rows = service._excel_rows(reviewed.items, active_balloons)
    sip_metadata = service._sip_metadata(reviewed.sip_metadata)
    source_page_count = service._validate_pdf(
        source.content,
        contents["ballooned_pdf"],
        frozen_balloons,
    )
    service._validate_excel(
        contents["sip_excel"],
        registration,
        sip_metadata,
        excel_rows,
    )
    expected_manifest = service._manifest(
        export,
        reviewed,
        source,
        registration,
        source_page_count,
        service._filenames(source.filename),
        by_kind["ballooned_pdf"],
        by_kind["sip_excel"],
        active_balloons,
    )
    service._validate_manifest(contents["manifest"], expected_manifest)
    assert_artifact_identity(reviewed_id, artifacts, contents["manifest"])
    manifest = json.loads(contents["manifest"])

    pdf_numbers = []
    with fitz.open(stream=contents["ballooned_pdf"], filetype="pdf") as document:
        for balloon in frozen_balloons:
            center_x, center_y = balloon.center_pdf
            clip = fitz.Rect(
                center_x - BALLOON_RADIUS_PDF,
                center_y - BALLOON_RADIUS_PDF,
                center_x + BALLOON_RADIUS_PDF,
                center_y + BALLOON_RADIUS_PDF,
            )
            text = document[balloon.page_index].get_text("text", clip=clip)
            if re.search(
                rf"(?<!\d){int(balloon.formal_number)}(?!\d)",
                text,
            ) is None:
                raise RuntimeError("targeted PDF balloon number is unreadable")
            pdf_numbers.append(balloon.formal_number)

    workbook = load_workbook(BytesIO(contents["sip_excel"]), data_only=False)
    try:
        sheet = workbook[registration.sheet]
        number_column = registration.detail_columns["balloon_number"]
        excel_numbers = []
        for offset in range(len(excel_rows)):
            value = sheet[f"{number_column}{registration.first_row + offset}"].value
            if value not in (None, ""):
                excel_numbers.append(int(value))
    finally:
        workbook.close()

    active_items = [item for item in reviewed.items if item.get("active", True)]
    required_items = [
        item for item in active_items if item.get("balloon_required") is True
    ]
    reviewed_active_item_ids = sorted(
        str(item["item_id"]) for item in active_items
    )
    reviewed_item_numbers = sorted(
        [
            {
                "item_id": str(balloon["inspection_item_id"]),
                "formal_number": int(balloon["formal_number"]),
            }
            for balloon in active_balloons
        ],
        key=lambda entry: entry["item_id"],
    )
    reviewed_item_ids = [entry["item_id"] for entry in reviewed_item_numbers]
    balloon_item_ids = list(reviewed_item_ids)
    reviewed_numbers = sorted(
        entry["formal_number"] for entry in reviewed_item_numbers
    )
    print(json.dumps({
        "export": {
            "reviewed_result_id": str(reviewed_id),
            "export_id": str(export_id),
            "status": export.status,
            "artifact_kinds": kinds,
            "artifact_sha256": [by_kind[kind].sha256 for kind in kinds],
            "artifact_reviewed_result_ids": [
                str(by_kind[kind].reviewed_result_id) for kind in kinds
            ],
            "download_kinds": kinds,
        },
        "consistency": {
            "verified": True,
            "reviewed_result_id": str(reviewed_id),
            "reviewed_active_item_ids": reviewed_active_item_ids,
            "reviewed_item_ids": reviewed_item_ids,
            "balloon_item_ids": balloon_item_ids,
            "reviewed_item_numbers": reviewed_item_numbers,
            "reviewed_numbers": reviewed_numbers,
            "pdf_numbers": pdf_numbers,
            "excel_numbers": excel_numbers,
            "reviewed_item_count": len(active_items),
            "balloon_required_count": len(required_items),
            "balloon_count": len(active_balloons),
            "source_page_count": source_page_count,
            "manifest_reviewed_item_count": manifest["reviewed_item_count"],
            "manifest_balloon_required_count": manifest["balloon_required_count"],
            "manifest_balloon_count": manifest["balloon_count"],
            "manifest_source_page_count": manifest["source_page_count"],
        },
    }, sort_keys=True))
finally:
    session.close()
"""


def _prepare_live_project(
    run_dir: Path,
    *,
    source_path: Path,
    order: int,
    expected_sha256: str,
) -> dict[str, Any]:
    content = source_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RuntimeError("current-four source changed after live preflight")
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "-e",
        f"QI_P0_RUN_ID={run_dir.name}",
        "-e",
        f"QI_P0_ORDER={order}",
        "-e",
        f"QI_P0_SOURCE_SHA256={expected_sha256}",
        "api",
        "python",
        "-c",
        _PREPARE_PROJECT_PROGRAM,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        input=content,
        check=False,
        capture_output=True,
    )
    log_ref = f"logs/sample-{order}-prepare.log"
    output = b"\n".join(
        (
            f"exit_code={result.returncode}".encode(),
            b"stdout:",
            result.stdout,
            b"stderr:",
            result.stderr,
        )
    )
    (run_dir / log_ref).write_bytes(output)
    if result.returncode != 0:
        raise RuntimeError(
            f"sample {order} application upload/process failed; see {log_ref}"
        )
    try:
        document = json.loads(result.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"sample {order} project identity is invalid") from exc
    required = {
        "project_id",
        "working_copy_id",
        "working_version",
        "process",
        "candidates",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise RuntimeError(f"sample {order} project identity is incomplete")
    process = document.get("process")
    if not isinstance(process, dict):
        raise RuntimeError(f"sample {order} process evidence is incomplete")
    process["prepare_log_sha256"] = hashlib.sha256(output).hexdigest()
    return document


def _review_item_set_ready(
    review: Mapping[str, Any],
    candidates: Mapping[str, Any],
    item_write: Mapping[str, Any],
    *,
    operator_id: str,
) -> bool:
    commands = set(review.get("operation_commands", []))
    candidate_ids = set(candidates.get("candidate_ids", []))
    operation_targets = set(review.get("operation_target_ids", []))
    decisions = review.get("candidate_decisions")
    if not isinstance(decisions, list):
        return False
    decision_ids: list[str] = []
    decisions_ok = True
    for decision in decisions:
        if not isinstance(decision, Mapping):
            return False
        candidate_id = decision.get("candidate_id")
        final_state = decision.get("final_state")
        decision_commands = set(decision.get("commands", []))
        if not isinstance(candidate_id, str):
            return False
        decision_ids.append(candidate_id)
        decisions_ok = decisions_ok and bool(
            (final_state == "active" and "keep" in decision_commands)
            or (final_state == "excluded" and "exclude" in decision_commands)
            or (
                final_state == "superseded"
                and bool({"merge", "split"} & decision_commands)
            )
        )
    disposition = item_write.get("merge_split_disposition")
    merge_split_ok = bool(
        (
            disposition == "not_applicable"
            and not ({"merge", "split"} & commands)
        )
        or (disposition == "merge" and "merge" in commands)
        or (disposition == "split" and "split" in commands)
    )
    required_commands = {
        "keep",
        "exclude",
        "edit",
        "add",
        "resolve_confirmation",
    }
    return bool(
        required_commands.issubset(commands)
        and candidate_ids
        and candidate_ids.issubset(operation_targets)
        and len(decision_ids) == len(set(decision_ids))
        and set(decision_ids) == candidate_ids
        and decisions_ok
        and review.get("operation_operator_ids") == [operator_id]
        and review.get("active_item_ids")
        and review.get("excluded_item_ids")
        and merge_split_ok
        and review.get("merge_split_disposition", disposition) == disposition
        and review.get("merge_split_note", item_write.get("merge_split_note"))
        == item_write.get("merge_split_note")
        and bool(item_write.get("merge_split_note"))
    )


def _collect_item_set_readiness(
    run_dir: Path,
    *,
    order: int,
    project_id: str,
) -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "-e",
        f"QI_P0_PROJECT_ID={project_id}",
        "-e",
        f"QI_P0_RUN_ID={run_dir.name}",
        "-e",
        f"QI_P0_ORDER={order}",
        "-e",
        "QI_P0_REQUIRE_FROZEN=0",
        "api",
        "python",
        "-c",
        _REVIEW_EVIDENCE_PROGRAM,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sample {order} item-set readiness failed: {result.stderr[:1000]}"
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"sample {order} item-set readiness is invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"run_id", "order", "project_id", "review", "balloons"}
        or document.get("run_id") != run_dir.name
        or document.get("order") != order
        or document.get("project_id") != project_id
        or not isinstance(document.get("review"), dict)
    ):
        raise RuntimeError(f"sample {order} item-set readiness is incomplete")
    return document["review"]


def _collect_review_balloon_evidence(
    run_dir: Path,
    *,
    order: int,
    project_id: str,
) -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "-e",
        f"QI_P0_PROJECT_ID={project_id}",
        "-e",
        f"QI_P0_RUN_ID={run_dir.name}",
        "-e",
        f"QI_P0_ORDER={order}",
        "-e",
        "QI_P0_REQUIRE_FROZEN=1",
        "api",
        "python",
        "-c",
        _REVIEW_EVIDENCE_PROGRAM,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sample {order} review evidence failed: {result.stderr[:1000]}"
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"sample {order} review evidence is invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"run_id", "order", "project_id", "review", "balloons"}
        or document.get("run_id") != run_dir.name
        or document.get("order") != order
        or document.get("project_id") != project_id
    ):
        raise RuntimeError(f"sample {order} review evidence is incomplete")
    ref = f"reports/review-{order}.json"
    _write_json(run_dir / ref, document)
    review = dict(document["review"])
    review["evidence_ref"] = ref
    review["evidence_sha256"] = hashlib.sha256(
        (run_dir / ref).read_bytes()
    ).hexdigest()
    return {"review": review, "balloons": document["balloons"]}


def _collect_post_export_evidence(
    run_dir: Path,
    sample: Mapping[str, Any],
    browser_result: Mapping[str, Any],
) -> dict[str, Any]:
    order = int(sample["order"])
    project_id = str(sample["project_id"])
    reviewed_result_id = str(browser_result.get("reviewed_result_id", ""))
    export_id = str(browser_result.get("export_id", ""))
    if not reviewed_result_id or not export_id:
        raise RuntimeError(f"sample {order} browser export identity is incomplete")
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "-e",
        f"QI_P0_PROJECT_ID={project_id}",
        "-e",
        f"QI_P0_REVIEWED_RESULT_ID={reviewed_result_id}",
        "-e",
        f"QI_P0_EXPORT_ID={export_id}",
        "api",
        "python",
        "-c",
        _POST_EXPORT_EVIDENCE_PROGRAM,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sample {order} post-export consistency failed: {result.stderr[:1000]}"
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"sample {order} post-export evidence is invalid") from exc
    if not isinstance(document, dict) or set(document) != {"export", "consistency"}:
        raise RuntimeError(f"sample {order} post-export evidence is incomplete")

    export = document["export"]
    artifacts = browser_result.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise RuntimeError(f"sample {order} browser artifact evidence is incomplete")
    browser_by_kind = {
        artifact.get("kind"): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    }
    for index, kind in enumerate(export["artifact_kinds"]):
        artifact = browser_by_kind.get(kind)
        if (
            not isinstance(artifact, Mapping)
            or artifact.get("sha256") != export["artifact_sha256"][index]
            or artifact.get("reviewed_result_id")
            != export["artifact_reviewed_result_ids"][index]
            or artifact.get("download_sha256") != artifact.get("sha256")
            or artifact.get("download_size_bytes") != artifact.get("size_bytes")
        ):
            raise RuntimeError(
                f"sample {order} downloaded {kind} differs from formal artifact identity"
            )
    consistency = document["consistency"]
    workbench_item_numbers = _browser_item_numbers(
        browser_result.get("table_item_numbers")
    )
    workbench_overlay_item_numbers = _browser_item_numbers(
        browser_result.get("overlay_item_numbers")
    )
    workbench_backend_item_numbers = _browser_item_numbers(
        browser_result.get("backend_item_numbers")
    )
    reviewed_item_numbers = _browser_item_numbers(
        consistency.get("reviewed_item_numbers")
    )
    workbench_active_item_ids = _browser_item_ids(
        browser_result.get("table_active_item_ids")
    )
    reviewed_active_item_ids = _browser_item_ids(
        consistency.get("reviewed_active_item_ids")
    )
    if (
        workbench_item_numbers is None
        or workbench_overlay_item_numbers is None
        or workbench_backend_item_numbers is None
        or reviewed_item_numbers is None
        or workbench_item_numbers != reviewed_item_numbers
        or workbench_overlay_item_numbers != reviewed_item_numbers
        or workbench_backend_item_numbers != reviewed_item_numbers
        or workbench_active_item_ids is None
        or reviewed_active_item_ids is None
        or workbench_active_item_ids != reviewed_active_item_ids
    ):
        raise RuntimeError(
            f"sample {order} workbench items/numbers differ from reviewed result"
        )
    consistency["workbench_item_numbers"] = workbench_item_numbers
    consistency["workbench_overlay_item_numbers"] = (
        workbench_overlay_item_numbers
    )
    consistency["workbench_active_item_ids"] = workbench_active_item_ids
    consistency["workbench_numbers"] = sorted(
        entry["formal_number"] for entry in workbench_item_numbers
    )
    ref = f"reports/consistency-{order}.json"
    report = {
        "run_id": run_dir.name,
        "order": order,
        "project_id": project_id,
        "export": export,
        "consistency": consistency,
    }
    _write_json(run_dir / ref, report)
    consistency["evidence_ref"] = ref
    consistency["evidence_sha256"] = hashlib.sha256(
        (run_dir / ref).read_bytes()
    ).hexdigest()
    completed = dict(sample)
    completed["export"] = export
    completed["consistency"] = consistency
    return completed


def _wait_seconds() -> int:
    raw = os.environ.get("QI_P0_HUMAN_WAIT_SECONDS", "3600")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("QI_P0_HUMAN_WAIT_SECONDS must be one integer") from exc
    if value < 1 or value > 86_400:
        raise ValueError("QI_P0_HUMAN_WAIT_SECONDS must be between 1 and 86400")
    return value


def _load_human_verdict(run_dir: Path) -> dict[str, Any]:
    artifact = run_dir / HUMAN_VERDICT_ARTIFACT
    document = _load_json(artifact)
    verdict_module = _script_module(
        "qi_record_human_verdict_for_live_run",
        "record-human-verdict.py",
    )
    verdict_module._validate(document)
    if document.get("run_id") != run_dir.name:
        raise RuntimeError("human verdict run identity mismatch")
    return document


def _verdict_sample(
    document: Mapping[str, Any],
    *,
    order: int,
    project_id: str,
) -> Mapping[str, Any] | None:
    samples = document.get("samples")
    if not isinstance(samples, list):
        return None
    return next(
        (
            sample
            for sample in samples
            if isinstance(sample, Mapping)
            and sample.get("order") == order
            and sample.get("project_id") == project_id
        ),
        None,
    )


def _wait_for_sample_verdict(
    run_dir: Path,
    *,
    order: int,
    project_id: str,
    stage: str,
    timeout: int,
) -> dict[str, bool]:
    if stage not in {"item-set", "balloons"}:
        raise ValueError("live verdict stage is invalid")
    deadline = time.monotonic() + timeout
    artifact = run_dir / HUMAN_VERDICT_ARTIFACT
    while time.monotonic() < deadline:
        if artifact.is_file():
            document = _load_human_verdict(run_dir)
            sample = _verdict_sample(
                document,
                order=order,
                project_id=project_id,
            )
            if isinstance(sample, Mapping):
                field = "item_set" if stage == "item-set" else "balloons"
                write = sample.get(field)
                if not isinstance(write, Mapping):
                    time.sleep(1)
                    continue
                answers = write.get("answers")
                if not isinstance(answers, Mapping) or not answers:
                    raise RuntimeError(f"sample {order} {stage} verdict is unavailable")
                if not all(value is True for value in answers.values()):
                    action = "item freeze" if stage == "item-set" else "formal publication"
                    raise RuntimeError(
                        f"negative {stage} verdict blocks {action} for sample {order}"
                    )
                if stage == "balloons":
                    merged = sample.get("merged_verdict")
                    if not isinstance(merged, Mapping) or not merged:
                        raise RuntimeError(
                            f"sample {order} merged human verdict is unavailable"
                        )
                    if not all(value is True for value in merged.values()):
                        raise RuntimeError(
                            f"negative merged verdict blocks formal publication for sample {order}"
                        )
                    return {str(key): bool(value) for key, value in merged.items()}
                return {str(key): bool(value) for key, value in answers.items()}
        time.sleep(1)
    raise RuntimeError(
        f"timed out waiting for sample {order} explicit {stage} human verdict"
    )


def _workbench(project_id: str) -> dict[str, Any]:
    return _http_json("GET", f"/api/v1/projects/{quote(project_id)}/workbench")


def _acquire_review_lock(project_id: str, operator_id: str) -> None:
    _http_json(
        "POST",
        f"/api/v1/projects/{quote(project_id)}/review/lock",
        body={"ttl_seconds": 3600},
        operator_id=operator_id,
    )


def _freeze_and_generate_when_ready(
    project_id: str,
    operator_id: str,
    *,
    timeout: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "operator review has not completed"
    while time.monotonic() < deadline:
        _acquire_review_lock(project_id, operator_id)
        snapshot = _workbench(project_id)
        working = snapshot.get("working_copy")
        if not isinstance(working, Mapping):
            raise RuntimeError("project working copy is unavailable")
        try:
            if working.get("items_frozen_at") is None:
                _http_json(
                    "POST",
                    f"/api/v1/projects/{quote(project_id)}/review/freeze-items",
                    body={"expected_version": working.get("version")},
                    operator_id=operator_id,
                )
                snapshot = _workbench(project_id)
                working = snapshot["working_copy"]
            if not snapshot.get("balloons"):
                _http_json(
                    "POST",
                    f"/api/v1/projects/{quote(project_id)}/balloons/generate",
                    body={"expected_version": working.get("version")},
                    operator_id=operator_id,
                )
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(2)
            continue
        snapshot = _workbench(project_id)
        balloons = snapshot.get("balloons")
        if not isinstance(balloons, list):
            raise RuntimeError("project balloon projection is unavailable")
        blockers = snapshot.get("balloon_blockers")
        if not isinstance(blockers, list):
            raise RuntimeError("project balloon blockers are unavailable")
        manual_count = sum(
            balloon.get("placement_status") == "manual_required"
            for balloon in balloons
            if isinstance(balloon, Mapping)
        )
        hard_count = sum(
            len(balloon.get("collision_flags", []))
            for balloon in balloons
            if isinstance(balloon, Mapping)
            and isinstance(balloon.get("collision_flags", []), list)
        )
        if balloons and not blockers and manual_count == 0 and hard_count == 0:
            return snapshot
        last_error = (
            f"balloon blockers={len(blockers)} manual_required={manual_count} "
            f"hard_collisions={hard_count}"
        )
        time.sleep(2)
    raise RuntimeError(
        "timed out waiting for operator review/collision resolution: " + last_error
    )


def _initial_sample_evidence(
    *,
    entry: Mapping[str, Any],
    project: Mapping[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    order = int(entry["order"])
    project_id = str(project["project_id"])
    process = dict(project["process"])
    page_metadata = entry.get("page_metadata")
    if not isinstance(page_metadata, Mapping):
        raise RuntimeError(f"sample {order} page metadata is unavailable")
    process.update(
        {
            "expected_page_count": int(page_metadata["page_count"]),
            "expected_physical_page": str(page_metadata["physical_page"]),
            "prepare_log_ref": f"logs/sample-{order}-prepare.log",
        }
    )
    if (
        process.get("source_sha256") != entry.get("sha256")
        or process.get("actual_page_count") != process["expected_page_count"]
        or process.get("actual_physical_pages")
        != [process["expected_physical_page"]]
    ):
        raise RuntimeError(f"sample {order} process facts differ from frozen manifest")
    candidates = dict(project["candidates"])
    if (
        candidates.get("candidate_count") != len(candidates.get("candidate_ids", []))
        or not candidates.get("source_location_ids")
        or candidates.get("coverage_checked") is not True
        or candidates.get("coverage_blocking_count") != 0
    ):
        raise RuntimeError(f"sample {order} candidate/coverage evidence is incomplete")
    return {
        "order": order,
        "opaque_ref": str(entry["opaque_ref"]),
        "project_id": project_id,
        "project_url": (
            f"/?project_id={quote(project_id)}&operator_id={quote(operator_id)}"
        ),
        "process": process,
        "candidates": candidates,
        "review": None,
        "human_verdict": None,
        "balloons": None,
        "export": None,
        "consistency": None,
    }


def _write_live_sample(run_dir: Path, sample: Mapping[str, Any]) -> None:
    path = run_dir / LIVE_EVIDENCE_ARTIFACT
    live = _load_json(path)
    samples = live.get("samples")
    if not isinstance(samples, list):
        raise RuntimeError("live sample evidence collection is unavailable")
    order = sample.get("order")
    project_id = sample.get("project_id")
    if any(
        existing.get("project_id") == project_id and existing.get("order") != order
        for existing in samples
        if isinstance(existing, Mapping)
    ):
        raise RuntimeError("live project identity is already bound to another sample")
    index = next(
        (
            position
            for position, existing in enumerate(samples)
            if isinstance(existing, Mapping) and existing.get("order") == order
        ),
        None,
    )
    if index is None:
        samples.append(dict(sample))
    else:
        if samples[index].get("project_id") != project_id:
            raise RuntimeError("live sample project identity changed")
        samples[index] = dict(sample)
    samples.sort(key=lambda value: int(value["order"]))
    receipt_module = _receipt_module()
    receipt_module.validate_schema(
        live,
        "live-run-evidence.schema.json",
        ROOT,
    )
    _atomic_write_json(path, live)


def _freeze_sample_after_item_verdict(
    run_dir: Path,
    sample: dict[str, Any],
    *,
    operator_id: str,
    timeout: int,
) -> dict[str, Any]:
    order = int(sample["order"])
    project_id = str(sample["project_id"])
    _wait_for_sample_verdict(
        run_dir,
        order=order,
        project_id=project_id,
        stage="item-set",
        timeout=timeout,
    )
    verdict = _load_human_verdict(run_dir)
    verdict_sample = _verdict_sample(
        verdict,
        order=order,
        project_id=project_id,
    )
    if not isinstance(verdict_sample, Mapping) or not isinstance(
        verdict_sample.get("item_set"), Mapping
    ):
        raise RuntimeError(f"sample {order} item-set verdict binding disappeared")
    item_write = verdict_sample["item_set"]
    readiness = _collect_item_set_readiness(
        run_dir,
        order=order,
        project_id=project_id,
    )
    if any(
        readiness.get(field) is not None
        for field in ("frozen_version", "frozen_by", "items_frozen_at")
    ):
        raise RuntimeError(
            f"sample {order} item-set verdict must precede item freeze"
        )
    if not _review_item_set_ready(
        readiness,
        sample["candidates"],
        item_write,
        operator_id=operator_id,
    ):
        raise RuntimeError(
            f"sample {order} required review command/disposition proof is incomplete"
        )
    _freeze_and_generate_when_ready(
        project_id,
        operator_id,
        timeout=timeout,
    )
    evidence = _collect_review_balloon_evidence(
        run_dir,
        order=order,
        project_id=project_id,
    )
    review = dict(evidence["review"])
    review.update(
        {
            "merge_split_disposition": item_write["merge_split_disposition"],
            "merge_split_note": item_write["merge_split_note"],
        }
    )
    sample["review"] = review
    sample["balloons"] = {**evidence["balloons"], "browser": None}
    _write_live_sample(run_dir, sample)
    return sample


def pause_live_run(run_dir: Path) -> None:
    run_path = run_dir / "run.json"
    run = _load_json(run_path)
    if (
        run.get("run_id") != run_dir.name
        or run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("execution_state") != "running"
        or run.get("completed_at") is not None
    ):
        raise ValueError("only one running full-p0 live run can pause")
    live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
    if (
        live.get("run_id") != run_dir.name
        or live.get("design_qa") is not None
        or len(live.get("samples", [])) != 1
    ):
        raise ValueError("first-sample live evidence is not ready for visual-QA pause")
    receipt_module = _receipt_module()
    receipt_module.validate_schema(
        live,
        "live-run-evidence.schema.json",
        ROOT,
    )
    _atomic_write_json(run_dir / LIVE_EVIDENCE_ARTIFACT, live)
    run["pause_identity"] = {
        "code_identity": run["code_identity"],
        "config_identity": run["config_identity"],
        "contract_definition_hash": run["contract_definition_hash"],
        "input_identity": run["input_identity"],
        "live_identity": run["live_identity"],
    }
    run["execution_state"] = "visual_qa_pending"
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _atomic_write_json(run_path, run)


def _mark_live_run_resumed(run_dir: Path) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    run = _load_json(run_path)
    expected_pause_identity = {
        "code_identity": run.get("code_identity"),
        "config_identity": run.get("config_identity"),
        "contract_definition_hash": run.get("contract_definition_hash"),
        "input_identity": run.get("input_identity"),
        "live_identity": run.get("live_identity"),
    }
    if (
        run.get("run_id") != run_dir.name
        or run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("execution_state") != "visual_qa_pending"
        or run.get("pause_identity") != expected_pause_identity
        or run.get("completed_at") is not None
    ):
        raise ValueError("paused full-p0 live lifecycle cannot be resumed")
    run["execution_state"] = "running"
    receipt_module = _receipt_module()
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _atomic_write_json(run_path, run)
    return run


def _bind_design_qa_and_resume(
    run_dir: Path,
    design_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    live_path = run_dir / LIVE_EVIDENCE_ARTIFACT
    try:
        live = _load_json(live_path)
        live["design_qa"] = dict(design_evidence)
        receipt_module = _receipt_module()
        receipt_module.validate_schema(
            live,
            "live-run-evidence.schema.json",
            ROOT,
        )
        run = _mark_live_run_resumed(run_dir)
        _atomic_write_json(live_path, live)
        return run
    except Exception:
        try:
            abort_live_run(
                run_dir,
                reason="visual_qa_or_resume_transition_failed",
            )
        except Exception:
            pass
        raise


def start_live_run(preflight: LivePreflight) -> str:
    operator_id = str(_current_live_identity()["operator_id"])
    timeout = _wait_seconds()
    run_dir = _open_live_run(preflight)
    try:
        print(f"run_id={run_dir.name}", file=sys.stderr, flush=True)
        manifest = json.loads(preflight.manifest_bytes)
        first = manifest["entries"][0]
        project = _prepare_live_project(
            run_dir,
            source_path=preflight.source_paths[0],
            order=1,
            expected_sha256=first["sha256"],
        )
        sample = _initial_sample_evidence(
            entry=first,
            project=project,
            operator_id=operator_id,
        )
        _write_live_sample(run_dir, sample)
        project_id = str(sample["project_id"])
        frontend = str(_current_live_identity()["frontend_base"])
        print(
            f"project_url={frontend}{sample['project_url']}\n"
            f"record sample=1 project_id={project_id} item-set verdict in this "
            "run after reviewing every page",
            file=sys.stderr,
            flush=True,
        )
        _freeze_sample_after_item_verdict(
            run_dir,
            sample,
            operator_id=operator_id,
            timeout=timeout,
        )
        pause_live_run(run_dir)
        return run_dir.name
    except Exception as exc:
        try:
            abort_live_run(
                run_dir,
                reason=f"live_start_failed:{type(exc).__name__}",
            )
        except Exception:
            pass
        raise


def _design_qa_document_path() -> Path:
    return ROOT / "design-qa.md"


def _design_qa_evidence(path: Path, run_dir: Path) -> dict[str, Any]:
    expected = _design_qa_document_path().resolve(strict=False)
    if path.is_symlink() or not path.is_file() or path.resolve() != expected:
        raise ValueError("--design-qa must be the project-root design-qa.md")
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("design-qa.md must be UTF-8") from exc
    if "/home/" in text:
        raise ValueError("design-qa.md must not expose a host source path")

    def field(label: str) -> str:
        values = re.findall(
            rf"^{re.escape(label)}: (.+)$",
            text,
            flags=re.MULTILINE,
        )
        if len(values) != 1 or not values[0].strip():
            raise ValueError(
                f"design-qa.md required structured field is missing: {label}"
            )
        return values[0].strip()

    if len(re.findall(r"^final result: passed$", text, flags=re.MULTILINE)) != 1:
        raise ValueError("design-qa.md requires exactly one final result: passed")
    if re.search(r"^final result: blocked$", text, flags=re.MULTILINE):
        raise ValueError("blocked design QA cannot resume the formal run")
    source_sha256 = field("source sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("design-qa.md source identity must be SHA-256")
    implementation_route = field("implementation route")
    implementation_state = field("implementation state")
    if implementation_state != "visual_qa_pending:first-pdf-balloons":
        raise ValueError("design-qa.md implementation state is not the pause barrier")
    live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
    samples = live.get("samples")
    if (
        not isinstance(samples, list)
        or not samples
        or samples[0].get("order") != 1
        or samples[0].get("project_url") != implementation_route
    ):
        raise ValueError("design-qa.md implementation route is not run-bound")
    if field("browser") != LIVE_BROWSER or field("viewport") != "1565x796":
        raise ValueError("design-qa.md browser/viewport differs from the selected target")

    captures: dict[str, str] = {}
    capture_refs: list[str] = []
    capture_digests: list[str] = []
    for kind in ("implementation", "comparison"):
        ref = field(f"{kind} capture")
        digest = field(f"{kind} capture sha256")
        if not re.fullmatch(r"reports/[A-Za-z0-9][A-Za-z0-9._-]*\.png", ref):
            raise ValueError(f"design-qa.md {kind} capture ref is invalid")
        capture = run_dir / ref
        reports_root = (run_dir / "reports").resolve(strict=False)
        if (
            capture.is_symlink()
            or not capture.is_file()
            or capture.resolve() == reports_root
            or reports_root not in capture.resolve().parents
        ):
            raise ValueError(f"design-qa.md {kind} capture is unavailable")
        capture_content = capture.read_bytes()
        if not capture_content.startswith(PNG_SIGNATURE):
            raise ValueError(f"design-qa.md {kind} capture must be a PNG")
        content_digest = hashlib.sha256(capture_content).hexdigest()
        if digest != content_digest:
            raise ValueError(f"design-qa.md {kind} capture identity changed")
        captures[f"{kind}_capture_ref"] = ref
        captures[f"{kind}_capture_sha256"] = digest
        capture_refs.append(ref)
        capture_digests.append(digest)
    if len(set(capture_refs)) != 2 or len(set(capture_digests)) != 2:
        raise ValueError("design-qa.md comparison captures must be distinct")

    count_labels = {
        "console_error_count": "console errors",
        "network_error_count": "network errors",
        "p0": "P0 issues",
        "p1": "P1 issues",
        "p2": "P2 issues",
    }
    counts: dict[str, int] = {}
    for key, label in count_labels.items():
        value = field(label)
        if value != "0":
            raise ValueError(f"design-qa.md {label} must be zero")
        counts[key] = 0

    return {
        "ref": "design-qa.md",
        "sha256": hashlib.sha256(content).hexdigest(),
        "final_result": "passed",
        "browser": LIVE_BROWSER,
        "viewport": dict(LIVE_VIEWPORT),
        "source_sha256": source_sha256,
        "implementation_route": implementation_route,
        "implementation_state": implementation_state,
        **captures,
        "console_error_count": counts["console_error_count"],
        "network_error_count": counts["network_error_count"],
        "issue_counts": {
            "p0": counts["p0"],
            "p1": counts["p1"],
            "p2": counts["p2"],
        },
    }


def _resume_identity_preflight(run_dir: Path) -> LivePreflight:
    run = _load_json(run_dir / "run.json")
    if not can_resume_live_run(run_dir):
        raise ValueError("run is not one resumable visual-QA pause")
    preflight = preflight_full_p0_live(
        input_set="current-four",
        source_root=os.environ.get(LIVE_SOURCE_ROOT_ENV),
    )
    current = {
        "code_identity": preflight.code_identity,
        "config_identity": preflight.config_identity,
        "contract_definition_hash": preflight.mirror["contract_definition_hash"],
        "input_identity": preflight.input_identity,
        "live_identity": _current_live_identity(),
    }
    if run.get("pause_identity") != current:
        raise ValueError("paused live identity changed; resume is forbidden")
    artifact = (run_dir / CURRENT_FOUR_ARTIFACT).read_bytes()
    if artifact != preflight.manifest_bytes:
        raise ValueError("paused current-four manifest changed")
    return preflight


def _browser_environment(
    run_dir: Path,
    sample: Mapping[str, Any],
    *,
    operator_id: str,
    phase: str,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = dict(os.environ if base_environment is None else base_environment)
    frontend = source.get(
        LIVE_FRONTEND_BASE_ENV,
        "http://localhost:3000",
    ).rstrip("/")
    environment = {
        key: value
        for key, value in source.items()
        if key in SAFE_BROWSER_ENV_KEYS
    }
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QI_P0_PROJECT_URL": frontend + str(sample["project_url"]),
            "QI_P0_OPERATOR_ID": operator_id,
            "QI_P0_RUN_ID": run_dir.name,
            "QI_P0_SAMPLE_ORDER": str(int(sample["order"])),
            "QI_P0_E2E_PHASE": phase,
            "QI_P0_REPORT_DIR": str((run_dir / "reports").resolve()),
        }
    )
    return environment


def _browser_item_numbers(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping) or set(entry) != {
            "item_id",
            "formal_number",
        }:
            return None
        item_id = entry.get("item_id")
        formal_number = entry.get("formal_number")
        if (
            not isinstance(item_id, str)
            or not item_id
            or not isinstance(formal_number, int)
            or isinstance(formal_number, bool)
            or formal_number < 1
        ):
            return None
        normalized.append(
            {"item_id": item_id, "formal_number": formal_number}
        )
    if len({entry["item_id"] for entry in normalized}) != len(normalized):
        return None
    if len({entry["formal_number"] for entry in normalized}) != len(normalized):
        return None
    return sorted(normalized, key=lambda entry: entry["item_id"])


def _browser_item_ids(value: Any) -> list[str] | None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item_id, str) or not item_id for item_id in value)
        or len(set(value)) != len(value)
    ):
        return None
    return sorted(value)


def _run_browser_e2e(
    run_dir: Path,
    sample: Mapping[str, Any],
    *,
    operator_id: str,
    phase: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if phase not in {"pre-export", "export"}:
        raise ValueError("browser E2E phase must be pre-export or export")
    order = int(sample["order"])
    environment = _browser_environment(
        run_dir,
        sample,
        operator_id=operator_id,
        phase=phase,
    )
    command = [
        "npm",
        "--prefix",
        "frontend",
        "run",
        "e2e",
        "--",
        "e2e/p0-workbench.spec.ts",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    log_ref = f"logs/sample-{order}-playwright-{phase}.log"
    (run_dir / log_ref).write_text(
        "\n".join(
            (
                f"command={shlex.join(command)}",
                f"exit_code={result.returncode}",
                "stdout:",
                result.stdout,
                "stderr:",
                result.stderr,
            )
        ),
        encoding="utf-8",
    )
    report_ref = f"reports/playwright-{order}-{phase}.json"
    screenshot_ref = f"reports/workbench-{order}-{phase}.png"
    result_ref = f"reports/e2e-{order}-{phase}.json"
    for ref in (report_ref, screenshot_ref, result_ref):
        path = run_dir / ref
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"sample {order} browser evidence is missing: {ref}")
    if result.returncode != 0:
        raise RuntimeError(f"sample {order} Chrome E2E failed; see {log_ref}")
    browser_result = _load_json(run_dir / result_ref)
    table_item_numbers = _browser_item_numbers(
        browser_result.get("table_item_numbers")
    )
    backend_item_numbers = _browser_item_numbers(
        browser_result.get("backend_item_numbers")
    )
    overlay_item_numbers = _browser_item_numbers(
        browser_result.get("overlay_item_numbers")
    )
    common_invalid = (
        browser_result.get("run_id") != run_dir.name
        or browser_result.get("order") != order
        or browser_result.get("project_id") != sample.get("project_id")
        or browser_result.get("phase") != phase
        or not isinstance(browser_result.get("captured_at"), str)
        or browser_result.get("glyph_metrics_verified") is not True
        or table_item_numbers is None
        or backend_item_numbers is None
        or overlay_item_numbers is None
        or table_item_numbers != backend_item_numbers
        or table_item_numbers != overlay_item_numbers
        or _browser_item_ids(browser_result.get("table_active_item_ids")) is None
    )
    if phase == "pre-export":
        actions = browser_result.get("actions")
        active_ids = browser_result.get("active_item_ids")
        active_numbers = browser_result.get("active_item_numbers")
        phase_invalid = (
            browser_result.get("formal_publish_attempted") is not False
            or browser_result.get("hard_collision_count") != 0
            or browser_result.get("unresolved_manual_required_count") != 0
            or not isinstance(active_ids, list)
            or not isinstance(active_numbers, list)
            or sorted(str(value) for value in active_numbers)
            != sorted(str(value) for value in browser_result.get("overlay_numbers", []))
            or sorted(str(value) for value in active_ids)
            != sorted(entry["item_id"] for entry in backend_item_numbers or [])
            or sorted(int(value) for value in active_numbers)
            != sorted(
                entry["formal_number"] for entry in backend_item_numbers or []
            )
            or not isinstance(actions, Mapping)
            or set(actions) != {"drag", "delete", "rebuild", "renumber"}
            or not all(value is True for value in actions.values())
        )
    else:
        artifacts = browser_result.get("artifacts")
        reviewed_item_ids = browser_result.get("reviewed_item_ids")
        reviewed_numbers = browser_result.get("reviewed_numbers")
        content_types = {
            "ballooned_pdf": "application/pdf",
            "sip_excel": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "manifest": "application/json",
        }
        phase_invalid = (
            browser_result.get("formal_publish_attempted") is not True
            or browser_result.get("status") != "success"
            or not browser_result.get("reviewed_result_id")
            or not browser_result.get("export_id")
            or not isinstance(reviewed_item_ids, list)
            or not isinstance(reviewed_numbers, list)
            or sorted(str(value) for value in reviewed_item_ids)
            != sorted(entry["item_id"] for entry in backend_item_numbers or [])
            or sorted(int(value) for value in reviewed_numbers)
            != sorted(
                entry["formal_number"] for entry in backend_item_numbers or []
            )
            or browser_result.get("download_kinds")
            != ["ballooned_pdf", "sip_excel", "manifest"]
            or not isinstance(artifacts, list)
            or len(artifacts) != 3
            or any(
                not isinstance(artifact, Mapping)
                or artifact.get("downloadable") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", "")))
                or not isinstance(artifact.get("size_bytes"), int)
                or artifact.get("size_bytes", 0) < 1
                or not str(artifact.get("content_type", "")).startswith(
                    content_types.get(str(artifact.get("kind", "")), "missing/")
                )
                for artifact in artifacts
            )
        )
    if common_invalid or phase_invalid:
        raise RuntimeError(f"sample {order} browser evidence failed consistency gates")
    report_path = run_dir / report_ref
    screenshot_path = run_dir / screenshot_ref
    result_path = run_dir / result_ref
    screenshot_content = screenshot_path.read_bytes()
    if not screenshot_content.startswith(PNG_SIGNATURE):
        raise RuntimeError(f"sample {order} browser screenshot is not a PNG")
    browser_evidence = {
        "passed": True,
        "captured_at": browser_result["captured_at"],
        "report_ref": report_ref,
        "screenshot_refs": [screenshot_ref],
        "result_ref": result_ref,
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "screenshot_sha256": hashlib.sha256(screenshot_content).hexdigest(),
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
    }
    return browser_evidence, browser_result


def _complete_sample_after_balloons(
    run_dir: Path,
    sample: Mapping[str, Any],
    *,
    operator_id: str,
    timeout: int,
) -> dict[str, Any]:
    completed = dict(sample)
    order = int(completed["order"])
    project_id = str(completed["project_id"])
    balloon_evidence = completed.get("balloons")
    if not isinstance(balloon_evidence, Mapping):
        raise RuntimeError(f"sample {order} balloon evidence is unavailable")

    pre_browser, pre_result = _run_browser_e2e(
        run_dir,
        completed,
        operator_id=operator_id,
        phase="pre-export",
    )
    balloon_evidence = dict(balloon_evidence)
    balloon_evidence.update(
        {
            "hard_collision_count": pre_result["hard_collision_count"],
            "unresolved_manual_required_count": pre_result[
                "unresolved_manual_required_count"
            ],
            "active_item_ids": pre_result["active_item_ids"],
            "formal_numbers": [
                int(value) for value in pre_result["active_item_numbers"]
            ],
            "browser": pre_browser,
        }
    )
    completed["balloons"] = balloon_evidence
    _write_live_sample(run_dir, completed)

    merged = _wait_for_sample_verdict(
        run_dir,
        order=order,
        project_id=project_id,
        stage="balloons",
        timeout=timeout,
    )
    completed["human_verdict"] = merged
    # Persist the affirmative, run/project-bound gate before any Confirm/export call.
    _write_live_sample(run_dir, completed)

    export_browser, export_result = _run_browser_e2e(
        run_dir,
        completed,
        operator_id=operator_id,
        phase="export",
    )
    completed = _collect_post_export_evidence(
        run_dir,
        completed,
        export_result,
    )
    export_evidence = completed.get("export")
    if not isinstance(export_evidence, dict):
        raise RuntimeError(f"sample {order} export evidence is unavailable")
    export_evidence["browser"] = export_browser
    _write_live_sample(run_dir, completed)
    return completed


def _live_phase_outcome(
    selector: str,
    run_dir: Path,
) -> tuple[int | None, str, str, list[str]]:
    phase = urlsplit(selector).path.lstrip("/")
    if phase not in LIVE_PHASES:
        return None, "blocked", f"unknown live phase: {phase}", []
    try:
        live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
        manifest = _load_json(run_dir / CURRENT_FOUR_ARTIFACT)
        run = _load_json(run_dir / "run.json")
        human = _load_json(run_dir / HUMAN_VERDICT_ARTIFACT)
        receipt_module = _receipt_module()
        for document, schema_name in (
            (run, "run.schema.json"),
            (live, "live-run-evidence.schema.json"),
            (manifest, "current-four-manifest.schema.json"),
            (human, "human-verdict.schema.json"),
        ):
            receipt_module.validate_schema(document, schema_name, ROOT)

        expected_pause_identity = {
            "code_identity": run["code_identity"],
            "config_identity": run["config_identity"],
            "contract_definition_hash": run["contract_definition_hash"],
            "input_identity": run["input_identity"],
            "live_identity": run["live_identity"],
        }
        if (
            run_dir.name != run.get("run_id")
            or run_dir.name != live.get("run_id")
            or run_dir.name != human.get("run_id")
            or run.get("mode") != "live"
            or run.get("scope") != "full-p0"
            or run.get("task_id") is not None
            or run.get("execution_state") != "running"
            or run.get("failure_reason") is not None
            or run.get("pause_identity") != expected_pause_identity
            or live.get("input_set") != "current-four"
            or live.get("phases") != list(LIVE_PHASES)
            or live.get("child_run_ids") != []
            or manifest.get("input_set") != "current-four"
        ):
            raise ValueError("full-p0 live run identity or lifecycle is inconsistent")

        samples = live.get("samples")
        entries = manifest.get("entries")
        verdict_samples = human.get("samples")
        if (
            not isinstance(samples, list)
            or len(samples) != 4
            or not isinstance(entries, list)
            or len(entries) != 4
            or not isinstance(verdict_samples, list)
            or len(verdict_samples) != 4
        ):
            raise ValueError("current-four evidence is incomplete")
        by_order = {
            int(sample["order"]): sample
            for sample in samples
            if isinstance(sample, Mapping)
        }
        manifest_by_order = {
            int(entry["order"]): entry
            for entry in entries
            if isinstance(entry, Mapping)
        }
        verdict_by_order = {
            int(sample["order"]): sample
            for sample in verdict_samples
            if isinstance(sample, Mapping)
        }
        expected_orders = {1, 2, 3, 4}
        if (
            set(by_order) != expected_orders
            or set(manifest_by_order) != expected_orders
            or set(verdict_by_order) != expected_orders
            or len({sample["project_id"] for sample in samples}) != 4
        ):
            raise ValueError("current-four sample identity is incomplete")

        design = live.get("design_qa")
        if not isinstance(design, Mapping) or dict(design) != _design_qa_evidence(
            _design_qa_document_path(),
            run_dir,
        ):
            raise ValueError("design QA evidence is not bound to this run")

        live_identity = run.get("live_identity")
        if not isinstance(live_identity, Mapping):
            raise ValueError("live operator identity is unavailable")
        operator_id = live_identity.get("operator_id")
        if (
            not isinstance(operator_id, str)
            or live_identity.get("browser", {}).get("name") != LIVE_BROWSER
            or live_identity.get("viewport") != LIVE_VIEWPORT
        ):
            raise ValueError("live operator/browser identity is invalid")

        bound: dict[int, dict[str, Any]] = {}
        for order in sorted(expected_orders):
            sample = by_order[order]
            entry = manifest_by_order[order]
            verdict_sample = verdict_by_order[order]
            project_id = sample.get("project_id")
            item_write = verdict_sample.get("item_set")
            balloon_write = verdict_sample.get("balloons")
            item_answers = (
                item_write.get("answers")
                if isinstance(item_write, Mapping)
                else None
            )
            balloon_answers = (
                balloon_write.get("answers")
                if isinstance(balloon_write, Mapping)
                else None
            )
            merged_verdict = (
                {**item_answers, **balloon_answers}
                if isinstance(item_answers, Mapping)
                and isinstance(balloon_answers, Mapping)
                else None
            )
            if (
                verdict_sample.get("project_id") != project_id
                or not isinstance(item_write, Mapping)
                or not isinstance(balloon_write, Mapping)
                or not isinstance(item_answers, Mapping)
                or not isinstance(balloon_answers, Mapping)
                or not all(value is True for value in item_answers.values())
                or not all(value is True for value in balloon_answers.values())
                or item_write.get("operator_id") != operator_id
                or balloon_write.get("operator_id") != operator_id
                or verdict_sample.get("merged_verdict")
                != merged_verdict
                or merged_verdict
                != sample.get("human_verdict")
                or sample.get("opaque_ref") != entry.get("opaque_ref")
            ):
                raise ValueError(f"sample {order} human/input identity is spliced")

            process = sample.get("process")
            review = sample.get("review")
            balloons = sample.get("balloons")
            export = sample.get("export")
            consistency = sample.get("consistency")
            if not all(
                isinstance(value, Mapping)
                for value in (process, review, balloons, export, consistency)
            ):
                raise ValueError(f"sample {order} phase evidence is incomplete")
            if (
                review.get("merge_split_disposition")
                != item_write.get("merge_split_disposition")
                or review.get("merge_split_note")
                != item_write.get("merge_split_note")
            ):
                raise ValueError(
                    f"sample {order} merge/split disposition is not human-bound"
                )
            item_verdict_time = _parse_utc_timestamp(
                item_write.get("recorded_at")
            )
            items_frozen_time = _parse_utc_timestamp(
                review.get("items_frozen_at")
            )
            if (
                item_verdict_time is None
                or items_frozen_time is None
                or not item_verdict_time < items_frozen_time
            ):
                raise ValueError(
                    f"sample {order} item-set verdict did not precede item freeze"
                )

            _verified_run_artifact(
                run_dir,
                process.get("prepare_log_ref"),
                process.get("prepare_log_sha256"),
            )
            _, review_report = _verified_run_artifact(
                run_dir,
                review.get("evidence_ref"),
                review.get("evidence_sha256"),
                expect_json=True,
            )
            expected_review_report = {
                key: value
                for key, value in review.items()
                if key
                not in {
                    "merge_split_disposition",
                    "merge_split_note",
                    "evidence_ref",
                    "evidence_sha256",
                }
            }
            if (
                review_report.get("run_id") != run_dir.name
                or review_report.get("order") != order
                or review_report.get("project_id") != project_id
                or review_report.get("review") != expected_review_report
                or review_report.get("balloons")
                != {key: value for key, value in balloons.items() if key != "browser"}
            ):
                raise ValueError(f"sample {order} review report is not cross-bound")

            browser_results: dict[str, dict[str, Any]] = {}
            for browser_phase, section in (
                ("pre-export", balloons),
                ("export", export),
            ):
                browser = section.get("browser")
                if not isinstance(browser, Mapping):
                    raise ValueError(
                        f"sample {order} {browser_phase} browser evidence is missing"
                    )
                screenshots = browser.get("screenshot_refs")
                if not isinstance(screenshots, list) or len(screenshots) != 1:
                    raise ValueError(
                        f"sample {order} {browser_phase} screenshot set is invalid"
                    )
                _verified_run_artifact(
                    run_dir,
                    browser.get("report_ref"),
                    browser.get("report_sha256"),
                )
                _verified_run_artifact(
                    run_dir,
                    screenshots[0],
                    browser.get("screenshot_sha256"),
                    expect_png=True,
                )
                _, browser_result = _verified_run_artifact(
                    run_dir,
                    browser.get("result_ref"),
                    browser.get("result_sha256"),
                    expect_json=True,
                )
                table_item_numbers = _browser_item_numbers(
                    browser_result.get("table_item_numbers")
                )
                backend_item_numbers = _browser_item_numbers(
                    browser_result.get("backend_item_numbers")
                )
                overlay_item_numbers = _browser_item_numbers(
                    browser_result.get("overlay_item_numbers")
                )
                if (
                    browser_result.get("run_id") != run_dir.name
                    or browser_result.get("order") != order
                    or browser_result.get("project_id") != project_id
                    or browser_result.get("phase") != browser_phase
                    or browser_result.get("captured_at")
                    != browser.get("captured_at")
                    or browser_result.get("glyph_metrics_verified") is not True
                    or table_item_numbers is None
                    or backend_item_numbers is None
                    or overlay_item_numbers is None
                    or table_item_numbers != backend_item_numbers
                    or table_item_numbers != overlay_item_numbers
                    or _browser_item_ids(
                        browser_result.get("table_active_item_ids")
                    )
                    is None
                ):
                    raise ValueError(
                        f"sample {order} {browser_phase} result is not cross-bound"
                    )
                browser_results[browser_phase] = browser_result

            pre_time = _parse_utc_timestamp(
                browser_results["pre-export"].get("captured_at")
            )
            verdict_time = _parse_utc_timestamp(balloon_write.get("recorded_at"))
            export_time = _parse_utc_timestamp(
                browser_results["export"].get("captured_at")
            )
            if (
                pre_time is None
                or verdict_time is None
                or export_time is None
                or not pre_time < verdict_time < export_time
            ):
                raise ValueError(
                    f"sample {order} balloon verdict is not between browser phases"
                )

            _, consistency_report = _verified_run_artifact(
                run_dir,
                consistency.get("evidence_ref"),
                consistency.get("evidence_sha256"),
                expect_json=True,
            )
            expected_consistency_report = {
                key: value
                for key, value in consistency.items()
                if key not in {"evidence_ref", "evidence_sha256"}
            }
            if (
                consistency_report.get("run_id") != run_dir.name
                or consistency_report.get("order") != order
                or consistency_report.get("project_id") != project_id
                or consistency_report.get("export")
                != {key: value for key, value in export.items() if key != "browser"}
                or consistency_report.get("consistency")
                != expected_consistency_report
            ):
                raise ValueError(
                    f"sample {order} consistency report is not cross-bound"
                )
            bound[order] = {
                "verdict": verdict_sample,
                "browsers": browser_results,
            }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return None, "blocked", f"live evidence validation failed: {exc}", []

    def process_ok(sample: Mapping[str, Any]) -> bool:
        entry = manifest_by_order[int(sample["order"])]
        evidence = sample.get("process")
        metadata = entry.get("page_metadata")
        return bool(
            isinstance(evidence, Mapping)
            and isinstance(metadata, Mapping)
            and sample.get("opaque_ref") == entry.get("opaque_ref")
            and evidence.get("source_sha256") == entry.get("sha256")
            and str(sample.get("opaque_ref", "")).endswith(
                str(evidence.get("source_sha256", ""))
            )
            and evidence.get("expected_page_count") == metadata.get("page_count")
            and evidence.get("actual_page_count") == metadata.get("page_count")
            and evidence.get("expected_physical_page")
            == metadata.get("physical_page")
            and evidence.get("actual_physical_pages")
            == [metadata.get("physical_page")]
            and evidence.get("automatic_result_id")
        )

    def candidates_ok(sample: Mapping[str, Any]) -> bool:
        evidence = sample.get("candidates")
        if not isinstance(evidence, Mapping):
            return False
        candidate_ids = evidence.get("candidate_ids")
        sources = evidence.get("source_location_ids")
        records = evidence.get("candidate_records")
        count = evidence.get("candidate_count")
        if not isinstance(records, list):
            return False

        def valid_box(value: Any) -> bool:
            return bool(
                isinstance(value, list)
                and len(value) == 4
                and all(
                    isinstance(number, (int, float))
                    and not isinstance(number, bool)
                    and math.isfinite(number)
                    for number in value
                )
                and value[0] < value[2]
                and value[1] < value[3]
            )

        record_ids: list[str] = []
        source_ids: list[str] = []
        for record in records:
            if not isinstance(record, Mapping) or not valid_box(
                record.get("coordinates")
            ):
                return False
            candidate_id = record.get("candidate_id")
            source_evidence = record.get("source_evidence")
            expected_source_ids = record.get("source_location_ids")
            if (
                not isinstance(candidate_id, str)
                or not isinstance(source_evidence, list)
                or not source_evidence
                or not isinstance(expected_source_ids, list)
                or not expected_source_ids
            ):
                return False
            record_ids.append(candidate_id)
            for source in source_evidence:
                if (
                    not isinstance(source, Mapping)
                    or source.get("disposition") != "candidate"
                    or not isinstance(source.get("source_location_id"), str)
                    or not valid_box(source.get("coordinates"))
                ):
                    return False
                source_ids.append(source["source_location_id"])
            if set(expected_source_ids) != {
                source["source_location_id"] for source in source_evidence
            }:
                return False
        return bool(
            isinstance(count, int)
            and count > 0
            and isinstance(candidate_ids, list)
            and len(candidate_ids) == count
            and len(set(candidate_ids)) == count
            and isinstance(sources, list)
            and set(record_ids) == set(candidate_ids)
            and len(record_ids) == count
            and set(source_ids) == set(sources)
            and len(source_ids) >= count
            and evidence.get("coverage_checked") is True
            and evidence.get("coverage_blocking_count") == 0
            and isinstance(evidence.get("coverage_disposition_count"), int)
            and evidence["coverage_disposition_count"] >= count
        )

    def review_ok(sample: Mapping[str, Any]) -> bool:
        evidence = sample.get("review")
        verdict = sample.get("human_verdict")
        candidates = sample.get("candidates")
        if not all(
            isinstance(value, Mapping)
            for value in (evidence, verdict, candidates)
        ):
            return False
        item_write = bound[int(sample["order"])]["verdict"].get("item_set")
        if not isinstance(item_write, Mapping):
            return False
        return bool(
            all(value is True for value in verdict.values())
            and verdict.get("operator_confirmed_item_set_is_complete") is True
            and evidence.get("frozen_version")
            and evidence.get("frozen_by") == operator_id
            and _review_item_set_ready(
                evidence,
                candidates,
                item_write,
                operator_id=operator_id,
            )
        )

    def balloons_ok(sample: Mapping[str, Any]) -> bool:
        evidence = sample.get("balloons")
        review = sample.get("review")
        verdict = sample.get("human_verdict")
        if (
            not isinstance(evidence, Mapping)
            or not isinstance(review, Mapping)
            or not isinstance(verdict, Mapping)
        ):
            return False
        browser = evidence.get("browser")
        browser_result = bound[int(sample["order"])]["browsers"]["pre-export"]
        table_pairs = _browser_item_numbers(
            browser_result.get("table_item_numbers")
        )
        backend_pairs = _browser_item_numbers(
            browser_result.get("backend_item_numbers")
        )
        overlay_pairs = _browser_item_numbers(
            browser_result.get("overlay_item_numbers")
        )
        table_ids = sorted(entry["item_id"] for entry in table_pairs or [])
        table_numbers = sorted(
            entry["formal_number"] for entry in table_pairs or []
        )
        return bool(
            evidence.get("hard_collision_count") == 0
            and evidence.get("unresolved_manual_required_count") == 0
            and evidence.get("active_item_ids")
            == review.get("balloon_required_item_ids")
            and len(evidence.get("formal_numbers", []))
            == len(evidence.get("active_item_ids", []))
            and isinstance(browser, Mapping)
            and browser.get("passed") is True
            and browser_result.get("formal_publish_attempted") is False
            and browser_result.get("hard_collision_count") == 0
            and browser_result.get("unresolved_manual_required_count") == 0
            and table_pairs == backend_pairs == overlay_pairs
            and sorted(browser_result.get("active_item_ids", [])) == table_ids
            and sorted(
                int(value) for value in browser_result.get("active_item_numbers", [])
            )
            == table_numbers
            and sorted(
                int(value) for value in browser_result.get("overlay_numbers", [])
            )
            == table_numbers
            and sorted(evidence.get("active_item_ids", [])) == table_ids
            and sorted(evidence.get("formal_numbers", [])) == table_numbers
            and browser_result.get("actions")
            == {"drag": True, "delete": True, "rebuild": True, "renumber": True}
            and verdict.get("all_required_balloons_visible") is True
            and verdict.get("hard_collisions_resolved") is True
        )

    def export_ok(sample: Mapping[str, Any]) -> bool:
        evidence = sample.get("export")
        if not isinstance(evidence, Mapping):
            return False
        reviewed_id = evidence.get("reviewed_result_id")
        browser = evidence.get("browser")
        browser_result = bound[int(sample["order"])]["browsers"]["export"]
        artifacts = browser_result.get("artifacts")
        browser_by_kind = {
            artifact.get("kind"): artifact
            for artifact in artifacts
            if isinstance(artifact, Mapping)
        } if isinstance(artifacts, list) else {}
        artifact_kinds = evidence.get("artifact_kinds", [])
        return bool(
            reviewed_id
            and evidence.get("status") == "success"
            and evidence.get("artifact_kinds")
            == ["ballooned_pdf", "sip_excel", "manifest"]
            and evidence.get("download_kinds")
            == ["ballooned_pdf", "sip_excel", "manifest"]
            and len(evidence.get("artifact_sha256", [])) == 3
            and evidence.get("artifact_reviewed_result_ids") == [reviewed_id] * 3
            and isinstance(browser, Mapping)
            and browser.get("passed") is True
            and browser_result.get("formal_publish_attempted") is True
            and browser_result.get("status") == "success"
            and browser_result.get("reviewed_result_id") == reviewed_id
            and browser_result.get("export_id") == evidence.get("export_id")
            and browser_result.get("download_kinds") == artifact_kinds
            and set(browser_by_kind) == set(artifact_kinds)
            and all(
                browser_by_kind[kind].get("sha256")
                == evidence["artifact_sha256"][index]
                and browser_by_kind[kind].get("reviewed_result_id") == reviewed_id
                and browser_by_kind[kind].get("download_sha256")
                == browser_by_kind[kind].get("sha256")
                and browser_by_kind[kind].get("download_size_bytes")
                == browser_by_kind[kind].get("size_bytes")
                for index, kind in enumerate(artifact_kinds)
            )
        )

    def consistency_ok(sample: Mapping[str, Any]) -> bool:
        evidence = sample.get("consistency")
        export = sample.get("export")
        review = sample.get("review")
        process = sample.get("process")
        if not all(
            isinstance(value, Mapping)
            for value in (evidence, export, review, process)
        ):
            return False
        number_sets = [
            evidence.get(name)
            for name in (
                "workbench_numbers",
                "reviewed_numbers",
                "pdf_numbers",
                "excel_numbers",
            )
        ]
        normalized_numbers = [
            sorted(values) if isinstance(values, list) else None
            for values in number_sets
        ]
        workbench_pairs = _browser_item_numbers(
            evidence.get("workbench_item_numbers")
        )
        workbench_overlay_pairs = _browser_item_numbers(
            evidence.get("workbench_overlay_item_numbers")
        )
        reviewed_pairs = _browser_item_numbers(
            evidence.get("reviewed_item_numbers")
        )
        export_browser = bound[int(sample["order"])]["browsers"]["export"]
        browser_pairs = _browser_item_numbers(
            export_browser.get("table_item_numbers")
        )
        browser_backend_pairs = _browser_item_numbers(
            export_browser.get("backend_item_numbers")
        )
        browser_overlay_pairs = _browser_item_numbers(
            export_browser.get("overlay_item_numbers")
        )
        workbench_active_ids = _browser_item_ids(
            evidence.get("workbench_active_item_ids")
        )
        reviewed_active_ids = _browser_item_ids(
            evidence.get("reviewed_active_item_ids")
        )
        browser_active_ids = _browser_item_ids(
            export_browser.get("table_active_item_ids")
        )
        return bool(
            evidence.get("verified") is True
            and evidence.get("reviewed_result_id")
            == export.get("reviewed_result_id")
            and evidence.get("reviewed_item_ids")
            == evidence.get("balloon_item_ids")
            == review.get("balloon_required_item_ids")
            and workbench_pairs
            == workbench_overlay_pairs
            == reviewed_pairs
            == browser_pairs
            == browser_backend_pairs
            == browser_overlay_pairs
            and workbench_active_ids
            == reviewed_active_ids
            == browser_active_ids
            and evidence.get("reviewed_item_count")
            == len(reviewed_active_ids or [])
            and [entry["item_id"] for entry in reviewed_pairs or []]
            == evidence.get("reviewed_item_ids")
            and sorted(entry["formal_number"] for entry in reviewed_pairs or [])
            == normalized_numbers[0]
            and normalized_numbers[0]
            == normalized_numbers[1]
            == normalized_numbers[2]
            == normalized_numbers[3]
            and evidence.get("balloon_required_count")
            == evidence.get("balloon_count")
            == len(evidence.get("reviewed_item_ids", []))
            == len(number_sets[0] or [])
            and evidence.get("reviewed_item_count")
            == evidence.get("manifest_reviewed_item_count")
            and evidence.get("balloon_required_count")
            == evidence.get("manifest_balloon_required_count")
            == evidence.get("manifest_balloon_count")
            and evidence.get("source_page_count")
            == evidence.get("manifest_source_page_count")
            == process.get("actual_page_count")
        )

    design = live.get("design_qa")
    design_ok = isinstance(design, Mapping) and (
        design.get("final_result") == "passed"
        and design.get("issue_counts") == {"p0": 0, "p1": 0, "p2": 0}
        and design.get("console_error_count") == 0
        and design.get("network_error_count") == 0
    )
    checks: dict[str, bool] = {
        "process": design_ok and all(process_ok(sample) for sample in samples),
        "candidates": design_ok and all(candidates_ok(sample) for sample in samples),
        "review": design_ok and all(review_ok(sample) for sample in samples),
        "balloons": design_ok and all(balloons_ok(sample) for sample in samples),
        "export": design_ok and all(export_ok(sample) for sample in samples),
        "consistency": design_ok
        and all(consistency_ok(sample) for sample in samples),
    }
    state = "passed" if checks[phase] else "blocked"
    refs = [
        LIVE_EVIDENCE_ARTIFACT,
        HUMAN_VERDICT_ARTIFACT,
        CURRENT_FOUR_ARTIFACT,
    ]
    for sample in samples:
        process = sample.get("process")
        review = sample.get("review")
        if isinstance(process, Mapping):
            refs.append(str(process["prepare_log_ref"]))
        if isinstance(review, Mapping):
            refs.append(str(review["evidence_ref"]))
        for section in (sample.get("balloons"), sample.get("export")):
            if not isinstance(section, Mapping):
                continue
            browser = section.get("browser")
            if isinstance(browser, Mapping):
                refs.extend(
                    [str(browser["report_ref"]), str(browser["result_ref"])]
                )
                refs.extend(str(ref) for ref in browser["screenshot_refs"])
        consistency = sample.get("consistency")
        if isinstance(consistency, Mapping):
            refs.append(str(consistency["evidence_ref"]))
    return (
        0 if state == "passed" else None,
        state,
        json.dumps(
            {"selector": selector, "phase": phase, "passed": checks[phase]},
            sort_keys=True,
        ),
        list(dict.fromkeys(refs)),
    )


def _execute_full_p0_contracts(
    run_dir: Path,
    mirror: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected = sorted(
        mirror["contracts"],
        key=lambda row: row["p0_contract_id"],
    )
    outcomes: dict[str, dict[str, Any]] = {}
    log_refs: dict[str, str] = {}
    selectors = dict.fromkeys(row["verification_selector"] for row in selected)
    for index, selector in enumerate(selectors, start=1):
        outcome = _execute_selector_in_run(selector, "live", run_dir)
        log_ref = f"logs/selector-{index:03d}.log"
        (run_dir / log_ref).write_text(
            outcome.pop("output") + "\n",
            encoding="utf-8",
        )
        outcomes[selector] = outcome
        log_refs[selector] = log_ref
    receipt_module = _receipt_module()
    results: list[dict[str, Any]] = []
    for row in selected:
        selector = row["verification_selector"]
        outcome = outcomes[selector]
        result = {
            "schema_version": "contract-result/1",
            "run_id": run_dir.name,
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
        receipt_module.validate_schema(
            result,
            "contract-result.schema.json",
            ROOT,
        )
        results.append(result)
    return results


def resume_live_run(
    run_dir: Path,
    *,
    design_qa: Path,
) -> tuple[str, str]:
    operator_id = str(_current_live_identity()["operator_id"])
    timeout = _wait_seconds()
    try:
        preflight = _resume_identity_preflight(run_dir)
        design_evidence = _design_qa_evidence(design_qa, run_dir)
    except Exception:
        if can_resume_live_run(run_dir):
            abort_live_run(run_dir, reason="visual_qa_or_identity_changed")
        raise

    run_path = run_dir / "run.json"
    live_path = run_dir / LIVE_EVIDENCE_ARTIFACT
    run = _bind_design_qa_and_resume(run_dir, design_evidence)
    receipt_module = _receipt_module()

    try:
        manifest = json.loads(preflight.manifest_bytes)
        live = _load_json(live_path)
        receipt_module.validate_schema(
            live,
            "live-run-evidence.schema.json",
            ROOT,
        )
        live_samples = live.get("samples")
        if not isinstance(live_samples, list) or len(live_samples) != 1:
            raise RuntimeError("paused live run must contain exactly the first sample")
        samples = list(live_samples)
        print(
            "record sample=1 project_id="
            f"{samples[0]['project_id']} balloons verdict after the pre-export "
            "Chrome inspection",
            file=sys.stderr,
            flush=True,
        )
        samples[0] = _complete_sample_after_balloons(
            run_dir,
            samples[0],
            operator_id=operator_id,
            timeout=timeout,
        )

        for entry, source_path in zip(
            manifest["entries"][1:],
            preflight.source_paths[1:],
            strict=True,
        ):
            order = int(entry["order"])
            project = _prepare_live_project(
                run_dir,
                source_path=source_path,
                order=order,
                expected_sha256=entry["sha256"],
            )
            sample = _initial_sample_evidence(
                entry=entry,
                project=project,
                operator_id=operator_id,
            )
            _write_live_sample(run_dir, sample)
            project_id = str(sample["project_id"])
            frontend = str(_current_live_identity()["frontend_base"])
            print(
                f"sample={order} project_url={frontend}{sample['project_url']}\n"
                f"record sample={order} project_id={project_id} item-set verdict "
                "after reviewing every page",
                file=sys.stderr,
                flush=True,
            )
            sample = _freeze_sample_after_item_verdict(
                run_dir,
                sample,
                operator_id=operator_id,
                timeout=timeout,
            )
            print(
                f"record sample={order} project_id={project_id} balloons verdict "
                "after the pre-export Chrome inspection",
                file=sys.stderr,
                flush=True,
            )
            sample = _complete_sample_after_balloons(
                run_dir,
                sample,
                operator_id=operator_id,
                timeout=timeout,
            )
            samples.append(sample)

        live = _load_json(live_path)
        live_samples = live.get("samples")
        if not isinstance(live_samples, list) or len(live_samples) != 4:
            raise RuntimeError("current-four live evidence is incomplete")
        receipt_module.validate_schema(
            live,
            "live-run-evidence.schema.json",
            ROOT,
        )
        _atomic_write_json(live_path, live)

        results = _execute_full_p0_contracts(run_dir, preflight.mirror)
        _write_json(
            run_dir / "contract-results.json",
            {
                "schema_version": "contract-results/1",
                "run_id": run_dir.name,
                "results": results,
            },
        )
        run["execution_state"] = "completed"
        run["completed_at"] = _iso_now()
        receipt_module.validate_schema(run, "run.schema.json", ROOT)
        receipt = receipt_module.build_receipt(
            ROOT,
            run,
            results,
            preflight.mirror,
            preflight.bindings,
            preflight.policies,
        )
        _atomic_write_json(run_path, run)
        _write_json(run_dir / "receipt.json", receipt)
        _seal_run(run_dir)
        return run_dir.name, receipt["overall_verdict"]
    except Exception as exc:
        try:
            abort_live_run(
                run_dir,
                reason=f"live_resume_failed:{type(exc).__name__}",
            )
        except Exception:
            pass
        raise


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
    parser.add_argument("--task")
    parser.add_argument("--current-four-run", metavar="RUN_ID")
    parser.add_argument("--input-set", choices=("current-four",))
    parser.add_argument("--pause-after", choices=(LIVE_PAUSE_BARRIER,))
    parser.add_argument("--print-run-id-only", action="store_true")
    parser.add_argument("--resume-run", metavar="RUN_ID")
    parser.add_argument("--design-qa", metavar="PATH")
    parser.add_argument("--abort-run", metavar="RUN_ID")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    try:
        if args.abort_run:
            if (
                args.mode != "live"
                or args.scope != "full-p0"
                or args.resume_run
                or args.task
                or not args.reason
            ):
                raise ValueError(
                    "--abort-run requires live --scope full-p0 and --reason only"
                )
            abort_live_run(RUNS / args.abort_run, reason=args.reason)
            print(f"run_id={args.abort_run} execution_state=failed")
            return 1

        if args.resume_run:
            if (
                args.mode != "live"
                or args.scope != "full-p0"
                or args.task
                or not args.design_qa
            ):
                raise ValueError(
                    "--resume-run requires live --scope full-p0 and --design-qa"
                )
            run_id, verdict = resume_live_run(
                RUNS / args.resume_run,
                design_qa=Path(args.design_qa),
            )
            print(
                f"run_id={run_id} scope=full-p0 task=None "
                f"overall_verdict={verdict}"
            )
            return 0 if verdict == "passed" else 1

        if args.mode == "live" and args.scope == "full-p0":
            if (
                args.task
                or args.current_four_run
                or args.input_set != "current-four"
                or args.pause_after != LIVE_PAUSE_BARRIER
            ):
                raise ValueError(
                    "full-p0 live start requires current-four, the first-PDF "
                    "balloon pause, and no task/registration run"
                )
            preflight = preflight_full_p0_live(
                input_set=args.input_set,
                source_root=os.environ.get(LIVE_SOURCE_ROOT_ENV),
            )
            run_id = start_live_run(preflight)
            print(run_id if args.print_run_id_only else (
                f"run_id={run_id} scope=full-p0 task=None "
                "execution_state=visual_qa_pending"
            ))
            return 0

        if not args.task:
            raise ValueError("task scope requires --task Dn-Tn")
        if any(
            value
            for value in (
                args.input_set,
                args.pause_after,
                args.design_qa,
                args.reason,
            )
        ) or args.print_run_id_only:
            raise ValueError("live lifecycle options are limited to full-p0 live")
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
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"run-p0: {exc}", file=sys.stderr)
        return 2
    print(f"run_id={run_id} scope={args.scope} task={args.task} overall_verdict={verdict}")
    return 0 if verdict == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
