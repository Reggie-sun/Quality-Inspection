#!/usr/bin/env python3
"""Own the private GDT-10E operator readiness attestation only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCHEMA_VERSION = "provider-account-readiness/1"
RUNTIME_ACCEPTANCE_SCHEMA_VERSION = "provider-account-runtime-acceptance/1"
CLEANUP_INTENT_SCHEMA_VERSION = "provider-cycle-cleanup-intent/1"
PRIVATE_ROOT = Path("/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d")
CLEANUP_INTENT_PATH = Path(
    "/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json"
)
HARNESS_RUNS_ROOT = Path(
    "/home/reggie/vscode_folder/Quality_Inspection/.worktrees/gdt10e-retry-archive-continuation/.agent/harness/runs"
)
DOCUMENT_NAME = "account-readiness.json"
CYCLE_ID = "gdt10e-auth-remediated-live-20260802"
MODEL = "qwen3-vl-plus-2025-12-19"
REGION = "cn-beijing"
MAX_INCREMENTAL_CNY = "46.473344"
MAX_EXPIRY_SECONDS = 1800
OPERATOR_CLAIMS = (
    "remediation_completed",
    "workspace_account_binding_verified",
    "compatible_mode_enabled",
    "model_entitlement_verified",
    "billing_and_quota_verified",
)
PUBLIC_FIELDS = (
    "schema_version",
    "content_sha256",
    "issued_at",
    "expires_at",
    "operator_state",
    "all_operator_checks_passed",
    "credential_binding_matches",
)
EXPECTED_STEPS = (
    "safe_runtime_proved",
    "live_override_absent",
    "safe_override_absent",
    "preparation_report_absent",
    "zero_paid_report_absent",
    "account_readiness_absent",
    "authorization_root_absent",
    "private_root_absent",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")


class AccountReadinessError(ValueError):
    """A readiness control is malformed, unsafe, or not the exact control."""


class AccountReadinessCleanupIncomplete(AccountReadinessError):
    """The sole permitted deletion occurred but its durable fsync did not."""

    def __init__(self) -> None:
        super().__init__("account_readiness_cleanup_incomplete")


@dataclass(frozen=True)
class AccountReadinessEvidence:
    schema_version: str
    content_sha256: str
    issued_at: str
    expires_at: str
    operator_state: str
    all_operator_checks_passed: bool
    credential_binding_matches: bool

    def public_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in PUBLIC_FIELDS}


@dataclass(frozen=True)
class CleanupEvidence:
    deleted: bool
    content_sha256: str


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AccountReadinessError from None


def _invalid() -> AccountReadinessError:
    return AccountReadinessError("account readiness is invalid")


def _canonical_hash(payload: Mapping[str, object]) -> str:
    content = dict(payload)
    content.pop("content_sha256", None)
    return hashlib.sha256(
        json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ):
        raise _invalid()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid() from exc


def _sha256(value: object) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise _invalid()
    return value


def _exact_json_id(value: object, current_id: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        and value == current_id
    )


def _safe_id(value: object) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise _invalid()
    return value


def _environment(environment: Mapping[str, str]) -> tuple[str, str, str, str]:
    names = (
        "QI_QWEN_API_KEY",
        "QI_QWEN_WORKSPACE_ID",
        "QI_QWEN_MODEL",
        "QI_P0_OPERATOR_ID",
    )
    values = tuple(environment.get(name) for name in names)
    if any(not isinstance(value, str) or not value for value in values):
        raise _invalid()
    api_key, workspace_id, model, operator_id = values
    return api_key, workspace_id, _safe_id(model), _safe_id(operator_id)


def _bundle_binding(
    *, salt: bytes, cycle_id: str, model: str, workspace_id: str, api_key: str
) -> str:
    digest = hashlib.sha256(b"provider-account-readiness/1\0")
    for value in (salt.hex(), cycle_id, model, workspace_id, api_key):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _assert_directory_stat(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
        or metadata.st_gid != os.getgid()
    ):
        raise _invalid()


def _require_root(root: Path) -> None:
    if root != PRIVATE_ROOT:
        raise _invalid()


def _open_private_root(root: Path, *, create: bool = False) -> int:
    _require_root(root)
    if create:
        try:
            root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise _invalid() from exc
    try:
        descriptor = os.open(root, _directory_flags())
    except OSError as exc:
        raise _invalid() from exc
    try:
        _assert_directory_stat(os.fstat(descriptor))
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _fsync_root_after_unlink(root_descriptor: int) -> None:
    os.fsync(root_descriptor)


def _write_exclusive(root_descriptor: int, document: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DOCUMENT_NAME, flags, 0o600, dir_fd=root_descriptor)
    except OSError as exc:
        raise _invalid() from exc
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(encoded):
            count = os.write(descriptor, encoded[written:])
            if count <= 0:
                raise OSError("short readiness write")
            written += count
        os.fsync(descriptor)
    except OSError as exc:
        raise _invalid() from exc
    finally:
        os.close(descriptor)
    try:
        os.fsync(root_descriptor)
    except OSError as exc:
        raise _invalid() from exc


def _read_document(root_descriptor: int) -> dict[str, object]:
    try:
        descriptor = os.open(
            DOCUMENT_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_descriptor
        )
    except OSError as exc:
        raise _invalid() from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
        ):
            raise _invalid()
        content = os.read(descriptor, metadata.st_size)
        document = json.loads(content)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _invalid() from exc
    finally:
        os.close(descriptor)
    if not isinstance(document, dict) or content != (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"):
        raise _invalid()
    return document


def _validate_document_shape(document: Mapping[str, object]) -> tuple[datetime, datetime]:
    fields = {
        "schema_version", "cycle_id", "operator_id", "issued_at", "expires_at", "source",
        *OPERATOR_CLAIMS, "region", "model", "max_incremental_cny", "binding_salt",
        "credential_bundle_binding_sha256", "content_sha256",
    }
    if set(document) != fields or _canonical_hash(document) != _sha256(document.get("content_sha256")):
        raise _invalid()
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["cycle_id"] != CYCLE_ID
        or document["source"] != "provider_console"
        or document["region"] != REGION
        or document["model"] != MODEL
        or document["max_incremental_cny"] != MAX_INCREMENTAL_CNY
        or not all(document[name] is True for name in OPERATOR_CLAIMS)
    ):
        raise _invalid()
    _safe_id(document["operator_id"])
    salt = document["binding_salt"]
    if not isinstance(salt, str) or re.fullmatch(r"[0-9a-f]{64}", salt) is None:
        raise _invalid()
    _sha256(document["credential_bundle_binding_sha256"])
    issued_at, expires_at = _parse_timestamp(document["issued_at"]), _parse_timestamp(document["expires_at"])
    if expires_at <= issued_at or expires_at - issued_at > timedelta(seconds=MAX_EXPIRY_SECONDS):
        raise _invalid()
    return issued_at, expires_at


def _validate_document_with_environment(
    document: Mapping[str, object], environment: Mapping[str, str]
) -> None:
    api_key, workspace_id, model, operator_id = _environment(environment)
    if model != MODEL or document["operator_id"] != operator_id:
        raise _invalid()
    if document["credential_bundle_binding_sha256"] != _bundle_binding(
        salt=bytes.fromhex(str(document["binding_salt"])), cycle_id=CYCLE_ID,
        model=MODEL, workspace_id=workspace_id, api_key=api_key,
    ):
        raise _invalid()


def _require_exact_inputs(cycle_id: str, region: str, max_incremental_cny: str) -> None:
    if cycle_id != CYCLE_ID or region != REGION or max_incremental_cny != MAX_INCREMENTAL_CNY:
        raise _invalid()


def issue_account_readiness(
    *, root: Path, cycle_id: str, region: str, max_incremental_cny: str, expires_in_seconds: int,
    operator_checks: Mapping[str, object], environment: Mapping[str, str],
) -> dict[str, object]:
    """Create exactly one private attestation at the fixed private root."""
    _require_exact_inputs(cycle_id, region, max_incremental_cny)
    if (
        isinstance(expires_in_seconds, bool) or not isinstance(expires_in_seconds, int)
        or not 0 < expires_in_seconds <= MAX_EXPIRY_SECONDS
        or set(operator_checks) != set(OPERATOR_CLAIMS)
        or not all(operator_checks[name] is True for name in OPERATOR_CLAIMS)
    ):
        raise _invalid()
    api_key, workspace_id, model, operator_id = _environment(environment)
    if model != MODEL:
        raise _invalid()
    root_descriptor = _open_private_root(root, create=True)
    try:
        if os.listdir(root_descriptor):
            raise _invalid()
        issued_at = datetime.now(UTC)
        salt = secrets.token_bytes(32)
        document: dict[str, object] = {
            "schema_version": SCHEMA_VERSION, "cycle_id": CYCLE_ID, "operator_id": operator_id,
            "issued_at": _timestamp(issued_at),
            "expires_at": _timestamp(issued_at + timedelta(seconds=expires_in_seconds)),
            "source": "provider_console", "region": REGION, "model": MODEL,
            "max_incremental_cny": MAX_INCREMENTAL_CNY, "binding_salt": salt.hex(),
            "credential_bundle_binding_sha256": _bundle_binding(
                salt=salt, cycle_id=CYCLE_ID, model=MODEL, workspace_id=workspace_id, api_key=api_key
            ),
            **{name: True for name in OPERATOR_CLAIMS},
        }
        document["content_sha256"] = _canonical_hash(document)
        _write_exclusive(root_descriptor, document)
        return document
    finally:
        os.close(root_descriptor)


def validate_account_readiness(
    *, root: Path, cycle_id: str, model: str, region: str, max_incremental_cny: str,
    environment: Mapping[str, str], phase: str = "start", expected_content_sha256: str | None = None,
    runtime_acceptance: Path | None = None,
) -> AccountReadinessEvidence:
    """Validate the exact private fact and expose only its seven public fields."""
    _require_exact_inputs(cycle_id, region, max_incremental_cny)
    if model != MODEL:
        raise _invalid()
    root_descriptor = _open_private_root(root)
    try:
        document = _read_document(root_descriptor)
    finally:
        os.close(root_descriptor)
    issued_at, expires_at = _validate_document_shape(document)
    _validate_document_with_environment(document, environment)
    if expected_content_sha256 is not None and document["content_sha256"] != _sha256(expected_content_sha256):
        raise _invalid()
    now = datetime.now(UTC)
    if issued_at > now:
        raise _invalid()
    if phase == "start":
        if runtime_acceptance is not None:
            raise _invalid()
        if now > expires_at:
            raise _invalid()
    elif phase == "resume":
        if expected_content_sha256 is None or document["content_sha256"] != _sha256(expected_content_sha256):
            raise _invalid()
        if not isinstance(runtime_acceptance, Path) or not _validate_runtime_acceptance(runtime_acceptance, str(document["content_sha256"])):
            raise _invalid()
    else:
        raise _invalid()
    return AccountReadinessEvidence(
        schema_version=SCHEMA_VERSION, content_sha256=str(document["content_sha256"]),
        issued_at=str(document["issued_at"]), expires_at=str(document["expires_at"]),
        operator_state="operator_attested", all_operator_checks_passed=True,
        credential_binding_matches=True,
    )


def _validate_runtime_acceptance(path: Path, readiness_sha256: str) -> bool:
    close_failed = False
    try:
        relative = path.relative_to(HARNESS_RUNS_ROOT)
    except ValueError:
        return False
    if len(relative.parts) != 3 or relative.parts[1:] != ("reports", "provider-account-runtime-acceptance.json") or RUN_ID.fullmatch(relative.parts[0]) is None:
        return False
    descriptors: list[int] = []
    try:
        root = os.open(HARNESS_RUNS_ROOT, _directory_flags())
        descriptors.append(root)
        run = os.open(relative.parts[0], _directory_flags(), dir_fd=root)
        descriptors.append(run)
        reports = os.open("reports", _directory_flags(), dir_fd=run)
        descriptors.append(reports)
        descriptor = os.open("provider-account-runtime-acceptance.json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=reports)
        descriptors.append(descriptor)
        for directory in descriptors[:-1]:
            metadata = os.fstat(directory)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_gid != os.getgid() or stat.S_IMODE(metadata.st_mode) & 0o022:
                return False
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid() or metadata.st_gid != os.getgid():
            return False
        content = os.read(descriptor, metadata.st_size)
        fact = json.loads(content)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    finally:
        close_failed = _close_all(descriptors)
    if close_failed:
        return False
    fields = {"schema_version", "cycle_id", "run_id", "project_id", "readiness_sha256", "model", "ledger_attempt_index", "submission_started_sha256", "settlement_sha256", "call_evidence_sha256", "accepted_at", "content_sha256"}
    if not isinstance(fact, dict) or set(fact) != fields or content != (json.dumps(fact, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode():
        return False
    return (
        fact["schema_version"] == RUNTIME_ACCEPTANCE_SCHEMA_VERSION and fact["cycle_id"] == CYCLE_ID
        and fact["run_id"] == relative.parts[0] and fact["readiness_sha256"] == readiness_sha256
        and fact["model"] == MODEL and isinstance(fact["project_id"], str) and bool(fact["project_id"])
        and isinstance(fact["ledger_attempt_index"], int) and not isinstance(fact["ledger_attempt_index"], bool) and fact["ledger_attempt_index"] >= 1
        and isinstance(fact["accepted_at"], str) and bool(fact["accepted_at"])
        and all(isinstance(fact[name], str) and SHA256.fullmatch(fact[name]) for name in ("readiness_sha256", "submission_started_sha256", "settlement_sha256", "call_evidence_sha256", "content_sha256"))
        and _canonical_hash(fact) == fact["content_sha256"]
    )


def _safe_paths(run_id: str | None = None) -> dict[str, str]:
    authorization = PRIVATE_ROOT / "authorization"
    suffix = "-cleanup-"
    paths = {
        "private_root": str(PRIVATE_ROOT), "account_readiness": str(PRIVATE_ROOT / DOCUMENT_NAME),
        "live_override": str(PRIVATE_ROOT / "live.env"), "safe_override": str(PRIVATE_ROOT / "safe.env"),
        "authorization_root": str(authorization), "authorization_issuance": str(authorization / "issuance.json"),
        "authorization_consumption": str(authorization / "consumption.json"), "authorization_run": str(authorization / "run.json"),
        "authorization_pause_handoff": str(authorization / "pause-handoff.json"),
        "authorization_resume_consumed": str(authorization / "resume-consumed.json"),
        "authorization_terminal": str(authorization / "terminal.json"),
        "authorization_unconsumed_cancellation": str(authorization / "unconsumed-cancellation.json"),
        "authorization_legacy_cleanup_blocker": str(authorization / "cleanup-blocker.json"),
        "preparation_report": str(PRIVATE_ROOT / "preparation.json"),
        "zero_paid_report": str(PRIVATE_ROOT / "zero-paid-readiness.json"),
        "cleanup_intent": str(CLEANUP_INTENT_PATH),
        "cleanup_receipt": str(CLEANUP_INTENT_PATH).replace(suffix + "intent", suffix + "receipt"),
        "cleanup_blocker": str(CLEANUP_INTENT_PATH).replace(suffix + "intent", suffix + "blocker"),
    }
    if run_id is not None:
        run_root = HARNESS_RUNS_ROOT / run_id
        paths.update({
            "harness_run_root": str(run_root),
            "harness_run_document": str(run_root / "run.json"),
            "harness_live_evidence": str(run_root / "live-run-evidence.json"),
            "harness_runtime_acceptance": str(run_root / "reports/provider-account-runtime-acceptance.json"),
            "harness_quiescence": str(run_root / "reports/provider-cycle-quiescence.json"),
            "harness_close_bridge": str(run_root / "reports/provider-cycle-close-bridge.json"),
        })
    return paths


def _read_exact_intent(path: Path) -> dict[str, object]:
    if path != CLEANUP_INTENT_PATH:
        raise _invalid()
    try:
        parent = os.open(path.parent, _directory_flags())
        descriptor = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
    except OSError as exc:
        raise _invalid() from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid() or metadata.st_gid != os.getgid()
        ):
            raise _invalid()
        content = os.read(descriptor, metadata.st_size)
        intent = json.loads(content)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _invalid() from exc
    finally:
        os.close(descriptor)
        os.close(parent)
    if not isinstance(intent, dict) or content != (json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"):
        raise _invalid()
    return intent


def _validate_intent(intent: Mapping[str, object]) -> None:
    fields = {
        "schema_version", "cycle_id", "branch", "account_readiness_sha256", "issuance_sha256",
        "cancellation_sha256", "terminal_sha256", "run_id", "safe_path_sha256s", "expected_steps",
        "created_at", "readiness_expires_at", "review_deadline", "owner_uid", "owner_gid", "mode", "content_sha256",
    }
    if set(intent) != fields or _canonical_hash(intent) != _sha256(intent.get("content_sha256")):
        raise _invalid()
    if (
        intent["schema_version"] != CLEANUP_INTENT_SCHEMA_VERSION or intent["cycle_id"] != CYCLE_ID
        or intent["branch"] not in {"no_issuance", "issued_unconsumed", "terminal"}
        or intent["expected_steps"] != list(EXPECTED_STEPS) or intent["review_deadline"] != "2026-08-09T23:59:59+08:00"
        or not _exact_json_id(intent["owner_uid"], os.getuid())
        or not _exact_json_id(intent["owner_gid"], os.getgid())
        or intent["mode"] != "0600"
    ):
        raise _invalid()
    created_at, expires_at = _parse_timestamp(intent["created_at"]), _parse_timestamp(intent["readiness_expires_at"])
    if created_at > expires_at:
        raise _invalid()
    _sha256(intent["account_readiness_sha256"])
    branch = intent["branch"]
    nullable_hashes = ("issuance_sha256", "cancellation_sha256", "terminal_sha256")
    if branch == "no_issuance":
        if any(intent[name] is not None for name in (*nullable_hashes, "run_id")):
            raise _invalid()
    elif branch == "issued_unconsumed":
        if not (_sha256(intent["issuance_sha256"]) and _sha256(intent["cancellation_sha256"])):
            raise _invalid()
        if intent["terminal_sha256"] is not None or intent["run_id"] is not None:
            raise _invalid()
    else:
        if not (_sha256(intent["issuance_sha256"]) and _sha256(intent["terminal_sha256"])):
            raise _invalid()
        if (
            intent["cancellation_sha256"] is not None
            or not isinstance(intent["run_id"], str)
            or RUN_ID.fullmatch(intent["run_id"]) is None
        ):
            raise _invalid()
    expected_hashes = {
        name: hashlib.sha256(path.encode("utf-8")).hexdigest()
        for name, path in _safe_paths(intent["run_id"] if branch == "terminal" else None).items()
    }
    if intent["safe_path_sha256s"] != expected_hashes:
        raise _invalid()


def _validate_root_children(root_descriptor: int, intent: Mapping[str, object], *, replay: bool) -> None:
    authorization = "authorization"
    branch = intent["branch"]
    expected = set() if replay else {DOCUMENT_NAME}
    if branch != "no_issuance":
        expected.add(authorization)
    if set(os.listdir(root_descriptor)) != expected:
        raise _invalid()
    if branch != "no_issuance":
        try:
            descriptor = os.open(authorization, _directory_flags(), dir_fd=root_descriptor)
        except OSError as exc:
            raise _invalid() from exc
        try:
            _assert_directory_stat(os.fstat(descriptor))
        finally:
            os.close(descriptor)


def _unlink_readiness(root_descriptor: int) -> None:
    os.unlink(DOCUMENT_NAME, dir_fd=root_descriptor)


def _assert_regular_stat(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_gid != os.getgid()
    ):
        raise _invalid()


def _read_canonical_json(descriptor: int, metadata: os.stat_result) -> dict[str, object]:
    try:
        content = os.read(descriptor, metadata.st_size)
        document = json.loads(content)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _invalid() from exc
    if not isinstance(document, dict) or content != (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8"):
        raise _invalid()
    return document


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _entry_matches(parent_descriptor: int, name: str, expected: os.stat_result) -> bool:
    try:
        return _same_inode(
            os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False), expected
        )
    except OSError:
        return False


def _entry_is_absent(parent_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _close_all(descriptors: list[int]) -> bool:
    failed = False
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError:
            failed = True
    return failed


def dispose_account_readiness(cleanup_intent: Path) -> CleanupEvidence:
    """Consume immutable Task 3 intent and remove only the readiness file."""
    if (
        cleanup_intent != CLEANUP_INTENT_PATH
        or PRIVATE_ROOT.parent != CLEANUP_INTENT_PATH.parent
    ):
        raise _invalid()
    descriptors: list[int] = []
    committed = False
    result: CleanupEvidence | None = None
    failure: BaseException | None = None
    try:
        parent_descriptor = os.open(PRIVATE_ROOT.parent, _directory_flags())
        descriptors.append(parent_descriptor)
        if not stat.S_ISDIR(os.fstat(parent_descriptor).st_mode):
            raise _invalid()
        root_descriptor = os.open(
            PRIVATE_ROOT.name, _directory_flags(), dir_fd=parent_descriptor
        )
        descriptors.append(root_descriptor)
        root_metadata = os.fstat(root_descriptor)
        _assert_directory_stat(root_metadata)
        intent_descriptor = os.open(
            CLEANUP_INTENT_PATH.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        descriptors.append(intent_descriptor)
        intent_metadata = os.fstat(intent_descriptor)
        _assert_regular_stat(intent_metadata)
        intent = _read_canonical_json(intent_descriptor, intent_metadata)
        _validate_intent(intent)
        try:
            readiness_descriptor = os.open(
                DOCUMENT_NAME,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_descriptor,
            )
        except FileNotFoundError:
            _validate_root_children(root_descriptor, intent, replay=True)
            if not (
                _entry_matches(parent_descriptor, PRIVATE_ROOT.name, root_metadata)
                and _entry_matches(
                    parent_descriptor, CLEANUP_INTENT_PATH.name, intent_metadata
                )
            ):
                raise _invalid()
            committed = True
            _fsync_root_after_unlink(root_descriptor)
            if not (
                _entry_is_absent(root_descriptor, DOCUMENT_NAME)
                and _entry_matches(parent_descriptor, PRIVATE_ROOT.name, root_metadata)
                and _entry_matches(
                    parent_descriptor, CLEANUP_INTENT_PATH.name, intent_metadata
                )
            ):
                raise AccountReadinessCleanupIncomplete()
            result = CleanupEvidence(
                deleted=False, content_sha256=str(intent["account_readiness_sha256"])
            )
        except OSError as exc:
            raise _invalid() from exc
        else:
            descriptors.append(readiness_descriptor)
            readiness_metadata = os.fstat(readiness_descriptor)
            _assert_regular_stat(readiness_metadata)
            document = _read_canonical_json(readiness_descriptor, readiness_metadata)
            _validate_root_children(root_descriptor, intent, replay=False)
            _, expires_at = _validate_document_shape(document)
            if (
                document["content_sha256"] != intent["account_readiness_sha256"]
                or document["expires_at"] != intent["readiness_expires_at"]
                or _parse_timestamp(intent["readiness_expires_at"]) != expires_at
            ):
                raise _invalid()
            if not (
                _entry_matches(parent_descriptor, PRIVATE_ROOT.name, root_metadata)
                and _entry_matches(
                    parent_descriptor, CLEANUP_INTENT_PATH.name, intent_metadata
                )
                and _entry_matches(root_descriptor, DOCUMENT_NAME, readiness_metadata)
            ):
                raise _invalid()
            _unlink_readiness(root_descriptor)
            committed = True
            _fsync_root_after_unlink(root_descriptor)
            if not (
                os.fstat(readiness_descriptor).st_nlink == 0
                and _entry_is_absent(root_descriptor, DOCUMENT_NAME)
                and _entry_matches(parent_descriptor, PRIVATE_ROOT.name, root_metadata)
                and _entry_matches(
                    parent_descriptor, CLEANUP_INTENT_PATH.name, intent_metadata
                )
            ):
                raise AccountReadinessCleanupIncomplete()
            result = CleanupEvidence(
                deleted=True, content_sha256=str(document["content_sha256"])
            )
    except AccountReadinessCleanupIncomplete as exc:
        failure = exc
    except (AccountReadinessError, OSError, ValueError, TypeError) as exc:
        failure = exc
    finally:
        close_failed = _close_all(descriptors)
    if committed and (failure is not None or close_failed):
        raise AccountReadinessCleanupIncomplete()
    if failure is not None or close_failed or result is None:
        raise _invalid()
    return result


def _parse_json(value: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise _invalid() from exc
    if not isinstance(parsed, Mapping):
        raise _invalid()
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser("issue", allow_abbrev=False)
    validate = commands.add_parser("validate", allow_abbrev=False)
    dispose = commands.add_parser("dispose", allow_abbrev=False)
    for command in (issue, validate):
        command.add_argument("--root", required=True)
        command.add_argument("--cycle-id", required=True)
        command.add_argument("--region", required=True)
        command.add_argument("--max-incremental-cny", required=True)
    issue.add_argument("--expires-in-seconds", required=True, type=int)
    for name in OPERATOR_CLAIMS:
        issue.add_argument("--" + name.replace("_", "-"), action="store_true")
    validate.add_argument("--phase", choices=("start", "resume"), default="start")
    validate.add_argument("--expected-content-sha256")
    validate.add_argument("--runtime-acceptance")
    dispose.add_argument("--cleanup-intent", required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(arguments)
        if args.command == "issue":
            document = issue_account_readiness(
                root=Path(args.root),
                cycle_id=args.cycle_id, region=args.region, max_incremental_cny=args.max_incremental_cny,
                expires_in_seconds=args.expires_in_seconds,
                operator_checks={name: getattr(args, name) for name in OPERATOR_CLAIMS}, environment=os.environ,
            )
            output = validate_account_readiness(
                root=Path(args.root),
                cycle_id=args.cycle_id, model=os.environ.get("QI_QWEN_MODEL", ""), region=args.region,
                max_incremental_cny=args.max_incremental_cny, environment=os.environ,
                expected_content_sha256=str(document["content_sha256"]),
            ).public_dict()
        elif args.command == "validate":
            output = validate_account_readiness(
                root=Path(args.root),
                cycle_id=args.cycle_id, model=os.environ.get("QI_QWEN_MODEL", ""), region=args.region,
                max_incremental_cny=args.max_incremental_cny, environment=os.environ, phase=args.phase,
                expected_content_sha256=args.expected_content_sha256,
                runtime_acceptance=None if args.runtime_acceptance is None else Path(args.runtime_acceptance),
            ).public_dict()
        else:
            output = dispose_account_readiness(Path(args.cleanup_intent)).__dict__
    except AccountReadinessCleanupIncomplete:
        print(json.dumps({"error": "account_readiness_cleanup_incomplete"}, sort_keys=True))
        return 3
    except (AccountReadinessError, OSError, ValueError, TypeError):
        print(json.dumps({"error": "account readiness is invalid"}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
