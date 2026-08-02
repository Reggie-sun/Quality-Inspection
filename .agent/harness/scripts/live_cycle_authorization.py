#!/usr/bin/env python3
"""Own the one-use, append-only GDT-10D paid-cycle authorization protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
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
    "GDT10D_RUN_ID",
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
        os.write(fd, content)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        raise
    else:
        os.close(fd)
    _fsync_directory(path.parent)
    return payload


def _read_fact(path: Path, *, keys: set[str], schema_version: str) -> dict[str, Any]:
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
        or set(document) != keys
        or document.get("schema_version") != schema_version
        or document.get("content_sha256") != _canonical_hash(document)
    ):
        raise ValueError(f"cycle authorization {path.stem} is invalid")
    return document


def _issuance(root: Path, *, require_active: bool = True) -> dict[str, Any]:
    _safe_root(root)
    issuance = _read_fact(
        root / "issuance.json",
        keys=_ISSUANCE_KEYS,
        schema_version="provider-cycle-issuance/1",
    )
    if require_active:
        try:
            expiry = datetime.fromisoformat(str(issuance["expires_at"]))
        except ValueError as exc:
            raise ValueError("cycle authorization expiry is invalid") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("cycle authorization expiry is invalid")
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
    image = subprocess.run(
        [*_compose_command(), "images", "-q", "api"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    image_id = image.stdout.strip()
    if (
        image.returncode != 0
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or image_id != issuance["backend_image_id"]
    ):
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


def validate_issuance_for_start(root: Path) -> None:
    issuance = _issuance(root)
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


def deactivate_runtime() -> None:
    safe_ref = os.environ.get("QI_LIVE_CYCLE_SAFE_OVERRIDE_REF", "").strip()
    if not safe_ref:
        raise ValueError("safe override reference is required")
    safe_override = Path(safe_ref)
    validate_safe_override(safe_override)
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
        raise RuntimeError("safe runtime deactivation failed")
    for service_name in ("api", "worker"):
        _prove_safe_runtime_identity(service_name)


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
    validate_issuance: Callable[[Path], None] = validate_issuance_for_start,
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
        validate_issuance(path)
        consume_authorization(path, invocation_id=invocation_id)
        consumed = True
        bind_run_state(path, run_id=run_id)
        activate_runtime(override)
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
    validate_issuance: Callable[[Path], None] = validate_issuance_for_start,
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
        validate_issuance(path)
        pause_evidence_sha256 = validate_pause(run_id)
        consume_resume(
            path,
            run_id=run_id,
            pause_evidence_sha256=pause_evidence_sha256,
            invocation_id=invocation_id,
        )
        resumed = True
        activate_runtime(override)
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
        if command in {
            "bind-run",
            "admit-project",
            "resume-consume",
            "close",
            "execute-resume",
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
