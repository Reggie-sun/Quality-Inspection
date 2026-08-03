#!/usr/bin/env python3
"""Own the one-use, append-only GDT-10D paid-cycle authorization protocol."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[3]


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEAD = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
_RUNTIME_MANIFEST_LINE = re.compile(
    r"(?P<sha256>[0-9a-f]{64})  "
    r"(?P<path>backend/app/[A-Za-z0-9._/-]+\.(?:py|json))"
)
_FORBIDDEN = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer|password|cookie",
    re.IGNORECASE,
)
_ISSUANCE_KEYS = {
    "schema_version",
    "cycle_id",
    "expires_at",
    "head_revision",
    "plan_sha256",
    "pricing_sha256",
    "runtime_closure_sha256",
    "current_four_sha256",
    "backend_image_id",
    "compose_project",
    "expected_db_revision",
    "max_total_cny",
    "content_sha256",
}
_GDT10E_CYCLE_ID = "gdt10e-auth-remediated-live-20260802"
_GDT10E_PRIOR_CYCLE_EVIDENCE_SHA256 = (
    "db7c74f7fd0623c34a496309c744da3d32fd9614786fbde485e569968939749a"
)
_GDT10E_PRICING_DEADLINE = datetime(
    2026, 8, 3, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))
)
_GDT10E_ISSUANCE_KEYS = _ISSUANCE_KEYS | {
    "historical_committed_cny",
    "overall_envelope_cny",
    "readiness_sha256",
    "plan_ref",
    "prior_cycle_evidence_sha256",
}
_GDT10E_PLAN_REF = (
    "docs/superpowers/plans/"
    "2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md"
)
_GDT10E_PRIVATE_ROOT = Path(
    "/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d"
)
_GDT10E_PRIVATE_NAMES = {
    "authorization": "authorization",
    "override": "live.env",
    "safe_override": "safe.env",
    "readiness": "account-readiness.json",
    "preparation_report": "preparation.json",
    "zero_paid_report": "zero-paid-readiness.json",
}
_LIVE_CREDENTIAL_KEYS = {
    "QI_TENCENT_SECRET_ID",
    "QI_TENCENT_SECRET_KEY",
    "QI_QWEN_API_KEY",
    "QI_QWEN_WORKSPACE_ID",
}
_CYCLE_RUNTIME_KEYS = {
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ID",
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
}
_HOST_CONTROL_KEYS = {
    *_LIVE_CREDENTIAL_KEYS,
    *_CYCLE_RUNTIME_KEYS,
    "QI_LIVE_CYCLE_AUTHORIZATION_REF",
    "QI_LIVE_CYCLE_OVERRIDE_REF",
    "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
    "GDT10E_RUN_ID",
}
_SAFE_RUNTIME_ENVIRONMENT = {
    "QI_SYMBOL_RECOGNITION_MODE": "production_uncertainty",
    "QI_QWEN_MODEL": "qwen3-vl-plus-2025-12-19",
}
_AUTHORIZATION_MOUNT_TARGET = "/run/qi-live-authorization"


def _new_cycle_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def _new_invocation_id() -> str:
    return secrets.token_hex(32)


def _gdt10e_issuance_now() -> datetime:
    return datetime.now(timezone.utc)


_QUIESCENCE_PROGRAM = r"""
import json
from app.celery_app import celery_app

inspector = celery_app.control.inspect(timeout=5.0)
print(json.dumps({
    "active": inspector.active(),
    "reserved": inspector.reserved(),
    "scheduled": inspector.scheduled(),
}, sort_keys=True))
"""


_RUNTIME_CONTROL_IDENTITY_PROGRAM = r"""
import json
import os

credential_keys = {
    "QI_TENCENT_SECRET_ID",
    "QI_TENCENT_SECRET_KEY",
    "QI_QWEN_API_KEY",
    "QI_QWEN_WORKSPACE_ID",
}
cycle_keys = {
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ID",
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
}
mount_target = "/run/qi-live-authorization"
mount_present = False
with open("/proc/self/mountinfo", encoding="utf-8") as stream:
    for line in stream:
        fields = line.split()
        if len(fields) > 4 and fields[4] == mount_target:
            mount_present = True
            break
print(json.dumps({
    "credential_keys_present": sorted(credential_keys & set(os.environ)),
    "cycle_keys_present": sorted(cycle_keys & set(os.environ)),
    "authorization_mount_present": mount_present,
    "mode": os.environ.get("QI_SYMBOL_RECOGNITION_MODE"),
    "model": os.environ.get("QI_QWEN_MODEL"),
}, sort_keys=True))
"""


_LIVE_RUNTIME_CONTROL_IDENTITY_PROGRAM = r"""
import json
import os
import sys

credential_keys = {
    "QI_TENCENT_SECRET_ID",
    "QI_TENCENT_SECRET_KEY",
    "QI_QWEN_API_KEY",
    "QI_QWEN_WORKSPACE_ID",
}
cycle_keys = {
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ID",
    "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
}
mount_target = "/run/qi-live-authorization"
mount_present = False
mount_read_only = False
with open("/proc/self/mountinfo", encoding="utf-8") as stream:
    for line in stream:
        fields = line.split()
        if len(fields) > 4 and fields[4] == mount_target:
            mount_present = True
            mount_read_only = "ro" in fields[5].split(",")
            break
print(json.dumps({
    "credential_keys_present": sorted(credential_keys & set(os.environ)),
    "cycle_keys_present": sorted(cycle_keys & set(os.environ)),
    "authorization_mount_present": mount_present,
    "authorization_mount_read_only": mount_read_only,
    "cycle_id_matches": (
        os.environ.get("QI_PROVIDER_CYCLE_AUTHORIZATION_ID") == sys.argv[1]
    ),
    "authorization_root_matches": (
        os.environ.get("QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT") == mount_target
    ),
    "mode": os.environ.get("QI_SYMBOL_RECOGNITION_MODE"),
    "model": os.environ.get("QI_QWEN_MODEL"),
}, sort_keys=True))
"""


def _canonical_hash(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("content_sha256", None)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _hashed(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def _safe_id(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_ID.fullmatch(value) is None
        or _FORBIDDEN.search(value) is not None
    ):
        raise ValueError(f"cycle authorization {field} is invalid")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"cycle authorization {field} is invalid")
    return value


def _six_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+\.[0-9]{6}", value) is None:
        raise ValueError(f"cycle authorization {field} is invalid")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - regex narrows input
        raise ValueError(f"cycle authorization {field} is invalid") from exc


def _gdt10e_private_path(value: str | Path, field: str) -> Path:
    """Accept only the literal, fixed private-control pathname for ``field``."""
    try:
        expected = _GDT10E_PRIVATE_ROOT / _GDT10E_PRIVATE_NAMES[field]
    except KeyError as exc:  # pragma: no cover - internal caller contract
        raise ValueError("GDT-10E path is invalid") from exc
    if os.fspath(value) != str(expected):
        raise ValueError("GDT-10E path is invalid")
    try:
        root_metadata = _GDT10E_PRIVATE_ROOT.lstat()
    except OSError as exc:
        raise ValueError("GDT-10E path is invalid") from exc
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
        or root_metadata.st_uid != os.getuid()
        or root_metadata.st_gid != os.getgid()
    ):
        raise ValueError("GDT-10E path is invalid")
    return expected


def _gdt10e_private_lexical_path(value: str | Path, field: str) -> Path:
    """Check the immutable command-line spelling even after the root is gone."""
    try:
        expected = _GDT10E_PRIVATE_ROOT / _GDT10E_PRIVATE_NAMES[field]
    except KeyError as exc:  # pragma: no cover - internal caller contract
        raise ValueError("GDT-10E path is invalid") from exc
    if os.fspath(value) != str(expected):
        raise ValueError("GDT-10E path is invalid")
    return expected


def _gdt10e_committed_identity() -> dict[str, str]:
    plan = subprocess.run(
        ["git", "show", f"HEAD:{_GDT10E_PLAN_REF}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    pricing_path = ROOT / "backend/app/providers/provider_pricing_gdt10d_v1.json"
    try:
        pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("GDT-10E pricing identity is invalid") from exc
    if (
        plan.returncode != 0
        or revision.returncode != 0
        or not plan.stdout
        or not isinstance(pricing, Mapping)
        or pricing.get("content_sha256") != _canonical_hash(pricing)
    ):
        raise ValueError("GDT-10E committed identity is invalid")
    return {
        "head_revision": revision.stdout.strip(),
        "plan_sha256": hashlib.sha256(plan.stdout).hexdigest(),
        "pricing_sha256": _sha256(pricing.get("content_sha256"), "pricing_sha256"),
        "runtime_closure_sha256": _runtime_closure_sha256(),
        "current_four_sha256": _current_four_manifest_sha256(),
        "backend_image_id": _current_api_image_id(),
        "compose_project": _safe_id(
            os.environ.get("COMPOSE_PROJECT_NAME", ""), "compose_project"
        ),
    }


def _run_zero_paid_preflight() -> None:
    """Use the existing Harness zero-mutation preflight Owner directly."""
    source_root = os.environ.get("QI_P0_LIVE_SOURCE_ROOT", "").strip()
    spec = importlib.util.spec_from_file_location(
        "qi_gdt10e_zero_paid_preflight", ROOT / ".agent/harness/scripts/run-p0.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("GDT-10E preflight Owner is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    artifacts = module._current_live_input_artifacts(source_root)
    module.preflight_full_p0_live(
        input_set="current-four", source_root=source_root,
        current_four_run=None, symbol_eval_run=None, input_artifacts=artifacts,
        environment=os.environ,
    )


def _gdt10e_report(
    path: Path, *, schema_version: str, fields: Mapping[str, Any]
) -> dict[str, Any]:
    document = {"schema_version": schema_version, "cycle_id": _GDT10E_CYCLE_ID, **fields}
    expected = _hashed(document)
    if path.exists() or path.is_symlink():
        current = _read_fact(
            path, keys=set(expected), schema_version=schema_version
        )
        if current != expected:
            raise ValueError("GDT-10E report conflicts")
        return current
    return _exclusive_fact(path, document)


def _read_gdt10e_private_readiness(path: Path) -> str:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("GDT-10E path is invalid") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_gid != os.getgid()
    ):
        raise ValueError("GDT-10E path is invalid")
    module = _provider_account_readiness_module()
    evidence = module.validate_account_readiness(
        root=_GDT10E_PRIVATE_ROOT,
        cycle_id=_GDT10E_CYCLE_ID,
        model="qwen3-vl-plus-2025-12-19",
        region="cn-beijing",
        max_incremental_cny="46.473344",
        environment=os.environ,
        phase="start",
    )
    return _sha256(evidence.content_sha256, "readiness_sha256")


def _provider_account_readiness_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "qi_gdt10e_account_readiness",
        ROOT / ".agent/harness/scripts/provider_account_readiness.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("GDT-10E readiness Owner is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(spec.name) is module:
            del sys.modules[spec.name]
        raise
    return module


def _write_private_override(path: Path, document: Mapping[str, Any]) -> None:
    content = yaml.safe_dump(dict(document), sort_keys=True).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError("GDT-10E private control is invalid") from exc
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _create_zero_paid_overrides(override: Path, safe_override: Path) -> None:
    credentials = {key: os.environ.get(key, "") for key in _LIVE_CREDENTIAL_KEYS}
    if any(not value for value in credentials.values()):
        raise ValueError("GDT-10E private control is invalid")
    environment = {
        **credentials,
        **_SAFE_RUNTIME_ENVIRONMENT,
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID": _GDT10E_CYCLE_ID,
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT": _AUTHORIZATION_MOUNT_TARGET,
    }
    live = {"services": {name: {"environment": environment, "volumes": [{
        "type": "bind", "source": str(_GDT10E_PRIVATE_ROOT / "authorization"),
        "target": _AUTHORIZATION_MOUNT_TARGET, "read_only": True,
    }]} for name in ("api", "worker")}}
    safe = {"services": {name: {"environment": _SAFE_RUNTIME_ENVIRONMENT} for name in ("api", "worker")}}
    _write_private_override(override, live)
    _write_private_override(safe_override, safe)


def _validate_future_live_override(path: Path) -> None:
    _validate_private_file(path, "live override")
    try:
        services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
        api = services["api"]
        worker = services["worker"]
    except (OSError, UnicodeError, KeyError, TypeError, yaml.YAMLError) as exc:
        raise ValueError("GDT-10E private control is invalid") from exc
    expected_keys = {
        *_LIVE_CREDENTIAL_KEYS, "QI_SYMBOL_RECOGNITION_MODE", "QI_QWEN_MODEL",
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID", "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
    }
    for service in (api, worker):
        if (
            not isinstance(service, Mapping)
            or set(service) != {"environment", "volumes"}
            or not isinstance(service["environment"], Mapping)
            or set(service["environment"]) != expected_keys
            or any(not isinstance(service["environment"][key], str) or not service["environment"][key] for key in expected_keys)
            or service["environment"].get("QI_SYMBOL_RECOGNITION_MODE") != _SAFE_RUNTIME_ENVIRONMENT["QI_SYMBOL_RECOGNITION_MODE"]
            or service["environment"].get("QI_QWEN_MODEL") != _SAFE_RUNTIME_ENVIRONMENT["QI_QWEN_MODEL"]
            or service["environment"].get("QI_PROVIDER_CYCLE_AUTHORIZATION_ID") != _GDT10E_CYCLE_ID
            or service["environment"].get("QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT") != _AUTHORIZATION_MOUNT_TARGET
            or service["volumes"] != [{"type": "bind", "source": str(_GDT10E_PRIVATE_ROOT / "authorization"), "target": _AUTHORIZATION_MOUNT_TARGET, "read_only": True}]
        ):
            raise ValueError("GDT-10E private control is invalid")


def prepare_zero_paid(
    *, authorization: str | Path, override: str | Path, safe_override: str | Path,
    readiness: str | Path, report: str | Path,
) -> dict[str, Any]:
    """Seal the first, authorization-free local readiness gate."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    override_path = _gdt10e_private_path(override, "override")
    safe_override_path = _gdt10e_private_path(safe_override, "safe_override")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    report_path = _gdt10e_private_path(report, "preparation_report")
    if authorization_path.exists() or authorization_path.is_symlink():
        raise ValueError("GDT-10E authorization must be absent before zero-paid gates")
    readiness_sha256 = _read_gdt10e_private_readiness(readiness_path)
    if not override_path.exists() and not safe_override_path.exists():
        _create_zero_paid_overrides(override_path, safe_override_path)
    elif not override_path.exists() or not safe_override_path.exists():
        raise ValueError("GDT-10E private controls are incomplete")
    _validate_future_live_override(override_path)
    validate_safe_override(safe_override_path)
    _activate_safe_runtime(safe_override_path)
    return _gdt10e_report(
        report_path,
        schema_version="provider-cycle-zero-paid-preparation/1",
        fields={"readiness_sha256": readiness_sha256, "safe_runtime_proved": True},
    )


def zero_paid_preflight(
    *, authorization: str | Path, override: str | Path, safe_override: str | Path,
    readiness: str | Path, preparation_report: str | Path, report: str | Path,
) -> dict[str, Any]:
    """Recheck the immutable preparation gate without issuing an authorization."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    _gdt10e_private_path(override, "override")
    safe_override_path = _gdt10e_private_path(safe_override, "safe_override")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    preparation_path = _gdt10e_private_path(preparation_report, "preparation_report")
    report_path = _gdt10e_private_path(report, "zero_paid_report")
    if authorization_path.exists() or authorization_path.is_symlink():
        raise ValueError("GDT-10E authorization must be absent before zero-paid gates")
    readiness_sha256 = _read_gdt10e_private_readiness(readiness_path)
    preparation = _read_fact(
        preparation_path,
        keys={"schema_version", "cycle_id", "readiness_sha256", "safe_runtime_proved", "content_sha256"},
        schema_version="provider-cycle-zero-paid-preparation/1",
    )
    if preparation["cycle_id"] != _GDT10E_CYCLE_ID or preparation["readiness_sha256"] != readiness_sha256 or preparation["safe_runtime_proved"] is not True:
        raise ValueError("GDT-10E preparation report is invalid")
    validate_safe_override(safe_override_path)
    check_head_contracts()
    _run_zero_paid_preflight()
    return _gdt10e_report(
        report_path,
        schema_version="provider-cycle-zero-paid-readiness/1",
        fields={
            "preparation_sha256": preparation["content_sha256"],
            "readiness_sha256": readiness_sha256,
            "no_delta_proved": True,
            **_gdt10e_committed_identity(),
        },
    )


def issue_gdt10e(
    *, authorization: str | Path, readiness: str | Path, zero_paid_report: str | Path,
    cycle_id: str, plan_ref: str, prior_cycle_evidence_sha256: str,
    historical_committed_cny: str, max_total_cny: str, overall_envelope_cny: str,
    expires_in_seconds: int,
) -> dict[str, Any]:
    """Issue only after reading the sealed zero-paid report; never accept hashes from argv."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    report_path = _gdt10e_private_path(zero_paid_report, "zero_paid_report")
    readiness_sha256 = _read_gdt10e_private_readiness(readiness_path)
    report = _read_fact(
        report_path,
        keys={
            "schema_version", "cycle_id", "preparation_sha256", "readiness_sha256",
            "no_delta_proved", "head_revision", "plan_sha256", "pricing_sha256",
            "runtime_closure_sha256", "current_four_sha256", "backend_image_id",
            "compose_project", "content_sha256",
        },
        schema_version="provider-cycle-zero-paid-readiness/1",
    )
    if report["cycle_id"] != _GDT10E_CYCLE_ID or report["readiness_sha256"] != readiness_sha256 or report["no_delta_proved"] is not True:
        raise ValueError("GDT-10E zero-paid report is invalid")
    if not isinstance(expires_in_seconds, int) or not 0 < expires_in_seconds <= 1800:
        raise ValueError("GDT-10E expiry is invalid")
    identity_keys = {
        "head_revision", "plan_sha256", "pricing_sha256", "runtime_closure_sha256",
        "current_four_sha256", "backend_image_id", "compose_project",
    }
    expected_report_keys = {
        "schema_version", "cycle_id", "preparation_sha256", "readiness_sha256",
        "no_delta_proved", "content_sha256", *identity_keys,
    }
    if set(report) != expected_report_keys:
        raise ValueError("GDT-10E zero-paid report is invalid")
    return issue_gdt10e_authorization(
        authorization_path, readiness_sha256=readiness_sha256, cycle_id=cycle_id,
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat(),
        head_revision=str(report["head_revision"]), plan_sha256=str(report["plan_sha256"]),
        pricing_sha256=str(report["pricing_sha256"]),
        runtime_closure_sha256=str(report["runtime_closure_sha256"]),
        current_four_sha256=str(report["current_four_sha256"]),
        backend_image_id=str(report["backend_image_id"]),
        compose_project=str(report["compose_project"]),
        expected_db_revision="0014", historical_committed_cny=historical_committed_cny,
        max_total_cny=max_total_cny, overall_envelope_cny=overall_envelope_cny,
        plan_ref=plan_ref, prior_cycle_evidence_sha256=prior_cycle_evidence_sha256,
    )


def validate_unconsumed(
    *, authorization: str | Path, override: str | Path, readiness: str | Path,
    zero_paid_report: str | Path,
) -> None:
    """Revalidate the pre-start boundary without creating or changing any file."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    override_path = _gdt10e_private_path(override, "override")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    report_path = _gdt10e_private_path(zero_paid_report, "zero_paid_report")
    issuance = _issuance(authorization_path)
    if (authorization_path / "consumption.json").exists() or (authorization_path / "consumption.json").is_symlink():
        raise ValueError("GDT-10E authorization is already consumed")
    readiness_sha256 = _read_gdt10e_private_readiness(readiness_path)
    report = _read_fact(
        report_path,
        keys={
            "schema_version", "cycle_id", "preparation_sha256", "readiness_sha256",
            "no_delta_proved", "head_revision", "plan_sha256", "pricing_sha256",
            "runtime_closure_sha256", "current_four_sha256", "backend_image_id",
            "compose_project", "content_sha256",
        },
        schema_version="provider-cycle-zero-paid-readiness/1",
    )
    identity_fields = (
        "head_revision", "plan_sha256", "pricing_sha256", "runtime_closure_sha256",
        "current_four_sha256", "backend_image_id", "compose_project",
    )
    if (
        issuance.get("readiness_sha256") != readiness_sha256
        or report.get("readiness_sha256") != readiness_sha256
        or report.get("no_delta_proved") is not True
        or any(issuance.get(field) != report.get(field) for field in identity_fields)
    ):
        raise ValueError("GDT-10E unconsumed validation is invalid")
    validate_live_override(override_path, authorization_path)


def prepare_resume(
    *,
    authorization: str | Path,
    override: str | Path,
    safe_override: str | Path,
    readiness: str | Path,
    runtime_acceptance: str | Path,
    run_id: str,
) -> None:
    """Recreate only unapplied GDT-10E controls for the bound paused run."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    override_path = _gdt10e_private_path(override, "override")
    safe_override_path = _gdt10e_private_path(safe_override, "safe_override")
    _gdt10e_private_path(readiness, "readiness")
    expected_acceptance = _gdt10e_runtime_acceptance_path(run_id)
    if os.fspath(runtime_acceptance) != str(expected_acceptance):
        raise ValueError("GDT-10E runtime acceptance path is invalid")
    if bound_run_id(authorization_path) != run_id:
        raise ValueError("GDT-10E run binding is invalid")
    validate_issuance_for_start(
        authorization_path, phase="resume", run_id=run_id
    )
    pause_evidence_sha256 = validate_paused_run(run_id)
    _pause_handoff(
        authorization_path,
        run_id=run_id,
        pause_evidence_sha256=pause_evidence_sha256,
    )
    if not override_path.exists() and not safe_override_path.exists():
        _create_zero_paid_overrides(override_path, safe_override_path)
    elif not override_path.exists() or not safe_override_path.exists():
        raise ValueError("GDT-10E private controls are incomplete")
    _validate_future_live_override(override_path)
    validate_safe_override(safe_override_path)


_PRECONSUME_CLEANUP_STEPS = (
    "safe_runtime_proved",
    "live_override_absent",
    "safe_override_absent",
    "preparation_report_absent",
    "zero_paid_report_absent",
    "account_readiness_absent",
    "authorization_root_absent",
    "private_root_absent",
)
_PRECONSUME_CLEANUP_DEADLINE = "2026-08-09T23:59:59+08:00"


def _preconsume_cleanup_paths() -> dict[str, Path]:
    """Return the fixed lexical paths frozen into a cleanup intent."""
    authorization = _GDT10E_PRIVATE_ROOT / "authorization"
    prefix = _GDT10E_PRIVATE_ROOT.name + "-cleanup-"
    parent = _GDT10E_PRIVATE_ROOT.parent
    return {
        "private_root": _GDT10E_PRIVATE_ROOT,
        "account_readiness": _GDT10E_PRIVATE_ROOT / "account-readiness.json",
        "live_override": _GDT10E_PRIVATE_ROOT / "live.env",
        "safe_override": _GDT10E_PRIVATE_ROOT / "safe.env",
        "authorization_root": authorization,
        "authorization_issuance": authorization / "issuance.json",
        "authorization_consumption": authorization / "consumption.json",
        "authorization_run": authorization / "run.json",
        "authorization_pause_handoff": authorization / "pause-handoff.json",
        "authorization_resume_consumed": authorization / "resume-consumed.json",
        "authorization_terminal": authorization / "terminal.json",
        "authorization_unconsumed_cancellation": authorization / "unconsumed-cancellation.json",
        "authorization_legacy_cleanup_blocker": authorization / "cleanup-blocker.json",
        "preparation_report": _GDT10E_PRIVATE_ROOT / "preparation.json",
        "zero_paid_report": _GDT10E_PRIVATE_ROOT / "zero-paid-readiness.json",
        "cleanup_intent": parent / f"{prefix}intent.json",
        "cleanup_receipt": parent / f"{prefix}receipt.json",
        "cleanup_blocker": parent / f"{prefix}blocker.json",
    }


def _preconsume_cleanup_path(value: str | Path, field: str) -> Path:
    try:
        expected = _preconsume_cleanup_paths()[field]
    except KeyError as exc:  # pragma: no cover - internal caller contract
        raise ValueError("GDT-10E cleanup path is invalid") from exc
    if os.fspath(value) != str(expected):
        raise ValueError("GDT-10E cleanup path is invalid")
    return expected


def _terminal_cleanup_paths(run_id: str) -> dict[str, Path]:
    """Extend the frozen cleanup map with the one literal public run tree."""
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("GDT-10E terminal cleanup run is invalid")
    paths = dict(_preconsume_cleanup_paths())
    run_root = ROOT / ".agent/harness/runs" / run_id
    paths.update(
        {
            "harness_run_root": run_root,
            "harness_run_document": run_root / "run.json",
            "harness_live_evidence": run_root / "live-run-evidence.json",
            "harness_runtime_acceptance": run_root
            / "reports/provider-account-runtime-acceptance.json",
            "harness_quiescence": run_root / "reports/provider-cycle-quiescence.json",
            "harness_close_bridge": run_root / "reports/provider-cycle-close-bridge.json",
        }
    )
    return paths


def _terminal_cleanup_lifecycle(
    root: Path, *, run_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return only the exact immutable terminal tuple eligible for disposal."""
    _safe_root(root)
    children = set(os.listdir(root))
    required = {"issuance.json", "consumption.json", "run.json", "terminal.json"}
    allowed = required | {
        "projects", "pause-handoff.json", "resume-consumed.json", "cleanup-blocker.json"
    }
    if not required.issubset(children) or not children.issubset(allowed):
        raise ValueError("GDT-10E terminal cleanup lifecycle is invalid")
    issuance = _issuance(root, require_active=False)
    if issuance["cycle_id"] != _GDT10E_CYCLE_ID:
        raise ValueError("GDT-10E terminal cleanup lifecycle is invalid")
    _consumption(root, issuance)
    run = _run(root, issuance)
    terminal = terminal_evidence(root)
    if (
        run["run_id"] != run_id
        or not isinstance(terminal, Mapping)
        or terminal["cycle_id"] != _GDT10E_CYCLE_ID
        or terminal["run_id"] != run_id
        or terminal["run_sha256"] != run["content_sha256"]
        or terminal["status"] not in {"completed", "failed", "aborted"}
    ):
        raise ValueError("GDT-10E terminal cleanup lifecycle is invalid")
    _sha256(terminal["quiescence_sha256"], "quiescence_sha256")
    if "unconsumed-cancellation.json" in children:
        raise ValueError("GDT-10E terminal cleanup lifecycle is invalid")
    try:
        _validate_terminal_authorization_children(root, issuance, run, terminal)
    except (OSError, ValueError):
        raise ValueError("GDT-10E terminal cleanup lifecycle is invalid") from None
    return issuance, run, dict(terminal)


def _validate_terminal_authorization_children(
    root: Path,
    issuance: Mapping[str, Any],
    run: Mapping[str, Any],
    terminal: Mapping[str, Any],
) -> None:
    """Require every retained terminal child to bind the sealed lifecycle tuple."""
    run_id = run["run_id"]
    pause_path = root / "pause-handoff.json"
    resume_path = root / "resume-consumed.json"
    pause_exists = pause_path.exists() or pause_path.is_symlink()
    resume_exists = resume_path.exists() or resume_path.is_symlink()
    if pause_exists != resume_exists:
        raise ValueError("terminal pause/resume pair is incomplete")
    if pause_exists:
        pause = _read_fact(
            pause_path,
            keys={
                "schema_version", "cycle_id", "run_id", "pause_evidence_sha256",
                "run_sha256", "safe_runtime_proved", "private_controls_removed",
                "content_sha256",
            },
            schema_version="provider-cycle-pause-handoff/1",
        )
        resume = _read_fact(
            resume_path,
            keys={
                "schema_version", "cycle_id", "run_id", "pause_evidence_sha256",
                "run_sha256", "invocation_id", "resumed_at", "content_sha256",
            },
            schema_version="provider-cycle-resume-consumed/1",
        )
        if (
            pause["cycle_id"] != issuance["cycle_id"]
            or pause["run_id"] != run_id
            or pause["run_sha256"] != run["content_sha256"]
            or pause["safe_runtime_proved"] is not True
            or pause["private_controls_removed"] is not True
            or _SHA256.fullmatch(str(pause["pause_evidence_sha256"])) is None
            or resume["cycle_id"] != issuance["cycle_id"]
            or resume["run_id"] != run_id
            or resume["run_sha256"] != run["content_sha256"]
            or resume["pause_evidence_sha256"] != pause["pause_evidence_sha256"]
            or _SHA256.fullmatch(str(resume["invocation_id"])) is None
        ):
            raise ValueError("terminal pause/resume correlation is invalid")

    projects = root / "projects"
    if projects.exists() or projects.is_symlink():
        _safe_root(projects)
        project_ids: set[str] = set()
        project_orders: set[int] = set()
        for project_path in projects.iterdir():
            project = _read_fact(
                project_path,
                keys={
                    "schema_version", "cycle_id", "run_id", "project_id",
                    "project_order", "source_sha256", "run_sha256", "content_sha256",
                },
                schema_version="provider-cycle-project/1",
            )
            order = project["project_order"]
            project_id = project["project_id"]
            if (
                not isinstance(order, int)
                or isinstance(order, bool)
                or not 1 <= order <= 4
                or project_path.name != f"{order:04d}.json"
                or not isinstance(project_id, str)
                or _SAFE_ID.fullmatch(project_id) is None
                or project["cycle_id"] != issuance["cycle_id"]
                or project["run_id"] != run_id
                or project["run_sha256"] != run["content_sha256"]
                or _SHA256.fullmatch(str(project["source_sha256"])) is None
                or project_id in project_ids
                or order in project_orders
            ):
                raise ValueError("terminal project correlation is invalid")
            project_ids.add(project_id)
            project_orders.add(order)

    blocker_path = root / "cleanup-blocker.json"
    if blocker_path.exists() or blocker_path.is_symlink():
        blocker = _read_fact(
            blocker_path,
            keys={
                "schema_version", "cycle_id", "run_id", "status", "failure_codes",
                "content_sha256",
            },
            schema_version="provider-cycle-cleanup-blocker/1",
        )
        if (
            blocker["cycle_id"] != issuance["cycle_id"]
            or blocker["run_id"] != run_id
            or blocker["status"] != terminal["status"]
            or not isinstance(blocker["failure_codes"], list)
            or not blocker["failure_codes"]
            or len(blocker["failure_codes"]) != len(set(blocker["failure_codes"]))
            or any(
                code not in {
                    "quiescence_close_or_finalize_failed", "safe_deactivation_failed",
                    "private_control_cleanup_failed", "pause_handoff_failed",
                }
                for code in blocker["failure_codes"]
            )
        ):
            raise ValueError("terminal legacy blocker is invalid")


def _terminal_cleanup_intent_document(
    *, issuance_sha256: str, terminal_sha256: str, run_id: str,
    readiness_sha256: str, readiness_expires_at: str, review_deadline: str,
) -> dict[str, Any]:
    created_at = _cleanup_timestamp()
    if (
        _validate_cleanup_timestamp(created_at)
        > _validate_cleanup_timestamp(readiness_expires_at)
        or review_deadline != _PRECONSUME_CLEANUP_DEADLINE
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    paths = _terminal_cleanup_paths(run_id)
    return _hashed(
        {
            "schema_version": "provider-cycle-cleanup-intent/1",
            "cycle_id": _GDT10E_CYCLE_ID,
            "branch": "terminal",
            "account_readiness_sha256": _sha256(readiness_sha256, "readiness_sha256"),
            "issuance_sha256": _sha256(issuance_sha256, "issuance_sha256"),
            "cancellation_sha256": None,
            "terminal_sha256": _sha256(terminal_sha256, "terminal_sha256"),
            "run_id": run_id,
            "safe_path_sha256s": {
                name: hashlib.sha256(str(path).encode("utf-8")).hexdigest()
                for name, path in paths.items()
            },
            "expected_steps": list(_PRECONSUME_CLEANUP_STEPS),
            "created_at": created_at,
            "readiness_expires_at": readiness_expires_at,
            "review_deadline": review_deadline,
            "owner_uid": os.getuid(),
            "owner_gid": os.getgid(),
            "mode": "0600",
        }
    )


def prepare_terminal_cleanup_intent(
    *, authorization: str | Path, readiness: str | Path, run_id: str,
    cleanup_intent: str | Path, cleanup_receipt: str | Path,
    cleanup_blocker: str | Path, review_deadline: str,
) -> dict[str, Any]:
    """Seal the immutable terminal tuple before any destructive cleanup action."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    intent_path = _preconsume_cleanup_path(cleanup_intent, "cleanup_intent")
    receipt_path = _preconsume_cleanup_path(cleanup_receipt, "cleanup_receipt")
    blocker_path = _preconsume_cleanup_path(cleanup_blocker, "cleanup_blocker")
    if (
        receipt_path.exists() or receipt_path.is_symlink()
        or blocker_path.exists() or blocker_path.is_symlink()
        or intent_path.exists() or intent_path.is_symlink()
    ):
        raise ValueError("GDT-10E cleanup journal is invalid")
    allowed = {
        "account-readiness.json", "authorization", "live.env", "safe.env",
        "preparation.json", "zero-paid-readiness.json",
    }
    if set(os.listdir(_GDT10E_PRIVATE_ROOT)) - allowed:
        raise ValueError("GDT-10E terminal cleanup private root is invalid")
    for path, field in (
        (_GDT10E_PRIVATE_ROOT / "live.env", "live override"),
        (_GDT10E_PRIVATE_ROOT / "safe.env", "safe override"),
        (_GDT10E_PRIVATE_ROOT / "preparation.json", "GDT-10E preparation report"),
        (_GDT10E_PRIVATE_ROOT / "zero-paid-readiness.json", "GDT-10E zero-paid report"),
    ):
        if path.exists() or path.is_symlink():
            _validate_private_file(path, field)
    issuance, _, terminal = _terminal_cleanup_lifecycle(
        authorization_path, run_id=run_id
    )
    evidence = _provider_account_readiness_module().validate_account_readiness(
        root=_GDT10E_PRIVATE_ROOT,
        cycle_id=_GDT10E_CYCLE_ID,
        model="qwen3-vl-plus-2025-12-19",
        region="cn-beijing",
        max_incremental_cny="46.473344",
        environment=os.environ,
        phase="start",
    )
    _validate_private_file(readiness_path, "GDT-10E readiness")
    return _exclusive_fact(
        intent_path,
        _terminal_cleanup_intent_document(
            issuance_sha256=issuance["content_sha256"],
            terminal_sha256=terminal["content_sha256"], run_id=run_id,
            readiness_sha256=evidence.content_sha256,
            readiness_expires_at=evidence.expires_at,
            review_deadline=review_deadline,
        ),
    )


def _read_terminal_cleanup_intent(path: Path) -> dict[str, Any]:
    document = _read_canonical_cleanup_fact(
        path,
        keys={
            "schema_version", "cycle_id", "branch", "account_readiness_sha256",
            "issuance_sha256", "cancellation_sha256", "terminal_sha256", "run_id",
            "safe_path_sha256s", "expected_steps", "created_at", "readiness_expires_at",
            "review_deadline", "owner_uid", "owner_gid", "mode", "content_sha256",
        },
        schema_version="provider-cycle-cleanup-intent/1",
    )
    run_id = document.get("run_id")
    if (
        document.get("cycle_id") != _GDT10E_CYCLE_ID
        or document.get("branch") != "terminal"
        or not isinstance(run_id, str)
        or _RUN_ID.fullmatch(run_id) is None
        or document.get("cancellation_sha256") is not None
        or document.get("safe_path_sha256s")
        != {
            name: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
            for name, value in _terminal_cleanup_paths(run_id).items()
        }
        or document.get("expected_steps") != list(_PRECONSUME_CLEANUP_STEPS)
        or document.get("review_deadline") != _PRECONSUME_CLEANUP_DEADLINE
        or document.get("owner_uid") != os.getuid()
        or document.get("owner_gid") != os.getgid()
        or document.get("mode") != "0600"
        or type(document.get("owner_uid")) is not int
        or type(document.get("owner_gid")) is not int
        or document["owner_uid"] < 0
        or document["owner_gid"] < 0
    ):
        raise ValueError("GDT-10E terminal cleanup intent is invalid")
    for field in ("account_readiness_sha256", "issuance_sha256", "terminal_sha256"):
        _sha256(document.get(field), field)
    if _validate_cleanup_timestamp(document.get("created_at")) > _validate_cleanup_timestamp(
        document.get("readiness_expires_at")
    ):
        raise ValueError("GDT-10E terminal cleanup intent is invalid")
    return document


def _read_terminal_cleanup_receipt(path: Path) -> dict[str, Any]:
    """Validate the self-contained terminal receipt used after intent retirement."""
    document = _read_canonical_cleanup_fact(
        path,
        keys={
            "schema_version", "cycle_id", "branch", "cleanup_intent_sha256",
            "account_readiness_sha256", "safe_path_sha256s_sha256", "completed_steps",
            "completed_at", "readiness_expires_at", "review_deadline", "owner_uid",
            "owner_gid", "mode", "content_sha256",
        },
        schema_version="provider-cycle-cleanup-receipt/1",
    )
    if (
        document["cycle_id"] != _GDT10E_CYCLE_ID
        or document["branch"] != "terminal"
        or document["review_deadline"] != _PRECONSUME_CLEANUP_DEADLINE
        or document["owner_uid"] != os.getuid()
        or document["owner_gid"] != os.getgid()
        or document["mode"] != "0600"
        or not isinstance(document["completed_steps"], Mapping)
        or set(document["completed_steps"]) != set(_PRECONSUME_CLEANUP_STEPS)
        or any(value is not True for value in document["completed_steps"].values())
    ):
        raise ValueError("GDT-10E terminal cleanup receipt is invalid")
    _validate_cleanup_timestamp(document["completed_at"])
    return document


def _read_terminal_public_json(path: Path) -> dict[str, Any]:
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("duplicate key")
        return dict(pairs)

    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("GDT-10E terminal public evidence is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("GDT-10E terminal public evidence is invalid")
    return document


def _terminal_public_policy_owner() -> Any:
    """Load the existing run/live schema and policy Owners without a second parser."""
    spec = importlib.util.spec_from_file_location(
        "qi_gdt10e_terminal_public_policy",
        Path(__file__).with_name("live_evidence_policy.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("GDT-10E terminal public policy Owner is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _terminal_public_schema_owner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "qi_gdt10e_terminal_public_schema",
        Path(__file__).with_name("generate-receipt.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("GDT-10E terminal public schema Owner is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_terminal_public_binding(
    intent: Mapping[str, Any], issuance: Mapping[str, Any], run: Mapping[str, Any],
    terminal: Mapping[str, Any],
) -> None:
    """Validate the fixed public terminal evidence without ever deleting it."""
    run_id = str(intent["run_id"])
    paths = _terminal_cleanup_paths(run_id)
    run_root = paths["harness_run_root"]
    reports = run_root / "reports"
    for directory in (
        ROOT / ".agent",
        ROOT / ".agent/harness",
        ROOT / ".agent/harness/runs",
        run_root,
        reports,
    ):
        try:
            metadata = directory.lstat()
        except OSError as exc:
            raise ValueError("GDT-10E terminal public evidence is invalid") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("GDT-10E terminal public evidence is invalid")
    run_document = _read_terminal_public_json(paths["harness_run_document"])
    live = _read_terminal_public_json(paths["harness_live_evidence"])
    try:
        schema_owner = _terminal_public_schema_owner()
        schema_owner.validate_schema(run_document, "run.schema.json", ROOT)
        schema_owner.validate_schema(live, "live-run-evidence.schema.json", ROOT)
        _terminal_public_policy_owner().validate_paid_cycle_evidence(
            run_document,
            live,
            require_success=False,
            evidence_dir=run_root,
            root=ROOT,
        )
    except Exception as exc:
        raise ValueError("GDT-10E terminal public evidence is invalid") from exc
    if (
        run_document.get("schema_version") != "run/3"
        or run_document.get("run_id") != run_id
        or run_document.get("cycle_authorization", {}).get("cycle_id") != _GDT10E_CYCLE_ID
        or run_document["cycle_authorization"].get("issuance_sha256") != issuance["content_sha256"]
        or run_document["cycle_authorization"].get("consumption_sha256")
        != run.get("consumption_sha256")
        or run_document["cycle_authorization"].get("run_authorization_sha256")
        != run["content_sha256"]
        or live.get("schema_version") != "live-run-evidence/3"
        or live.get("run_id") != run_id
        or not isinstance(live.get("paid_cycle"), Mapping)
        or live["paid_cycle"].get("cycle_id") != _GDT10E_CYCLE_ID
        or live["paid_cycle"].get("terminal", {}).get("terminal_sha256")
        != terminal["content_sha256"]
        or live["paid_cycle"]["terminal"].get("quiescence_sha256")
        != terminal["quiescence_sha256"]
    ):
        raise ValueError("GDT-10E terminal public evidence is invalid")
    quiescence = _read_canonical_cleanup_fact(
        paths["harness_quiescence"],
        keys={
            "schema_version", "run_id", "status", "harness_returned", "queue_depth",
            "worker_sets", "worker_stopped", "content_sha256",
        },
        schema_version="provider-cycle-quiescence/1",
    )
    bridge = _read_canonical_cleanup_fact(
        paths["harness_close_bridge"],
        keys={
            "schema_version", "run_id", "image_id", "storage_volume", "network",
            "container_user", "authorization_owner_uid", "authorization_owner_gid",
            "mounts", "terminal_sha256", "content_sha256",
        },
        schema_version="provider-cycle-close-bridge/1",
    )
    if (
        quiescence.get("run_id") != run_id
        or quiescence.get("status") != terminal["status"]
        or quiescence.get("content_sha256") != terminal["quiescence_sha256"]
        or bridge.get("run_id") != run_id
        or bridge.get("terminal_sha256") != terminal["content_sha256"]
        or live["paid_cycle"]["terminal"].get("bridge_evidence_sha256")
        != bridge["content_sha256"]
    ):
        raise ValueError("GDT-10E terminal public evidence is invalid")
    _provider_account_readiness_module().validate_account_readiness(
        root=_GDT10E_PRIVATE_ROOT,
        cycle_id=_GDT10E_CYCLE_ID,
        model="qwen3-vl-plus-2025-12-19",
        region="cn-beijing",
        max_incremental_cny="46.473344",
        environment=os.environ,
        phase="resume",
        expected_content_sha256=intent["account_readiness_sha256"],
        runtime_acceptance=paths["harness_runtime_acceptance"],
    )


def _delete_terminal_authorization(root: Path) -> None:
    _safe_root(root)
    allowed = {
        "issuance.json", "consumption.json", "run.json", "terminal.json", "projects",
        "pause-handoff.json", "resume-consumed.json", "cleanup-blocker.json",
    }
    children = set(os.listdir(root))
    if not children.issubset(allowed):
        raise ValueError("GDT-10E terminal cleanup authorization is invalid")
    projects = root / "projects"
    if projects.exists() or projects.is_symlink():
        _safe_root(projects)
        for project in projects.iterdir():
            _delete_preconsume_file(project, "GDT-10E terminal project")
        os.rmdir(projects)
        _fsync_directory(root)
    for name in (
        "cleanup-blocker.json", "resume-consumed.json", "pause-handoff.json",
        "terminal.json", "run.json", "consumption.json", "issuance.json",
    ):
        _delete_preconsume_file(root / name, "GDT-10E terminal authorization")
    if os.listdir(root):
        raise ValueError("GDT-10E terminal cleanup authorization is invalid")
    os.rmdir(root)
    _fsync_directory(root.parent)


def dispose_terminal(
    *, authorization: str | Path, readiness: str | Path, run_id: str,
    cleanup_intent: str | Path, cleanup_receipt: str | Path,
    cleanup_blocker: str | Path, review_deadline: str,
) -> dict[str, Any]:
    """Replay the durable terminal cleanup journal while retaining public run evidence."""
    authorization_path = _gdt10e_private_lexical_path(authorization, "authorization")
    readiness_path = _gdt10e_private_lexical_path(readiness, "readiness")
    intent_path = _preconsume_cleanup_path(cleanup_intent, "cleanup_intent")
    receipt_path = _preconsume_cleanup_path(cleanup_receipt, "cleanup_receipt")
    blocker_path = _preconsume_cleanup_path(cleanup_blocker, "cleanup_blocker")
    if review_deadline != _PRECONSUME_CLEANUP_DEADLINE or _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("GDT-10E terminal cleanup is invalid")
    if receipt_path.exists() or receipt_path.is_symlink():
        if blocker_path.exists() or blocker_path.is_symlink():
            raise ValueError("GDT-10E cleanup journal conflicts")
        if intent_path.exists() or intent_path.is_symlink():
            intent = _read_terminal_cleanup_intent(intent_path)
            receipt = _read_preconsume_journal(
                receipt_path,
                schema_version="provider-cycle-cleanup-receipt/1",
                intent=intent,
            )
            if not all(receipt["completed_steps"].values()):
                raise ValueError("GDT-10E cleanup receipt is invalid")
            _verify_preconsume_targets_absent()
            _delete_preconsume_file(intent_path, "GDT-10E cleanup intent")
            return receipt
        _verify_preconsume_targets_absent()
        return _read_terminal_cleanup_receipt(receipt_path)
    if not intent_path.exists() and not intent_path.is_symlink():
        prepare_terminal_cleanup_intent(
            authorization=authorization_path, readiness=readiness_path, run_id=run_id,
            cleanup_intent=intent_path, cleanup_receipt=receipt_path,
            cleanup_blocker=blocker_path, review_deadline=review_deadline,
        )
    intent = _read_terminal_cleanup_intent(intent_path)
    if intent["run_id"] != run_id:
        raise ValueError("GDT-10E terminal cleanup is invalid")
    blocker_retired = False
    blocker = None
    if blocker_path.exists() or blocker_path.is_symlink():
        blocker = _read_preconsume_journal(
            blocker_path, schema_version="provider-cycle-cleanup-blocker/2", intent=intent
        )
        actual = _cleanup_step_snapshot()
        if any(
            blocker["completed_steps"][name] and not actual[name]
            for name in _PRECONSUME_CLEANUP_STEPS
            if name != "safe_runtime_proved"
        ):
            raise ValueError("GDT-10E cleanup journal is invalid")
    lifecycle_present = authorization_path.exists() or authorization_path.is_symlink()
    lifecycle_intact = lifecycle_present and (
        blocker is None
        or not any(
            blocker["completed_steps"][name]
            for name in _PRECONSUME_CLEANUP_STEPS
            if name != "safe_runtime_proved"
        )
    )
    if lifecycle_intact:
        issuance, run, terminal = _terminal_cleanup_lifecycle(
            authorization_path, run_id=run_id
        )
        if (
            intent["issuance_sha256"] != issuance["content_sha256"]
            or intent["terminal_sha256"] != terminal["content_sha256"]
        ):
            raise ValueError("GDT-10E terminal cleanup is invalid")
    elif blocker is None and (
        _GDT10E_PRIVATE_ROOT.exists() or _GDT10E_PRIVATE_ROOT.is_symlink()
    ):
        raise ValueError("GDT-10E terminal cleanup lifecycle is missing")
    else:
        issuance = run = terminal = None
    step = "safe"
    try:
        deactivate_runtime()
        check_head_contracts()
        _run_zero_paid_preflight()
        if lifecycle_intact:
            _validate_terminal_public_binding(intent, issuance, run, terminal)
        step = "controls"
        _delete_preconsume_file(
            _GDT10E_PRIVATE_ROOT / "live.env", "live override"
        )
        _delete_preconsume_file(
            _GDT10E_PRIVATE_ROOT / "safe.env", "safe override"
        )
        _delete_preconsume_file(
            _GDT10E_PRIVATE_ROOT / "preparation.json",
            "GDT-10E preparation report",
        )
        _delete_preconsume_file(
            _GDT10E_PRIVATE_ROOT / "zero-paid-readiness.json",
            "GDT-10E zero-paid report",
        )
        step = "readiness"
        if _GDT10E_PRIVATE_ROOT.exists() and not _GDT10E_PRIVATE_ROOT.is_symlink():
            if readiness_path.exists() or readiness_path.is_symlink():
                evidence = _provider_account_readiness_module().dispose_account_readiness(intent_path)
                if evidence.content_sha256 != intent["account_readiness_sha256"]:
                    raise ValueError("GDT-10E terminal cleanup readiness is invalid")
        step = "authorization"
        if authorization_path.exists() or authorization_path.is_symlink():
            _delete_terminal_authorization(authorization_path)
        step = "root"
        _delete_preconsume_root()
        if blocker_path.exists() or blocker_path.is_symlink():
            _delete_preconsume_file(blocker_path, "GDT-10E cleanup blocker")
        blocker_retired = True
        step = "receipt"
        receipt = _write_preconsume_journal(
            receipt_path, schema_version="provider-cycle-cleanup-receipt/1", intent=intent,
            completed_steps={name: True for name in _PRECONSUME_CLEANUP_STEPS},
        )
        _delete_preconsume_file(intent_path, "GDT-10E cleanup intent")
        return receipt
    except BaseException as exc:
        if step == "receipt" and (receipt_path.exists() or receipt_path.is_symlink()):
            _delete_preconsume_file(receipt_path, "GDT-10E cleanup receipt")
        if not blocker_retired and not blocker_path.exists() and not blocker_path.is_symlink():
            snapshot = _cleanup_step_snapshot()
            snapshot["safe_runtime_proved"] = False
            _write_preconsume_journal(
                blocker_path, schema_version="provider-cycle-cleanup-blocker/2", intent=intent,
                completed_steps=snapshot,
                failure_code=_blocker_failure_code(step),
            )
        incomplete = _provider_account_readiness_module().AccountReadinessCleanupIncomplete
        if isinstance(exc, incomplete):
            raise
        raise RuntimeError("GDT-10E terminal cleanup failed") from None


def _read_canonical_cleanup_fact(
    path: Path, *, keys: set[str], schema_version: str
) -> dict[str, Any]:
    """Read an immutable fact without accepting aliases or noncanonical bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("GDT-10E cleanup fact is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or metadata.st_size > 64 * 1024
        ):
            raise ValueError("GDT-10E cleanup fact is invalid")
        content = b""
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            content += chunk
    finally:
        os.close(descriptor)
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("GDT-10E cleanup fact is invalid") from exc
    canonical = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if (
        not isinstance(document, dict)
        or set(document) != keys
        or document.get("schema_version") != schema_version
        or document.get("content_sha256") != _canonical_hash(document)
        or content != canonical
    ):
        raise ValueError("GDT-10E cleanup fact is invalid")
    return document


def _cleanup_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _validate_cleanup_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ) is None:
        raise ValueError("GDT-10E cleanup timestamp is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("GDT-10E cleanup timestamp is invalid") from exc


def _validate_unconsumed_cancellation(
    path: Path, issuance: Mapping[str, Any]
) -> dict[str, Any]:
    cancellation = _read_canonical_cleanup_fact(
        path,
        keys={
            "schema_version", "cycle_id", "issuance_sha256", "cancelled_at",
            "content_sha256",
        },
        schema_version="provider-cycle-unconsumed-cancellation/1",
    )
    if (
        cancellation["cycle_id"] != _GDT10E_CYCLE_ID
        or cancellation["issuance_sha256"] != issuance["content_sha256"]
    ):
        raise ValueError("GDT-10E cleanup cancellation is invalid")
    _validate_cleanup_timestamp(cancellation["cancelled_at"])
    return cancellation


def _create_or_validate_unconsumed_cancellation(
    root: Path, issuance: Mapping[str, Any]
) -> dict[str, Any]:
    path = root / "unconsumed-cancellation.json"
    if path.exists() or path.is_symlink():
        return _validate_unconsumed_cancellation(path, issuance)
    return _exclusive_fact(
        path,
        {
            "schema_version": "provider-cycle-unconsumed-cancellation/1",
            "cycle_id": _GDT10E_CYCLE_ID,
            "issuance_sha256": issuance["content_sha256"],
            "cancelled_at": _cleanup_timestamp(),
        },
    )


def _validate_preconsume_authorization(root: Path) -> tuple[str, str | None, str | None]:
    """Classify only states that have not reached consumption or activation."""
    if root.is_symlink():
        raise ValueError("GDT-10E cleanup lifecycle is invalid")
    if not root.exists():
        return "no_issuance", None, None
    _safe_root(root)
    try:
        children = set(os.listdir(root))
    except OSError as exc:
        raise ValueError("GDT-10E cleanup lifecycle is invalid") from exc
    if children not in ({"issuance.json"}, {"issuance.json", "unconsumed-cancellation.json"}):
        raise ValueError("GDT-10E cleanup lifecycle is not pre-consume")
    issuance = _read_canonical_cleanup_fact(
        root / "issuance.json",
        keys=_GDT10E_ISSUANCE_KEYS,
        schema_version="provider-cycle-issuance/1",
    )
    _validate_gdt10e_issuance_shape(issuance)
    cancellation = (
        _validate_unconsumed_cancellation(root / "unconsumed-cancellation.json", issuance)
        if "unconsumed-cancellation.json" in children
        else _create_or_validate_unconsumed_cancellation(root, issuance)
    )
    return "issued_unconsumed", issuance["content_sha256"], cancellation["content_sha256"]


def _cleanup_intent_document(
    *, branch: str, readiness_sha256: str, readiness_expires_at: str,
    issuance_sha256: str | None, cancellation_sha256: str | None,
    review_deadline: str,
) -> dict[str, Any]:
    created_at = _cleanup_timestamp()
    if _validate_cleanup_timestamp(created_at) > _validate_cleanup_timestamp(
        readiness_expires_at
    ):
        raise ValueError("GDT-10E cleanup intent is expired")
    if review_deadline != _PRECONSUME_CLEANUP_DEADLINE:
        raise ValueError("GDT-10E cleanup deadline is invalid")
    paths = _preconsume_cleanup_paths()
    document: dict[str, Any] = {
        "schema_version": "provider-cycle-cleanup-intent/1",
        "cycle_id": _GDT10E_CYCLE_ID,
        "branch": branch,
        "account_readiness_sha256": _sha256(readiness_sha256, "readiness_sha256"),
        "issuance_sha256": issuance_sha256,
        "cancellation_sha256": cancellation_sha256,
        "terminal_sha256": None,
        "run_id": None,
        "safe_path_sha256s": {
            name: hashlib.sha256(str(path).encode("utf-8")).hexdigest()
            for name, path in paths.items()
        },
        "expected_steps": list(_PRECONSUME_CLEANUP_STEPS),
        "created_at": created_at,
        "readiness_expires_at": readiness_expires_at,
        "review_deadline": review_deadline,
        "owner_uid": os.getuid(),
        "owner_gid": os.getgid(),
        "mode": "0600",
    }
    return _hashed(document)


def validate_preconsume_cleanup_intent(cleanup_intent: str | Path) -> dict[str, Any]:
    """Validate the sealed Step 7A cleanup preparation without deleting anything."""
    path = _preconsume_cleanup_path(cleanup_intent, "cleanup_intent")
    paths = _preconsume_cleanup_paths()
    document = _read_canonical_cleanup_fact(
        path,
        keys={
            "schema_version", "cycle_id", "branch", "account_readiness_sha256",
            "issuance_sha256", "cancellation_sha256", "terminal_sha256", "run_id",
            "safe_path_sha256s", "expected_steps", "created_at", "readiness_expires_at",
            "review_deadline", "owner_uid", "owner_gid", "mode", "content_sha256",
        },
        schema_version="provider-cycle-cleanup-intent/1",
    )
    expected_hashes = {
        name: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
        for name, value in paths.items()
    }
    if (
        document["cycle_id"] != _GDT10E_CYCLE_ID
        or document["branch"] not in {"no_issuance", "issued_unconsumed"}
        or document["safe_path_sha256s"] != expected_hashes
        or document["expected_steps"] != list(_PRECONSUME_CLEANUP_STEPS)
        or document["review_deadline"] != _PRECONSUME_CLEANUP_DEADLINE
        or document["owner_uid"] != os.getuid()
        or document["owner_gid"] != os.getgid()
        or document["mode"] != "0600"
        or document["terminal_sha256"] is not None
        or document["run_id"] is not None
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    if (
        type(document["owner_uid"]) is not int
        or type(document["owner_gid"]) is not int
        or document["owner_uid"] < 0
        or document["owner_gid"] < 0
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    created_at = _validate_cleanup_timestamp(document["created_at"])
    expires_at = _validate_cleanup_timestamp(document["readiness_expires_at"])
    if created_at > expires_at:
        raise ValueError("GDT-10E cleanup intent is invalid")
    _sha256(document["account_readiness_sha256"], "readiness_sha256")
    if document["branch"] == "no_issuance":
        if document["issuance_sha256"] is not None or document["cancellation_sha256"] is not None:
            raise ValueError("GDT-10E cleanup intent is invalid")
    root = _GDT10E_PRIVATE_ROOT
    _safe_root(root)
    expected_children = {"account-readiness.json"}
    if document["branch"] == "issued_unconsumed":
        expected_children.add("authorization")
    if set(os.listdir(root)) != expected_children:
        raise ValueError("GDT-10E cleanup intent is invalid")
    if document["branch"] == "no_issuance":
        return document
    issuance = _read_canonical_cleanup_fact(
        root / "authorization/issuance.json",
        keys=_GDT10E_ISSUANCE_KEYS,
        schema_version="provider-cycle-issuance/1",
    )
    _validate_gdt10e_issuance_shape(issuance)
    cancellation = _validate_unconsumed_cancellation(
        root / "authorization/unconsumed-cancellation.json", issuance
    )
    if (
        document["issuance_sha256"] != issuance["content_sha256"]
        or document["cancellation_sha256"] != cancellation["content_sha256"]
        or set(os.listdir(root / "authorization"))
        != {"issuance.json", "unconsumed-cancellation.json"}
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    return document


def prepare_preconsume_cleanup_intent(
    *, authorization: str | Path, override: str | Path, safe_override: str | Path,
    readiness: str | Path, preparation_report: str | Path, zero_paid_report: str | Path,
    cleanup_intent: str | Path, cleanup_receipt: str | Path, cleanup_blocker: str | Path,
    review_deadline: str,
) -> dict[str, Any]:
    """Seal lifecycle classification and intent; Step 7B owns all deletion."""
    authorization_path = _gdt10e_private_path(authorization, "authorization")
    _gdt10e_private_path(override, "override")
    _gdt10e_private_path(safe_override, "safe_override")
    readiness_path = _gdt10e_private_path(readiness, "readiness")
    _gdt10e_private_path(preparation_report, "preparation_report")
    _gdt10e_private_path(zero_paid_report, "zero_paid_report")
    intent_path = _preconsume_cleanup_path(cleanup_intent, "cleanup_intent")
    receipt_path = _preconsume_cleanup_path(cleanup_receipt, "cleanup_receipt")
    blocker_path = _preconsume_cleanup_path(cleanup_blocker, "cleanup_blocker")
    if receipt_path.exists() or receipt_path.is_symlink() or blocker_path.exists() or blocker_path.is_symlink():
        raise ValueError("GDT-10E cleanup journal is invalid")
    if intent_path.exists() or intent_path.is_symlink():
        return validate_preconsume_cleanup_intent(intent_path)
    allowed = {
        "account-readiness.json", "authorization", "live.env", "safe.env",
        "preparation.json", "zero-paid-readiness.json",
    }
    if set(os.listdir(_GDT10E_PRIVATE_ROOT)) - allowed:
        raise ValueError("GDT-10E cleanup private root is invalid")
    for path, field in (
        (_GDT10E_PRIVATE_ROOT / "live.env", "live override"),
        (_GDT10E_PRIVATE_ROOT / "safe.env", "safe override"),
        (_GDT10E_PRIVATE_ROOT / "preparation.json", "GDT-10E preparation report"),
        (_GDT10E_PRIVATE_ROOT / "zero-paid-readiness.json", "GDT-10E zero-paid report"),
    ):
        if path.exists() or path.is_symlink():
            _validate_private_file(path, field)
    branch, issuance_sha256, cancellation_sha256 = _validate_preconsume_authorization(
        authorization_path
    )
    module = _provider_account_readiness_module()
    evidence = module.validate_account_readiness(
        root=_GDT10E_PRIVATE_ROOT,
        cycle_id=_GDT10E_CYCLE_ID,
        model="qwen3-vl-plus-2025-12-19",
        region="cn-beijing",
        max_incremental_cny="46.473344",
        environment=os.environ,
        phase="start",
    )
    _validate_private_file(readiness_path, "GDT-10E readiness")
    document = _cleanup_intent_document(
        branch=branch,
        readiness_sha256=evidence.content_sha256,
        readiness_expires_at=evidence.expires_at,
        issuance_sha256=issuance_sha256,
        cancellation_sha256=cancellation_sha256,
        review_deadline=review_deadline,
    )
    return _exclusive_fact(intent_path, document)


_PRECONSUME_BLOCKER_CODES = {
    "safe_runtime_proof_failed",
    "private_control_cleanup_failed",
    "account_readiness_cleanup_incomplete",
    "authorization_cleanup_failed",
    "private_root_cleanup_failed",
    "cleanup_replay_validation_failed",
    "cleanup_receipt_write_failed",
}


def _validate_preconsume_intent_shape(document: Mapping[str, Any]) -> None:
    """Validate durable fields which remain readable after private deletion."""
    paths = _preconsume_cleanup_paths()
    expected_hashes = {
        name: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
        for name, value in paths.items()
    }
    if (
        document.get("cycle_id") != _GDT10E_CYCLE_ID
        or document.get("branch") not in {"no_issuance", "issued_unconsumed"}
        or document.get("safe_path_sha256s") != expected_hashes
        or document.get("expected_steps") != list(_PRECONSUME_CLEANUP_STEPS)
        or document.get("review_deadline") != _PRECONSUME_CLEANUP_DEADLINE
        or document.get("owner_uid") != os.getuid()
        or document.get("owner_gid") != os.getgid()
        or document.get("mode") != "0600"
        or document.get("terminal_sha256") is not None
        or document.get("run_id") is not None
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    if (
        type(document["owner_uid"]) is not int
        or type(document["owner_gid"]) is not int
        or document["owner_uid"] < 0
        or document["owner_gid"] < 0
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")
    created_at = _validate_cleanup_timestamp(document.get("created_at"))
    expires_at = _validate_cleanup_timestamp(document.get("readiness_expires_at"))
    if created_at > expires_at:
        raise ValueError("GDT-10E cleanup intent is invalid")
    _sha256(document.get("account_readiness_sha256"), "readiness_sha256")
    if document["branch"] == "no_issuance":
        if document.get("issuance_sha256") is not None or document.get("cancellation_sha256") is not None:
            raise ValueError("GDT-10E cleanup intent is invalid")
    elif not (
        isinstance(document.get("issuance_sha256"), str)
        and isinstance(document.get("cancellation_sha256"), str)
    ):
        raise ValueError("GDT-10E cleanup intent is invalid")


def _read_preconsume_intent_for_replay(path: Path) -> dict[str, Any]:
    document = _read_canonical_cleanup_fact(
        path,
        keys={
            "schema_version", "cycle_id", "branch", "account_readiness_sha256",
            "issuance_sha256", "cancellation_sha256", "terminal_sha256", "run_id",
            "safe_path_sha256s", "expected_steps", "created_at", "readiness_expires_at",
            "review_deadline", "owner_uid", "owner_gid", "mode", "content_sha256",
        },
        schema_version="provider-cycle-cleanup-intent/1",
    )
    _validate_preconsume_intent_shape(document)
    return document


def _journal_cross_hashes(intent: Mapping[str, Any]) -> dict[str, str]:
    return {
        "cleanup_intent_sha256": str(intent["content_sha256"]),
        "account_readiness_sha256": str(intent["account_readiness_sha256"]),
        "safe_path_sha256s_sha256": _canonical_hash(intent["safe_path_sha256s"]),
    }


def _read_preconsume_journal(
    path: Path, *, schema_version: str, intent: Mapping[str, Any]
) -> dict[str, Any]:
    common = {
        "schema_version", "cycle_id", "branch", "cleanup_intent_sha256",
        "account_readiness_sha256", "safe_path_sha256s_sha256", "completed_steps",
        "readiness_expires_at", "review_deadline", "owner_uid", "owner_gid", "mode",
        "content_sha256",
    }
    timestamp = "completed_at" if schema_version.endswith("receipt/1") else "observed_at"
    if schema_version.endswith("blocker/2"):
        common.add("failure_code")
    document = _read_canonical_cleanup_fact(
        path, keys={*common, timestamp}, schema_version=schema_version
    )
    if (
        document["cycle_id"] != _GDT10E_CYCLE_ID
        or document["branch"] != intent["branch"]
        or any(document[name] != value for name, value in _journal_cross_hashes(intent).items())
        or document["readiness_expires_at"] != intent["readiness_expires_at"]
        or document["review_deadline"] != intent["review_deadline"]
        or document["owner_uid"] != os.getuid()
        or document["owner_gid"] != os.getgid()
        or document["mode"] != "0600"
        or not isinstance(document["completed_steps"], Mapping)
        or set(document["completed_steps"]) != set(_PRECONSUME_CLEANUP_STEPS)
        or any(type(value) is not bool for value in document["completed_steps"].values())
        or type(document["owner_uid"]) is not int
        or type(document["owner_gid"]) is not int
        or document["owner_uid"] < 0
        or document["owner_gid"] < 0
    ):
        raise ValueError("GDT-10E cleanup journal is invalid")
    if schema_version.endswith("blocker/2") and document["failure_code"] not in _PRECONSUME_BLOCKER_CODES:
        raise ValueError("GDT-10E cleanup journal is invalid")
    _validate_cleanup_timestamp(document[timestamp])
    _validate_cleanup_timestamp(document["readiness_expires_at"])
    return document


def _cleanup_step_snapshot() -> dict[str, bool]:
    paths = _preconsume_cleanup_paths()
    return {
        "safe_runtime_proved": False,
        "live_override_absent": not paths["live_override"].exists() and not paths["live_override"].is_symlink(),
        "safe_override_absent": not paths["safe_override"].exists() and not paths["safe_override"].is_symlink(),
        "preparation_report_absent": not paths["preparation_report"].exists() and not paths["preparation_report"].is_symlink(),
        "zero_paid_report_absent": not paths["zero_paid_report"].exists() and not paths["zero_paid_report"].is_symlink(),
        "account_readiness_absent": not paths["account_readiness"].exists() and not paths["account_readiness"].is_symlink(),
        "authorization_root_absent": not paths["authorization_root"].exists() and not paths["authorization_root"].is_symlink(),
        "private_root_absent": not paths["private_root"].exists() and not paths["private_root"].is_symlink(),
    }


def _write_preconsume_journal(
    path: Path, *, schema_version: str, intent: Mapping[str, Any],
    completed_steps: Mapping[str, bool], failure_code: str | None = None,
) -> dict[str, Any]:
    timestamp = "completed_at" if schema_version.endswith("receipt/1") else "observed_at"
    document: dict[str, Any] = {
        "schema_version": schema_version,
        "cycle_id": _GDT10E_CYCLE_ID,
        "branch": intent["branch"],
        **_journal_cross_hashes(intent),
        "completed_steps": dict(completed_steps),
        timestamp: _cleanup_timestamp(),
        "readiness_expires_at": intent["readiness_expires_at"],
        "review_deadline": intent["review_deadline"],
        "owner_uid": os.getuid(), "owner_gid": os.getgid(), "mode": "0600",
    }
    if schema_version.endswith("blocker/2"):
        if failure_code not in _PRECONSUME_BLOCKER_CODES:
            raise ValueError("GDT-10E cleanup blocker is invalid")
        document["failure_code"] = failure_code
    return _exclusive_fact(path, document)


def _delete_preconsume_file(path: Path, field: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    _validate_private_file(path, field)
    path.unlink()
    _fsync_directory(path.parent)
    if path.exists() or path.is_symlink():
        raise ValueError("GDT-10E cleanup target reappeared")


def _delete_preconsume_authorization(intent: Mapping[str, Any]) -> None:
    root = _preconsume_cleanup_paths()["authorization_root"]
    if not root.exists() and not root.is_symlink():
        return
    _safe_root(root)
    expected = (
        {"issuance.json", "unconsumed-cancellation.json"}
        if intent["branch"] == "issued_unconsumed" else set()
    )
    # An interruption may occur after unlinking one immutable authorization
    # fact but before the directory fsync.  Replay may therefore see any
    # prefix of the fixed deletion order, never a foreign child.
    if not set(os.listdir(root)).issubset(expected):
        raise ValueError("GDT-10E cleanup authorization is invalid")
    for name in ("unconsumed-cancellation.json", "issuance.json"):
        if name in expected:
            _delete_preconsume_file(root / name, "GDT-10E authorization")
    os.rmdir(root)
    _fsync_directory(root.parent)
    if root.exists() or root.is_symlink():
        raise ValueError("GDT-10E cleanup target reappeared")


def _delete_preconsume_root() -> None:
    root = _GDT10E_PRIVATE_ROOT
    if not root.exists() and not root.is_symlink():
        return
    _safe_root(root)
    if os.listdir(root):
        raise ValueError("GDT-10E cleanup private root is not empty")
    os.rmdir(root)
    _fsync_directory(root.parent)
    if root.exists() or root.is_symlink():
        raise ValueError("GDT-10E cleanup target reappeared")


def _verify_preconsume_targets_absent() -> None:
    paths = _preconsume_cleanup_paths()
    for name in (
        "private_root", "account_readiness", "live_override", "safe_override",
        "authorization_root", "preparation_report", "zero_paid_report",
    ):
        if paths[name].exists() or paths[name].is_symlink():
            raise ValueError("GDT-10E cleanup target reappeared")


def _blocker_failure_code(step: str) -> str:
    return {
        "safe": "safe_runtime_proof_failed",
        "controls": "private_control_cleanup_failed",
        "readiness": "account_readiness_cleanup_incomplete",
        "authorization": "authorization_cleanup_failed",
        "root": "private_root_cleanup_failed",
        "receipt": "cleanup_receipt_write_failed",
    }.get(step, "cleanup_replay_validation_failed")


def abort_preconsume(
    *, authorization: str | Path, override: str | Path, safe_override: str | Path,
    readiness: str | Path, preparation_report: str | Path, zero_paid_report: str | Path,
    cleanup_intent: str | Path, cleanup_receipt: str | Path, cleanup_blocker: str | Path,
    review_deadline: str,
) -> dict[str, Any]:
    """Replay the only durable non-terminal cancellation cleanup sequence."""
    authorization_path = _gdt10e_private_lexical_path(authorization, "authorization")
    override_path = _gdt10e_private_lexical_path(override, "override")
    safe_override_path = _gdt10e_private_lexical_path(safe_override, "safe_override")
    readiness_path = _gdt10e_private_lexical_path(readiness, "readiness")
    preparation_path = _gdt10e_private_lexical_path(preparation_report, "preparation_report")
    zero_paid_path = _gdt10e_private_lexical_path(zero_paid_report, "zero_paid_report")
    intent_path = _preconsume_cleanup_path(cleanup_intent, "cleanup_intent")
    receipt_path = _preconsume_cleanup_path(cleanup_receipt, "cleanup_receipt")
    blocker_path = _preconsume_cleanup_path(cleanup_blocker, "cleanup_blocker")
    if review_deadline != _PRECONSUME_CLEANUP_DEADLINE:
        raise ValueError("GDT-10E cleanup deadline is invalid")
    if receipt_path.exists() or receipt_path.is_symlink():
        if blocker_path.exists() or blocker_path.is_symlink():
            raise ValueError("GDT-10E cleanup journal conflicts")
        if intent_path.exists() or intent_path.is_symlink():
            intent = _read_preconsume_intent_for_replay(intent_path)
            receipt = _read_preconsume_journal(
                receipt_path, schema_version="provider-cycle-cleanup-receipt/1", intent=intent
            )
            if not all(receipt["completed_steps"].values()):
                raise ValueError("GDT-10E cleanup receipt is invalid")
            _verify_preconsume_targets_absent()
            _delete_preconsume_file(intent_path, "GDT-10E cleanup intent")
        else:
            _verify_preconsume_targets_absent()
        receipt = _read_canonical_cleanup_fact(
            receipt_path,
            keys={
                "schema_version", "cycle_id", "branch", "cleanup_intent_sha256",
                "account_readiness_sha256", "safe_path_sha256s_sha256", "completed_steps",
                "completed_at", "readiness_expires_at", "review_deadline", "owner_uid",
                "owner_gid", "mode", "content_sha256",
            }, schema_version="provider-cycle-cleanup-receipt/1",
        )
        return receipt
    if not intent_path.exists() and not intent_path.is_symlink():
        prepare_preconsume_cleanup_intent(
            authorization=authorization_path, override=override_path, safe_override=safe_override_path,
            readiness=readiness_path, preparation_report=preparation_path,
            zero_paid_report=zero_paid_path, cleanup_intent=intent_path,
            cleanup_receipt=receipt_path, cleanup_blocker=blocker_path,
            review_deadline=review_deadline,
        )
    intent = _read_preconsume_intent_for_replay(intent_path)
    if blocker_path.exists() or blocker_path.is_symlink():
        blocker = _read_preconsume_journal(
            blocker_path, schema_version="provider-cycle-cleanup-blocker/2", intent=intent
        )
        actual = _cleanup_step_snapshot()
        if any(
            blocker["completed_steps"][name] and not actual[name]
            for name in _PRECONSUME_CLEANUP_STEPS
            if name != "safe_runtime_proved"
        ):
            raise ValueError("GDT-10E cleanup journal is invalid")
    blocker_retired = False
    step = "safe"
    try:
        deactivate_runtime()
        step = "controls"
        _delete_preconsume_file(override_path, "live override")
        _delete_preconsume_file(safe_override_path, "safe override")
        _delete_preconsume_file(preparation_path, "GDT-10E preparation report")
        _delete_preconsume_file(zero_paid_path, "GDT-10E zero-paid report")
        step = "readiness"
        if _GDT10E_PRIVATE_ROOT.exists() and not _GDT10E_PRIVATE_ROOT.is_symlink():
            evidence = _provider_account_readiness_module().dispose_account_readiness(intent_path)
            if evidence.content_sha256 != intent["account_readiness_sha256"]:
                raise ValueError("GDT-10E cleanup readiness is invalid")
        step = "authorization"
        _delete_preconsume_authorization(intent)
        step = "root"
        _delete_preconsume_root()
        if blocker_path.exists() or blocker_path.is_symlink():
            _delete_preconsume_file(blocker_path, "GDT-10E cleanup blocker")
            blocker_retired = True
        step = "receipt"
        completed = {name: True for name in _PRECONSUME_CLEANUP_STEPS}
        receipt = _write_preconsume_journal(
            receipt_path, schema_version="provider-cycle-cleanup-receipt/1",
            intent=intent, completed_steps=completed,
        )
        _delete_preconsume_file(intent_path, "GDT-10E cleanup intent")
        return receipt
    except BaseException as exc:
        # A receipt is the terminal journal fact only after this call returns.
        # If its write/fsync path fails after the blocker was retired, restore the
        # required intent-only crash state rather than leaving an unverifiable
        # receipt that prevents the ordered replay from continuing.
        if step == "receipt" and (receipt_path.exists() or receipt_path.is_symlink()):
            _delete_preconsume_file(receipt_path, "GDT-10E cleanup receipt")
        if (
            not blocker_retired
            and not blocker_path.exists()
            and not blocker_path.is_symlink()
        ):
            snapshot = _cleanup_step_snapshot()
            snapshot["safe_runtime_proved"] = False
            try:
                _write_preconsume_journal(
                    blocker_path, schema_version="provider-cycle-cleanup-blocker/2",
                    intent=intent, completed_steps=snapshot,
                    failure_code=_blocker_failure_code(step),
                )
            except BaseException as blocker_exc:
                raise RuntimeError("GDT-10E cleanup blocker persistence failed") from blocker_exc
        raise exc


def _validate_gdt10e_issuance_shape(issuance: Mapping[str, Any]) -> None:
    if issuance.get("cycle_id") != _GDT10E_CYCLE_ID:
        return
    historical = _six_decimal(
        issuance.get("historical_committed_cny"), "historical_committed_cny"
    )
    incremental = _six_decimal(issuance.get("max_total_cny"), "max_total_cny")
    overall = _six_decimal(issuance.get("overall_envelope_cny"), "overall_envelope_cny")
    if (
        historical != Decimal("3.526656")
        or incremental != Decimal("46.473344")
        or historical + incremental != overall
        or overall != Decimal("50.000000")
        or issuance.get("plan_ref") != _GDT10E_PLAN_REF
    ):
        raise ValueError("cycle authorization fixed boundary is invalid")
    _sha256(issuance.get("readiness_sha256"), "readiness_sha256")
    _sha256(
        issuance.get("prior_cycle_evidence_sha256"),
        "prior_cycle_evidence_sha256",
    )
    if (
        issuance.get("prior_cycle_evidence_sha256")
        != _GDT10E_PRIOR_CYCLE_EVIDENCE_SHA256
    ):
        raise ValueError("cycle authorization prior_cycle_evidence_sha256 is invalid")


def _safe_root(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise ValueError("cycle authorization directory is invalid") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
        or metadata.st_gid != os.getgid()
    ):
        raise ValueError("cycle authorization directory is invalid")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exclusive_fact(path: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    payload = _hashed(document)
    content = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"cycle authorization {path.stem} is already bound") from exc
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, content)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        raise
    else:
        os.close(fd)
    _fsync_directory(path.parent)
    return payload


def _write_all(descriptor: int, content: bytes) -> None:
    """Persist an immutable payload completely; partial writes are a failure."""
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise OSError("immutable fact write was incomplete")
        offset += written


def _read_fact(
    path: Path,
    *,
    keys: set[str] | tuple[set[str], ...],
    schema_version: str,
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cycle authorization {path.stem} is unavailable") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or metadata.st_size > 64 * 1024
        ):
            raise ValueError(f"cycle authorization {path.stem} is invalid")
        content = b""
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            content += chunk
    finally:
        os.close(fd)
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cycle authorization {path.stem} is invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) not in (keys if isinstance(keys, tuple) else (keys,))
        or document.get("schema_version") != schema_version
        or document.get("content_sha256") != _canonical_hash(document)
    ):
        raise ValueError(f"cycle authorization {path.stem} is invalid")
    return document


def _issuance(root: Path, *, require_active: bool = True) -> dict[str, Any]:
    _safe_root(root)
    issuance = _read_fact(
        root / "issuance.json",
        keys=(_ISSUANCE_KEYS, _GDT10E_ISSUANCE_KEYS),
        schema_version="provider-cycle-issuance/1",
    )
    if require_active:
        try:
            expiry = datetime.fromisoformat(str(issuance["expires_at"]))
        except ValueError as exc:
            raise ValueError("cycle authorization expiry is invalid") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("cycle authorization expiry is invalid")
    _validate_gdt10e_issuance_shape(issuance)
    return issuance


def _ensure_nonterminal(root: Path) -> None:
    terminal = root / "terminal.json"
    if terminal.exists() or terminal.is_symlink():
        raise ValueError("cycle authorization is terminal")


def _ensure_no_cleanup_blocker(root: Path) -> None:
    blocker = root / "cleanup-blocker.json"
    if blocker.exists() or blocker.is_symlink():
        _read_fact(
            blocker,
            keys={
                "schema_version",
                "cycle_id",
                "run_id",
                "status",
                "failure_codes",
                "content_sha256",
            },
            schema_version="provider-cycle-cleanup-blocker/1",
        )
        raise ValueError("cycle authorization has unresolved cleanup blocker")


def _pause_handoff(
    root: Path,
    *,
    run_id: str,
    pause_evidence_sha256: str,
) -> dict[str, Any]:
    issuance = _issuance(root)
    run = _run(root, issuance)
    handoff = _read_fact(
        root / "pause-handoff.json",
        keys={
            "schema_version",
            "cycle_id",
            "run_id",
            "pause_evidence_sha256",
            "run_sha256",
            "safe_runtime_proved",
            "private_controls_removed",
            "content_sha256",
        },
        schema_version="provider-cycle-pause-handoff/1",
    )
    if (
        handoff["cycle_id"] != issuance["cycle_id"]
        or handoff["run_id"] != run_id
        or handoff["run_sha256"] != run["content_sha256"]
        or handoff["pause_evidence_sha256"] != pause_evidence_sha256
        or handoff["safe_runtime_proved"] is not True
        or handoff["private_controls_removed"] is not True
    ):
        raise ValueError("cycle authorization pause handoff is invalid")
    return handoff


def record_pause_handoff(
    root: str | Path,
    *,
    run_id: str,
    pause_evidence_sha256: str,
) -> dict[str, Any]:
    path = Path(root)
    _ensure_nonterminal(path)
    _ensure_no_cleanup_blocker(path)
    issuance = _issuance(path)
    run = _run(path, issuance)
    if run["run_id"] != run_id:
        raise ValueError("cycle authorization run identity is invalid")
    return _exclusive_fact(
        path / "pause-handoff.json",
        {
            "schema_version": "provider-cycle-pause-handoff/1",
            "cycle_id": issuance["cycle_id"],
            "run_id": run_id,
            "pause_evidence_sha256": _sha256(
                pause_evidence_sha256, "pause_evidence_sha256"
            ),
            "run_sha256": run["content_sha256"],
            "safe_runtime_proved": True,
            "private_controls_removed": True,
        },
    )


def _consumption(root: Path, issuance: Mapping[str, Any]) -> dict[str, Any]:
    consumption = _read_fact(
        root / "consumption.json",
        keys={
            "schema_version",
            "cycle_id",
            "issuance_sha256",
            "invocation_id",
            "consumed_at",
            "content_sha256",
        },
        schema_version="provider-cycle-consumption/1",
    )
    if (
        consumption["cycle_id"] != issuance["cycle_id"]
        or consumption["issuance_sha256"] != issuance["content_sha256"]
        or _SHA256.fullmatch(str(consumption["invocation_id"])) is None
    ):
        raise ValueError("cycle authorization consumption identity is invalid")
    return consumption


def _run(root: Path, issuance: Mapping[str, Any]) -> dict[str, Any]:
    run = _read_fact(
        root / "run.json",
        keys={
            "schema_version",
            "cycle_id",
            "run_id",
            "consumption_sha256",
            "content_sha256",
        },
        schema_version="provider-cycle-run/1",
    )
    consumption = _consumption(root, issuance)
    if (
        run["cycle_id"] != issuance["cycle_id"]
        or run["consumption_sha256"] != consumption["content_sha256"]
    ):
        raise ValueError("cycle authorization run identity is invalid")
    _safe_id(run["run_id"], "run_id")
    return run


def authorization_evidence(
    root: str | Path,
    *,
    require_run: bool = False,
) -> dict[str, Any]:
    """Return only public identities and content hashes safe for run evidence."""
    path = Path(root)
    issuance = _issuance(path)
    consumption = _consumption(path, issuance)
    evidence = {
        "cycle_id": issuance["cycle_id"],
        "head_revision": issuance["head_revision"],
        "plan_sha256": issuance["plan_sha256"],
        "pricing_sha256": issuance["pricing_sha256"],
        "runtime_closure_sha256": issuance["runtime_closure_sha256"],
        "current_four_sha256": issuance["current_four_sha256"],
        "backend_image_id": issuance["backend_image_id"],
        "compose_project": issuance["compose_project"],
        "expected_db_revision": issuance["expected_db_revision"],
        "max_total_cny": issuance["max_total_cny"],
        "issuance_sha256": issuance["content_sha256"],
        "consumption_sha256": consumption["content_sha256"],
    }
    if issuance["cycle_id"] == _GDT10E_CYCLE_ID:
        evidence.update(
            {
                "historical_committed_cny": issuance[
                    "historical_committed_cny"
                ],
                "overall_envelope_cny": issuance["overall_envelope_cny"],
                "readiness_sha256": issuance["readiness_sha256"],
            }
        )
    run_path = path / "run.json"
    if require_run or run_path.exists() or run_path.is_symlink():
        run = _run(path, issuance)
        evidence["run_id"] = run["run_id"]
        evidence["run_authorization_sha256"] = run["content_sha256"]
    return evidence


def _resume_consumption(
    root: Path,
    *,
    run_id: str,
    require_active: bool = True,
) -> dict[str, Any]:
    issuance = _issuance(root, require_active=require_active)
    run = _run(root, issuance)
    resume = _read_fact(
        root / "resume-consumed.json",
        keys={
            "schema_version",
            "cycle_id",
            "run_id",
            "pause_evidence_sha256",
            "run_sha256",
            "invocation_id",
            "resumed_at",
            "content_sha256",
        },
        schema_version="provider-cycle-resume-consumed/1",
    )
    if (
        run["run_id"] != run_id
        or resume["cycle_id"] != issuance["cycle_id"]
        or resume["run_id"] != run_id
        or resume["run_sha256"] != run["content_sha256"]
        or _SHA256.fullmatch(str(resume["invocation_id"])) is None
    ):
        raise ValueError("cycle authorization resume identity is invalid")
    return resume


def resume_evidence(root: str | Path, *, run_id: str) -> dict[str, Any]:
    resume = _resume_consumption(Path(root), run_id=run_id)
    return {
        "resume_consumed_sha256": resume["content_sha256"],
        "pause_evidence_sha256": resume["pause_evidence_sha256"],
    }


def terminal_evidence(root: str | Path) -> dict[str, Any] | None:
    path = Path(root)
    terminal_path = path / "terminal.json"
    if not terminal_path.exists() and not terminal_path.is_symlink():
        return None
    return _read_fact(
        terminal_path,
        keys={
            "schema_version",
            "cycle_id",
            "run_id",
            "status",
            "quiescence_sha256",
            "run_sha256",
            "content_sha256",
        },
        schema_version="provider-cycle-terminal/1",
    )


def issue_authorization(
    root: str | Path,
    *,
    cycle_id: str,
    expires_at: str,
    head_revision: str,
    plan_sha256: str,
    pricing_sha256: str,
    runtime_closure_sha256: str,
    current_four_sha256: str,
    backend_image_id: str,
    compose_project: str,
    expected_db_revision: str,
    max_total_cny: str,
) -> dict[str, Any]:
    path = Path(root)
    if path.exists() or path.is_symlink():
        raise ValueError("cycle authorization directory already exists")
    path.mkdir(mode=0o700)
    _fsync_directory(path.parent)
    _safe_root(path)
    safe_cycle_id = _safe_id(cycle_id, "cycle_id")
    _safe_id(compose_project, "compose_project")
    if _HEAD.fullmatch(head_revision) is None:
        raise ValueError("cycle authorization head_revision is invalid")
    for field, value in (
        ("plan_sha256", plan_sha256),
        ("pricing_sha256", pricing_sha256),
        ("runtime_closure_sha256", runtime_closure_sha256),
        ("current_four_sha256", current_four_sha256),
    ):
        _sha256(value, field)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", backend_image_id) is None:
        raise ValueError("cycle authorization backend image identity is invalid")
    if expected_db_revision != "0014" or max_total_cny != "50.000000":
        raise ValueError("cycle authorization fixed boundary is invalid")
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise ValueError("cycle authorization expiry is invalid") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("cycle authorization expiry is invalid")
    return _exclusive_fact(
        path / "issuance.json",
        {
            "schema_version": "provider-cycle-issuance/1",
            "cycle_id": safe_cycle_id,
            "expires_at": expires_at,
            "head_revision": head_revision,
            "plan_sha256": plan_sha256,
            "pricing_sha256": pricing_sha256,
            "runtime_closure_sha256": runtime_closure_sha256,
            "current_four_sha256": current_four_sha256,
            "backend_image_id": backend_image_id,
            "compose_project": compose_project,
            "expected_db_revision": expected_db_revision,
            "max_total_cny": max_total_cny,
        },
    )


def issue_gdt10e_authorization(
    root: str | Path,
    *,
    readiness_sha256: str,
    cycle_id: str,
    expires_at: str,
    head_revision: str,
    plan_sha256: str,
    pricing_sha256: str,
    runtime_closure_sha256: str,
    current_four_sha256: str,
    backend_image_id: str,
    compose_project: str,
    expected_db_revision: str,
    historical_committed_cny: str,
    max_total_cny: str,
    overall_envelope_cny: str,
    plan_ref: str,
    prior_cycle_evidence_sha256: str,
) -> dict[str, Any]:
    """Issue the exact GDT-10E envelope only while readiness is still fresh."""
    if cycle_id != _GDT10E_CYCLE_ID or plan_ref != _GDT10E_PLAN_REF:
        raise ValueError("cycle authorization fixed boundary is invalid")
    if _gdt10e_issuance_now() > _GDT10E_PRICING_DEADLINE:
        raise ValueError("cycle authorization pricing deadline is expired")
    historical = _six_decimal(historical_committed_cny, "historical_committed_cny")
    incremental = _six_decimal(max_total_cny, "max_total_cny")
    envelope = _six_decimal(overall_envelope_cny, "overall_envelope_cny")
    if (
        incremental <= Decimal("0.000000")
        or incremental > Decimal("50.000000")
        or historical + incremental != envelope
        or envelope != Decimal("50.000000")
        or historical != Decimal("3.526656")
        or incremental != Decimal("46.473344")
    ):
        raise ValueError("cycle authorization fixed boundary is invalid")
    readiness_sha256 = _sha256(readiness_sha256, "readiness_sha256")
    if prior_cycle_evidence_sha256 != _GDT10E_PRIOR_CYCLE_EVIDENCE_SHA256:
        raise ValueError("cycle authorization prior_cycle_evidence_sha256 is invalid")
    if _HEAD.fullmatch(head_revision) is None:
        raise ValueError("cycle authorization head_revision is invalid")
    _safe_id(compose_project, "compose_project")
    for field, value in (
        ("plan_sha256", plan_sha256),
        ("pricing_sha256", pricing_sha256),
        ("runtime_closure_sha256", runtime_closure_sha256),
        ("current_four_sha256", current_four_sha256),
    ):
        _sha256(value, field)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", backend_image_id) is None or expected_db_revision != "0014":
        raise ValueError("cycle authorization fixed boundary is invalid")
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise ValueError("cycle authorization expiry is invalid") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("cycle authorization expiry is invalid")
    path = Path(root)
    if path.exists() or path.is_symlink():
        raise ValueError("cycle authorization directory already exists")
    path.mkdir(mode=0o700)
    _fsync_directory(path.parent)
    _safe_root(path)
    return _exclusive_fact(
        path / "issuance.json",
        {
            "schema_version": "provider-cycle-issuance/1",
            "cycle_id": cycle_id,
            "expires_at": expires_at,
            "head_revision": head_revision,
            "plan_sha256": plan_sha256,
            "pricing_sha256": pricing_sha256,
            "runtime_closure_sha256": runtime_closure_sha256,
            "current_four_sha256": current_four_sha256,
            "backend_image_id": backend_image_id,
            "compose_project": compose_project,
            "expected_db_revision": expected_db_revision,
            "max_total_cny": max_total_cny,
            "historical_committed_cny": historical_committed_cny,
            "overall_envelope_cny": overall_envelope_cny,
            "readiness_sha256": readiness_sha256,
            "plan_ref": plan_ref,
            "prior_cycle_evidence_sha256": prior_cycle_evidence_sha256,
        },
    )


def consume_authorization(
    root: str | Path,
    *,
    invocation_id: str | None = None,
) -> dict[str, Any]:
    path = Path(root)
    issuance = _issuance(path)
    _ensure_nonterminal(path)
    return _exclusive_fact(
        path / "consumption.json",
        {
            "schema_version": "provider-cycle-consumption/1",
            "cycle_id": issuance["cycle_id"],
            "issuance_sha256": issuance["content_sha256"],
            "invocation_id": _sha256(
                invocation_id or _new_invocation_id(),
                "invocation_id",
            ),
            "consumed_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def bind_run(root: str | Path, *, run_id: str) -> dict[str, Any]:
    path = Path(root)
    issuance = _issuance(path)
    _ensure_nonterminal(path)
    consumption = _consumption(path, issuance)
    return _exclusive_fact(
        path / "run.json",
        {
            "schema_version": "provider-cycle-run/1",
            "cycle_id": issuance["cycle_id"],
            "run_id": _safe_id(run_id, "run_id"),
            "consumption_sha256": consumption["content_sha256"],
        },
    )


def admit_project(
    root: str | Path,
    *,
    run_id: str,
    project_id: str,
    project_order: int,
    source_sha256: str,
) -> dict[str, Any]:
    path = Path(root)
    issuance = _issuance(path)
    _ensure_nonterminal(path)
    run = _run(path, issuance)
    if run["run_id"] != run_id:
        raise ValueError("cycle authorization run identity is invalid")
    safe_project_id = _safe_id(project_id, "project_id")
    if isinstance(project_order, bool) or not isinstance(project_order, int) or not 1 <= project_order <= 4:
        raise ValueError("cycle authorization project_order is invalid")
    source = _sha256(source_sha256, "source_sha256")
    projects = path / "projects"
    if not projects.exists():
        projects.mkdir(mode=0o700)
        _fsync_directory(path)
    _safe_root(projects)
    for existing_path in projects.iterdir():
        existing = _read_fact(
            existing_path,
            keys={
                "schema_version",
                "cycle_id",
                "run_id",
                "project_id",
                "project_order",
                "source_sha256",
                "run_sha256",
                "content_sha256",
            },
            schema_version="provider-cycle-project/1",
        )
        if existing["project_id"] == safe_project_id or existing["project_order"] == project_order:
            raise ValueError("cycle authorization project is already admitted")
    return _exclusive_fact(
        projects / f"{project_order:04d}.json",
        {
            "schema_version": "provider-cycle-project/1",
            "cycle_id": issuance["cycle_id"],
            "run_id": run_id,
            "project_id": safe_project_id,
            "project_order": project_order,
            "source_sha256": source,
            "run_sha256": run["content_sha256"],
        },
    )


def consume_resume(
    root: str | Path,
    *,
    run_id: str,
    pause_evidence_sha256: str,
    invocation_id: str | None = None,
) -> dict[str, Any]:
    path = Path(root)
    issuance = _issuance(path)
    _ensure_nonterminal(path)
    _ensure_no_cleanup_blocker(path)
    run = _run(path, issuance)
    if run["run_id"] != run_id:
        raise ValueError("cycle authorization run identity is invalid")
    _pause_handoff(
        path,
        run_id=run_id,
        pause_evidence_sha256=pause_evidence_sha256,
    )
    return _exclusive_fact(
        path / "resume-consumed.json",
        {
            "schema_version": "provider-cycle-resume-consumed/1",
            "cycle_id": issuance["cycle_id"],
            "run_id": run_id,
            "pause_evidence_sha256": _sha256(
                pause_evidence_sha256, "pause_evidence_sha256"
            ),
            "run_sha256": run["content_sha256"],
            "invocation_id": _sha256(
                invocation_id or _new_invocation_id(),
                "invocation_id",
            ),
            "resumed_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def close_via_bridge(
    root: str | Path,
    *,
    run_id: str,
    status: str,
    quiescence_sha256: str,
) -> dict[str, Any]:
    path = Path(root)
    issuance = _issuance(path, require_active=False)
    run_path = path / "run.json"
    run = (
        _run(path, issuance)
        if run_path.exists() or run_path.is_symlink()
        else None
    )
    if run is not None and run["run_id"] != run_id:
        raise ValueError("cycle close bridge run identity is invalid")
    projects_root = path / "projects"
    project: dict[str, Any] | None = None
    if projects_root.exists() or projects_root.is_symlink():
        _safe_root(projects_root)
        project_paths = sorted(projects_root.iterdir())
        if project_paths:
            if run is None:
                raise ValueError("cycle close bridge project has no run binding")
            project = _read_fact(
                project_paths[0],
                keys={
                    "schema_version",
                    "cycle_id",
                    "run_id",
                    "project_id",
                    "project_order",
                    "source_sha256",
                    "run_sha256",
                    "content_sha256",
                },
                schema_version="provider-cycle-project/1",
            )
    try:
        image_id = _current_api_image_id()
    except ValueError as exc:
        raise RuntimeError(
            "cycle close bridge image identity is invalid"
        ) from exc
    if image_id != issuance["backend_image_id"]:
        raise RuntimeError("cycle close bridge image identity is invalid")
    storage_volume = f"{issuance['compose_project']}_storage_qa_dev"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "0:0",
        "--mount",
        f"type=volume,src={storage_volume},dst=/data",
        "--mount",
        f"type=bind,src={path.resolve()},dst=/auth",
        image_id,
        "python",
        "-m",
        "app.providers.cycle_close_bridge",
        "--cycle-id",
        str(issuance["cycle_id"]),
        "--run-id",
        run_id,
        "--status",
        status,
        "--quiescence-sha256",
        quiescence_sha256,
    ]
    if project is not None:
        command.extend(("--project-id", str(project["project_id"])))
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        terminal = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("cycle close bridge evidence is invalid") from exc
    persisted_run = _run(path, issuance)
    if (
        result.returncode != 0
        or not isinstance(terminal, dict)
        or terminal.get("cycle_id") != issuance["cycle_id"]
        or terminal.get("run_id") != run_id
        or terminal.get("status") != status
        or terminal.get("quiescence_sha256") != quiescence_sha256
        or persisted_run.get("run_id") != run_id
        or terminal.get("run_sha256") != persisted_run["content_sha256"]
        or terminal.get("content_sha256") != _canonical_hash(terminal)
    ):
        raise RuntimeError("cycle close bridge evidence is inconsistent")
    _write_close_bridge_evidence(
        run_id=run_id,
        image_id=image_id,
        storage_volume=storage_volume,
        authorization_root=path,
        terminal=terminal,
    )
    return terminal


def _write_close_bridge_evidence(
    *,
    run_id: str,
    image_id: str,
    storage_volume: str,
    authorization_root: Path,
    terminal: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = ROOT / ".agent/harness/runs" / run_id
    reports = run_dir / "reports"
    if (
        run_dir.is_symlink()
        or not run_dir.is_dir()
        or reports.is_symlink()
        or not reports.is_dir()
    ):
        raise ValueError("cycle close bridge run evidence directory is invalid")
    owner = authorization_root.stat()
    document = {
        "schema_version": "provider-cycle-close-bridge/1",
        "run_id": run_id,
        "image_id": image_id,
        "storage_volume": storage_volume,
        "network": "none",
        "container_user": "0:0",
        "authorization_owner_uid": owner.st_uid,
        "authorization_owner_gid": owner.st_gid,
        "mounts": [
            {"type": "volume", "target": "/data", "mode": "rw"},
            {"type": "bind", "target": "/auth", "mode": "rw"},
        ],
        "terminal_sha256": terminal["content_sha256"],
    }
    report_path = reports / "provider-cycle-close-bridge.json"
    expected = _hashed(document)
    if report_path.exists() or report_path.is_symlink():
        current = _read_fact(
            report_path,
            keys=set(expected),
            schema_version="provider-cycle-close-bridge/1",
        )
        if current != expected:
            raise ValueError("cycle close bridge evidence conflicts")
        return current
    return _exclusive_fact(report_path, document)


def close_paid_cycle(
    root: str | Path,
    *,
    run_id: str | None,
    status: str,
    quiescence_sha256: str,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("paid cycle close run identity is invalid")
    return close_via_bridge(
        root,
        run_id=run_id,
        status=status,
        quiescence_sha256=quiescence_sha256,
    )


def _validate_private_file(path: Path, field: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"{field} is invalid") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_gid != os.getgid()
    ):
        raise ValueError(f"{field} is invalid")


def _runtime_closure_sha256() -> str:
    manifest_path = ROOT / ".agent/harness/policy/gdt10d-runtime-closure.txt"
    try:
        content = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("paid cycle runtime closure manifest is invalid") from exc
    components = []
    previous = ""
    for line in content.splitlines():
        match = _RUNTIME_MANIFEST_LINE.fullmatch(line)
        if match is None or match["path"] <= previous:
            raise ValueError("paid cycle runtime closure manifest is invalid")
        path = ROOT / match["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != match["sha256"]
        ):
            raise ValueError("paid cycle runtime closure manifest is stale")
        previous = match["path"]
        components.append(
            {"path": match["path"], "sha256": match["sha256"]}
        )
    if not components or not content.endswith("\n"):
        raise ValueError("paid cycle runtime closure manifest is invalid")
    return hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _current_four_manifest_sha256() -> str:
    schema = json.loads(
        (
            ROOT / ".agent/harness/schemas/current-four-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    entries = []
    for item in schema["properties"]["entries"]["prefixItems"]:
        properties = item["allOf"][1]["properties"]
        entries.append(
            {
                "order": properties["order"]["const"],
                "basename": properties["basename"]["const"],
                "sha256": properties["sha256"]["const"],
                "opaque_ref": properties["opaque_ref"]["const"],
                "page_metadata": properties["page_metadata"]["const"],
            }
        )
    manifest = {
        "schema_version": "current-four-manifest/1",
        "input_set": "current-four",
        "first_checkpoint": {
            key: entries[0][key]
            for key in ("order", "basename", "sha256", "opaque_ref")
        },
        "entries": entries,
    }
    content = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _current_api_image_id() -> str:
    result = subprocess.run(
        [*_compose_command(), "images", "-q", "api"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    image_id = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{64}", image_id) is not None:
        image_id = f"sha256:{image_id}"
    if (
        result.returncode != 0
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
    ):
        raise ValueError("paid cycle backend image identity is invalid")
    return image_id


def _gdt10e_runtime_acceptance_path(run_id: str) -> Path:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("GDT-10E run identity is invalid")
    return (
        ROOT
        / ".agent/harness/runs"
        / run_id
        / "reports/provider-account-runtime-acceptance.json"
    )


def _validate_gdt10e_readiness(
    root: Path,
    issuance: Mapping[str, Any],
    *,
    phase: str,
    run_id: str | None = None,
) -> None:
    authorization_path = _gdt10e_private_path(root, "authorization")
    readiness_path = _gdt10e_private_path(
        _GDT10E_PRIVATE_ROOT / "account-readiness.json", "readiness"
    )
    if authorization_path != Path(root):
        raise ValueError("GDT-10E authorization binding is invalid")
    expected_readiness_sha256 = _sha256(
        issuance.get("readiness_sha256"), "readiness_sha256"
    )
    module = _provider_account_readiness_module()
    runtime_acceptance = None
    if phase == "resume":
        if not isinstance(run_id, str):
            raise ValueError("GDT-10E run identity is invalid")
        runtime_acceptance = _gdt10e_runtime_acceptance_path(run_id)
    evidence = module.validate_account_readiness(
        root=_GDT10E_PRIVATE_ROOT,
        cycle_id=_GDT10E_CYCLE_ID,
        model="qwen3-vl-plus-2025-12-19",
        region="cn-beijing",
        max_incremental_cny="46.473344",
        environment=os.environ,
        phase=phase,
        expected_content_sha256=expected_readiness_sha256,
        runtime_acceptance=runtime_acceptance,
    )
    if evidence.content_sha256 != expected_readiness_sha256:
        raise ValueError("GDT-10E readiness binding is invalid")
    _validate_private_file(readiness_path, "GDT-10E readiness")


def _validate_gdt10e_issuance(
    root: Path,
    issuance: Mapping[str, Any],
    *,
    phase: str,
    run_id: str | None = None,
) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    identity = _gdt10e_committed_identity()
    report = _read_fact(
        _gdt10e_private_path(
            _GDT10E_PRIVATE_ROOT / "zero-paid-readiness.json", "zero_paid_report"
        ),
        keys={
            "schema_version", "cycle_id", "preparation_sha256", "readiness_sha256",
            "no_delta_proved", "head_revision", "plan_sha256", "pricing_sha256",
            "runtime_closure_sha256", "current_four_sha256", "backend_image_id",
            "compose_project", "content_sha256",
        },
        schema_version="provider-cycle-zero-paid-readiness/1",
    )
    identity_fields = (
        "head_revision", "plan_sha256", "pricing_sha256", "runtime_closure_sha256",
        "current_four_sha256", "backend_image_id", "compose_project",
    )
    if (
        status.returncode != 0
        or status.stdout
        or issuance.get("plan_ref") != _GDT10E_PLAN_REF
        or issuance.get("historical_committed_cny") != "3.526656"
        or issuance.get("max_total_cny") != "46.473344"
        or issuance.get("overall_envelope_cny") != "50.000000"
        or report.get("cycle_id") != _GDT10E_CYCLE_ID
        or report.get("no_delta_proved") is not True
        or any(issuance.get(field) != identity[field] for field in identity_fields)
        or any(report.get(field) != identity[field] for field in identity_fields)
        or report.get("readiness_sha256") != issuance.get("readiness_sha256")
    ):
        raise ValueError("GDT-10E issuance does not match the committed runtime")
    _validate_gdt10e_readiness(root, issuance, phase=phase, run_id=run_id)


def validate_issuance_for_start(
    root: Path,
    *,
    phase: str = "start",
    run_id: str | None = None,
) -> None:
    issuance = _issuance(root)
    if issuance["cycle_id"] == _GDT10E_CYCLE_ID:
        _validate_gdt10e_issuance(root, issuance, phase=phase, run_id=run_id)
        return
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    plan_path = (
        ROOT
        / "docs/superpowers/plans/2026-08-02-gdt10d-classified-provider-live-verification.md"
    )
    pricing_path = ROOT / "backend/app/providers/provider_pricing_gdt10d_v1.json"
    try:
        pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("paid cycle pricing identity is invalid") from exc
    if (
        status.returncode != 0
        or status.stdout
        or revision.returncode != 0
        or issuance["head_revision"] != revision.stdout.strip()
        or issuance["plan_sha256"]
        != hashlib.sha256(plan_path.read_bytes()).hexdigest()
        or not isinstance(pricing, Mapping)
        or pricing.get("content_sha256") != _canonical_hash(pricing)
        or issuance["pricing_sha256"] != pricing.get("content_sha256")
        or issuance["runtime_closure_sha256"] != _runtime_closure_sha256()
        or issuance["current_four_sha256"]
        != _current_four_manifest_sha256()
        or issuance["backend_image_id"] != _current_api_image_id()
        or issuance["compose_project"]
        != os.environ.get("COMPOSE_PROJECT_NAME", "").strip()
        or issuance["expected_db_revision"] != "0014"
        or issuance["max_total_cny"] != "50.000000"
    ):
        raise ValueError("paid cycle issuance does not match the committed runtime")


def _validate_execution_boundary(
    root: Path,
    *,
    phase: str,
    run_id: str | None,
    validate_issuance: Callable[[Path], None] | None,
) -> None:
    if validate_issuance is not None:
        validate_issuance(root)
        return
    validate_issuance_for_start(root, phase=phase, run_id=run_id)


def validate_live_override(path: Path, authorization_root: Path) -> None:
    """Validate only key/mount shape; never print resolved values."""
    _validate_private_file(path, "live override")
    issuance = _issuance(authorization_root)
    expected_source = str(authorization_root.resolve())
    if (ROOT / ".env").exists() or (ROOT / ".env").is_symlink():
        raise ValueError("worktree .env is forbidden for paid live execution")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("live override is invalid") from exc
    services = document.get("services") if isinstance(document, Mapping) else None
    if not isinstance(services, Mapping) or set(services) != {"api", "worker"}:
        raise ValueError("live override service set is invalid")
    expected_keys = {
        "QI_TENCENT_SECRET_ID",
        "QI_TENCENT_SECRET_KEY",
        "QI_QWEN_API_KEY",
        "QI_QWEN_WORKSPACE_ID",
        "QI_SYMBOL_RECOGNITION_MODE",
        "QI_QWEN_MODEL",
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID",
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
    }
    expected_root = "/run/qi-live-authorization"
    for service_name in ("api", "worker"):
        service = services.get(service_name)
        environment = service.get("environment") if isinstance(service, Mapping) else None
        volumes = service.get("volumes") if isinstance(service, Mapping) else None
        if not isinstance(environment, Mapping) or set(environment) != expected_keys:
            raise ValueError("live override environment key set is invalid")
        if (
            any(not isinstance(environment[key], str) or not environment[key] for key in expected_keys)
            or environment["QI_SYMBOL_RECOGNITION_MODE"] != "production_uncertainty"
            or environment["QI_QWEN_MODEL"] != "qwen3-vl-plus-2025-12-19"
            or environment["QI_PROVIDER_CYCLE_AUTHORIZATION_ID"]
            != issuance["cycle_id"]
            or environment["QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT"] != expected_root
        ):
            raise ValueError("live override environment identity is invalid")
        if (
            not isinstance(volumes, list)
            or len(volumes) != 1
            or not isinstance(volumes[0], Mapping)
            or set(volumes[0]) != {"type", "source", "target", "read_only"}
            or volumes[0].get("type") != "bind"
            or volumes[0].get("source") != expected_source
            or volumes[0].get("target") != expected_root
            or volumes[0].get("read_only") is not True
        ):
            raise ValueError("live override authorization mount is invalid")


def validate_safe_override(path: Path) -> None:
    """Validate the credential-free override without exposing values."""
    _validate_private_file(path, "safe override")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("safe override is invalid") from exc
    services = document.get("services") if isinstance(document, Mapping) else None
    if not isinstance(services, Mapping) or set(services) != {"api", "worker"}:
        raise ValueError("safe override service set is invalid")
    for service_name in ("api", "worker"):
        service = services.get(service_name)
        if not isinstance(service, Mapping) or set(service) != {"environment"}:
            raise ValueError("safe override service shape is invalid")
        environment = service.get("environment")
        if (
            not isinstance(environment, Mapping)
            or dict(environment) != _SAFE_RUNTIME_ENVIRONMENT
        ):
            raise ValueError("safe override environment identity is invalid")


def _live_override_authorization_root(path: Path) -> Path:
    _validate_private_file(path, "live override")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = document["services"]
        api_volumes = services["api"]["volumes"]
        source = api_volumes[0]["source"]
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("live override authorization source is invalid") from exc
    if not isinstance(source, str) or not source:
        raise ValueError("live override authorization source is invalid")
    root = Path(source)
    validate_live_override(path, root)
    return root


def _prove_safe_runtime_identity(service_name: str) -> None:
    result = subprocess.run(
        [
            *_compose_command(),
            "exec",
            "-T",
            service_name,
            "python",
            "-c",
            _RUNTIME_CONTROL_IDENTITY_PROGRAM,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("safe runtime identity proof failed") from exc
    if (
        result.returncode != 0
        or not isinstance(identity, Mapping)
        or set(identity)
        != {
            "credential_keys_present",
            "cycle_keys_present",
            "authorization_mount_present",
            "mode",
            "model",
        }
        or identity.get("credential_keys_present") != []
        or identity.get("cycle_keys_present") != []
        or identity.get("authorization_mount_present") is not False
        or identity.get("mode")
        != _SAFE_RUNTIME_ENVIRONMENT["QI_SYMBOL_RECOGNITION_MODE"]
        or identity.get("model")
        != _SAFE_RUNTIME_ENVIRONMENT["QI_QWEN_MODEL"]
    ):
        raise RuntimeError("safe runtime identity proof failed")


def _prove_live_runtime_identity(service_name: str, cycle_id: str) -> None:
    result = subprocess.run(
        [
            *_compose_command(),
            "exec",
            "-T",
            service_name,
            "python",
            "-c",
            _LIVE_RUNTIME_CONTROL_IDENTITY_PROGRAM,
            cycle_id,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("paid runtime identity proof failed") from exc
    if (
        result.returncode != 0
        or not isinstance(identity, Mapping)
        or set(identity)
        != {
            "credential_keys_present",
            "cycle_keys_present",
            "authorization_mount_present",
            "authorization_mount_read_only",
            "cycle_id_matches",
            "authorization_root_matches",
            "mode",
            "model",
        }
        or identity.get("credential_keys_present")
        != sorted(_LIVE_CREDENTIAL_KEYS)
        or identity.get("cycle_keys_present")
        != sorted(_CYCLE_RUNTIME_KEYS)
        or identity.get("authorization_mount_present") is not True
        or identity.get("authorization_mount_read_only") is not True
        or identity.get("cycle_id_matches") is not True
        or identity.get("authorization_root_matches") is not True
        or identity.get("mode")
        != _SAFE_RUNTIME_ENVIRONMENT["QI_SYMBOL_RECOGNITION_MODE"]
        or identity.get("model")
        != _SAFE_RUNTIME_ENVIRONMENT["QI_QWEN_MODEL"]
    ):
        raise RuntimeError("paid runtime identity proof failed")


def _compose_command(*extra_files: Path) -> list[str]:
    command = [
        "docker",
        "compose",
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.qa-dev.yaml"),
    ]
    for path in extra_files:
        command.extend(("-f", str(path)))
    return command


def activate_runtime(override: Path) -> None:
    safe_ref = os.environ.get("QI_LIVE_CYCLE_SAFE_OVERRIDE_REF", "").strip()
    if not safe_ref:
        raise ValueError("safe override reference is required")
    safe_override = Path(safe_ref)
    validate_safe_override(safe_override)
    authorization_root = _live_override_authorization_root(override)
    cycle_id = str(_issuance(authorization_root)["cycle_id"])
    result = subprocess.run(
        [
            *_compose_command(safe_override, override),
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "api",
            "worker",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("paid runtime activation failed")
    for service_name in ("api", "worker"):
        _prove_live_runtime_identity(service_name, cycle_id)


def _activate_safe_runtime(safe_override: Path) -> None:
    result = subprocess.run(
        [
            *_compose_command(safe_override),
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "api",
            "worker",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("safe runtime activation failed")
    for service_name in ("api", "worker"):
        _prove_safe_runtime_identity(service_name)


def deactivate_runtime() -> None:
    safe_ref = os.environ.get("QI_LIVE_CYCLE_SAFE_OVERRIDE_REF", "").strip()
    if not safe_ref:
        raise ValueError("safe override reference is required")
    safe_override = Path(safe_ref)
    validate_safe_override(safe_override)
    _activate_safe_runtime(safe_override)


def _delete_private_control_file(path: Path, field: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    _validate_private_file(path, field)
    path.unlink()
    _fsync_directory(path.parent)


def cleanup_runtime_controls(override: Path) -> None:
    """Remove private overrides and this process's inherited controls."""
    safe_ref = os.environ.get("QI_LIVE_CYCLE_SAFE_OVERRIDE_REF", "").strip()
    failures = False
    paths = [override]
    if safe_ref:
        paths.append(Path(safe_ref))
    else:
        failures = True
    seen: set[Path] = set()
    try:
        for index, path in enumerate(paths):
            resolved = path.absolute()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                _delete_private_control_file(
                    path,
                    "live override" if index == 0 else "safe override",
                )
            except (OSError, ValueError):
                failures = True
    finally:
        for key in _HOST_CONTROL_KEYS:
            os.environ.pop(key, None)
    if (ROOT / ".env").exists() or (ROOT / ".env").is_symlink():
        failures = True
    if failures:
        raise RuntimeError("private runtime control cleanup failed")


def check_head_contracts() -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("paid live execution requires a clean committed HEAD")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".agent/harness/scripts/check-contracts.py"),
            "--runtime-closure-source",
            "HEAD",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("committed contract/runtime closure check failed")


def _run_state(run_id: str | None) -> str:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        return "failed"
    run_path = ROOT / ".agent/harness/runs" / run_id / "run.json"
    if run_path.is_symlink() or not run_path.is_file():
        return "failed"
    try:
        document = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "failed"
    state = document.get("execution_state")
    return str(state) if isinstance(state, str) else "failed"


def prove_run_quiescence(run_id: str, status: str) -> str:
    if _RUN_ID.fullmatch(run_id) is None or status not in {
        "completed",
        "failed",
        "aborted",
    }:
        raise ValueError("paid cycle quiescence identity is invalid")
    run_dir = ROOT / ".agent/harness/runs" / run_id
    if run_dir.is_symlink():
        raise ValueError("paid cycle run directory is invalid")
    if not run_dir.exists():
        run_dir.mkdir(mode=0o700)
        (run_dir / "reports").mkdir(mode=0o700)
    elif not run_dir.is_dir():
        raise ValueError("paid cycle run directory is invalid")
    reports = run_dir / "reports"
    if reports.is_symlink() or not reports.is_dir():
        raise ValueError("paid cycle run reports directory is invalid")
    celery = subprocess.run(
        [
            *_compose_command(),
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            _QUIESCENCE_PROGRAM,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    queue = subprocess.run(
        [
            *_compose_command(),
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "LLEN",
            "celery",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        inspections = json.loads(celery.stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        inspections = None
    try:
        queue_depth = int(queue.stdout.strip())
    except (TypeError, ValueError):
        queue_depth = -1
    worker_sets: dict[str, list[str]] = {}
    inspection_quiet = (
        celery.returncode == 0
        and isinstance(inspections, Mapping)
        and set(inspections) == {"active", "reserved", "scheduled"}
    )
    if inspection_quiet:
        for category in ("active", "reserved", "scheduled"):
            workers = inspections.get(category)
            if (
                not isinstance(workers, Mapping)
                or not workers
                or any(
                    not isinstance(items, list) or items
                    for items in workers.values()
                )
            ):
                inspection_quiet = False
                break
            worker_sets[category] = sorted(str(name) for name in workers)
    worker_stopped = False
    if not inspection_quiet or queue.returncode != 0 or queue_depth != 0:
        stop = subprocess.run(
            [*_compose_command(), "stop", "worker"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        running = subprocess.run(
            [*_compose_command(), "ps", "--status", "running", "--services"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        queue = subprocess.run(
            [
                *_compose_command(),
                "exec",
                "-T",
                "redis",
                "redis-cli",
                "LLEN",
                "celery",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            queue_depth = int(queue.stdout.strip())
        except (TypeError, ValueError) as exc:
            raise RuntimeError("paid cycle quiescence evidence is invalid") from exc
        running_services = set(running.stdout.split())
        if (
            stop.returncode != 0
            or running.returncode != 0
            or "worker" in running_services
            or queue.returncode != 0
            or queue_depth != 0
        ):
            raise RuntimeError("paid cycle is not quiescent")
        worker_stopped = True
        worker_sets = {
            category: [] for category in ("active", "reserved", "scheduled")
        }
    document = {
        "schema_version": "provider-cycle-quiescence/1",
        "run_id": run_id,
        "status": status,
        "harness_returned": True,
        "queue_depth": queue_depth,
        "worker_sets": worker_sets,
        "worker_stopped": worker_stopped,
    }
    document["content_sha256"] = _canonical_hash(document)
    report_path = reports / "provider-cycle-quiescence.json"
    _exclusive_fact(report_path, document)
    persisted = _read_fact(
        report_path,
        keys=set(document),
        schema_version="provider-cycle-quiescence/1",
    )
    return str(persisted["content_sha256"])


def run_finalize_harness(run_id: str, status: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".agent/harness/scripts/run-p0.py"),
            "live",
            "--scope",
            "full-p0",
            "--finalize-run",
            run_id,
            "--terminal-status",
            status,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": result.returncode,
        "run_id": run_id,
        "execution_state": _run_state(run_id),
    }


def run_start_harness(run_id: str) -> dict[str, Any]:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("paid cycle run identity is invalid")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".agent/harness/scripts/run-p0.py"),
            "live",
            "--scope",
            "full-p0",
            "--input-set",
            "current-four",
            "--activate-current-inputs",
            "--pause-after",
            "first-pdf-balloons",
            "--print-run-id-only",
            "--authorized-run-id",
            run_id,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(
        r"(?:run_id=)?([0-9]{8}T[0-9]{12}Z-[0-9a-f]{8})",
        result.stdout + "\n" + result.stderr,
    )
    return {
        "returncode": result.returncode,
        "run_id": match.group(1) if match else None,
        "execution_state": _run_state(match.group(1) if match else None),
    }


def _quiescence_hash(run_id: str | None, status: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {"harness_returned": True, "run_id": run_id, "status": status},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _bound_run_id(root: Path) -> str | None:
    try:
        evidence = authorization_evidence(root, require_run=True)
    except (OSError, ValueError):
        return None
    run_id = evidence.get("run_id")
    return str(run_id) if isinstance(run_id, str) else None


def bound_run_id(authorization: str | Path) -> str:
    """Return the one durable GDT-10E run binding without Harness discovery."""
    path = _gdt10e_private_path(authorization, "authorization")
    evidence = authorization_evidence(path, require_run=True)
    if evidence.get("cycle_id") != _GDT10E_CYCLE_ID:
        raise ValueError("GDT-10E authorization binding is invalid")
    run_id = evidence.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("GDT-10E run binding is invalid")
    return run_id


def _record_cleanup_blocker(
    root: Path,
    *,
    run_id: str,
    status: str,
    failure_codes: list[str],
) -> dict[str, Any]:
    allowed_codes = {
        "quiescence_close_or_finalize_failed",
        "safe_deactivation_failed",
        "private_control_cleanup_failed",
        "pause_handoff_failed",
    }
    if (
        _RUN_ID.fullmatch(run_id) is None
        or status not in {"completed", "failed", "aborted", "paused"}
        or not failure_codes
        or len(failure_codes) != len(set(failure_codes))
        or any(code not in allowed_codes for code in failure_codes)
    ):
        raise ValueError("paid cycle cleanup blocker is invalid")
    issuance = _issuance(root, require_active=False)
    document = {
        "schema_version": "provider-cycle-cleanup-blocker/1",
        "cycle_id": issuance["cycle_id"],
        "run_id": run_id,
        "status": status,
        "failure_codes": failure_codes,
    }
    path = root / "cleanup-blocker.json"
    try:
        return _exclusive_fact(path, document)
    except ValueError:
        existing = _read_fact(
            path,
            keys={*document, "content_sha256"},
            schema_version="provider-cycle-cleanup-blocker/1",
        )
        if any(existing.get(key) != value for key, value in document.items()):
            raise ValueError("paid cycle cleanup blocker conflicts") from None
        return existing


def execute_start(
    root: str | Path,
    *,
    override: Path,
    validate_override: Callable[[Path, Path], None] = validate_live_override,
    validate_issuance: Callable[[Path], None] | None = None,
    new_run_id: Callable[[], str] = _new_cycle_run_id,
    bind_run_state: Callable[..., dict[str, Any]] = bind_run,
    activate_runtime: Callable[[Path], None] = activate_runtime,
    check_contracts: Callable[[], None] = check_head_contracts,
    run_harness: Callable[[str], dict[str, Any]] = run_start_harness,
    prove_quiescence: Callable[[str, str], str] = prove_run_quiescence,
    finalize_harness: Callable[[str, str], dict[str, Any]] = run_finalize_harness,
    deactivate_runtime: Callable[[], None] = deactivate_runtime,
    cleanup_controls: Callable[[Path], None] = cleanup_runtime_controls,
    validate_pause: Callable[[str], str] | None = None,
    close_cycle: Callable[..., Any] = close_paid_cycle,
) -> int:
    path = Path(root)
    invocation_id = _new_invocation_id()
    run_id = new_run_id()
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("paid cycle run identity is invalid")
    outcome: dict[str, Any] = {
        "returncode": 1,
        "run_id": run_id,
        "execution_state": "failed",
    }
    close_required = True
    consumed = False
    cleanup_failures: list[str] = []
    primary_error: BaseException | None = None
    try:
        validate_override(override, path)
        _validate_execution_boundary(
            path,
            phase="start",
            run_id=None,
            validate_issuance=validate_issuance,
        )
        consume_authorization(path, invocation_id=invocation_id)
        consumed = True
        bind_run_state(path, run_id=run_id)
        _validate_execution_boundary(
            path,
            phase="start",
            run_id=run_id,
            validate_issuance=validate_issuance,
        )
        activate_runtime(override)
        _validate_execution_boundary(
            path,
            phase="start",
            run_id=run_id,
            validate_issuance=validate_issuance,
        )
        check_contracts()
        outcome = run_harness(run_id)
        if outcome.get("run_id") != run_id:
            raise RuntimeError("paid Harness returned a different run identity")
        close_required = not (
            outcome.get("returncode") == 0
            and outcome.get("execution_state") == "visual_qa_pending"
        )
    except BaseException as exc:
        primary_error = exc
        close_required = True
        if not consumed:
            try:
                consumption = _consumption(
                    path,
                    _issuance(path, require_active=False),
                )
                consumed = consumption["invocation_id"] == invocation_id
            except (OSError, ValueError):
                consumed = False
    finally:
        if consumed and close_required:
            try:
                run_id = outcome.get("run_id") or _bound_run_id(path)
                quiescence_sha256 = (
                    prove_quiescence(str(run_id), "failed")
                    if isinstance(run_id, str)
                    else _quiescence_hash(None, "failed")
                )
                close_cycle(
                    path,
                    run_id=run_id,
                    status="failed",
                    quiescence_sha256=quiescence_sha256,
                )
                run_record = (
                    ROOT / ".agent/harness/runs" / str(run_id) / "run.json"
                )
                if (
                    isinstance(run_id, str)
                    and not run_record.is_symlink()
                    and run_record.is_file()
                ):
                    finalized = finalize_harness(run_id, "failed")
                    if finalized.get("execution_state") != "failed":
                        raise RuntimeError("paid failed run finalization failed")
            except BaseException:
                cleanup_failures.append(
                    "quiescence_close_or_finalize_failed"
                )
        if consumed:
            try:
                deactivate_runtime()
            except BaseException:
                cleanup_failures.append("safe_deactivation_failed")
        try:
            cleanup_controls(override)
        except BaseException:
            cleanup_failures.append("private_control_cleanup_failed")
    if not consumed and primary_error is not None:
        if cleanup_failures:
            raise RuntimeError("paid cycle pre-consume cleanup failed") from primary_error
        raise primary_error
    if not close_required and not cleanup_failures:
        try:
            pause_evidence_sha256 = (validate_pause or validate_paused_run)(
                run_id
            )
            record_pause_handoff(
                path,
                run_id=run_id,
                pause_evidence_sha256=pause_evidence_sha256,
            )
        except BaseException:
            cleanup_failures.append("pause_handoff_failed")
    if cleanup_failures:
        try:
            _record_cleanup_blocker(
                path,
                run_id=run_id,
                status="failed" if close_required else "paused",
                failure_codes=cleanup_failures,
            )
        except BaseException as exc:
            raise RuntimeError(
                "paid cycle cleanup blocker persistence failed"
            ) from exc
        return 2
    return 0 if not close_required else 1


def validate_paused_run(run_id: str) -> str:
    safe_run_id = _safe_id(run_id, "run_id")
    run_dir = ROOT / ".agent/harness/runs" / safe_run_id
    run_path = run_dir / "run.json"
    live_path = run_dir / "live-run-evidence.json"
    if (
        run_dir.is_symlink()
        or not run_dir.is_dir()
        or run_path.is_symlink()
        or live_path.is_symlink()
        or not run_path.is_file()
        or not live_path.is_file()
    ):
        raise ValueError("paused live run evidence is unavailable")
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("paused live run evidence is invalid") from exc
    if (
        not isinstance(run, Mapping)
        or run.get("run_id") != safe_run_id
        or run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("execution_state") != "visual_qa_pending"
        or run.get("completed_at") is not None
        or not isinstance(run.get("pause_identity"), Mapping)
    ):
        raise ValueError("paused live run is not resumable")
    return hashlib.sha256(live_path.read_bytes()).hexdigest()


def run_resume_harness(run_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".agent/harness/scripts/run-p0.py"),
            "live",
            "--scope",
            "full-p0",
            "--resume-run",
            run_id,
            "--design-qa",
            str(ROOT / "design-qa.md"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": result.returncode,
        "run_id": run_id,
        "execution_state": _run_state(run_id),
    }


def execute_resume(
    root: str | Path,
    *,
    override: Path,
    run_id: str,
    validate_override: Callable[[Path, Path], None] = validate_live_override,
    validate_issuance: Callable[[Path], None] | None = None,
    validate_pause: Callable[[str], str] = validate_paused_run,
    activate_runtime: Callable[[Path], None] = activate_runtime,
    check_contracts: Callable[[], None] = check_head_contracts,
    run_harness: Callable[[str], dict[str, Any]] = run_resume_harness,
    prove_quiescence: Callable[[str, str], str] = prove_run_quiescence,
    finalize_harness: Callable[[str, str], dict[str, Any]] = run_finalize_harness,
    deactivate_runtime: Callable[[], None] = deactivate_runtime,
    cleanup_controls: Callable[[Path], None] = cleanup_runtime_controls,
    close_cycle: Callable[..., Any] = close_paid_cycle,
) -> int:
    path = Path(root)
    invocation_id = _new_invocation_id()
    pause_evidence_sha256: str | None = None
    outcome: dict[str, Any] = {
        "returncode": 1,
        "run_id": run_id,
        "execution_state": "failed",
    }
    resumed = False
    cleanup_failures: list[str] = []
    try:
        validate_override(override, path)
        _validate_execution_boundary(
            path,
            phase="resume",
            run_id=run_id,
            validate_issuance=validate_issuance,
        )
        pause_evidence_sha256 = validate_pause(run_id)
        consume_resume(
            path,
            run_id=run_id,
            pause_evidence_sha256=pause_evidence_sha256,
            invocation_id=invocation_id,
        )
        resumed = True
        _validate_execution_boundary(
            path,
            phase="resume",
            run_id=run_id,
            validate_issuance=validate_issuance,
        )
        activate_runtime(override)
        _validate_execution_boundary(
            path,
            phase="resume",
            run_id=run_id,
            validate_issuance=validate_issuance,
        )
        check_contracts()
        outcome = run_harness(run_id)
    except BaseException:
        if not resumed:
            try:
                if pause_evidence_sha256 is None:
                    raise ValueError("pause evidence was not validated")
                resume = _resume_consumption(
                    path,
                    run_id=run_id,
                    require_active=False,
                )
                resumed = (
                    resume.get("pause_evidence_sha256")
                    == pause_evidence_sha256
                    and resume.get("invocation_id") == invocation_id
                )
            except (OSError, ValueError):
                resumed = False
    if not resumed:
        try:
            cleanup_controls(override)
        except BaseException as exc:
            raise RuntimeError(
                "paid resume pre-consume cleanup failed"
            ) from exc
        return 1
    status = (
        "completed"
        if outcome.get("returncode") == 0
        and outcome.get("execution_state") == "terminal_pending"
        else "failed"
    )
    try:
        quiescence_sha256 = prove_quiescence(run_id, status)
        close_cycle(
            path,
            run_id=run_id,
            status=status,
            quiescence_sha256=quiescence_sha256,
        )
        finalized = finalize_harness(run_id, status)
        expected_state = "completed" if status == "completed" else "failed"
        if finalized.get("execution_state") != expected_state:
            raise RuntimeError("paid run finalization failed")
    except BaseException:
        cleanup_failures.append("quiescence_close_or_finalize_failed")
    try:
        deactivate_runtime()
    except BaseException:
        cleanup_failures.append("safe_deactivation_failed")
    try:
        cleanup_controls(override)
    except BaseException:
        cleanup_failures.append("private_control_cleanup_failed")
    if cleanup_failures:
        try:
            _record_cleanup_blocker(
                path,
                run_id=run_id,
                status=status,
                failure_codes=cleanup_failures,
            )
        except BaseException as exc:
            raise RuntimeError(
                "paid cycle cleanup blocker persistence failed"
            ) from exc
        return 2
    return 0 if status == "completed" else 1


def install_lifecycle_signal_handlers() -> None:
    """Convert operator termination signals into synchronous cleanup."""

    def interrupted(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "issue",
        "consume",
        "bind-run",
        "admit-project",
        "resume-consume",
        "close",
        "execute-start",
        "execute-resume",
        "prepare-zero-paid",
        "zero-paid-preflight",
        "issue-gdt10e",
        "validate-unconsumed",
        "prepare-resume",
        "bound-run-id",
        "abort-preconsume",
        "dispose-terminal",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--authorization", required=True)
        if command == "issue":
            child.add_argument("--cycle-id", required=True)
            child.add_argument("--expires-at", required=True)
            child.add_argument("--head-revision", required=True)
            child.add_argument("--plan-sha256", required=True)
            child.add_argument("--pricing-sha256", required=True)
            child.add_argument("--runtime-closure-sha256", required=True)
            child.add_argument("--current-four-sha256", required=True)
            child.add_argument("--backend-image-id", required=True)
            child.add_argument("--compose-project", required=True)
            child.add_argument("--expected-db-revision", default="0014")
            child.add_argument("--max-total-cny", default="50.000000")
        if command == "prepare-zero-paid":
            child.add_argument("--override", required=True)
            child.add_argument("--safe-override", required=True)
            child.add_argument("--readiness", required=True)
            child.add_argument("--report", required=True)
        if command == "zero-paid-preflight":
            child.add_argument("--override", required=True)
            child.add_argument("--safe-override", required=True)
            child.add_argument("--readiness", required=True)
            child.add_argument("--preparation-report", required=True)
            child.add_argument("--report", required=True)
        if command == "issue-gdt10e":
            child.add_argument("--readiness", required=True)
            child.add_argument("--zero-paid-report", required=True)
            child.add_argument("--cycle-id", required=True)
            child.add_argument("--plan-ref", required=True)
            child.add_argument("--prior-cycle-evidence-sha256", required=True)
            child.add_argument("--historical-committed-cny", required=True)
            child.add_argument("--max-total-cny", required=True)
            child.add_argument("--overall-envelope-cny", required=True)
            child.add_argument("--expires-in-seconds", required=True, type=int)
        if command == "validate-unconsumed":
            child.add_argument("--override", required=True)
            child.add_argument("--readiness", required=True)
            child.add_argument("--zero-paid-report", required=True)
        if command == "prepare-resume":
            child.add_argument("--override", required=True)
            child.add_argument("--safe-override", required=True)
            child.add_argument("--readiness", required=True)
            child.add_argument("--runtime-acceptance", required=True)
        if command == "abort-preconsume":
            child.add_argument("--override", required=True)
            child.add_argument("--safe-override", required=True)
            child.add_argument("--readiness", required=True)
            child.add_argument("--preparation-report", required=True)
            child.add_argument("--zero-paid-report", required=True)
            child.add_argument("--cleanup-intent", required=True)
            child.add_argument("--cleanup-receipt", required=True)
            child.add_argument("--cleanup-blocker", required=True)
            child.add_argument("--review-deadline", required=True)
        if command == "dispose-terminal":
            child.add_argument("--readiness", required=True)
            child.add_argument("--run-id", required=True)
            child.add_argument("--cleanup-intent", required=True)
            child.add_argument("--cleanup-receipt", required=True)
            child.add_argument("--cleanup-blocker", required=True)
            child.add_argument("--review-deadline", required=True)
        if command in {
            "bind-run",
            "admit-project",
            "resume-consume",
            "close",
            "execute-resume",
            "prepare-resume",
        }:
            child.add_argument("--run-id", required=True)
        if command == "admit-project":
            child.add_argument("--project-id", required=True)
            child.add_argument("--project-order", required=True, type=int)
            child.add_argument("--source-sha256", required=True)
        if command == "resume-consume":
            child.add_argument("--pause-evidence-sha256", required=True)
        if command == "close":
            child.add_argument("--status", required=True)
            child.add_argument("--quiescence-sha256", required=True)
        if command in {"execute-start", "execute-resume"}:
            child.add_argument("--override", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "issue":
            issue_authorization(
                args.authorization,
                cycle_id=args.cycle_id,
                expires_at=args.expires_at,
                head_revision=args.head_revision,
                plan_sha256=args.plan_sha256,
                pricing_sha256=args.pricing_sha256,
                runtime_closure_sha256=args.runtime_closure_sha256,
                current_four_sha256=args.current_four_sha256,
                backend_image_id=args.backend_image_id,
                compose_project=args.compose_project,
                expected_db_revision=args.expected_db_revision,
                max_total_cny=args.max_total_cny,
            )
        elif args.command == "consume":
            consume_authorization(args.authorization)
        elif args.command == "bind-run":
            bind_run(args.authorization, run_id=args.run_id)
        elif args.command == "admit-project":
            admit_project(
                args.authorization,
                run_id=args.run_id,
                project_id=args.project_id,
                project_order=args.project_order,
                source_sha256=args.source_sha256,
            )
        elif args.command == "resume-consume":
            consume_resume(
                args.authorization,
                run_id=args.run_id,
                pause_evidence_sha256=args.pause_evidence_sha256,
            )
        elif args.command == "close":
            close_paid_cycle(
                args.authorization,
                run_id=args.run_id,
                status=args.status,
                quiescence_sha256=args.quiescence_sha256,
            )
        elif args.command == "execute-start":
            install_lifecycle_signal_handlers()
            return execute_start(
                args.authorization,
                override=Path(args.override),
            )
        elif args.command == "prepare-zero-paid":
            prepare_zero_paid(
                authorization=args.authorization, override=args.override,
                safe_override=args.safe_override, readiness=args.readiness,
                report=args.report,
            )
        elif args.command == "zero-paid-preflight":
            zero_paid_preflight(
                authorization=args.authorization, override=args.override,
                safe_override=args.safe_override, readiness=args.readiness,
                preparation_report=args.preparation_report, report=args.report,
            )
        elif args.command == "issue-gdt10e":
            issue_gdt10e(
                authorization=args.authorization, readiness=args.readiness,
                zero_paid_report=args.zero_paid_report, cycle_id=args.cycle_id,
                plan_ref=args.plan_ref,
                prior_cycle_evidence_sha256=args.prior_cycle_evidence_sha256,
                historical_committed_cny=args.historical_committed_cny,
                max_total_cny=args.max_total_cny,
                overall_envelope_cny=args.overall_envelope_cny,
                expires_in_seconds=args.expires_in_seconds,
            )
        elif args.command == "validate-unconsumed":
            validate_unconsumed(
                authorization=args.authorization, override=args.override,
                readiness=args.readiness, zero_paid_report=args.zero_paid_report,
            )
        elif args.command == "prepare-resume":
            prepare_resume(
                authorization=args.authorization,
                override=args.override,
                safe_override=args.safe_override,
                readiness=args.readiness,
                runtime_acceptance=args.runtime_acceptance,
                run_id=args.run_id,
            )
        elif args.command == "bound-run-id":
            print(bound_run_id(args.authorization))
            return 0
        elif args.command == "abort-preconsume":
            abort_preconsume(
                authorization=args.authorization, override=args.override,
                safe_override=args.safe_override, readiness=args.readiness,
                preparation_report=args.preparation_report,
                zero_paid_report=args.zero_paid_report,
                cleanup_intent=args.cleanup_intent,
                cleanup_receipt=args.cleanup_receipt,
                cleanup_blocker=args.cleanup_blocker,
                review_deadline=args.review_deadline,
            )
        elif args.command == "dispose-terminal":
            dispose_terminal(
                authorization=args.authorization,
                readiness=args.readiness,
                run_id=args.run_id,
                cleanup_intent=args.cleanup_intent,
                cleanup_receipt=args.cleanup_receipt,
                cleanup_blocker=args.cleanup_blocker,
                review_deadline=args.review_deadline,
            )
        elif args.command == "execute-resume":
            install_lifecycle_signal_handlers()
            return execute_resume(
                args.authorization,
                override=Path(args.override),
                run_id=args.run_id,
            )
        else:  # pragma: no cover - argparse owns command choices
            raise ValueError("unsupported authorization command")
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as exc:
        print(f"authorization_error={type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"authorization_action={args.command} status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
