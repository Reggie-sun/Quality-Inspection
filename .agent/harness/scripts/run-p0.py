#!/usr/bin/env python3
"""Run the literal selectors for one P0 task and seal immutable evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
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

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
MIRROR_PATH = HARNESS / "contracts/p0-contracts.json"
BINDINGS_PATH = HARNESS / "contracts/global-contract-bindings.json"
TASK_RE = re.compile(r"^D[0-9]+-T[0-9]+$")
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<"}
CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
SYMBOL_EVAL_ARTIFACT = "artifacts/visual-symbol-eval.json"
SYMBOL_VERDICT_ARTIFACT = "artifacts/visual-symbol-annotation-verdict.json"
SYMBOL_EVAL_ARTIFACTS = (SYMBOL_EVAL_ARTIFACT, SYMBOL_VERDICT_ARTIFACT)
ROUTING_COMPARISON_ARTIFACT = "artifacts/symbol-routing-comparison.json"
ROUTING_COMPARISON_FIXTURE = (
    HARNESS / "fixtures/manifests/symbol-routing-comparison-v1.json"
)
SYMBOL_REGISTRATION_REPORT = "reports/symbol-eval-registration.json"
SYMBOL_REGISTRATION_SELECTOR = "phase://live/symbol-eval-registration"
SYMBOL_RECOGNITION_REPORT = "reports/symbol-recognition.json"
SYMBOL_RECOGNITION_SELECTOR = (
    "phase://live/symbol-recognition?input_set=current-four"
)
LIVE_EVIDENCE_ARTIFACT = "live-run-evidence.json"
LIVE_EVIDENCE_SCHEMA_VERSION = "live-run-evidence/2"
HUMAN_VERDICT_ARTIFACT = "artifacts/human-verdict.json"
NO_SILENT_SUCCESS_CONTRACT_ID = "P0-ACC-007"
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
FIXTURE_OFFLINE_PROOF = "reports/fixture-offline-proof.json"
FIXTURE_PYTHON_TRIPWIRE = ".fixture-network-tripwire/sitecustomize.py"
FIXTURE_NODE_TRIPWIRE = ".fixture-network-tripwire/node-network-tripwire.cjs"
FIXTURE_PROVIDER_MODE_KEYS = (
    "QI_PROVIDER_MODE",
    "PROVIDER_MODE",
    "OCR_PROVIDER_MODE",
    "VISION_PROVIDER_MODE",
    "VISION_LLM_PROVIDER_MODE",
)
FIXTURE_PROVIDER_NETWORK_KEYS = (
    "QI_PROVIDER_NETWORK_ENABLED",
    "PROVIDER_NETWORK_ENABLED",
    "OCR_PROVIDER_NETWORK_ENABLED",
    "VISION_PROVIDER_NETWORK_ENABLED",
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
LIVE_COMPOSE_PROJECT_ENV = "COMPOSE_PROJECT_NAME"
EXPECTED_LIVE_API_BASE = "http://127.0.0.1:18000"
EXPECTED_LIVE_FRONTEND_BASE = "http://127.0.0.1:14173"
EXPECTED_LIVE_COMPOSE_PROJECT = f"{ROOT.name.lower()}-qa"
LIVE_API_GDT_RUNTIME_PATHS = (
    "app/providers/visual_symbol_review.schema.json",
    "app/providers/qwen_vl.py",
    "app/candidates/advisor.py",
    "app/candidates/gdt_evidence.py",
    "app/candidates/geometric_tolerance.py",
    "app/candidates/symbol_review.py",
    "app/candidates/complex_fallback.py",
    "app/processing/automatic_result.py",
    "app/processing/runtime_recognition.py",
    "app/pdf/inventory.py",
    "app/pdf/gdt_frames.py",
    "app/pdf/gdt_raster_frames.py",
)
EXPECTED_RECOGNITION_IDENTITY = {
    "mode": "production_uncertainty",
    "router": "symbol-uncertainty-router/1",
    "model": "qwen3-vl-plus-2025-12-19",
}
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
    input_artifacts: dict[str, bytes]
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


def _registered_contract_selector(p0_contract_id: str) -> str:
    mirror = _load_json(MIRROR_PATH)
    matches = [
        row["verification_selector"]
        for row in mirror["contracts"]
        if row["p0_contract_id"] == p0_contract_id
    ]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise RuntimeError(
            f"{p0_contract_id} must register exactly one verification selector"
        )
    return matches[0]


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


def _build_receipt(
    receipt_module: ModuleType,
    run: dict[str, Any],
    results: list[dict[str, Any]],
    mirror: dict[str, Any],
    bindings: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    kwargs = {"run_dir": run_dir} if getattr(receipt_module, "SUPPORTS_RUN_DIR", False) else {}
    return receipt_module.build_receipt(
        ROOT,
        run,
        results,
        mirror,
        bindings,
        policies,
        **kwargs,
    )


def _script_module(name: str, filename: str) -> ModuleType:
    path = HARNESS / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _live_evidence_policy_module() -> ModuleType:
    name = "qi_live_evidence_policy"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    return _script_module(name, "live_evidence_policy.py")


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
    no_silent_success_selector = _registered_contract_selector(
        NO_SILENT_SUCCESS_CONTRACT_ID
    )
    # P0-ACC-007 remains a failure-mode proof, but a full live gate must reuse
    # it inside the already-open run instead of spawning a nested task run.
    if selector == no_silent_success_selector and mode == "live":
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
    if selector == no_silent_success_selector:
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


def _write_fixture_network_tripwires(run_dir: Path) -> None:
    tripwire_dir = run_dir / Path(FIXTURE_PYTHON_TRIPWIRE).parent
    tripwire_dir.mkdir(exist_ok=False)
    (run_dir / FIXTURE_PYTHON_TRIPWIRE).write_text(
        "import socket\n"
        "_socket = socket.socket\n"
        "def _blocked(*_args, **_kwargs):\n"
        "    raise RuntimeError('fixture network access is blocked')\n"
        "class _BlockedSocket(_socket):\n"
        "    connect = _blocked\n"
        "    connect_ex = _blocked\n"
        "socket.socket = _BlockedSocket\n"
        "socket.create_connection = _blocked\n",
        encoding="utf-8",
    )
    (run_dir / FIXTURE_NODE_TRIPWIRE).write_text(
        "const blocked = () => { throw new Error('fixture network access is blocked'); };\n"
        "for (const name of ['net', 'tls']) {\n"
        "  const module = require(name); module.connect = blocked; module.createConnection = blocked;\n"
        "}\n"
        "for (const name of ['http', 'https']) {\n"
        "  const module = require(name); module.request = blocked; module.get = blocked;\n"
        "}\n"
        "globalThis.fetch = blocked;\n"
        "try {\n"
        "  const undici = require('undici'); undici.fetch = blocked; undici.request = blocked;\n"
        "} catch (_error) {}\n",
        encoding="utf-8",
    )


def _fixture_selector_environment(run_dir: Path) -> dict[str, str]:
    environment = dict(os.environ)
    backend_root = str(ROOT / "backend")
    python_paths = [
        path
        for path in environment.get("PYTHONPATH", "").split(os.pathsep)
        if path and path != backend_root
    ]
    environment["PYTHONPATH"] = os.pathsep.join(
        [str((run_dir / FIXTURE_PYTHON_TRIPWIRE).parent), backend_root, *python_paths]
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in LIVE_CREDENTIAL_KEYS:
        environment[key] = ""
    for key in FIXTURE_PROVIDER_MODE_KEYS:
        environment[key] = "fixture"
    for key in FIXTURE_PROVIDER_NETWORK_KEYS:
        environment[key] = "disabled"
    environment["QI_P0_FIXTURE_OFFLINE_PROOF"] = FIXTURE_OFFLINE_PROOF
    existing_node_options = environment.get("NODE_OPTIONS", "").strip()
    environment["NODE_OPTIONS"] = " ".join(
        part
        for part in (
            existing_node_options,
            "--require",
            str(run_dir / FIXTURE_NODE_TRIPWIRE),
        )
        if part
    )
    return environment


def _command_outcome(
    selector: str,
    mode: str,
    run_dir: Path | None,
) -> tuple[int | None, str, str, bool]:
    try:
        argv = shlex.split(selector)
    except ValueError as exc:
        return None, "blocked", f"invalid selector argv: {exc}", False
    if not argv or any(token in SHELL_OPERATORS for token in argv):
        return None, "blocked", "selector is not one exact argv command", False
    try:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            env=(
                _fixture_selector_environment(run_dir)
                if mode == "fixture" and run_dir is not None
                else _selector_environment()
            ),
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError, RuntimeError) as exc:
        return None, "blocked", f"selector could not start: {exc}", False
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
    return result.returncode, state, output, True


def _execute_selector(selector: str, mode: str) -> dict[str, Any]:
    started_at = _iso_now()
    fixture_offline_enforced = False
    subprocess_started = False
    pre_execution_blocked = False
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
            fixture_offline_enforced = (
                mode == "fixture"
                and exit_code is None
                and state == "blocked"
                and not artifact_refs
                and output == "phase mode mismatch: runner=fixture selector=live"
            )
            pre_execution_blocked = fixture_offline_enforced
    else:
        exit_code, state, output, subprocess_started = _command_outcome(
            selector,
            mode,
            _ACTIVE_RUN_DIR,
        )
        artifact_refs = []
        pre_execution_blocked = not subprocess_started
        fixture_offline_enforced = (
            mode == "fixture"
            and _ACTIVE_RUN_DIR is not None
            and (subprocess_started or pre_execution_blocked)
        )
    return {
        "exit_code": exit_code,
        "result_state": state,
        "started_at": started_at,
        "completed_at": _iso_now(),
        "output": output,
        "artifact_refs": artifact_refs,
        "subprocess_started": subprocess_started,
        "pre_execution_blocked": pre_execution_blocked,
        "fixture_offline_enforced": fixture_offline_enforced,
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


def _fixture_proof_complete(proof: Mapping[str, Any], selectors: list[str]) -> bool:
    attempted = proof["attempted_selectors"]
    executed = proof["executed_selectors"]
    preblocked = proof["pre_execution_blocked_selectors"]
    offline = proof["offline_enforced_selectors"]
    if not all(isinstance(values, list) for values in (attempted, executed, preblocked, offline)):
        return False
    if not all(
        isinstance(selector, str)
        for values in (attempted, executed, preblocked, offline)
        for selector in values
    ):
        return False
    if attempted != selectors or offline != selectors:
        return False
    executed_set = set(executed)
    preblocked_set = set(preblocked)
    if (
        len(executed) != len(executed_set)
        or len(preblocked) != len(preblocked_set)
        or executed_set & preblocked_set
        or executed_set | preblocked_set != set(selectors)
        or len(executed) + len(preblocked) != len(selectors)
    ):
        return False
    return (
        executed == [selector for selector in selectors if selector in executed_set]
        and preblocked == [selector for selector in selectors if selector in preblocked_set]
    )


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
    artifact_names = set(artifacts)
    if artifact_names and artifact_names not in (
        {CURRENT_FOUR_ARTIFACT},
        set(SYMBOL_EVAL_ARTIFACTS),
        {CURRENT_FOUR_ARTIFACT, *SYMBOL_EVAL_ARTIFACTS},
        {ROUTING_COMPARISON_ARTIFACT},
    ):
        raise ValueError(
            "input artifacts must be the exact current-four-manifest artifact or exact "
            "visual-symbol eval/verdict pair, or routing comparison artifact"
        )
    if any(not isinstance(content, bytes) for content in artifacts.values()):
        raise TypeError("input artifact content must be bytes")
    return {
        name: artifacts[name]
        for name in (
            CURRENT_FOUR_ARTIFACT,
            *SYMBOL_EVAL_ARTIFACTS,
            ROUTING_COMPARISON_ARTIFACT,
        )
        if name in artifacts
    }


def _routing_comparison_fixture_artifacts() -> dict[str, bytes]:
    artifact = ROUTING_COMPARISON_FIXTURE.read_bytes()
    try:
        document = json.loads(artifact)
    except json.JSONDecodeError as exc:
        raise ValueError("routing comparison fixture is invalid JSON") from exc
    schema = _load_json(HARNESS / "schemas/visual-symbol-eval.schema.json")
    Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/routingComparisonEvidence",
        },
        format_checker=FormatChecker(),
    ).validate(document)
    _script_module(
        "qi_routing_comparison_fixture_validator",
        "symbol_eval.py",
    ).validate_routing_comparison_evidence(document)
    return {ROUTING_COMPARISON_ARTIFACT: artifact}


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


def _literal_symbol_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id) or run_id in {
        "latest",
        "latest-successful",
    }:
        raise ValueError("symbol eval requires one literal run ID")
    return run_id


def _symbol_registration_layout(run_dir: Path, *, sealed: bool) -> None:
    root_names = {"run.json", "logs", "reports", "artifacts"}
    if (
        run_dir.is_symlink()
        or not run_dir.is_dir()
        or {path.name for path in run_dir.iterdir()} != root_names
    ):
        raise ValueError("symbol registration run members are not exact")
    if any(
        path.exists() or path.is_symlink()
        for path in (
            run_dir / "receipt.json",
            run_dir / "contract-results.json",
        )
    ):
        raise ValueError(
            "symbol registration-only run cannot contain receipt or results"
        )
    expected_children = (
        {
            "logs": set(),
            "reports": {Path(SYMBOL_REGISTRATION_REPORT).name},
            "artifacts": {
                Path(name).name for name in SYMBOL_EVAL_ARTIFACTS
            },
        }
        if sealed
        else {"logs": set(), "reports": set(), "artifacts": set()}
    )
    for directory, expected in expected_children.items():
        path = run_dir / directory
        if (
            path.is_symlink()
            or not path.is_dir()
            or {child.name for child in path.iterdir()} != expected
        ):
            raise ValueError("symbol registration run members are not exact")
    members = (run_dir, *tuple(run_dir.rglob("*")))
    if any(path.is_symlink() for path in members):
        raise ValueError("symbol registration run must not contain symlinks")
    if any(_is_sealed(path) != sealed for path in members):
        state = "sealed" if sealed else "open and writable"
        raise ValueError(f"symbol registration run must be {state}")


def _validate_symbol_run_identity(
    run: Mapping[str, Any],
    *,
    run_id: str,
    completed: bool,
) -> None:
    if (
        run.get("run_id") != run_id
        or run.get("mode") != "live"
        or run.get("scope") != "task"
        or run.get("task_id") != "D7-T2"
        or run.get("selected_contract_ids") != []
        or bool(run.get("completed_at")) is not completed
    ):
        state = "completed" if completed else "open"
        raise ValueError(
            f"symbol eval source is not a {state} D7-T2 registration-only run"
        )


def register_live_input_artifacts(
    *,
    task_id: str,
    artifacts: Mapping[str, bytes],
    run_id: str | None = None,
) -> str:
    if task_id != "D7-T2":
        raise ValueError("symbol registration is limited to literal task D7-T2")
    stage = _script_module(
        "qi_symbol_eval_artifact_contract",
        "stage-symbol-eval.py",
    )
    validated = stage.validate_artifacts(artifacts)
    receipt = _receipt_module()
    receipt.check_contract_authority(ROOT)
    mirror = _load_json(MIRROR_PATH)
    bindings = _load_json(BINDINGS_PATH)
    policies = receipt.load_policies(ROOT)
    _validate_live_policy(policies)
    receipt.validate_schema(mirror, "p0-contracts.schema.json", ROOT)
    receipt.validate_schema(
        bindings,
        "global-contract-bindings.schema.json",
        ROOT,
    )
    identity_fields = {
        "code_identity": receipt.code_identity(ROOT),
        "config_identity": receipt.config_identity(
            "live", "task", "D7-T2", ROOT
        ),
        "contract_definition_hash": mirror["contract_definition_hash"],
        "status_projection_hash_at_start": mirror["status_projection_hash"],
        "policy_versions": receipt.policy_versions(policies),
    }

    if run_id is None:
        literal_run_id = _new_run_id()
        run_dir = RUNS / literal_run_id
        run: dict[str, Any] = {
            "schema_version": "run/1",
            "run_id": literal_run_id,
            "mode": "live",
            "scope": "task",
            "task_id": "D7-T2",
            **identity_fields,
            "git_revision_at_start": _git_revision(),
            "input_identity": receipt.input_identity(
                "live", "task", "D7-T2", validated, root=ROOT
            ),
            "selected_contract_ids": [],
            "started_at": _iso_now(),
            "completed_at": None,
        }
        receipt.validate_schema(run, "run.schema.json", ROOT)
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in ("logs", "reports", "artifacts"):
            (run_dir / name).mkdir()
    else:
        literal_run_id = _literal_symbol_run_id(run_id)
        run_dir = RUNS / literal_run_id
        _symbol_registration_layout(run_dir, sealed=False)
        run = _load_json(run_dir / "run.json")
        receipt.validate_schema(run, "run.schema.json", ROOT)
        _validate_symbol_run_identity(
            run,
            run_id=literal_run_id,
            completed=False,
        )
        if any(run.get(name) != value for name, value in identity_fields.items()):
            raise ValueError("open symbol registration run identity is stale")
        if run.get("input_identity") != receipt.input_identity(
            "live", "task", "D7-T2", root=ROOT
        ):
            raise ValueError("open symbol registration input identity is not empty")
        run["input_identity"] = receipt.input_identity(
            "live", "task", "D7-T2", validated, root=ROOT
        )
        receipt.validate_schema(run, "run.schema.json", ROOT)

    _write_json(run_dir / "run.json", run)
    for name, content in validated.items():
        (run_dir / name).write_bytes(content)
    run["completed_at"] = _iso_now()
    receipt.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)
    report = {
        "schema_version": "symbol-eval-registration/1",
        "run_id": literal_run_id,
        "selector": SYMBOL_REGISTRATION_SELECTOR,
        "artifact_refs": list(SYMBOL_EVAL_ARTIFACTS),
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
    }
    _write_json(run_dir / SYMBOL_REGISTRATION_REPORT, report)
    _seal_run(run_dir)
    return literal_run_id


def load_symbol_eval_artifacts(run_id: str) -> dict[str, bytes]:
    literal_run_id = _literal_symbol_run_id(run_id)
    run_dir = RUNS / literal_run_id
    _symbol_registration_layout(run_dir, sealed=True)
    run = _load_json(run_dir / "run.json")
    receipt = _receipt_module()
    receipt.validate_schema(run, "run.schema.json", ROOT)
    _validate_symbol_run_identity(
        run,
        run_id=literal_run_id,
        completed=True,
    )
    stage = _script_module(
        "qi_symbol_eval_sealed_artifact_contract",
        "stage-symbol-eval.py",
    )
    artifacts = stage.validate_artifacts(
        {
            name: (run_dir / name).read_bytes()
            for name in SYMBOL_EVAL_ARTIFACTS
        }
    )
    if run.get("input_identity") != receipt.input_identity(
        "live", "task", "D7-T2", artifacts, root=ROOT
    ):
        raise ValueError(
            "symbol eval input identity does not match exact artifact bytes"
        )
    expected_report = {
        "schema_version": "symbol-eval-registration/1",
        "run_id": literal_run_id,
        "selector": SYMBOL_REGISTRATION_SELECTOR,
        "artifact_refs": list(SYMBOL_EVAL_ARTIFACTS),
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
    }
    if _load_json(run_dir / SYMBOL_REGISTRATION_REPORT) != expected_report:
        raise ValueError("symbol registration phase record is inconsistent")
    return artifacts


def _load_full_live_input_artifacts(
    *,
    current_four_run: str,
    symbol_eval_run: str,
) -> dict[str, bytes]:
    artifacts = {
        **_load_current_four_artifact(current_four_run),
        **load_symbol_eval_artifacts(symbol_eval_run),
    }
    expected = {
        CURRENT_FOUR_ARTIFACT,
        *SYMBOL_EVAL_ARTIFACTS,
    }
    if set(artifacts) != expected:
        raise ValueError("full live input artifacts are incomplete")
    return _validate_input_artifacts(artifacts)


def _git_head_bytes(relative_path: str) -> bytes:
    if (
        not relative_path.startswith(".agent/harness/runs/")
        or Path(relative_path).is_absolute()
        or ".." in Path(relative_path).parts
    ):
        raise ValueError("approved symbol input path is invalid")
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise ValueError("approved symbol input bytes are unavailable from Git HEAD")
    return result.stdout


def _git_head_symbol_artifact_sets() -> list[dict[str, bytes]]:
    result = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            ".agent/harness/runs",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("approved symbol input inventory is unavailable from Git HEAD")
    paths = set(result.stdout.splitlines())
    manifests = sorted(
        path for path in paths if path.endswith(f"/{SYMBOL_EVAL_ARTIFACT}")
    )
    candidates: list[dict[str, bytes]] = []
    for manifest_path in manifests:
        run_prefix = manifest_path[: -len(SYMBOL_EVAL_ARTIFACT)]
        verdict_path = f"{run_prefix}{SYMBOL_VERDICT_ARTIFACT}"
        if verdict_path not in paths:
            continue
        candidates.append(
            {
                SYMBOL_EVAL_ARTIFACT: _git_head_bytes(manifest_path),
                SYMBOL_VERDICT_ARTIFACT: _git_head_bytes(verdict_path),
            }
        )
    return candidates


def _approved_symbol_input_artifacts(source_sha256: str) -> dict[str, bytes]:
    stage = _script_module(
        "qi_approved_symbol_input_contract",
        "stage-symbol-eval.py",
    )
    unique: dict[str, dict[str, bytes]] = {}
    for candidate in _git_head_symbol_artifact_sets():
        try:
            validated = stage.validate_artifacts(candidate)
            manifest = json.loads(validated[SYMBOL_EVAL_ARTIFACT])
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if manifest.get("source_sha256") != source_sha256:
            continue
        identity = hashlib.sha256(
            b"\0".join(validated[name] for name in SYMBOL_EVAL_ARTIFACTS)
        ).hexdigest()
        unique[identity] = validated
    if len(unique) != 1:
        raise ValueError(
            "Git HEAD must contain one unique approved symbol annotation input set"
        )
    return next(iter(unique.values()))


def _current_live_input_artifacts(source_root: str) -> dict[str, bytes]:
    stage = _script_module(
        "qi_current_live_input_activation",
        "stage-current-four.py",
    )
    sources = stage._resolve_sources(None, source_root)
    stage._verify_sources(sources)
    manifest_bytes = stage._manifest_bytes(stage.FROZEN_DOCUMENTS)
    manifest = json.loads(manifest_bytes)
    source_sha256 = manifest.get("first_checkpoint", {}).get("sha256")
    if not isinstance(source_sha256, str):
        raise ValueError("current-four first checkpoint identity is unavailable")
    return {
        CURRENT_FOUR_ARTIFACT: manifest_bytes,
        **_approved_symbol_input_artifacts(source_sha256),
    }


def activate_full_live_inputs(
    *,
    source_root: str | None,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    current_environment = os.environ if environment is None else environment
    _require_live_environment(current_environment)
    _current_live_identity(current_environment)
    if source_root is None or not source_root.strip():
        raise ValueError(f"{LIVE_SOURCE_ROOT_ENV} is required")
    artifacts = _current_live_input_artifacts(source_root)
    preflight_full_p0_live(
        input_set="current-four",
        source_root=source_root,
        current_four_run=None,
        symbol_eval_run=None,
        input_artifacts=artifacts,
        environment=current_environment,
    )
    current_four_run, verdict = run_task(
        "live",
        "task",
        "D2-T1",
        input_artifacts={CURRENT_FOUR_ARTIFACT: artifacts[CURRENT_FOUR_ARTIFACT]},
    )
    if verdict != "passed":
        raise RuntimeError("fresh current-four registration did not pass")
    symbol_eval_run = register_live_input_artifacts(
        task_id="D7-T2",
        artifacts={name: artifacts[name] for name in SYMBOL_EVAL_ARTIFACTS},
    )
    return current_four_run, symbol_eval_run


def _attach_full_live_input_artifacts(
    run_dir: Path,
    artifacts: Mapping[str, bytes],
) -> None:
    validated = _validate_input_artifacts(artifacts)
    expected = {
        CURRENT_FOUR_ARTIFACT,
        *SYMBOL_EVAL_ARTIFACTS,
    }
    if set(validated) != expected:
        raise ValueError("full live input artifacts are incomplete")
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("full live run directory is unavailable")
    for name, content in validated.items():
        path = run_dir / name
        if (
            path.parent.is_symlink()
            or not path.parent.is_dir()
            or path.exists()
            or path.is_symlink()
        ):
            raise ValueError("full live input artifact destination is invalid")
        path.write_bytes(content)


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
    api_base = current.get(LIVE_API_BASE_ENV, "").rstrip("/")
    frontend_base = current.get(LIVE_FRONTEND_BASE_ENV, "").rstrip("/")
    compose_project = current.get(LIVE_COMPOSE_PROJECT_ENV, "").strip()
    if (
        api_base != EXPECTED_LIVE_API_BASE
        or frontend_base != EXPECTED_LIVE_FRONTEND_BASE
        or compose_project != EXPECTED_LIVE_COMPOSE_PROJECT
    ):
        raise ValueError(
            "live identity must target the verified isolated Compose project"
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
        "max_vision_calls_per_page": 16,
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


def _require_compose_runtime_identity() -> None:
    expected_hashes: dict[str, str] = {}
    for relative in LIVE_API_GDT_RUNTIME_PATHS:
        path = ROOT / "backend" / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("current worktree GDT runtime identity is incomplete")
        expected_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = {
        **EXPECTED_RECOGNITION_IDENTITY,
        "hashes": expected_hashes,
    }
    program = (
        "import hashlib,json,sys; from pathlib import Path; "
        "from app.candidates.symbol_routing import symbol_routing_identity; "
        "from app.config import get_settings; "
        "paths=json.loads(sys.argv[1]); hashes={}; "
        "exec(\"for relative in paths:\\n"
        " path=Path('/app')/relative\\n"
        " hashes[relative]=(hashlib.sha256(path.read_bytes()).hexdigest() "
        "if path.is_file() and not path.is_symlink() else None)\"); "
        "settings=get_settings(); "
        "mode,router=symbol_routing_identity(settings.symbol_recognition_mode); "
        "result={'mode':mode,'router':router,'model':settings.qwen_model.strip(),"
        "'hashes':hashes}; "
        "print(json.dumps(result,sort_keys=True))"
    )
    for service in ("api", "worker"):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                service,
                "python",
                "-c",
                program,
                json.dumps(list(LIVE_API_GDT_RUNTIME_PATHS)),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            observed = json.loads(result.stdout)
        except json.JSONDecodeError:
            observed = None
        if result.returncode != 0 or observed != expected:
            raise ValueError(
                "Compose runtime identity does not match GDT-10 live contract"
            )
    for service, container_port, expected_binding in (
        ("api", "8000", "127.0.0.1:18000"),
        ("frontend", "4173", "127.0.0.1:14173"),
    ):
        binding = subprocess.run(
            ["docker", "compose", "port", service, container_port],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if binding.returncode != 0 or binding.stdout.strip() != expected_binding:
            raise ValueError(
                "Compose runtime identity does not match GDT-10 live contract"
            )
    database = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "--username",
            "qi",
            "--dbname",
            "qi",
            "--tuples-only",
            "--no-align",
            "--command",
            "SELECT version_num FROM alembic_version",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if database.returncode != 0 or database.stdout.strip() != "0013":
        raise ValueError(
            "Compose runtime identity does not match GDT-10 live contract"
        )


def preflight_full_p0_live(
    *,
    input_set: str,
    source_root: str | None,
    current_four_run: str | None = None,
    symbol_eval_run: str | None = None,
    input_artifacts: Mapping[str, bytes] | None = None,
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
    _require_compose_runtime_identity()

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
    if input_artifacts is None:
        if current_four_run is None or symbol_eval_run is None:
            raise ValueError(
                "full-p0 live preflight requires both literal registration runs"
            )
        artifacts = _load_full_live_input_artifacts(
            current_four_run=current_four_run,
            symbol_eval_run=symbol_eval_run,
        )
    else:
        if current_four_run is not None or symbol_eval_run is not None:
            raise ValueError(
                "bound live input bytes cannot be mixed with registration run IDs"
            )
        artifacts = _validate_input_artifacts(input_artifacts)
        if set(artifacts) != {
            CURRENT_FOUR_ARTIFACT,
            *SYMBOL_EVAL_ARTIFACTS,
        }:
            raise ValueError("bound live input artifacts are incomplete")
    manifest_bytes = artifacts[CURRENT_FOUR_ARTIFACT]
    expected_manifest_bytes = stage_module._manifest_bytes(
        stage_module.FROZEN_DOCUMENTS
    )
    if manifest_bytes != expected_manifest_bytes:
        raise ValueError(
            "sealed current-four registration differs from current source identity"
        )
    current_four_manifest = json.loads(manifest_bytes)
    symbol_manifest = json.loads(artifacts[SYMBOL_EVAL_ARTIFACT])
    if (
        symbol_manifest.get("source_sha256")
        != current_four_manifest.get("first_checkpoint", {}).get("sha256")
    ):
        raise ValueError(
            "sealed symbol manifest does not bind the first current-four source"
        )

    _validate_export_assets()
    return LivePreflight(
        source_root=Path(source_root),
        source_paths=tuple(
            sources[document.basename]
            for document in stage_module.FROZEN_DOCUMENTS
        ),
        manifest_bytes=manifest_bytes,
        input_artifacts=artifacts,
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
    _attach_full_live_input_artifacts(run_dir, preflight.input_artifacts)
    live = {
        "schema_version": LIVE_EVIDENCE_SCHEMA_VERSION,
        "run_id": run_id,
        "input_set": "current-four",
        "phases": list(LIVE_PHASES),
        "child_run_ids": [],
        "symbol_recognition": None,
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
    base = os.environ.get(LIVE_API_BASE_ENV, "").rstrip("/")
    if base != EXPECTED_LIVE_API_BASE:
        raise ValueError("live API target is not the verified isolated runtime")
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

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.candidates.symbol_routing import symbol_routing_identity
from app.candidates.models import AutomaticResult
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


def create_live_project(settings):
    recognition_mode, recognition_router_version = symbol_routing_identity(
        settings.symbol_recognition_mode
    )
    return Project(
        id=uuid.uuid4(),
        state=ProjectState.PROCESSING,
        recognition_mode=recognition_mode,
        recognition_router_version=recognition_router_version,
    )


def project_candidate_evidence(candidates, pages, coverage_entries):
    if not isinstance(candidates, list):
        raise RuntimeError("automatic candidate inventory is invalid")
    source_index = {}
    for page in pages:
        if not isinstance(page, dict):
            raise RuntimeError("stored page inventory is invalid")
        observations = page.get("observations")
        visual_observations = page.get("visual_observations", [])
        if not isinstance(observations, list) or not isinstance(
            visual_observations,
            list,
        ):
            raise RuntimeError("stored source inventory is invalid")
        for source in [*observations, *visual_observations]:
            if not isinstance(source, dict):
                raise RuntimeError("stored source inventory is invalid")
            source_id = source.get("observation_id")
            source_type = source.get("source_type")
            observation_level = source.get("observation_level")
            coordinates = source.get("bbox_pdf")
            if (
                not isinstance(source_id, str)
                or not source_id
                or source_id in source_index
                or not isinstance(source_type, str)
                or not source_type
                or not isinstance(observation_level, str)
                or not observation_level
                or not isinstance(coordinates, list)
                or len(coordinates) != 4
            ):
                raise RuntimeError("stored source inventory is invalid")
            source_index[source_id] = {
                "source_location_id": source_id,
                "source_type": source_type,
                "observation_level": observation_level,
                "coordinates": coordinates,
            }

    coverage_index = {}
    for entry in coverage_entries:
        if not isinstance(entry, dict):
            raise RuntimeError("coverage evidence is invalid")
        source_id = entry.get("source_location_id")
        disposition = entry.get("disposition")
        candidate_id = entry.get("candidate_id")
        if (
            not isinstance(source_id, str)
            or not source_id
            or source_id not in source_index
            or source_id in coverage_index
            or disposition
            not in {
                "candidate",
                "reference_context",
                "non_inspection",
                "ambiguous",
            }
            or (
                candidate_id is not None
                and (not isinstance(candidate_id, str) or not candidate_id)
            )
        ):
            raise RuntimeError("coverage evidence is invalid")
        coverage_index[source_id] = {
            "disposition": disposition,
            "candidate_id": candidate_id,
        }

    candidate_ids = []
    candidate_sources_by_id = {}
    source_location_ids = set()
    candidate_records = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise RuntimeError("automatic candidate identity is incomplete")
        candidate_id = candidate.get("candidate_id")
        sources = candidate.get("source_location_ids")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(sources, list)
            or not sources
            or candidate_id in candidate_sources_by_id
            or any(
                not isinstance(source_id, str)
                or not source_id
                or source_id not in source_index
                for source_id in sources
            )
            or len(set(sources)) != len(sources)
        ):
            raise RuntimeError("automatic candidate source relation is incomplete")
        payload = candidate.get("payload")
        coordinates = (
            payload.get("coordinates")
            if isinstance(payload, dict)
            else None
        )
        ordered_source_ids = sorted(sources)
        candidate_ids.append(candidate_id)
        candidate_sources_by_id[candidate_id] = set(ordered_source_ids)
        source_location_ids.update(ordered_source_ids)
        candidate_records.append({
            "candidate_id": candidate_id,
            "coordinates": coordinates,
            "source_location_ids": ordered_source_ids,
            "source_evidence": [
                {
                    **source_index[source_id],
                    "coverage": coverage_index.get(source_id),
                }
                for source_id in ordered_source_ids
            ],
        })
    for source_id, coverage in coverage_index.items():
        if coverage["disposition"] != "candidate":
            continue
        candidate_id = coverage["candidate_id"]
        if (
            candidate_id not in candidate_sources_by_id
            or source_id not in candidate_sources_by_id[candidate_id]
        ):
            raise RuntimeError("candidate coverage relation is invalid")
    return {
        "candidate_ids": sorted(candidate_ids),
        "source_location_ids": sorted(source_location_ids),
        "candidate_records": sorted(
            candidate_records,
            key=lambda entry: entry["candidate_id"],
        ),
    }


payload = sys.stdin.buffer.read()
expected = os.environ["QI_P0_SOURCE_SHA256"]
if hashlib.sha256(payload).hexdigest() != expected:
    raise RuntimeError("source identity changed before application upload")
settings = get_settings()
storage = LocalFileStorage(settings.storage_root)
seed_session = SessionLocal()
try:
    project = create_live_project(settings)
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
    seed_session.add_all([project, source])
    seed_session.commit()
    project_id = project.id
    source_ref = source.resource_ref
    source_sha256 = source.sha256
finally:
    seed_session.close()

result_ref = inventory_project.run(
    str(project_id),
    source_ref,
    "p0-live:" + os.environ["QI_P0_RUN_ID"] + ":" + os.environ["QI_P0_ORDER"],
)
session = SessionLocal()
try:
    raw = session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project_id)
    )
    working = session.scalar(
        select(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project_id
        )
    )
    if raw is None:
        raise RuntimeError("automatic result was not created")
    if working is None:
        raise RuntimeError("review working copy was not created")
    if result_ref != f"automatic-result://{raw.id}":
        raise RuntimeError("canonical processing result identity changed")
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

    coverage_entries = raw.coverage.get("entries")
    if not isinstance(coverage_entries, list):
        raise RuntimeError("coverage evidence is unavailable")
    candidate_evidence = project_candidate_evidence(
        raw.candidates,
        pages,
        coverage_entries,
    )
    print(json.dumps({
        "project_id": str(project_id),
        "working_copy_id": str(working.id),
        "working_version": working.version,
        "process": {
            "source_sha256": source_sha256,
            "actual_page_count": len(pages),
            "actual_physical_pages": sorted({physical_page(page) for page in pages}),
            "automatic_result_id": str(raw.id),
        },
        "candidates": {
            "candidate_count": len(raw.candidates),
            **candidate_evidence,
            "coverage_checked": raw.coverage.get("coverage_checked") is True,
            "coverage_blocking_count": int(raw.coverage.get("blocking_count", -1)),
            "coverage_disposition_count": sum(
                isinstance(entry.get("disposition"), str)
                and bool(entry["disposition"].strip())
                for entry in coverage_entries
                if isinstance(entry, dict)
            ),
        },
    }, sort_keys=True))
finally:
    session.close()
"""


_SYMBOL_RESULT_PROGRAM = r"""
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import select

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.candidates.symbol_review import (
    SCHEMA_PATH,
    build_visual_failure_envelope,
    parse_visual_request_evidence,
)
from app.config import get_settings
from app.db import SessionLocal
from app.providers.call_records import serialize_call_record
from app.storage.local import LocalFileStorage


def visual_attempt_count(audit, retry_evidence):
    if (
        not isinstance(audit, dict)
        or not isinstance(audit.get("request_id"), str)
        or not audit["request_id"]
        or not isinstance(audit.get("retry_count"), int)
        or isinstance(audit["retry_count"], bool)
        or audit["retry_count"] not in (0, 1)
        or not isinstance(retry_evidence, list)
        or len(retry_evidence) != audit["retry_count"]
    ):
        raise RuntimeError("visual Provider retry evidence is invalid")
    for retry in retry_evidence:
        if (
            not isinstance(retry, dict)
            or set(retry)
            != {"request_id", "retry_count", "failure_stage"}
            or not isinstance(retry["request_id"], str)
            or not retry["request_id"]
            or retry["request_id"] == audit["request_id"]
            or retry["retry_count"] != 0
            or retry["failure_stage"]
            != "tool_arguments_schema_invalid"
        ):
            raise RuntimeError("visual Provider retry evidence is invalid")
    return 1 + audit["retry_count"]


def provider_call_identity(identity, *, request_id, schema_sha256):
    if not isinstance(identity, dict):
        raise RuntimeError("visual Provider sealed identity is invalid")
    source_sha256 = identity.get("source_sha256")
    visual_ids = identity.get("visual_observation_ids")
    crop_bbox_pdf = identity.get("crop_bbox_pdf")
    crop_sha256 = identity.get("crop_sha256")
    model = identity.get("model")
    prompt_version = identity.get("prompt_version")
    schema_version = identity.get("schema_version")
    hashes = (source_sha256, crop_sha256, schema_sha256)
    if (
        any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in hashes
        )
        or not isinstance(visual_ids, list)
        or not visual_ids
        or any(not isinstance(value, str) or not value for value in visual_ids)
        or not isinstance(crop_bbox_pdf, list)
        or len(crop_bbox_pdf) != 4
        or any(not isinstance(value, (int, float)) for value in crop_bbox_pdf)
        or not isinstance(model, str)
        or not model
        or not isinstance(prompt_version, str)
        or not prompt_version
        or not isinstance(schema_version, str)
        or not schema_version
        or not isinstance(request_id, str)
        or not request_id
    ):
        raise RuntimeError("visual Provider sealed identity is invalid")
    prompt_identity = json.dumps(
        {
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "visual_observation_ids": visual_ids,
            "crop_bbox_pdf": crop_bbox_pdf,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "source_sha256": source_sha256,
        "visual_observation_ids": visual_ids,
        "crop_bbox_pdf": crop_bbox_pdf,
        "crop_sha256": crop_sha256,
        "model": model,
        "model_identity_sha256": hashlib.sha256(model.encode("utf-8")).hexdigest(),
        "prompt_version": prompt_version,
        "prompt_identity_sha256": hashlib.sha256(prompt_identity).hexdigest(),
        "schema_version": schema_version,
        "schema_sha256": schema_sha256,
        "request_id_sha256": hashlib.sha256(request_id.encode("utf-8")).hexdigest(),
    }


def paired_cache(project_root, storage, project_id, relative):
    def exact_json_files(evidence_relative):
        directory = project_root / evidence_relative
        if not directory.exists():
            return []
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("Provider evidence directory is invalid")
        files = sorted(directory.glob("*.json"))
        if any(path.is_symlink() or not path.is_file() for path in files):
            raise RuntimeError("Provider evidence file is invalid")
        return files

    cache_files = exact_json_files(f"provider-cache/{relative}")
    audit_files = exact_json_files(f"provider-calls/{relative}")
    cache_names = {path.name for path in cache_files}
    if cache_names != {path.name for path in audit_files}:
        raise RuntimeError("Provider cache/call evidence differs")

    retry_by_cache = {}
    if relative == "qwen-symbol":
        retry_directories = {
            "audit": "provider-calls/qwen-symbol-retries",
            "request": "provider-requests/qwen-symbol-retries",
            "response": "provider-responses/qwen-symbol-retries",
        }
        retry_files = {
            kind: exact_json_files(directory)
            for kind, directory in retry_directories.items()
        }
        retry_names = {
            kind: {path.name for path in paths}
            for kind, paths in retry_files.items()
        }
        if (
            retry_names["audit"] != retry_names["request"]
            or retry_names["audit"] != retry_names["response"]
        ):
            raise RuntimeError("visual Provider retry evidence is invalid")
        for filename in retry_names["audit"]:
            suffix = ".attempt-1.json"
            digest = filename.removesuffix(suffix)
            if (
                not filename.endswith(suffix)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise RuntimeError("visual Provider retry evidence is invalid")
            cache_name = f"{digest}.json"
            if cache_name not in cache_names or cache_name in retry_by_cache:
                raise RuntimeError("visual Provider retry evidence is invalid")
            retry_by_cache[cache_name] = {
                kind: project_root / directory / filename
                for kind, directory in retry_directories.items()
            }

    pairs = []
    for cache_path in cache_files:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        audit_path = project_root / "provider-calls" / relative / cache_path.name
        audit_content = audit_path.read_bytes()
        audit = json.loads(audit_content)
        if (
            not isinstance(cache, dict)
            or not isinstance(audit, dict)
            or cache.get("request_id") != audit.get("request_id")
            or audit.get("logical_task_reused") is not False
            or serialize_call_record(audit) != audit_content
        ):
            raise RuntimeError("Provider cache/call identity is invalid")

        retry_evidence = []
        retry_paths = retry_by_cache.pop(cache_path.name, None)
        if retry_paths is not None:
            retry_contents = {
                kind: path.read_bytes()
                for kind, path in retry_paths.items()
            }
            retry_audit = json.loads(retry_contents["audit"])
            retry_request = json.loads(retry_contents["request"])
            retry_response = json.loads(retry_contents["response"])
            identity = cache.get("identity")
            crop_sha256 = (
                identity.get("crop_sha256")
                if isinstance(identity, dict)
                else None
            )
            filename = retry_paths["audit"].name
            project_segment = str(project_id)
            expected_request_ref = (
                f"asset://projects/{project_segment}/provider-requests/"
                f"qwen-symbol-retries/{filename}"
            )
            expected_response_ref = (
                f"asset://projects/{project_segment}/provider-responses/"
                f"qwen-symbol-retries/{filename}"
            )
            expected_crop_ref = (
                f"asset://projects/{project_segment}/provider-inputs/"
                f"qwen-symbol/{crop_sha256}.png"
            )
            expected_retry_audit = {
                "provider": "qwen-vl",
                "model": identity.get("model") if isinstance(identity, dict) else None,
                "prompt_version": (
                    identity.get("prompt_version")
                    if isinstance(identity, dict)
                    else None
                ),
                "schema_version": (
                    identity.get("schema_version")
                    if isinstance(identity, dict)
                    else None
                ),
                "retry_count": 0,
                "input_image_count": 1,
                "estimated_cost": None,
                "logical_task_reused": False,
                "request_ref": expected_request_ref,
                "response_ref": expected_response_ref,
            }
            if (
                not isinstance(retry_audit, dict)
                or not isinstance(retry_request, dict)
                or not isinstance(retry_response, dict)
                or not isinstance(crop_sha256, str)
                or len(crop_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in crop_sha256
                )
                or serialize_call_record(retry_audit)
                != retry_contents["audit"]
                or any(
                    retry_audit.get(key) != value
                    for key, value in expected_retry_audit.items()
                )
            ):
                raise RuntimeError("visual Provider retry evidence is invalid")
            try:
                parsed_request = parse_visual_request_evidence(
                    retry_request,
                    expected_crop_ref=expected_crop_ref,
                    expected_crop_sha256=crop_sha256,
                    expected_usage=retry_request.get("usage"),
                )
                crop_path = storage.resolve_resource_ref(expected_crop_ref)
            except (TypeError, ValueError):
                raise RuntimeError(
                    "visual Provider retry evidence is invalid"
                ) from None
            canonical_request = json.dumps(
                parsed_request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            expected_response = build_visual_failure_envelope(
                "tool_arguments_schema_invalid"
            )
            canonical_response = json.dumps(
                expected_response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if (
                canonical_request != retry_contents["request"]
                or retry_response != expected_response
                or canonical_response != retry_contents["response"]
                or hashlib.sha256(crop_path.read_bytes()).hexdigest()
                != crop_sha256
            ):
                raise RuntimeError("visual Provider retry evidence is invalid")
            retry_evidence.append({
                "request_id": retry_audit.get("request_id"),
                "retry_count": retry_audit.get("retry_count"),
                "failure_stage": retry_response.get("failure_stage"),
            })

        pairs.append((cache, visual_attempt_count(audit, retry_evidence)))
    if retry_by_cache:
        raise RuntimeError("visual Provider retry evidence is invalid")
    if (
        relative == "qwen-symbol"
        and sum(attempt_count - 1 for _, attempt_count in pairs) > 1
    ):
        raise RuntimeError("visual Provider retry evidence is invalid")
    return pairs


project_id = uuid.UUID(os.environ["QI_P0_PROJECT_ID"])
session = SessionLocal()
storage = LocalFileStorage(get_settings().storage_root)
try:
    raw = session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project_id)
    )
    if raw is None:
        raise RuntimeError("automatic result is unavailable")
    inventory = json.loads(storage.read_bytes(raw.inventory_ref))
    pages = inventory.get("pages")
    if not isinstance(pages, list) or not pages:
        raise RuntimeError("stored page inventory is unavailable")
    coverage = raw.coverage.get("entries")
    if not isinstance(coverage, list):
        raise RuntimeError("raw coverage is unavailable")

    visuals = []
    visual_page = {}
    page_indexes = []
    for page in pages:
        page_index = page.get("page_index")
        visual_observations = page.get("visual_observations")
        if not isinstance(page_index, int) or not isinstance(
            visual_observations,
            list,
        ):
            raise RuntimeError("visual inventory is invalid")
        page_indexes.append(page_index)
        for observation in visual_observations:
            observation_id = observation.get("observation_id")
            bbox_pdf = observation.get("bbox_pdf")
            if (
                not isinstance(observation_id, str)
                or not observation_id
                or not isinstance(bbox_pdf, list)
                or len(bbox_pdf) != 4
                or observation_id in visual_page
            ):
                raise RuntimeError("visual observation is invalid")
            visual_page[observation_id] = page_index
            visuals.append({
                "observation_id": observation_id,
                "page_index": page_index,
                "bbox_pdf": bbox_pdf,
            })

    project_root = storage.root / "projects" / str(project_id)

    visual_counts = {page_index: 0 for page_index in page_indexes}
    provider_call_identities = []
    provider_crop_artifacts = {}
    schema_sha256 = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    for cache, attempt_count in paired_cache(
        project_root,
        storage,
        project_id,
        "qwen-symbol",
    ):
        identity = cache.get("identity")
        visual_ids = (
            identity.get("visual_observation_ids")
            if isinstance(identity, dict)
            else None
        )
        if not isinstance(visual_ids, list) or not visual_ids:
            raise RuntimeError("visual Provider identity is unavailable")
        call_pages = {
            visual_page.get(visual_id)
            for visual_id in visual_ids
            if isinstance(visual_id, str)
        }
        if None in call_pages or len(call_pages) != 1:
            raise RuntimeError("visual Provider page identity is ambiguous")
        sealed_identity = provider_call_identity(
            identity,
            request_id=cache.get("request_id"),
            schema_sha256=schema_sha256,
        )
        crop_sha256 = sealed_identity["crop_sha256"]
        crop_ref = (
            f"asset://projects/{project_id}/provider-inputs/qwen-symbol/"
            f"{crop_sha256}.png"
        )
        crop_content = storage.resolve_resource_ref(crop_ref).read_bytes()
        if hashlib.sha256(crop_content).hexdigest() != crop_sha256:
            raise RuntimeError("visual Provider crop identity is invalid")
        provider_call_identities.append(sealed_identity)
        provider_crop_artifacts[crop_sha256] = base64.b64encode(
            crop_content
        ).decode("ascii")
        visual_counts[next(iter(call_pages))] += attempt_count

    text_pages_by_crop = {}
    for candidate in raw.candidates:
        review = candidate.get("advisor_review")
        if not isinstance(review, dict):
            continue
        crop_sha256 = review.get("crop_sha256")
        page_index = review.get("page_index")
        if (
            review.get("provider_role") == "advisor"
            and isinstance(crop_sha256, str)
            and isinstance(page_index, int)
        ):
            text_pages_by_crop.setdefault(crop_sha256, set()).add(page_index)
    for entry in coverage:
        review = entry.get("advisor_review") if isinstance(entry, dict) else None
        if not isinstance(review, dict):
            continue
        crop_sha256 = review.get("crop_sha256")
        page_index = review.get("page_index")
        if (
            review.get("provider_role") == "advisor"
            and isinstance(crop_sha256, str)
            and isinstance(page_index, int)
        ):
            text_pages_by_crop.setdefault(crop_sha256, set()).add(page_index)

    text_counts = {page_index: 0 for page_index in page_indexes}
    for cache, attempt_count in paired_cache(
        project_root,
        storage,
        project_id,
        "qwen",
    ):
        crop_sha256 = cache.get("crop_sha256")
        call_pages = text_pages_by_crop.get(crop_sha256, set())
        if len(call_pages) != 1:
            raise RuntimeError("text Provider page identity is ambiguous")
        text_counts[next(iter(call_pages))] += attempt_count

    source_commands = list(
        session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == project_id,
                OperationRecord.command.in_(("promote_source", "ignore_source")),
            )
        )
    )
    print(json.dumps({
        "automatic_result_id": str(raw.id),
        "visual_observations": visuals,
        "raw_candidates": raw.candidates,
        "raw_coverage": coverage,
        "provider_call_identities": provider_call_identities,
        "provider_crop_artifacts": [
            {
                "crop_sha256": crop_sha256,
                "content_base64": provider_crop_artifacts[crop_sha256],
            }
            for crop_sha256 in sorted(provider_crop_artifacts)
        ],
        "visual_calls_by_page": [
            {"page_index": page_index, "count": visual_counts[page_index]}
            for page_index in sorted(page_indexes)
        ],
        "total_vision_calls_by_page": [
            {
                "page_index": page_index,
                "count": visual_counts[page_index] + text_counts[page_index],
            }
            for page_index in sorted(page_indexes)
        ],
        "source_command_count": len(source_commands),
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


def _collect_symbol_result(
    *,
    project_id: str,
    automatic_result_id: str,
) -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "-e",
        f"QI_P0_PROJECT_ID={project_id}",
        "api",
        "python",
        "-c",
        _SYMBOL_RESULT_PROGRAM,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("post-result symbol evidence collection failed")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("post-result symbol evidence is invalid") from exc
    expected_fields = {
        "automatic_result_id",
        "visual_observations",
        "raw_candidates",
        "raw_coverage",
        "provider_call_identities",
        "provider_crop_artifacts",
        "visual_calls_by_page",
        "total_vision_calls_by_page",
        "source_command_count",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected_fields
        or document.get("automatic_result_id") != automatic_result_id
    ):
        raise RuntimeError("post-result symbol evidence identity is incomplete")
    return document


def _seal_provider_crop_evidence(
    run_dir: Path,
    identities: Any,
    crop_artifacts: Any,
) -> list[dict[str, Any]]:
    if not isinstance(identities, list) or not identities:
        raise RuntimeError("visual Provider identities are unavailable")
    if not isinstance(crop_artifacts, list) or not crop_artifacts:
        raise RuntimeError("visual Provider crop artifacts are unavailable")
    decoded: dict[str, bytes] = {}
    for artifact in crop_artifacts:
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != {"crop_sha256", "content_base64"}
            or not isinstance(artifact.get("crop_sha256"), str)
            or not isinstance(artifact.get("content_base64"), str)
        ):
            raise RuntimeError("visual Provider crop artifact is invalid")
        crop_sha256 = artifact["crop_sha256"]
        try:
            content = base64.b64decode(
                artifact["content_base64"],
                validate=True,
            )
        except (ValueError, TypeError):
            raise RuntimeError("visual Provider crop artifact is invalid") from None
        if (
            not content.startswith(PNG_SIGNATURE)
            or hashlib.sha256(content).hexdigest() != crop_sha256
            or crop_sha256 in decoded
        ):
            raise RuntimeError("visual Provider crop artifact is invalid")
        decoded[crop_sha256] = content
    required = {
        identity.get("crop_sha256")
        for identity in identities
        if isinstance(identity, Mapping)
    }
    if None in required or required != set(decoded):
        raise RuntimeError("visual Provider crop artifact identity is incomplete")
    crop_dir = run_dir / "artifacts/provider-crops"
    if crop_dir.exists() or crop_dir.is_symlink():
        raise RuntimeError("visual Provider crop artifact destination exists")
    crop_dir.mkdir()
    for crop_sha256, content in decoded.items():
        (crop_dir / f"{crop_sha256}.png").write_bytes(content)
    sealed: list[dict[str, Any]] = []
    for identity in identities:
        if not isinstance(identity, Mapping):
            raise RuntimeError("visual Provider sealed identity is invalid")
        crop_sha256 = identity.get("crop_sha256")
        if not isinstance(crop_sha256, str):
            raise RuntimeError("visual Provider sealed identity is invalid")
        crop_ref = f"artifacts/provider-crops/{crop_sha256}.png"
        sealed.append({**identity, "crop_ref": crop_ref})
    return sealed


def _typed_gdt_case_evidence(
    raw_candidates: Any,
    *,
    evaluation: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_candidates, list):
        raise RuntimeError("typed GDT Case A/B candidates are unavailable")
    expected = {
        "case_a": ("parallelism", "∥", "0.1", ["A"], "gdt_parallelism"),
        "case_b": ("flatness", "⏥", "0.08", [], "gdt_flatness"),
    }
    label_kinds = {
        label.get("label_id"): label.get("symbol_kinds")
        for page in manifest.get("pages", [])
        if isinstance(page, Mapping)
        for label in page.get("labels", [])
        if isinstance(label, Mapping)
    }
    label_matches = evaluation.get("label_matches")
    if not isinstance(label_matches, list):
        raise RuntimeError("typed GDT Case A/B annotation matches are unavailable")
    matches: dict[str, list[dict[str, Any]]] = {name: [] for name in expected}
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping):
            continue
        payload = candidate.get("payload")
        if not isinstance(payload, Mapping):
            continue
        datums = payload.get("datum_references")
        datum_names = (
            [entry.get("datum") for entry in datums if isinstance(entry, Mapping)]
            if isinstance(datums, list)
            else None
        )
        for case_name, (
            tolerance_type,
            symbol,
            value,
            expected_datums,
            expected_kind,
        ) in expected.items():
            if (
                payload.get("item_type") == "geometric_tolerance"
                and payload.get("tolerance_type") == tolerance_type
                and payload.get("tolerance_symbol") == symbol
                and payload.get("tolerance_value") == value
                and datum_names == expected_datums
            ):
                source_ids = payload.get(
                    "source_location_ids",
                    candidate.get("source_location_ids"),
                )
                candidate_id = payload.get(
                    "candidate_id",
                    candidate.get("candidate_id"),
                )
                annotation_matches = [
                    match
                    for match in label_matches
                    if isinstance(match, Mapping)
                    and match.get("candidate_id") == candidate_id
                    and match.get("disposition") == "candidate"
                    and label_kinds.get(match.get("label_id")) == [expected_kind]
                ]
                if len(annotation_matches) != 1:
                    continue
                fields = {
                    "candidate_id": candidate_id,
                    "annotation_label_id": annotation_matches[0]["label_id"],
                    "schema_version": payload.get("schema_version"),
                    "item_type": payload.get("item_type"),
                    "tolerance_type": payload.get("tolerance_type"),
                    "tolerance_symbol": payload.get("tolerance_symbol"),
                    "tolerance_value": payload.get("tolerance_value"),
                    "datum_references": payload.get("datum_references"),
                    "frames": payload.get("frames"),
                    "source_location_ids": source_ids,
                }
                if (
                    not isinstance(fields["candidate_id"], str)
                    or fields["schema_version"]
                    != "geometric-tolerance-candidate/1"
                    or not isinstance(fields["frames"], list)
                    or not fields["frames"]
                    or not isinstance(source_ids, list)
                    or not source_ids
                ):
                    raise RuntimeError("typed GDT Case A/B payload is incomplete")
                matches[case_name].append(
                    json.loads(json.dumps(fields, ensure_ascii=False))
                )
    if any(len(items) != 1 for items in matches.values()):
        raise RuntimeError("typed GDT Case A/B evidence is missing or ambiguous")
    return {name: items[0] for name, items in matches.items()}


def _call_counts(
    value: Any,
    *,
    field: str,
) -> list[dict[str, int]]:
    if not isinstance(value, list) or len(value) != 2:
        raise RuntimeError(f"{field} must cover both current-source pages")
    normalized: list[dict[str, int]] = []
    for entry in value:
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"page_index", "count"}
            or not isinstance(entry.get("page_index"), int)
            or not isinstance(entry.get("count"), int)
            or isinstance(entry.get("count"), bool)
            or int(entry["count"]) < 0
        ):
            raise RuntimeError(f"{field} contains an invalid count")
        normalized.append(
            {
                "page_index": int(entry["page_index"]),
                "count": int(entry["count"]),
            }
        )
    normalized.sort(key=lambda entry: entry["page_index"])
    if [entry["page_index"] for entry in normalized] != [0, 1]:
        raise RuntimeError(f"{field} page identity is incomplete")
    return normalized


def _vision_call_budget_failures(
    visual_calls: list[dict[str, int]],
    total_calls: list[dict[str, int]],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if any(entry["count"] > 16 for entry in visual_calls):
        failures.append({"reason": "visual_call_budget_exceeded"})
    if any(entry["count"] > 16 for entry in total_calls):
        failures.append({"reason": "total_vision_call_budget_exceeded"})
    if any(
        total["count"] < visual["count"]
        for visual, total in zip(visual_calls, total_calls, strict=True)
    ):
        failures.append({"reason": "vision_call_counts_inconsistent"})
    return failures


def _record_symbol_recognition_evidence(
    run_dir: Path,
    evidence: Mapping[str, Any],
) -> None:
    path = run_dir / LIVE_EVIDENCE_ARTIFACT
    live = _load_json(path)
    if live.get("symbol_recognition") is not None:
        raise RuntimeError("symbol recognition evidence is already recorded")
    live["symbol_recognition"] = dict(evidence)
    _receipt_module().validate_schema(
        live,
        "live-run-evidence.schema.json",
        ROOT,
    )
    _atomic_write_json(path, live)


def _run_symbol_recognition_gate(
    run_dir: Path,
    sample: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_paths = {
        name: run_dir / name
        for name in SYMBOL_EVAL_ARTIFACTS
    }
    if any(
        path.is_symlink() or not path.is_file()
        for path in artifact_paths.values()
    ):
        raise RuntimeError("sealed symbol input copies are unavailable")
    artifacts = {
        name: path.read_bytes()
        for name, path in artifact_paths.items()
    }
    validated = _script_module(
        "qi_live_symbol_artifact_contract",
        "stage-symbol-eval.py",
    ).validate_artifacts(artifacts)
    manifest_bytes = validated[SYMBOL_EVAL_ARTIFACT]
    verdict_bytes = validated[SYMBOL_VERDICT_ARTIFACT]
    manifest = json.loads(manifest_bytes)
    verdict = json.loads(verdict_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    process = sample.get("process")
    if (
        sample.get("order") != 1
        or not isinstance(process, Mapping)
        or process.get("source_sha256") != manifest.get("source_sha256")
        or verdict.get("manifest_sha256") != manifest_sha256
    ):
        raise RuntimeError("symbol gate does not bind the first raw result")
    project_id = str(sample.get("project_id"))
    automatic_result_id = str(process.get("automatic_result_id"))
    actual = _collect_symbol_result(
        project_id=project_id,
        automatic_result_id=automatic_result_id,
    )
    evaluation = _script_module(
        "qi_live_symbol_evaluator",
        "symbol_eval.py",
    ).evaluate_symbol_result(
        manifest=manifest,
        visual_observations=actual["visual_observations"],
        raw_candidates=actual["raw_candidates"],
        raw_coverage=actual["raw_coverage"],
    )
    visual_calls = _call_counts(
        actual["visual_calls_by_page"],
        field="visual_calls_by_page",
    )
    total_calls = _call_counts(
        actual["total_vision_calls_by_page"],
        field="total_vision_calls_by_page",
    )
    failures = list(evaluation.get("failures", []))
    failures.extend(
        _vision_call_budget_failures(
            visual_calls,
            total_calls,
        )
    )
    if actual.get("source_command_count") != 0:
        failures.append({"reason": "pre_manual_source_command_detected"})
    passed = evaluation.get("passed") is True and not failures
    typed_gdt_cases = _typed_gdt_case_evidence(
        actual["raw_candidates"],
        evaluation=evaluation,
        manifest=manifest,
    )
    provider_call_identities = _seal_provider_crop_evidence(
        run_dir,
        actual["provider_call_identities"],
        actual["provider_crop_artifacts"],
    )
    report = {
        "schema_version": "symbol-recognition-live-report/2",
        "selector": SYMBOL_RECOGNITION_SELECTOR,
        "run_id": run_dir.name,
        "order": 1,
        "project_id": project_id,
        "automatic_result_id": automatic_result_id,
        "source_sha256": process["source_sha256"],
        "manifest_sha256": manifest_sha256,
        "annotation_verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
        "visual_calls_by_page": visual_calls,
        "total_vision_calls_by_page": total_calls,
        "source_command_count": int(actual["source_command_count"]),
        "typed_gdt_cases": typed_gdt_cases,
        "provider_call_identities": provider_call_identities,
        "evaluation": evaluation,
        "failures": failures,
        "passed": passed,
    }
    _write_json(run_dir / SYMBOL_RECOGNITION_REPORT, report)
    report_sha256 = hashlib.sha256(
        (run_dir / SYMBOL_RECOGNITION_REPORT).read_bytes()
    ).hexdigest()
    counts = evaluation.get("counts")
    if not isinstance(counts, Mapping):
        raise RuntimeError("symbol evaluation counts are unavailable")
    evidence = {
        "selector": SYMBOL_RECOGNITION_SELECTOR,
        "passed": passed,
        "order": 1,
        "project_id": project_id,
        "automatic_result_id": automatic_result_id,
        "source_sha256": process["source_sha256"],
        "manifest_sha256": manifest_sha256,
        "annotation_verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
        "label_count": int(counts["positive_label_count"])
        + int(counts["negative_label_count"]),
        "positive_label_count": int(counts["positive_label_count"]),
        "negative_label_count": int(counts["negative_label_count"]),
        "positive_family_counts": evaluation["positive_family_counts"],
        "negative_family_counts": evaluation["negative_family_counts"],
        "visual_calls_by_page": visual_calls,
        "total_vision_calls_by_page": total_calls,
        "candidate_match_count": int(counts["candidate_match_count"]),
        "reference_match_count": int(counts["reference_match_count"]),
        "non_inspection_match_count": int(
            counts["non_inspection_match_count"]
        ),
        "negative_false_positive_count": int(
            counts["negative_false_positive_count"]
        ),
        "source_command_count": int(actual["source_command_count"]),
        "report_ref": SYMBOL_RECOGNITION_REPORT,
        "report_sha256": report_sha256,
    }
    _record_symbol_recognition_evidence(run_dir, evidence)
    if not passed:
        raise RuntimeError("sealed symbol recognition gate failed")
    return evidence


def _review_item_set_ready(
    review: Mapping[str, Any],
    candidates: Mapping[str, Any],
    item_write: Mapping[str, Any],
    *,
    operator_id: str,
) -> bool:
    return bool(
        _live_evidence_policy_module().review_item_set_ready(
            review,
            candidates,
            item_write,
            operator_id=operator_id,
        )
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
    consistency = document["consistency"]
    if not isinstance(export, Mapping) or not isinstance(consistency, Mapping):
        raise RuntimeError(f"sample {order} post-export evidence is incomplete")
    try:
        consistency = _live_evidence_policy_module().bind_post_export_evidence(
            run_dir.name,
            order,
            project_id,
            browser_result,
            export,
            consistency,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"sample {order} post-export evidence failed consistency gates"
        ) from exc
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
    policy = _live_evidence_policy_module()
    try:
        policy.validate_candidate_evidence(order, candidates)
    except ValueError as exc:
        raise RuntimeError(
            f"sample {order} candidate/coverage evidence is incomplete"
        ) from exc
    return {
        "order": order,
        "opaque_ref": str(entry["opaque_ref"]),
        "project_id": project_id,
        "project_url": policy.canonical_project_url(project_id, operator_id),
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
        symbol_outcome = _execute_selector_in_run(
            SYMBOL_RECOGNITION_SELECTOR,
            "live",
            run_dir,
        )
        if (
            symbol_outcome.get("exit_code") != 0
            or symbol_outcome.get("result_state") != "passed"
        ):
            raise RuntimeError("sealed symbol recognition selector blocked")
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
    live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
    samples = live.get("samples")
    if (
        not isinstance(samples, list)
        or not samples
        or samples[0].get("order") != 1
        or not isinstance(samples[0].get("project_url"), str)
    ):
        raise ValueError("design-qa.md implementation route is not run-bound")
    return dict(
        _live_evidence_policy_module().design_qa_evidence(
            path,
            run_dir,
            expected_route=samples[0]["project_url"],
            browser_name=LIVE_BROWSER,
            viewport=LIVE_VIEWPORT,
        )
    )


def _resume_identity_preflight(run_dir: Path) -> LivePreflight:
    run = _load_json(run_dir / "run.json")
    if not can_resume_live_run(run_dir):
        raise ValueError("run is not one resumable visual-QA pause")
    artifact_paths = {
        name: run_dir / name
        for name in (
            CURRENT_FOUR_ARTIFACT,
            *SYMBOL_EVAL_ARTIFACTS,
        )
    }
    if any(
        path.is_symlink() or not path.is_file()
        for path in artifact_paths.values()
    ):
        raise ValueError("paused live input artifacts are unavailable")
    artifacts = {
        name: path.read_bytes()
        for name, path in artifact_paths.items()
    }
    preflight = preflight_full_p0_live(
        input_set="current-four",
        source_root=os.environ.get(LIVE_SOURCE_ROOT_ENV),
        input_artifacts=artifacts,
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
    if artifacts != preflight.input_artifacts:
        raise ValueError("paused full live input artifacts changed")
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
    frontend = source.get(LIVE_FRONTEND_BASE_ENV, "").rstrip("/")
    if frontend != EXPECTED_LIVE_FRONTEND_BASE:
        raise ValueError("live frontend target is not the verified isolated runtime")
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
    try:
        _live_evidence_policy_module().validate_browser_result(
            run_dir.name,
            order,
            str(sample.get("project_id")),
            phase,
            browser_result,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"sample {order} browser evidence failed consistency gates"
        ) from exc
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
    if selector == SYMBOL_RECOGNITION_SELECTOR:
        try:
            live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
            samples = live.get("samples")
            if (
                not isinstance(samples, list)
                or len(samples) != 1
                or not isinstance(samples[0], Mapping)
            ):
                raise ValueError(
                    "symbol selector requires exactly the first raw result"
                )
            if live.get("symbol_recognition") is None:
                _run_symbol_recognition_gate(run_dir, samples[0])
                live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
            run = _load_json(run_dir / "run.json")
            current_four = _load_json(run_dir / CURRENT_FOUR_ARTIFACT)
            _live_evidence_policy_module().validate_symbol_recognition_evidence(
                ROOT,
                run,
                current_four,
                live,
                schema_validator=_receipt_module().validate_schema,
                run_dir=run_dir,
            )
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            return (
                None,
                "blocked",
                f"symbol recognition evidence failed: {exc}",
                [
                    ref
                    for ref in (SYMBOL_RECOGNITION_REPORT,)
                    if (run_dir / ref).is_file()
                ],
            )
        return (
            0,
            "passed",
            json.dumps(
                {"selector": selector, "passed": True},
                sort_keys=True,
            ),
            [
                LIVE_EVIDENCE_ARTIFACT,
                CURRENT_FOUR_ARTIFACT,
                *SYMBOL_EVAL_ARTIFACTS,
                SYMBOL_RECOGNITION_REPORT,
                str(samples[0]["process"]["prepare_log_ref"]),
            ],
        )
    phase = urlsplit(selector).path.lstrip("/")
    if phase not in LIVE_PHASES:
        return None, "blocked", f"unknown live phase: {phase}", []
    try:
        live = _load_json(run_dir / LIVE_EVIDENCE_ARTIFACT)
        manifest = _load_json(run_dir / CURRENT_FOUR_ARTIFACT)
        run = _load_json(run_dir / "run.json")
        human = _load_json(run_dir / HUMAN_VERDICT_ARTIFACT)
        expected_pause_identity = {
            "code_identity": run["code_identity"],
            "config_identity": run["config_identity"],
            "contract_definition_hash": run["contract_definition_hash"],
            "input_identity": run["input_identity"],
            "live_identity": run["live_identity"],
        }
        if (
            run_dir.name != run.get("run_id")
            or run.get("mode") != "live"
            or run.get("scope") != "full-p0"
            or run.get("task_id") is not None
            or run.get("execution_state") != "running"
            or run.get("failure_reason") is not None
            or run.get("pause_identity") != expected_pause_identity
        ):
            raise ValueError(
                "full-p0 live run identity or lifecycle is inconsistent"
            )
        _live_evidence_policy_module().validate_live_evidence(
            ROOT,
            run,
            manifest,
            human,
            live,
            schema_validator=_receipt_module().validate_schema,
            run_dir=run_dir,
            design_path=_design_qa_document_path(),
        )
        samples = live["samples"]
        refs = [
            LIVE_EVIDENCE_ARTIFACT,
            HUMAN_VERDICT_ARTIFACT,
            CURRENT_FOUR_ARTIFACT,
            *SYMBOL_EVAL_ARTIFACTS,
            SYMBOL_RECOGNITION_REPORT,
        ]
        for sample in samples:
            process = sample["process"]
            review = sample["review"]
            refs.append(str(process["prepare_log_ref"]))
            refs.append(str(review["evidence_ref"]))
            for section in (sample["balloons"], sample["export"]):
                browser = section["browser"]
                refs.extend(
                    [str(browser["report_ref"]), str(browser["result_ref"])]
                )
                refs.extend(str(ref) for ref in browser["screenshot_refs"])
            refs.append(str(sample["consistency"]["evidence_ref"]))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return None, "blocked", f"live evidence validation failed: {exc}", []
    return (
        0,
        "passed",
        json.dumps(
            {"selector": selector, "phase": phase, "passed": True},
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
        receipt = _build_receipt(
            receipt_module,
            run,
            results,
            preflight.mirror,
            preflight.bindings,
            preflight.policies,
            run_dir,
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
    artifact_names = set(artifacts)
    if artifact_names & set(SYMBOL_EVAL_ARTIFACTS):
        raise ValueError("symbol-eval artifacts are registration-only and cannot run a task")
    if (mode, scope, task_id) == ("fixture", "task", "D7-T2"):
        fixture_artifacts = _routing_comparison_fixture_artifacts()
        if artifacts and artifacts != fixture_artifacts:
            raise ValueError("D7-T2 fixture routing evidence must use the sanitized fixture")
        artifacts = fixture_artifacts
    elif artifacts and not (
        artifact_names == {CURRENT_FOUR_ARTIFACT}
        and mode in {"fixture", "live"}
        and task_id == "D2-T1"
    ):
        raise ValueError(
            "input artifacts are limited to fixture/live D2-T1 current-four evidence "
            "or fixture D7-T2 routing evidence"
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
        if CURRENT_FOUR_ARTIFACT in artifacts:
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
    selectors = list(dict.fromkeys(row["verification_selector"] for row in selected))
    fixture_proof: dict[str, Any] | None = None
    if mode == "fixture":
        _write_fixture_network_tripwires(run_dir)
        fixture_proof = {
            "schema_version": "fixture-offline-proof/1",
            "run_id": run_id,
            "mode": "fixture",
            "credential_keys_empty": list(LIVE_CREDENTIAL_KEYS),
            "provider_mode": "fixture",
            "provider_network_enabled": "disabled",
            "selectors": selectors,
            "attempted_selectors": [],
            "executed_selectors": [],
            "pre_execution_blocked_selectors": [],
            "offline_enforced_selectors": [],
            "external_calls_proven": False,
        }
        _write_json(run_dir / FIXTURE_OFFLINE_PROOF, fixture_proof)
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)

    # Identical selectors execute once; every selected P0 ID still gets a result.
    outcomes: dict[str, dict[str, Any]] = {}
    log_refs: dict[str, str] = {}
    for index, selector in enumerate(selectors, start=1):
        outcome = _execute_selector_in_run(selector, mode, run_dir)
        if fixture_proof is not None:
            fixture_proof["attempted_selectors"].append(selector)
            if outcome.get("subprocess_started") is True:
                fixture_proof["executed_selectors"].append(selector)
            if outcome.get("pre_execution_blocked") is True:
                fixture_proof["pre_execution_blocked_selectors"].append(selector)
            if outcome.get("fixture_offline_enforced") is True:
                fixture_proof["offline_enforced_selectors"].append(selector)
            fixture_proof["external_calls_proven"] = _fixture_proof_complete(
                fixture_proof,
                selectors,
            )
            _write_json(run_dir / FIXTURE_OFFLINE_PROOF, fixture_proof)
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
                *([FIXTURE_OFFLINE_PROOF] if fixture_proof is not None else []),
                *artifacts,
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
    receipt = _build_receipt(
        receipt_module,
        run,
        results,
        mirror,
        bindings,
        policies,
        run_dir,
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
    parser.add_argument("--symbol-eval-run", metavar="RUN_ID")
    parser.add_argument("--activate-current-inputs", action="store_true")
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
                or args.current_four_run
                or args.symbol_eval_run
                or args.activate_current_inputs
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
                or args.current_four_run
                or args.symbol_eval_run
                or args.activate_current_inputs
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
            explicit_registrations = bool(
                args.current_four_run and args.symbol_eval_run
            )
            if (
                args.task
                or (
                    not args.activate_current_inputs
                    and not explicit_registrations
                )
                or (
                    args.activate_current_inputs
                    and (
                        args.current_four_run is not None
                        or args.symbol_eval_run is not None
                    )
                )
                or args.input_set != "current-four"
                or args.pause_after != LIVE_PAUSE_BARRIER
            ):
                raise ValueError(
                    "full-p0 live start requires literal current-four and symbol "
                    "registration runs, current-four input, the first-PDF "
                    "balloon pause, and no task"
                )
            if args.activate_current_inputs:
                (
                    args.current_four_run,
                    args.symbol_eval_run,
                ) = activate_full_live_inputs(
                    source_root=os.environ.get(LIVE_SOURCE_ROOT_ENV),
                    environment=os.environ,
                )
            preflight = preflight_full_p0_live(
                input_set=args.input_set,
                source_root=os.environ.get(LIVE_SOURCE_ROOT_ENV),
                current_four_run=args.current_four_run,
                symbol_eval_run=args.symbol_eval_run,
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
                args.symbol_eval_run,
                args.activate_current_inputs,
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
