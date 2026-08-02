from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_ID = re.compile(
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
_CONSUMPTION_KEYS = {
    "schema_version",
    "cycle_id",
    "issuance_sha256",
    "invocation_id",
    "consumed_at",
    "content_sha256",
}
_RESUME_KEYS = {
    "schema_version",
    "cycle_id",
    "run_id",
    "pause_evidence_sha256",
    "run_sha256",
    "invocation_id",
    "resumed_at",
    "content_sha256",
}
_CLEANUP_FAILURE_CODES = {
    "quiescence_close_or_finalize_failed",
    "safe_deactivation_failed",
    "private_control_cleanup_failed",
    "pause_handoff_failed",
}


@dataclass(frozen=True)
class ActiveCycleAuthorization:
    cycle_id: str
    run_id: str
    project_id: str
    project_order: int
    source_sha256: str
    pricing_sha256: str
    max_total_cny: str
    expires_at: str


def _safe_id(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_ID.fullmatch(value) is None
        or _FORBIDDEN_ID.search(value) is not None
    ):
        raise ValueError(f"cycle authorization {field} is invalid")
    return value


def _safe_directory(
    path: Path,
    *,
    owner: tuple[int, int] | None = None,
) -> tuple[int, int]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("cycle authorization directory is invalid") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (owner is not None and (metadata.st_uid, metadata.st_gid) != owner)
    ):
        raise ValueError("cycle authorization directory is invalid")
    return metadata.st_uid, metadata.st_gid


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


def _read_fact(
    path: Path,
    *,
    owner: tuple[int, int],
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("cycle authorization fact is invalid") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (metadata.st_uid, metadata.st_gid) != owner
            or metadata.st_size > 64 * 1024
        ):
            raise ValueError("cycle authorization fact is invalid")
        content = b""
        while len(content) <= metadata.st_size:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            content += chunk
    finally:
        os.close(fd)
    try:
        document = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("cycle authorization fact is invalid") from exc
    if not isinstance(document, Mapping):
        raise ValueError("cycle authorization fact is invalid")
    payload = dict(document)
    digest = payload.get("content_sha256")
    if (
        not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or digest != _canonical_hash(payload)
    ):
        raise ValueError("cycle authorization fact hash is invalid")
    return payload


def _exact_fact(
    path: Path,
    expected_keys: set[str],
    schema_version: str,
    *,
    owner: tuple[int, int],
) -> dict[str, Any]:
    document = _read_fact(path, owner=owner)
    if set(document) != expected_keys or document.get(
        "schema_version"
    ) != schema_version:
        raise ValueError("cycle authorization fact schema is invalid")
    return document


def _append_fact_exclusive(
    path: Path,
    document: dict[str, Any],
    *,
    owner: tuple[int, int],
) -> dict[str, Any]:
    payload = dict(document)
    payload["content_sha256"] = _canonical_hash(payload)
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
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
    except OSError as exc:
        raise ValueError("cycle authorization fact append failed") from exc
    try:
        os.fchown(fd, owner[0], owner[1])
        os.fchmod(fd, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short cycle authorization fact write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    directory_fd = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return payload


def ensure_run_binding_from_close_bridge(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Recover the run binding under the close bridge's ledger lock."""
    expected_cycle_id = _safe_id(cycle_id, "cycle_id")
    expected_run_id = _safe_id(run_id, "run_id")
    root = Path(authorization_root)
    owner = _safe_directory(root)
    issuance = _exact_fact(
        root / "issuance.json",
        _ISSUANCE_KEYS,
        "provider-cycle-issuance/1",
        owner=owner,
    )
    consumption = _exact_fact(
        root / "consumption.json",
        _CONSUMPTION_KEYS,
        "provider-cycle-consumption/1",
        owner=owner,
    )
    if (
        issuance["cycle_id"] != expected_cycle_id
        or consumption["cycle_id"] != expected_cycle_id
        or consumption["issuance_sha256"] != issuance["content_sha256"]
        or _SHA256.fullmatch(str(consumption["invocation_id"])) is None
    ):
        raise ValueError("cycle authorization close recovery identity is invalid")
    expected = {
        "schema_version": "provider-cycle-run/1",
        "cycle_id": expected_cycle_id,
        "run_id": expected_run_id,
        "consumption_sha256": consumption["content_sha256"],
    }
    run_path = root / "run.json"
    if run_path.exists() or run_path.is_symlink():
        run = _exact_fact(
            run_path,
            {*expected, "content_sha256"},
            "provider-cycle-run/1",
            owner=owner,
        )
        candidate = dict(expected)
        candidate["content_sha256"] = _canonical_hash(candidate)
        if run != candidate:
            raise ValueError("cycle authorization close recovery run conflicts")
        return run
    return _append_fact_exclusive(run_path, expected, owner=owner)


def _validate_cleanup_blocker(
    *,
    root: Path,
    owner: tuple[int, int],
    cycle_id: str,
    run_id: str,
) -> None:
    blocker_path = root / "cleanup-blocker.json"
    if not blocker_path.exists() and not blocker_path.is_symlink():
        return
    blocker = _exact_fact(
        blocker_path,
        {
            "schema_version",
            "cycle_id",
            "run_id",
            "status",
            "failure_codes",
            "content_sha256",
        },
        "provider-cycle-cleanup-blocker/1",
        owner=owner,
    )
    failure_codes = blocker["failure_codes"]
    if (
        blocker["cycle_id"] != cycle_id
        or blocker["run_id"] != run_id
        or blocker["status"]
        not in {"completed", "failed", "aborted", "paused"}
        or not isinstance(failure_codes, list)
        or not failure_codes
        or any(not isinstance(code, str) for code in failure_codes)
        or len(failure_codes) != len(set(failure_codes))
        or any(code not in _CLEANUP_FAILURE_CODES for code in failure_codes)
    ):
        raise ValueError("cycle authorization cleanup blocker is invalid")


def _validate_cycle_authorization(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    project_id: str,
    pricing_sha256: str,
    allow_terminal: bool,
) -> ActiveCycleAuthorization:
    expected_cycle_id = _safe_id(cycle_id, "cycle_id")
    expected_project_id = _safe_id(project_id, "project_id")
    root = Path(authorization_root)
    owner = _safe_directory(root)
    projects_root = root / "projects"
    _safe_directory(projects_root, owner=owner)

    allowed_root_names = {
        "issuance.json",
        "consumption.json",
        "run.json",
        "projects",
        "pause-handoff.json",
        "resume-consumed.json",
        "terminal.json",
    }
    if allow_terminal:
        allowed_root_names.add("cleanup-blocker.json")
    if any(
        item.is_symlink() or item.name not in allowed_root_names
        for item in root.iterdir()
    ):
        raise ValueError("cycle authorization directory contains unexpected state")

    issuance = _exact_fact(
        root / "issuance.json",
        _ISSUANCE_KEYS,
        "provider-cycle-issuance/1",
        owner=owner,
    )
    consumption = _exact_fact(
        root / "consumption.json",
        _CONSUMPTION_KEYS,
        "provider-cycle-consumption/1",
        owner=owner,
    )
    run = _exact_fact(
        root / "run.json",
        {
            "schema_version",
            "cycle_id",
            "run_id",
            "consumption_sha256",
            "content_sha256",
        },
        "provider-cycle-run/1",
        owner=owner,
    )
    terminal_path = root / "terminal.json"
    terminal: dict[str, Any] | None = None
    if terminal_path.exists() or terminal_path.is_symlink():
        terminal = _exact_fact(
            terminal_path,
            {
                "schema_version",
                "cycle_id",
                "run_id",
                "status",
                "quiescence_sha256",
                "run_sha256",
                "content_sha256",
            },
            "provider-cycle-terminal/1",
            owner=owner,
        )
        if not allow_terminal:
            raise ValueError("cycle authorization is terminal")

    handoff_path = root / "pause-handoff.json"
    handoff: dict[str, Any] | None = None
    if handoff_path.exists() or handoff_path.is_symlink():
        handoff = _exact_fact(
            handoff_path,
            {
                "schema_version",
                "cycle_id",
                "run_id",
                "pause_evidence_sha256",
                "run_sha256",
                "safe_runtime_proved",
                "private_controls_removed",
                "content_sha256",
            },
            "provider-cycle-pause-handoff/1",
            owner=owner,
        )
        if (
            handoff["cycle_id"] != expected_cycle_id
            or handoff["run_id"] != run["run_id"]
            or handoff["run_sha256"] != run["content_sha256"]
            or not isinstance(handoff["pause_evidence_sha256"], str)
            or _SHA256.fullmatch(handoff["pause_evidence_sha256"]) is None
            or handoff["safe_runtime_proved"] is not True
            or handoff["private_controls_removed"] is not True
        ):
            raise ValueError("cycle authorization pause handoff is invalid")

    resume_path = root / "resume-consumed.json"
    if resume_path.exists() or resume_path.is_symlink():
        resume = _exact_fact(
            resume_path,
            _RESUME_KEYS,
            "provider-cycle-resume-consumed/1",
            owner=owner,
        )
        if (
            handoff is None
            or resume["cycle_id"] != expected_cycle_id
            or resume["run_id"] != run["run_id"]
            or resume["run_sha256"] != run["content_sha256"]
            or not isinstance(resume["resumed_at"], str)
            or _SHA256.fullmatch(str(resume["invocation_id"])) is None
            or not isinstance(resume["pause_evidence_sha256"], str)
            or _SHA256.fullmatch(resume["pause_evidence_sha256"]) is None
            or resume["pause_evidence_sha256"]
            != handoff["pause_evidence_sha256"]
        ):
            raise ValueError("cycle authorization resume state is invalid")

    if allow_terminal:
        _validate_cleanup_blocker(
            root=root,
            owner=owner,
            cycle_id=expected_cycle_id,
            run_id=str(run["run_id"]),
        )

    if (
        issuance["cycle_id"] != expected_cycle_id
        or consumption["cycle_id"] != expected_cycle_id
        or run["cycle_id"] != expected_cycle_id
        or consumption["issuance_sha256"] != issuance["content_sha256"]
        or run["consumption_sha256"] != consumption["content_sha256"]
        or _SHA256.fullmatch(str(consumption["invocation_id"])) is None
        or issuance["pricing_sha256"] != pricing_sha256
        or issuance["max_total_cny"] != "50.000000"
        or issuance["expected_db_revision"] != "0014"
        or _SHA256.fullmatch(str(issuance["pricing_sha256"])) is None
        or _IMAGE_ID.fullmatch(str(issuance["backend_image_id"])) is None
    ):
        raise ValueError("cycle authorization identity is invalid")
    expires_at = issuance["expires_at"]
    if not isinstance(expires_at, str):
        raise ValueError("cycle authorization expiry is invalid")
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise ValueError("cycle authorization expiry is invalid") from exc
    if expiry.tzinfo is None or (
        not allow_terminal and expiry <= datetime.now(timezone.utc)
    ):
        raise ValueError("cycle authorization expiry is invalid")
    run_id = _safe_id(run["run_id"], "run_id")
    if terminal is not None and (
        terminal["cycle_id"] != expected_cycle_id
        or terminal["run_id"] != run_id
        or terminal["run_sha256"] != run["content_sha256"]
        or terminal["status"] not in {"completed", "failed", "aborted"}
        or not isinstance(terminal["quiescence_sha256"], str)
        or _SHA256.fullmatch(terminal["quiescence_sha256"]) is None
    ):
        raise ValueError("cycle authorization terminal identity is invalid")

    matches: list[dict[str, Any]] = []
    for path in sorted(projects_root.iterdir()):
        if path.is_symlink() or not path.name.endswith(".json"):
            raise ValueError("cycle authorization project state is invalid")
        project = _exact_fact(
            path,
            {
                "schema_version",
                "cycle_id",
                "run_id",
                "project_id",
                "project_order",
                "source_sha256",
                "run_sha256",
                "content_sha256",
            },
            "provider-cycle-project/1",
            owner=owner,
        )
        if project["project_id"] == expected_project_id:
            matches.append(project)
    if len(matches) != 1:
        raise ValueError("cycle authorization project admission is invalid")
    project = matches[0]
    project_order = project["project_order"]
    source_sha256 = project["source_sha256"]
    if (
        project["cycle_id"] != expected_cycle_id
        or project["run_id"] != run_id
        or project["run_sha256"] != run["content_sha256"]
        or not isinstance(project_order, int)
        or isinstance(project_order, bool)
        or project_order < 1
        or not isinstance(source_sha256, str)
        or _SHA256.fullmatch(source_sha256) is None
    ):
        raise ValueError("cycle authorization project admission is invalid")
    return ActiveCycleAuthorization(
        cycle_id=expected_cycle_id,
        run_id=run_id,
        project_id=expected_project_id,
        project_order=project_order,
        source_sha256=source_sha256,
        pricing_sha256=pricing_sha256,
        max_total_cny="50.000000",
        expires_at=expires_at,
    )


def validate_active_cycle_authorization(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    project_id: str,
    pricing_sha256: str,
) -> ActiveCycleAuthorization:
    return _validate_cycle_authorization(
        authorization_root=authorization_root,
        cycle_id=cycle_id,
        project_id=project_id,
        pricing_sha256=pricing_sha256,
        allow_terminal=False,
    )


def validate_cycle_authorization_for_close(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    project_id: str,
    pricing_sha256: str,
) -> ActiveCycleAuthorization:
    """Validate the historical binding while permitting exact terminal replay."""
    return _validate_cycle_authorization(
        authorization_root=authorization_root,
        cycle_id=cycle_id,
        project_id=project_id,
        pricing_sha256=pricing_sha256,
        allow_terminal=True,
    )


def validate_empty_cycle_authorization_for_close(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    run_id: str,
    pricing_sha256: str,
) -> dict[str, Any]:
    """Validate close-only state for a cycle with no admitted project."""
    expected_cycle_id = _safe_id(cycle_id, "cycle_id")
    expected_run_id = _safe_id(run_id, "run_id")
    root = Path(authorization_root)
    owner = _safe_directory(root)
    allowed_root_names = {
        "issuance.json",
        "consumption.json",
        "run.json",
        "projects",
        "cleanup-blocker.json",
        "terminal.json",
    }
    if any(
        item.is_symlink() or item.name not in allowed_root_names
        for item in root.iterdir()
    ):
        raise ValueError("cycle authorization directory contains unexpected state")
    projects = root / "projects"
    if projects.exists() or projects.is_symlink():
        _safe_directory(projects, owner=owner)
        if any(projects.iterdir()):
            raise ValueError("empty cycle close has admitted project state")
    issuance = _exact_fact(
        root / "issuance.json",
        _ISSUANCE_KEYS,
        "provider-cycle-issuance/1",
        owner=owner,
    )
    consumption = _exact_fact(
        root / "consumption.json",
        _CONSUMPTION_KEYS,
        "provider-cycle-consumption/1",
        owner=owner,
    )
    _validate_cleanup_blocker(
        root=root,
        owner=owner,
        cycle_id=expected_cycle_id,
        run_id=expected_run_id,
    )
    if (
        issuance["cycle_id"] != expected_cycle_id
        or consumption["cycle_id"] != expected_cycle_id
        or consumption["issuance_sha256"] != issuance["content_sha256"]
        or _SHA256.fullmatch(str(consumption["invocation_id"])) is None
        or issuance["pricing_sha256"] != pricing_sha256
        or issuance["max_total_cny"] != "50.000000"
        or issuance["expected_db_revision"] != "0014"
        or _SHA256.fullmatch(str(issuance["pricing_sha256"])) is None
        or _IMAGE_ID.fullmatch(str(issuance["backend_image_id"])) is None
    ):
        raise ValueError("cycle authorization identity is invalid")
    expires_at = issuance["expires_at"]
    if not isinstance(expires_at, str):
        raise ValueError("cycle authorization expiry is invalid")
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise ValueError("cycle authorization expiry is invalid") from exc
    if expiry.tzinfo is None:
        raise ValueError("cycle authorization expiry is invalid")
    run = ensure_run_binding_from_close_bridge(
        authorization_root=root,
        cycle_id=expected_cycle_id,
        run_id=expected_run_id,
    )
    if (
        run["cycle_id"] != expected_cycle_id
        or run["run_id"] != expected_run_id
        or run["consumption_sha256"] != consumption["content_sha256"]
    ):
        raise ValueError("cycle authorization identity is invalid")
    terminal_path = root / "terminal.json"
    if terminal_path.exists() or terminal_path.is_symlink():
        terminal = _exact_fact(
            terminal_path,
            {
                "schema_version",
                "cycle_id",
                "run_id",
                "status",
                "quiescence_sha256",
                "run_sha256",
                "content_sha256",
            },
            "provider-cycle-terminal/1",
            owner=owner,
        )
        if (
            terminal["cycle_id"] != expected_cycle_id
            or terminal["run_id"] != expected_run_id
            or terminal["run_sha256"] != run["content_sha256"]
            or terminal["status"] not in {"completed", "failed", "aborted"}
            or not isinstance(terminal["quiescence_sha256"], str)
            or _SHA256.fullmatch(terminal["quiescence_sha256"]) is None
        ):
            raise ValueError("cycle authorization terminal identity is invalid")
    return run


def write_terminal_from_close_bridge(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    run_id: str,
    status: str,
    quiescence_sha256: str,
) -> dict[str, Any]:
    """Write or exactly replay terminal state; caller must hold the ledger lock."""
    expected_cycle_id = _safe_id(cycle_id, "cycle_id")
    expected_run_id = _safe_id(run_id, "run_id")
    if status not in {"completed", "failed", "aborted"}:
        raise ValueError("cycle authorization terminal status is invalid")
    if _SHA256.fullmatch(quiescence_sha256) is None:
        raise ValueError("cycle authorization quiescence identity is invalid")
    root = Path(authorization_root)
    owner = _safe_directory(root)
    issuance = _exact_fact(
        root / "issuance.json",
        _ISSUANCE_KEYS,
        "provider-cycle-issuance/1",
        owner=owner,
    )
    consumption = _exact_fact(
        root / "consumption.json",
        _CONSUMPTION_KEYS,
        "provider-cycle-consumption/1",
        owner=owner,
    )
    run = ensure_run_binding_from_close_bridge(
        authorization_root=root,
        cycle_id=expected_cycle_id,
        run_id=expected_run_id,
    )
    if (
        issuance["cycle_id"] != expected_cycle_id
        or consumption["cycle_id"] != expected_cycle_id
        or consumption["issuance_sha256"] != issuance["content_sha256"]
        or run["cycle_id"] != expected_cycle_id
        or run["run_id"] != expected_run_id
        or run["consumption_sha256"] != consumption["content_sha256"]
    ):
        raise ValueError("cycle authorization terminal identity is invalid")
    document = {
        "schema_version": "provider-cycle-terminal/1",
        "cycle_id": expected_cycle_id,
        "run_id": expected_run_id,
        "status": status,
        "quiescence_sha256": quiescence_sha256,
        "run_sha256": run["content_sha256"],
    }
    document["content_sha256"] = _canonical_hash(document)
    terminal_path = root / "terminal.json"
    if terminal_path.exists() or terminal_path.is_symlink():
        existing = _exact_fact(
            terminal_path,
            set(document),
            "provider-cycle-terminal/1",
            owner=owner,
        )
        if existing != document:
            raise ValueError("cycle authorization terminal conflicts")
        return existing
    return _append_fact_exclusive(
        terminal_path,
        {key: value for key, value in document.items() if key != "content_sha256"},
        owner=owner,
    )


def write_empty_cycle_terminal_from_close_bridge(
    *,
    authorization_root: str | Path,
    cycle_id: str,
    run_id: str,
    status: str,
    quiescence_sha256: str,
) -> dict[str, Any]:
    """Close a bound cycle that failed before its first project admission."""
    root = Path(authorization_root)
    owner = _safe_directory(root)
    projects = root / "projects"
    if projects.exists() or projects.is_symlink():
        _safe_directory(projects, owner=owner)
        if any(projects.iterdir()):
            raise ValueError("empty cycle close has admitted project state")
    return write_terminal_from_close_bridge(
        authorization_root=root,
        cycle_id=cycle_id,
        run_id=run_id,
        status=status,
        quiescence_sha256=quiescence_sha256,
    )
