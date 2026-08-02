from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import os
import pickle
import re
import stat
import threading
from pathlib import Path

import pytest

from app.providers.pricing import load_pricing_snapshot
from app.providers.usage_ledger import (
    ProviderBudgetExceeded,
    ProviderUsageLedger,
    ReservationPermit,
)


CYCLE_ID = "gdt10d-classified-live-20260802"
RUN_ID = "20260802T000000000000Z-fixture"


def _hash_document(document: dict[str, object]) -> dict[str, object]:
    payload = dict(document)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(content).hexdigest()
    return payload


def _write_fact(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(
        json.dumps(_hash_document(document), sort_keys=True),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _authorization_root(
    tmp_path: Path,
    *,
    project_ids: tuple[str, ...] = ("project-one",),
) -> Path:
    root = tmp_path / "authorization"
    root.mkdir(mode=0o700)
    pricing = load_pricing_snapshot()
    _write_fact(
        root / "issuance.json",
        {
            "schema_version": "provider-cycle-issuance/1",
            "cycle_id": CYCLE_ID,
            "expires_at": "2099-08-02T23:59:59+00:00",
            "head_revision": "a" * 40,
            "plan_sha256": "b" * 64,
            "pricing_sha256": pricing.content_sha256,
            "runtime_closure_sha256": "c" * 64,
            "current_four_sha256": "d" * 64,
            "backend_image_id": "sha256:" + "9" * 64,
            "compose_project": "quality_inspection-qa",
            "expected_db_revision": "0014",
            "max_total_cny": "50.000000",
        },
    )
    issuance = json.loads((root / "issuance.json").read_text(encoding="utf-8"))
    _write_fact(
        root / "consumption.json",
        {
            "schema_version": "provider-cycle-consumption/1",
            "cycle_id": CYCLE_ID,
            "issuance_sha256": issuance["content_sha256"],
            "invocation_id": "e" * 64,
            "consumed_at": "2026-08-02T00:00:00+00:00",
        },
    )
    consumption = json.loads(
        (root / "consumption.json").read_text(encoding="utf-8")
    )
    _write_fact(
        root / "run.json",
        {
            "schema_version": "provider-cycle-run/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "consumption_sha256": consumption["content_sha256"],
        },
    )
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    for order, project_id in enumerate(project_ids, start=1):
        _write_fact(
            root / "projects" / f"{order:04d}.json",
            {
                "schema_version": "provider-cycle-project/1",
                "cycle_id": CYCLE_ID,
                "run_id": RUN_ID,
                "project_id": project_id,
                "project_order": order,
                "source_sha256": f"{order:x}" * 64,
                "run_sha256": run["content_sha256"],
            },
        )
    return root


def _open(
    storage_root: Path,
    authorization_root: Path,
    project_id: str = "project-one",
) -> ProviderUsageLedger:
    return ProviderUsageLedger.open(
        cycle_id=CYCLE_ID,
        storage_root=storage_root,
        authorization_root=authorization_root,
        project_id=project_id,
    )


def _reserve_qwen(
    ledger: ProviderUsageLedger,
    *,
    subject_id: str = "subject-one",
    retry_index: int = 0,
    page_index: int = 0,
):
    return ledger.reserve(
        provider="qwen-vl",
        operation="review_symbols",
        page_index=page_index,
        subject_kind="escalation_group",
        subject_id=subject_id,
        retry_index=retry_index,
        crop_expansion_count=0,
    )


def _multiprocess_reserve(
    storage_root: str,
    authorization_root: str,
    project_id: str,
    subject_id: str,
    ready,
    start,
    result,
) -> None:
    try:
        ledger = _open(
            Path(storage_root),
            Path(authorization_root),
            project_id,
        )
        ready.put("ready")
        start.wait(timeout=10)
        _reserve_qwen(ledger, subject_id=subject_id)
    except ProviderBudgetExceeded:
        result.put("budget")
    except Exception as exc:  # pragma: no cover - surfaced by parent assertion
        result.put(f"error:{type(exc).__name__}:{exc}")
    else:
        result.put("reserved")


def _multiprocess_close(
    storage_root: str,
    authorization_root: str,
    ready,
    start,
    result,
) -> None:
    try:
        ledger = _open(Path(storage_root), Path(authorization_root))
        ready.put("ready")
        start.wait(timeout=10)
        terminal = ledger.close_cycle(
            run_id=RUN_ID,
            status="failed",
            quiescence_sha256="f" * 64,
        )
    except Exception as exc:  # pragma: no cover - surfaced by parent assertion
        result.put(f"error:{type(exc).__name__}:{exc}")
    else:
        result.put(terminal["content_sha256"])


def test_reservation_exists_before_submission_and_reopen_keeps_charge(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)

    _reserve_qwen(ledger)

    snapshot = ledger.snapshot()
    assert snapshot.committed_total_cny == "1.763328"
    assert snapshot.reservation_count == 1
    assert snapshot.reserved_only_count == 1
    assert snapshot.submission_started_count == 0
    assert ledger.journal_ref == f"asset://provider-usage-cycles/{CYCLE_ID}/"
    reopened = _open(storage_root, authorization_root)
    assert reopened.snapshot() == snapshot
    assert sorted(
        path.name for path in (storage_root / "provider-usage-cycles" / CYCLE_ID).iterdir()
    ) == ["000001-reserved.json", "ledger.lock"]


def test_adapter_consumption_is_one_shot_and_unknown_keeps_reservation(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    ledger = _open(tmp_path / "storage", authorization_root)
    permit = _reserve_qwen(ledger)

    permit.consume_for_adapter(provider="qwen-vl", operation="review_symbols")
    with pytest.raises(ValueError, match="permit"):
        permit.consume_for_adapter(
            provider="qwen-vl",
            operation="review_symbols",
        )
    entry = ledger.retain_unknown(permit, request_id_state="absent")

    assert entry.state == "reserved_unknown"
    assert entry.charged_cny == "1.763328"
    assert ledger.snapshot().submission_started_count == 1
    assert ledger.snapshot().committed_total_cny == "1.763328"


def test_verified_usage_settles_down_and_ocr_remains_fixed(tmp_path: Path) -> None:
    authorization_root = _authorization_root(tmp_path)
    ledger = _open(tmp_path / "storage", authorization_root)
    qwen = _reserve_qwen(ledger)
    qwen.consume_for_adapter(provider="qwen-vl", operation="review_symbols")

    qwen_entry = ledger.settle(
        qwen,
        usage={"prompt_tokens": 32_769, "completion_tokens": 1},
        request_id="request-qwen-1",
    )
    ocr = ledger.reserve(
        provider="tencent-ocr",
        operation="GeneralAccurateOCR",
        page_index=1,
        subject_kind="ocr_region",
        subject_id="ocr-region-one",
        retry_index=0,
        crop_expansion_count=0,
    )
    ocr.consume_for_adapter(
        provider="tencent-ocr",
        operation="GeneralAccurateOCR",
    )
    ocr_entry = ledger.settle(
        ocr,
        usage=None,
        request_id="request-ocr-1",
    )

    assert qwen_entry.charged_cny == "0.049169"
    assert ocr_entry.charged_cny == "0.500000"
    assert ledger.snapshot().committed_total_cny == "0.549169"


def test_permit_is_process_local_noncopyable_and_cannot_be_reopened(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    permit = _reserve_qwen(ledger)

    with pytest.raises(TypeError, match="permit"):
        copy.copy(permit)
    with pytest.raises(TypeError, match="permit"):
        copy.deepcopy(permit)
    with pytest.raises(TypeError, match="permit"):
        pickle.dumps(permit)
    with pytest.raises(TypeError):
        json.dumps(permit)
    with pytest.raises(TypeError, match="permit"):
        ReservationPermit()  # type: ignore[call-arg]
    reopened = _open(storage_root, authorization_root)
    assert not hasattr(reopened, "recover_permit")
    assert reopened.snapshot().submission_started_count == 0


def test_forged_permit_before_first_consume_writes_no_started_fact(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    _reserve_qwen(ledger)
    forged = object.__new__(ReservationPermit)

    with pytest.raises(ValueError, match="permit"):
        forged.consume_for_adapter(  # type: ignore[attr-defined]
            provider="qwen-vl",
            operation="review_symbols",
        )

    assert ledger.snapshot().submission_started_count == 0
    assert not list(storage_root.rglob("*-submission-started.json"))


def test_two_projects_share_one_cycle_ceiling_across_processes(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(
        tmp_path,
        project_ids=("project-one", "project-two"),
    )
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    for index in range(27):
        _reserve_qwen(
            ledger,
            subject_id=f"prefill-{index:02d}",
            page_index=1 + index // 16,
        )

    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    result = context.Queue()
    processes = [
        context.Process(
            target=_multiprocess_reserve,
            args=(
                str(storage_root),
                str(authorization_root),
                project_id,
                f"contender-{index}",
                ready,
                start,
                result,
            ),
        )
        for index, project_id in enumerate(("project-one", "project-two"))
    ]
    for process in processes:
        process.start()
    assert [ready.get(timeout=10) for _ in processes] == ["ready", "ready"]
    start.set()
    outcomes = sorted(result.get(timeout=10) for _ in processes)
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert outcomes == ["budget", "reserved"]
    snapshot = _open(storage_root, authorization_root).snapshot()
    assert snapshot.reservation_count == 28
    assert snapshot.committed_total_cny == "49.373184"


def test_two_same_process_handles_do_not_reverse_lock_order(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    first = _open(storage_root, authorization_root)
    second = _open(storage_root, authorization_root)
    permit = _reserve_qwen(first, subject_id="consume-me")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            barrier.wait(timeout=2)
            permit.consume_for_adapter(
                provider="qwen-vl",
                operation="review_symbols",
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    def reserve() -> None:
        try:
            barrier.wait(timeout=2)
            _reserve_qwen(second, subject_id="reserve-too")
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=consume), threading.Thread(target=reserve)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert errors == []
    assert first.snapshot().reservation_count == 2
    assert first.snapshot().submission_started_count == 1


def test_two_process_close_contenders_converge_on_exact_terminal(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    _open(storage_root, authorization_root)
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    result = context.Queue()
    processes = [
        context.Process(
            target=_multiprocess_close,
            args=(
                str(storage_root),
                str(authorization_root),
                ready,
                start,
                result,
            ),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    assert [ready.get(timeout=10) for _ in processes] == ["ready", "ready"]
    start.set()
    outcomes = [result.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert len(set(outcomes)) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", outcomes[0])


def test_terminal_or_corrupt_journal_fails_closed(tmp_path: Path) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    _reserve_qwen(ledger)
    journal = storage_root / "provider-usage-cycles" / CYCLE_ID
    (journal / "unexpected.txt").write_text("unsafe", encoding="utf-8")

    with pytest.raises(ValueError, match="journal"):
        _open(storage_root, authorization_root)

    (journal / "unexpected.txt").unlink()
    _write_fact(
        authorization_root / "terminal.json",
        {
            "schema_version": "provider-cycle-terminal/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
                "status": "failed",
                "quiescence_sha256": "f" * 64,
                "run_sha256": json.loads(
                    (authorization_root / "run.json").read_text(encoding="utf-8")
                )["content_sha256"],
            },
    )
    with pytest.raises(ValueError, match="terminal"):
        _reserve_qwen(ledger, subject_id="after-terminal")


def test_page_subject_and_retry_budgets_fail_before_new_fact(tmp_path: Path) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    _reserve_qwen(ledger, subject_id="twice", retry_index=0)
    _reserve_qwen(ledger, subject_id="twice", retry_index=1)
    before = ledger.snapshot().reservation_count

    with pytest.raises(ProviderBudgetExceeded, match="subject"):
        _reserve_qwen(ledger, subject_id="twice", retry_index=1)
    with pytest.raises(ProviderBudgetExceeded, match="subject"):
        _reserve_qwen(ledger, subject_id="skipped-retry", retry_index=1)

    for index in range(14):
        _reserve_qwen(ledger, subject_id=f"page-fill-{index}")
    with pytest.raises(ProviderBudgetExceeded, match="page"):
        _reserve_qwen(ledger, subject_id="page-overflow")
    assert before == 2
    assert ledger.snapshot().reservation_count == 16


def test_lock_file_is_never_truncated_and_fact_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    journal = storage_root / "provider-usage-cycles" / CYCLE_ID
    lock_path = journal / "ledger.lock"
    lock_path.write_text("holder-diagnostic", encoding="utf-8")
    _reserve_qwen(ledger)

    assert lock_path.read_text(encoding="utf-8") == "holder-diagnostic"
    reservation_path = journal / "000001-reserved.json"
    reservation = json.loads(reservation_path.read_text(encoding="utf-8"))
    reservation["model"] = "tampered-model"
    reservation_path.write_text(json.dumps(reservation), encoding="utf-8")

    with pytest.raises(ValueError, match="hash"):
        _open(storage_root, authorization_root)


def test_symlinked_journal_or_authorization_fact_fails_closed(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    _reserve_qwen(ledger)
    journal = storage_root / "provider-usage-cycles" / CYCLE_ID
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    (journal / "000002-reserved.json").symlink_to(target)

    with pytest.raises(ValueError, match="journal"):
        _open(storage_root, authorization_root)

    (journal / "000002-reserved.json").unlink()
    (authorization_root / "resume-consumed.json").symlink_to(target)
    with pytest.raises(ValueError, match="authorization"):
        ledger.snapshot()


def test_duplicate_settlement_and_invalid_identity_are_rejected(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    ledger = _open(tmp_path / "storage", authorization_root)
    permit = _reserve_qwen(ledger)

    with pytest.raises(ValueError, match="permit"):
        permit.consume_for_adapter(
            provider="tencent-ocr",
            operation="GeneralAccurateOCR",
        )
    assert ledger.snapshot().submission_started_count == 0

    second = _reserve_qwen(ledger, subject_id="settle-once")
    second.consume_for_adapter(provider="qwen-vl", operation="review_symbols")
    ledger.retain_unknown(second, request_id_state="absent")
    with pytest.raises(ValueError, match="permit"):
        ledger.retain_unknown(second, request_id_state="absent")


def test_reserved_only_failure_retires_process_capability_without_started_fact(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    ledger = _open(tmp_path / "storage", authorization_root)
    permit = _reserve_qwen(ledger)

    assert (
        ledger.retain_unknown_if_started(
            permit,
            request_id_state="absent",
        )
        is None
    )
    with pytest.raises(ValueError, match="permit"):
        permit.consume_for_adapter(
            provider="qwen-vl",
            operation="review_symbols",
        )

    snapshot = ledger.snapshot()
    assert snapshot.reserved_only_count == 1
    assert snapshot.submission_started_count == 0


def test_close_cycle_holds_ledger_boundary_and_blocks_later_reservation(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    ledger = _open(tmp_path / "storage", authorization_root)
    permit = _reserve_qwen(ledger)
    permit.consume_for_adapter(provider="qwen-vl", operation="review_symbols")
    ledger.retain_unknown(permit, request_id_state="absent")

    terminal = ledger.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    )

    assert terminal["status"] == "failed"
    assert ledger.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    ) == terminal
    reopened_for_close = ProviderUsageLedger.open_for_close(
        cycle_id=CYCLE_ID,
        storage_root=tmp_path / "storage",
        authorization_root=authorization_root,
        project_id="project-one",
    )
    assert reopened_for_close.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    ) == terminal
    with pytest.raises(ValueError, match="terminal conflicts"):
        ledger.close_cycle(
            run_id=RUN_ID,
            status="aborted",
            quiescence_sha256="f" * 64,
        )
    assert stat.S_IMODE(
        (authorization_root / "terminal.json").stat().st_mode
    ) == 0o600
    with pytest.raises(ValueError, match="terminal"):
        _reserve_qwen(ledger, subject_id="after-close")


def test_close_only_validator_repairs_cycle_with_exact_cleanup_blocker(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    ledger = _open(storage_root, authorization_root)
    permit = _reserve_qwen(ledger)
    permit.consume_for_adapter(
        provider="qwen-vl",
        operation="review_symbols",
    )
    ledger.retain_unknown(permit, request_id_state="absent")
    _write_fact(
        authorization_root / "cleanup-blocker.json",
        {
            "schema_version": "provider-cycle-cleanup-blocker/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "status": "failed",
            "failure_codes": ["quiescence_close_or_finalize_failed"],
        },
    )

    with pytest.raises(ValueError, match="unexpected state"):
        _open(storage_root, authorization_root)

    reopened = ProviderUsageLedger.open_for_close(
        cycle_id=CYCLE_ID,
        storage_root=storage_root,
        authorization_root=authorization_root,
        project_id="project-one",
    )
    terminal = reopened.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    )

    assert terminal["status"] == "failed"
    assert reopened.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    ) == terminal
    assert (authorization_root / "cleanup-blocker.json").is_file()


def test_close_only_validator_rejects_invalid_cleanup_blocker(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path)
    storage_root = tmp_path / "storage"
    _open(storage_root, authorization_root)
    _write_fact(
        authorization_root / "cleanup-blocker.json",
        {
            "schema_version": "provider-cycle-cleanup-blocker/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "status": "failed",
            "failure_codes": ["private exception text"],
        },
    )

    with pytest.raises(ValueError, match="cleanup blocker"):
        ProviderUsageLedger.open_for_close(
            cycle_id=CYCLE_ID,
            storage_root=storage_root,
            authorization_root=authorization_root,
            project_id="project-one",
        )


def test_empty_cycle_close_repairs_exact_cleanup_blocker(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path, project_ids=())
    storage_root = tmp_path / "storage"
    _write_fact(
        authorization_root / "cleanup-blocker.json",
        {
            "schema_version": "provider-cycle-cleanup-blocker/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "status": "failed",
            "failure_codes": ["quiescence_close_or_finalize_failed"],
        },
    )

    terminal = ProviderUsageLedger.close_without_project(
        cycle_id=CYCLE_ID,
        storage_root=storage_root,
        authorization_root=authorization_root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    )

    assert terminal["status"] == "failed"
    assert ProviderUsageLedger.close_without_project(
        cycle_id=CYCLE_ID,
        storage_root=storage_root,
        authorization_root=authorization_root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    ) == terminal


def test_empty_cycle_close_rejects_invalid_cleanup_blocker(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path, project_ids=())
    (authorization_root / "run.json").unlink()
    storage_root = tmp_path / "storage"
    _write_fact(
        authorization_root / "cleanup-blocker.json",
        {
            "schema_version": "provider-cycle-cleanup-blocker/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "status": "failed",
            "failure_codes": ["private exception text"],
        },
    )

    with pytest.raises(ValueError, match="cleanup blocker"):
        ProviderUsageLedger.close_without_project(
            cycle_id=CYCLE_ID,
            storage_root=storage_root,
            authorization_root=authorization_root,
            run_id=RUN_ID,
            status="failed",
            quiescence_sha256="f" * 64,
        )
    assert not (authorization_root / "terminal.json").exists()
    assert not (authorization_root / "run.json").exists()


def test_close_cycle_revalidates_each_project_in_the_cycle_journal(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(
        tmp_path,
        project_ids=("project-one", "project-two"),
    )
    storage_root = tmp_path / "storage"
    first = _open(storage_root, authorization_root, "project-one")
    first_permit = _reserve_qwen(first, subject_id="first-project")
    first_permit.consume_for_adapter(
        provider="qwen-vl",
        operation="review_symbols",
    )
    first.retain_unknown(first_permit, request_id_state="absent")
    second = _open(storage_root, authorization_root, "project-two")
    second_permit = _reserve_qwen(second, subject_id="second-project")
    second_permit.consume_for_adapter(
        provider="qwen-vl",
        operation="review_symbols",
    )
    second.retain_unknown(second_permit, request_id_state="absent")

    terminal = first.close_cycle(
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="f" * 64,
    )

    assert terminal["status"] == "failed"


def test_bound_cycle_can_close_before_first_project_admission(
    tmp_path: Path,
) -> None:
    authorization_root = _authorization_root(tmp_path, project_ids=())
    (authorization_root / "run.json").unlink()

    terminal = ProviderUsageLedger.close_without_project(
        cycle_id=CYCLE_ID,
        storage_root=tmp_path / "storage",
        authorization_root=authorization_root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="e" * 64,
    )

    assert terminal["status"] == "failed"
    assert terminal["run_id"] == RUN_ID
    assert json.loads(
        (authorization_root / "run.json").read_text(encoding="utf-8")
    )["run_id"] == RUN_ID
    assert ProviderUsageLedger.close_without_project(
        cycle_id=CYCLE_ID,
        storage_root=tmp_path / "storage",
        authorization_root=authorization_root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="e" * 64,
    ) == terminal
