# Provider Failure Classification And Durable Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 production visual-symbol Provider failure 建立安全的事实分类、单一 Advisor disposition、脱敏且可重放的 durable evidence，以及 project-blocking stop 后 admitted-but-never-submitted groups 的完整 terminal evidence。

**Architecture:** `QwenVisionProvider` 只把 SDK/metadata/schema 边界观察转换为 typed `ProviderFailureFact`，现有 `VisualSymbolProviderError` 作为保留 safe schema metadata 的 typed carrier；`CandidateAdvisor` 用一个 frozen mapping 决定 `roi_localized|project_blocking` 与 pipeline cause，`ProductionRetryCoordinator` 继续独占唯一 schema retry decision。Routing evidence v2 在同一 transaction 写 sanitized diagnostic、attempt event 与 terminal outcome，production collector 只信任已持久化且与 propagated classification 完全一致的 failure，并为未提交 groups 写明确 cancellation terminal。

**Tech Stack:** Python 3.11、OpenAI Python SDK `>=1.60,<3`（当前环境 `2.46.0`）、SQLAlchemy 2、PostgreSQL JSONB、Alembic、pytest、Ruff。

## Global Constraints

- Parent design spec：`docs/superpowers/specs/2026-08-02-provider-failure-classification-and-durable-evidence-design.md`；用户批准前不得执行本 plan。
- Parent plan：`docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`；本 plan 不改变 GDT-10 Step 4 blocked 状态。
- Provider 只拥有 factual classification；`CandidateAdvisor`/`ProductionRetryCoordinator` 继续唯一拥有 scope 与 retry decision。
- 保持 `timeout=60.0`、SDK `max_retries=0`、`MAX_VISUAL_IN_FLIGHT=2`、page/project/call/wall budget 不变。
- timeout、transport 与已经用尽唯一 approved schema retry 的 schema failure 保持 `roi_localized`；authentication、request rejection、rate limit、service failure、metadata invalid 与 unclassified failure 必须 `project_blocking`。
- 除 production schema-invalid 现有最多一次 coordinator retry 外，不增加 automatic retry；user-facing `retryable` 不等于 automatic retry。
- 禁止持久化或返回 raw exception text/repr/class、cause/context、response body、SDK error code/param、headers map、URL、path、prompt、crop bytes、usage payload、token 或 credential；也不得对这些 raw detail 做 hash 后持久化。
- project-blocking failure 不生成 `AutomaticResult`、working copy、pause、symbol report 或 receipt。
- 不创建 `GDT-10D`，不调用 Provider，不运行 `make verify-p0-live`，不注入 credential，不 recreate runtime，不扩大 budget，不批准 production promotion。
- `0014` 的 v1 server default 只是 migration-first bridge；production promotion继续 blocked，直到另行批准的 `0015_drop_symbol_attempt_v1_default` 在所有 writers v2 + no-new-v1 observation gate后退休该 default。本 plan 不创建 `0015`。
- 本 plan 只修改下列 file map；不得顺手重构 OCR、legacy `review_candidate()`、GD&T normalizer、ReviewService、frontend、export 或 Harness live policy。
- 每个 implementation task 先 RED、再最小 GREEN、再 focused self-review、最后只提交该 task 的明确文件；全部 tasks 完成后执行一次 mandatory independent review gate。

---

## File Map

- Modify `backend/app/providers/base.py`：定义 immutable Provider failure fact、category/origin types 和 sanitized exception carrier。
- Modify `backend/app/providers/qwen_vl.py`：把 OpenAI SDK timeout/connection/status、metadata、schema 和 unknown exception 转成 Provider facts；保留 input validation 与 schema diagnostic contract。
- Modify `backend/app/candidates/advisor.py`：唯一 Advisor classification mapping、typed propagation、atomic persistence wrapper、collector stop/drain/cancel control flow。
- Modify `backend/app/candidates/routing_evidence.py`：attempt v2 exact diagnostic schema/hash、failure terminal atomic write、新 event/outcome codes、replay/conflict validation。
- Modify `backend/app/candidates/models.py`：为 attempt event ORM model 增加 schema version、diagnostic 与 diagnostic hash columns。
- Create `backend/alembic/versions/0014_symbol_provider_failure_diagnostics.py`：不触发 immutable-row update 的 v1 compatibility migration，以及 v2-present downgrade veto。
- Modify `backend/app/processing/pipeline.py`：按 propagated Advisor classification 投影 exact project failure cause。
- Modify `backend/tests/contract/test_qwen_symbol_provider.py`：Provider failure matrix、safe request ID 和 privacy RED/GREEN。
- Modify `backend/tests/integration/test_symbol_routing_evidence.py`：v1/v2 replay、diagnostic hash、atomic rollback 与 immutable conflict。
- Modify `backend/tests/integration/test_schema.py`：新 columns 的 exact schema contract。
- Modify `backend/tests/integration/test_migration_reconciliation.py`：`0013 -> 0014 -> 0013` upgrade/downgrade contract。
- Modify `backend/tests/unit/candidates/test_advisor.py`：单一 mapping、propagation equality、two-in-flight stop/drain 与 never-submitted cancellation。
- Modify `backend/tests/integration/test_symbol_recognition_pipeline.py`：localized regression、project-blocking durable evidence 与 false-success boundary。
- Modify `backend/tests/integration/test_processing_entry_task.py`：pipeline cause projection 和 result-layer absence。
- Modify `backend/tests/integration/test_project_status_api.py`：returned status payload 的 fixed-literal/privacy contract。
- Modify `.agent/bug-memory.md`：仅在 implementation 与 verification 都通过后追加根因/修复/防回归记录。
- Modify `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`：仅在 implementation review 后记录 companion plan commit 与 GDT-10 blocker 新状态；不声明 live closure。

### Task 1: Typed Provider Failure Facts And Safe Status Classification

**Files:**
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/qwen_vl.py`
- Test: `backend/tests/contract/test_qwen_symbol_provider.py`

**Interfaces:**
- Consumes: OpenAI SDK `APIStatusError.status_code` 与 `APIStatusError.request_id`，现有 `validate_visual_request_metadata()` safe ID policy，以及现有 sanitized `VisualSymbolProviderError` schema carrier。
- Produces: Provider-base-owned `classify_provider_failure_request_id()`、`ProviderFailureCategory`、`ProviderFailureOrigin`、`ProviderFailureFact`、`ClassifiedProviderFailure.fact`，以及 `VisualSymbolProviderError.fact`；Task 3 的 Advisor mapping 只消费 facts，不读取原 exception。

- [ ] **Step 1: Write the Provider fact invariant tests**

在 `backend/tests/contract/test_qwen_symbol_provider.py` 增加 exact constructor tests，证明 invalid status/origin/request-ID state 被拒绝，并且 exception message 是固定 literal：

```python
def test_provider_failure_fact_rejects_inconsistent_http_metadata() -> None:
    with pytest.raises(ValueError, match="^Provider failure fact is invalid$"):
        ProviderFailureFact(
            category="rate_limited",
            origin="sdk_http_status",
            http_status=None,
            provider_request_id=None,
            request_id_state="absent",
        )


def test_classified_provider_failure_does_not_render_private_detail() -> None:
    fact = ProviderFailureFact(
        category="unclassified",
        origin="provider_boundary",
        http_status=None,
        provider_request_id=None,
        request_id_state="absent",
    )
    error = ClassifiedProviderFailure(fact)
    assert str(error) == "visual symbol Provider request failed"
    assert error.fact is fact


@pytest.mark.parametrize(
    "unsafe_id",
    ("token-do-not-leak", "PASSWORD-value", "session.cookie"),
)
def test_provider_failure_fact_rejects_unsafe_accepted_request_id(
    unsafe_id: str,
) -> None:
    with pytest.raises(ValueError, match="^Provider failure fact is invalid$"):
        ProviderFailureFact(
            category="service_failure",
            origin="sdk_http_status",
            http_status=503,
            provider_request_id=unsafe_id,
            request_id_state="accepted",
        )
```

- [ ] **Step 2: Run the fact tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_qwen_symbol_provider.py -k 'provider_failure_fact or classified_provider_failure' -q
```

Expected: FAIL during collection because `ProviderFailureFact` and `ClassifiedProviderFailure` are not defined.

- [ ] **Step 3: Add immutable facts and the sanitized carrier**

在 `backend/app/providers/base.py` 使用 literal types 和 frozen dataclass；safe request-ID classifier 与 fact invariant 共同 enforce：只有 `sdk_http_status` 可携带 `400..599`，accepted request ID 才可非空且必须再次通过 allowlist/forbidden-word 检查，absent/rejected 必须为 `None`。

```python
ProviderFailureCategory = Literal[
    "timeout",
    "transport",
    "schema",
    "authentication",
    "request_rejected",
    "rate_limited",
    "service_failure",
    "metadata_invalid",
    "unclassified",
]
ProviderFailureOrigin = Literal[
    "sdk_timeout",
    "sdk_connection",
    "sdk_http_status",
    "response_metadata",
    "response_schema",
    "provider_boundary",
]
ProviderRequestIdState = Literal["absent", "accepted", "rejected"]

_SAFE_PROVIDER_FAILURE_REQUEST_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)
_FORBIDDEN_PROVIDER_FAILURE_REQUEST_ID = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer|"
    r"token|password|passwd|cookie|session",
    re.IGNORECASE,
)

_FACT_ORIGINS_BY_CATEGORY = {
    "timeout": {"sdk_timeout", "sdk_http_status"},
    "transport": {"sdk_connection"},
    "schema": {"response_schema"},
    "authentication": {"sdk_http_status"},
    "request_rejected": {"sdk_http_status"},
    "rate_limited": {"sdk_http_status"},
    "service_failure": {"sdk_http_status"},
    "metadata_invalid": {"response_metadata"},
    "unclassified": {"provider_boundary"},
}


def provider_failure_category_for_http_status(
    status: int,
) -> ProviderFailureCategory:
    if status == 408:
        return "timeout"
    if status in {401, 403}:
        return "authentication"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "service_failure"
    return "request_rejected"


def classify_provider_failure_request_id(
    value: object,
) -> tuple[str | None, ProviderRequestIdState]:
    if value is None:
        return None, "absent"
    if (
        isinstance(value, str)
        and _SAFE_PROVIDER_FAILURE_REQUEST_ID.fullmatch(value)
        and not _FORBIDDEN_PROVIDER_FAILURE_REQUEST_ID.search(value)
    ):
        return value, "accepted"
    return None, "rejected"


@dataclass(frozen=True)
class ProviderFailureFact:
    category: ProviderFailureCategory
    origin: ProviderFailureOrigin
    http_status: int | None
    provider_request_id: str | None
    request_id_state: ProviderRequestIdState

    def __post_init__(self) -> None:
        if (
            self.category not in _FACT_ORIGINS_BY_CATEGORY
            or self.origin not in _FACT_ORIGINS_BY_CATEGORY[self.category]
            or self.request_id_state not in {"absent", "accepted", "rejected"}
        ):
            raise ValueError("Provider failure fact is invalid")
        if self.origin == "sdk_http_status":
            if (
                not isinstance(self.http_status, int)
                or isinstance(self.http_status, bool)
                or not 400 <= self.http_status <= 599
                or self.category
                != provider_failure_category_for_http_status(self.http_status)
            ):
                raise ValueError("Provider failure fact is invalid")
        elif self.http_status is not None:
            raise ValueError("Provider failure fact is invalid")
        if (self.provider_request_id is not None) != (
            self.request_id_state == "accepted"
        ):
            raise ValueError("Provider failure fact is invalid")
        if self.request_id_state == "accepted" and (
            classify_provider_failure_request_id(self.provider_request_id)
            != (self.provider_request_id, "accepted")
        ):
            raise ValueError("Provider failure fact is invalid")


class ClassifiedProviderFailure(RuntimeError):
    def __init__(self, fact: ProviderFailureFact) -> None:
        super().__init__("visual symbol Provider request failed")
        self.fact = fact
```

保留 `LocalizedProviderFailure` 供不在本 scope 的 legacy behavior 使用，但 `review_symbols()` 新路径不得再为 unknown 创建它。

- [ ] **Step 4: Run the fact tests to verify GREEN**

Run the Step 2 command.

Expected: PASS for the new fact/carrier tests; no change to the existing localized category tests.

- [ ] **Step 5: Write the exact OpenAI/metadata/unknown classification matrix tests**

用 `httpx.Request`/`httpx.Response` 构造 SDK error，不读取 body 或 headers map；对每一行同时放入 private marker，并在 test 内定义 failing completions，断言 marker 与 raw exception chain 不出现在 sanitized carrier：

```python
@pytest.mark.parametrize(
    ("status", "category"),
    ((401, "authentication"), (403, "authentication"),
     (408, "timeout"), (429, "rate_limited"),
     (500, "service_failure"), (503, "service_failure"),
     (400, "request_rejected"), (422, "request_rejected")),
)
def test_review_symbols_classifies_http_status_without_private_detail(
    status: int,
    category: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "private://customer/token-do-not-leak"
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://private.invalid/v1"),
        headers={"x-request-id": "safe-status-request"},
    )
    provider_error = APIStatusError(
        marker, response=response, body={"detail": marker}
    )

    class FailingCompletions:
        @staticmethod
        def create(**_kwargs: object) -> object:
            raise provider_error

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions())
    )
    with pytest.raises(ClassifiedProviderFailure) as caught:
        QwenVisionProvider(client).review_symbols(_png(), "safe prompt")
    assert caught.value.fact.category == category
    assert caught.value.fact.origin == "sdk_http_status"
    assert caught.value.fact.http_status == status
    assert caught.value.fact.provider_request_id == "safe-status-request"
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value.fact)
    assert marker not in caplog.text
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
```

另加 timeout、connection、missing/unsafe completion ID、invalid usage、plain `RuntimeError(marker)` 和 schema carrier cases，分别期待 `timeout`、`transport`、`metadata_invalid`、`unclassified`、`schema`；每个 case 都断言 `__cause__ is None`、`__context__ is None`。unsafe request ID 使用 `token-do-not-leak|PASSWORD-value|session.cookie`，failure path只能产生 `request_id_state="rejected"` 与 `provider_request_id=None`；成功/schema response使用这些 ID 时必须在 metadata validation失败，且没有 call record/cache artifact。

- [ ] **Step 6: Run the matrix tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_qwen_symbol_provider.py -k 'classifies_http_status or classifies_timeout or classifies_connection or classifies_metadata or classifies_unknown' -q
```

Expected: FAIL because `review_symbols()` currently lets status/metadata/unknown failures cross the Provider boundary without `ProviderFailureFact`.

- [ ] **Step 7: Implement the safe boundary classifier**

在 `backend/app/providers/qwen_vl.py` import `APIStatusError`，只读取 `status_code`/`request_id`，并调用 Provider-base-owned request-ID classifier；禁止读取 `response.body`、`headers`、`message`、`code` 或 `param`：

```python
def _status_failure_fact(exc: APIStatusError) -> ProviderFailureFact:
    status = exc.status_code
    request_id, request_id_state = classify_provider_failure_request_id(
        exc.request_id
    )
    return ProviderFailureFact(
        category=provider_failure_category_for_http_status(status),
        origin="sdk_http_status",
        http_status=status,
        provider_request_id=request_id,
        request_id_state=request_id_state,
    )
```

`review_symbols()` 的 request call catches 按 specificity 排序：timeout、connection、status、unknown。每个 `except` 只赋 safe `failure_fact`，离开所有 `except` 后才 `raise ClassifiedProviderFailure(failure_fact)`，确保 raw exception 不进入 `__context__`。completion metadata validation采用同样的“catch 内 classify、catch 外 raise”结构，并让 `validate_visual_request_metadata()` 的 request-ID branch复用 Provider-base helper；因此成功、schema 和 error paths共享同一 forbidden-word policy，unsafe ID绝不进入 `VisionResult`、call record或 cache。

扩展现有 `VisualSymbolProviderError` constructor：先用 `validate_visual_request_metadata()` 得到 safe metadata，再创建 `ProviderFailureFact(category="schema", origin="response_schema", http_status=None, provider_request_id=request_id, request_id_state="accepted")` 并赋给 `.fact`。保留 `.request_id/.usage/.failure_stage/.diagnostic`；Task 3 的唯一 schema retry继续使用这些 safe fields。

- [ ] **Step 8: Run Provider contract and lint**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_qwen_symbol_provider.py -q
micromamba run -n qi-p0 ruff check backend/app/providers/base.py backend/app/providers/qwen_vl.py backend/tests/contract/test_qwen_symbol_provider.py
```

Expected: all tests PASS and Ruff exits `0`.

- [ ] **Step 9: Review and commit Task 1**

Review only Task 1 diff, confirm `review_candidate()` unchanged, then:

```bash
git add backend/app/providers/base.py backend/app/providers/qwen_vl.py backend/tests/contract/test_qwen_symbol_provider.py
git diff --cached --check
git commit -m "fix(provider): classify visual request failures safely"
```

Expected: one focused commit; no runtime, credential, live, or unrelated files staged.

### Task 2: Versioned Atomic Routing Failure Evidence

**Files:**
- Create: `backend/alembic/versions/0014_symbol_provider_failure_diagnostics.py`
- Modify: `backend/app/candidates/models.py`
- Modify: `backend/app/candidates/routing_evidence.py`
- Modify: `backend/tests/integration/test_symbol_routing_evidence.py`
- Modify: `backend/tests/integration/test_schema.py`
- Modify: `backend/tests/integration/test_migration_reconciliation.py`

**Interfaces:**
- Consumes: Task 1 categories as exact strings; existing `EscalationAttemptEvent`, `EscalationOutcome`, `ObservationOutcome`, decision hashes and immutable replay checks.
- Produces: `ProviderFailureDiagnostic`, `AdvisorBoundaryFailureDiagnostic`, `RetryControlDiagnostic`, `SchedulerStopDiagnostic`, attempt schema `symbol-escalation-attempt/2`, `RoutingEvidenceRepository.record_failure_terminal(...) -> str` and `record_schema_retry(...) -> str`; caller commits before propagation or retry.

- [ ] **Step 1: Write migration and schema RED tests**

先在 `0013` schema 插入一个 legacy attempt row，并用 `pg_trigger` 断言 `prevent_symbol_escalation_attempt_events_update_delete` active；再执行 upgrade，证明没有触发 immutable row update且 legacy row通过 constant server default读取为 v1：

```python
assert attempt_columns >= {
    "schema_version",
    "diagnostic",
    "diagnostic_sha256",
}
row = connection.execute(sa.text(
    "SELECT schema_version, diagnostic, diagnostic_sha256 "
    "FROM symbol_escalation_attempt_events WHERE id = :id"
), {"id": legacy_id}).one()
assert row == ("symbol-escalation-attempt/1", None, None)
```

覆盖两个 downgrade cases：v1-only DB 可 downgrade 到 `0013`，三个 columns消失且原 routing decision/outcome row count不变；另一个 DB先写 valid v2 row，downgrade必须抛 fixed `23514`，transaction rollback后 columns和 v2 row byte-for-byte 保留。

- [ ] **Step 2: Run migration/schema tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py -k 'symbol_escalation_attempt or provider_failure_diagnostic' -q
```

Expected: FAIL because revision `0014` and the new columns do not exist.

- [ ] **Step 3: Add the reversible `0014` migration and ORM columns**

Create `backend/alembic/versions/0014_symbol_provider_failure_diagnostics.py` with `revision="0014"`, `down_revision="0013"`。禁止 `UPDATE` legacy rows或 disable immutable trigger；constant server default同时提供 no-update backfill 和 migration-first old-writer compatibility：

```python
def upgrade() -> None:
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column(
            "schema_version",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'symbol-escalation-attempt/1'"),
        ),
    )
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column("diagnostic", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column("diagnostic_sha256", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_symbol_attempt_diagnostic_version",
        "symbol_escalation_attempt_events",
        "(schema_version = 'symbol-escalation-attempt/1' "
        "AND diagnostic IS NULL AND diagnostic_sha256 IS NULL) OR "
        "(schema_version = 'symbol-escalation-attempt/2' "
        "AND diagnostic IS NOT NULL "
        "AND diagnostic_sha256 ~ '^[0-9a-f]{64}$')",
    )


def downgrade() -> None:
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM symbol_escalation_attempt_events
                WHERE schema_version = 'symbol-escalation-attempt/2'
                   OR diagnostic IS NOT NULL
                   OR diagnostic_sha256 IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'symbol escalation v2 evidence blocks downgrade'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
    """))
    op.drop_constraint(
        "ck_symbol_attempt_diagnostic_version",
        "symbol_escalation_attempt_events",
        type_="check",
    )
    op.drop_column("symbol_escalation_attempt_events", "diagnostic_sha256")
    op.drop_column("symbol_escalation_attempt_events", "diagnostic")
    op.drop_column("symbol_escalation_attempt_events", "schema_version")
```

在 ORM model 增加 `Mapped[str]`、`Mapped[dict[str, Any] | None]` 与 `Mapped[str | None]`，长度、nullability和 v1 `server_default` 必须与 migration 相同；new repository writer仍须显式传 event schema version。

增加 repository test：new `append_attempt`/failure/retry/cancellation writers产生的 rows 全部为 v2；只有模拟 old writer不传 column时才命中 v1 default。把 future retirement gate名称 `0015_drop_symbol_attempt_v1_default` 写入 parent-plan implementation closeout，且在 default移除前保持 production promotion blocked。

- [ ] **Step 4: Run migration/schema tests to verify GREEN**

Run the Step 2 command.

Expected: PASS for active-trigger no-update upgrade、v1 compatibility、v1-only downgrade、v2-present downgrade veto and schema inspection.

- [ ] **Step 5: Write diagnostic validation/hash/atomicity RED tests**

在 `test_symbol_routing_evidence.py` 创建一组决策后，用 private marker 证明 exact keys、hash 和 rollback：

```python
diagnostic = ProviderFailureDiagnostic(
    schema_version="visual-symbol-provider-failure/1",
    failure_category="rate_limited",
    failure_stage="provider_rate_limited",
    scope="project_blocking",
    origin="sdk_http_status",
    http_status=429,
    request_id_state="absent",
    pipeline_cause_category="transient_provider_failure",
    retry_decision="not_authorized",
)
event_sha = repository.record_failure_terminal(
    project_id=project.id,
    event=EscalationAttemptEvent(
        schema_version="symbol-escalation-attempt/2",
        escalation_group_id=group_id,
        routing_decision_sha256=decision_sha,
        attempt_index=1,
        event_code="provider_rate_limited",
        cache_entry_id=None,
        provider_request_id=None,
        diagnostic=diagnostic.as_dict(),
    ),
    outcome_code="unresolved",
    observation_outcomes=tuple(
        ObservationOutcome(
            visual_observation_id=observation_id,
            outcome_code="provider_rate_limited",
        )
        for observation_id in group_observation_ids
    ),
)
session.commit()
assert persisted.event_sha256 == event_sha
assert persisted.diagnostic_sha256 == _canonical_sha256(diagnostic.as_dict())
assert "private://customer/token-do-not-leak" not in json.dumps(
    persisted.diagnostic
)
```

再 monkeypatch terminal insert 抛异常，调用 `session.rollback()` 后断言 attempt 与 terminal 都不存在；同一 unique key 用不同 diagnostic replay 必须抛 `RoutingEvidenceConflict`，first writer rows 不变。

- [ ] **Step 6: Run routing evidence tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_routing_evidence.py -k 'provider_failure_diagnostic or failure_terminal or scheduler_stop' -q
```

Expected: FAIL because v2 diagnostic dataclasses/codes/hash and atomic method are absent.

- [ ] **Step 7: Implement exact diagnostic schemas and canonical hashes**

在 `routing_evidence.py` 把 v1/v2 attempt versions 都列为 accepted，并加入 exact allowlists：

```python
PROVIDER_FAILURE_EVENT_CODES = frozenset({
    "provider_authentication_failed",
    "provider_request_rejected",
    "provider_rate_limited",
    "provider_service_failure",
    "provider_metadata_invalid",
    "provider_unclassified_failure",
})
ADVISOR_BOUNDARY_FAILURE_EVENT_CODES = frozenset({
    "provider_factory_failed",
    "provider_contract_failure",
    "advisor_result_missing",
})
PROJECT_FAILURE_CANCELLATION_EVENT_CODE = (
    "not_started_after_project_failure"
)
PROJECT_FAILURE_CANCELLATION_OUTCOME_CODE = (
    "cancelled_after_project_failure"
)
```

这些 codes进入 deterministic `ATTEMPT_EVENT_ORDER`；Provider/advisor failure codes也进入 observation outcome allowlist。然后定义 exact-key dataclasses：

```python
@dataclass(frozen=True)
class ProviderFailureDiagnostic:
    schema_version: str
    failure_category: str
    failure_stage: str
    scope: str
    origin: str
    http_status: int | None
    request_id_state: str
    pipeline_cause_category: str | None
    retry_decision: str

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_provider_failure_diagnostic(document)
        return document


@dataclass(frozen=True)
class AdvisorBoundaryFailureDiagnostic:
    schema_version: str
    failure_stage: str
    scope: str
    pipeline_cause_category: str
    provider_work_started: bool

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_advisor_boundary_failure_diagnostic(document)
        return document


@dataclass(frozen=True)
class RetryControlDiagnostic:
    schema_version: str
    retry_reason: str
    authorization_owner: str
    failure_event_sha256: str

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_retry_control_diagnostic(document)
        return document


@dataclass(frozen=True)
class SchedulerStopDiagnostic:
    schema_version: str
    stop_reason: str
    blocking_event_sha256: str
    provider_work_started: bool

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_scheduler_stop_diagnostic(document)
        return document
```

Provider diagnostic validator 必须执行 classification matrix exact match，并只接受 `retry_decision in {"not_authorized", "authorized_schema_retry"}`；后者只允许 schema + `provider_schema_invalid`。Retry-control validator只接受 `visual-symbol-retry-control/1`、`schema_invalid`、`production_retry_coordinator` 和 64 lowercase failure event SHA。Advisor-boundary validator只接受 design spec 三个 stage及其 exact `provider_work_started` 值。scheduler validator 只接受 `visual-symbol-scheduler-stop/1`、两个 exact stop reasons、64 lowercase hex 和 `provider_work_started is False`；stop reason必须与 blocking classification type相符。authorized schema event 与 retry-control event 的 adjacency/cross-reference只能由 Step 8 dedicated pair writer验证。`EscalationAttemptEvent` v2 canonical payload包含 sanitized diagnostic 与其 SHA；v1 hash算法保持 byte-for-byte 不变。

- [ ] **Step 8: Implement the atomic failure terminal repository method**

方法只使用 caller session，不自行 commit；append/replay 与 terminal insert 在同一 transaction 中完成，返回 canonical event SHA：

```python
def record_failure_terminal(
    self,
    *,
    project_id: uuid.UUID,
    event: EscalationAttemptEvent,
    outcome_code: str,
    observation_outcomes: tuple[ObservationOutcome, ...],
) -> str:
    attempt = self.append_attempt(project_id=project_id, event=event)
    attempt_sha256s = self.canonical_attempt_sha256s(
        project_id=project_id,
        escalation_group_id=event.escalation_group_id,
        routing_decision_sha256=event.routing_decision_sha256,
    )
    self.record_terminal_outcome(
        project_id=project_id,
        outcome=EscalationOutcome(
            schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
            escalation_group_id=event.escalation_group_id,
            routing_decision_sha256=event.routing_decision_sha256,
            outcome_code=outcome_code,
            observation_outcomes=observation_outcomes,
            attempt_event_sha256s=attempt_sha256s,
            terminal=True,
        ),
    )
    return attempt.event_sha256
```

`append_attempt()` 必须在 insert 前 validate diagnostic/hash pair，并在 replay 时比较完整 v2 hash；不能用 old unique key 命中后忽略 different diagnostic。

Public `append_attempt()` 与 `record_failure_terminal()` 必须先调用 `_is_schema_retry_pair_member(event)`；如果 event 是 `retry_scheduled`，或 Provider diagnostic 的 `retry_decision="authorized_schema_retry"`，固定抛 `RoutingEvidenceConflict("schema retry evidence requires pair writer")`。只有 `record_schema_retry()` 可以调用 private `_append_attempt_record()` 写 pair members。RED tests分别直接调用两个 public generic methods写两种 member，断言失败、rollback后 row count为 `0`。

`EscalationAttemptEvent` 新增 `diagnostic: Mapping[str, object] | None = None`；v1只允许 `None`，v2必须通过四个 exact diagnostic validators之一。`event_sha256` 对 v1必须显式构造旧七字段 payload，不能对新增 dataclass直接 `asdict()`；v2在旧字段之外加入 canonical diagnostic 与 `diagnostic_sha256`：

```python
@property
def event_sha256(self) -> str:
    payload: dict[str, object] = {
        "schema_version": self.schema_version,
        "escalation_group_id": self.escalation_group_id,
        "routing_decision_sha256": self.routing_decision_sha256,
        "attempt_index": self.attempt_index,
        "event_code": self.event_code,
        "cache_entry_id": (
            None if self.cache_entry_id is None else str(self.cache_entry_id)
        ),
        "provider_request_id": self.provider_request_id,
    }
    if self.schema_version == ESCALATION_ATTEMPT_SCHEMA_VERSION_V2:
        diagnostic = dict(self.diagnostic or {})
        payload["diagnostic"] = diagnostic
        payload["diagnostic_sha256"] = _canonical_sha256(diagnostic)
    return _canonical_sha256(payload)
```

先用 existing v1 fixture断言修改前后的 known `event_sha256` literal完全相同，再实现：

```python
def record_schema_retry(
    self,
    *,
    project_id: uuid.UUID,
    failure_event: EscalationAttemptEvent,
) -> str:
    if (
        failure_event.event_code != "provider_schema_invalid"
        or failure_event.diagnostic is None
        or failure_event.diagnostic.get("retry_decision")
        != "authorized_schema_retry"
    ):
        raise RoutingEvidenceConflict("schema retry evidence conflicts")
    retry_event = EscalationAttemptEvent(
        schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION_V2,
        escalation_group_id=failure_event.escalation_group_id,
        routing_decision_sha256=failure_event.routing_decision_sha256,
        attempt_index=failure_event.attempt_index,
        event_code="retry_scheduled",
        cache_entry_id=None,
        provider_request_id=failure_event.provider_request_id,
        diagnostic=RetryControlDiagnostic(
            schema_version="visual-symbol-retry-control/1",
            retry_reason="schema_invalid",
            authorization_owner="production_retry_coordinator",
            failure_event_sha256=failure_event.event_sha256,
        ).as_dict(),
    )
    _validate_schema_retry_pair(failure_event, retry_event)
    failure_attempt = self._append_attempt_record(
        project_id=project_id,
        event=failure_event,
    )
    self._append_attempt_record(project_id=project_id, event=retry_event)
    return failure_attempt.event_sha256
```

`_validate_schema_retry_pair()` 必须证明同 group/decision/attempt/request ID、failure code/diagnostic exact、retry control cross-reference exact，且 `ATTEMPT_EVENT_ORDER["provider_schema_invalid"] < ATTEMPT_EVENT_ORDER["retry_scheduled"]`。所有 v2 rows都必须有 diagnostic/hash；`retry_scheduled` 不允许 null diagnostic或 extension fields。若第二 insert/replay失败，caller rollback整个 transaction；test机械证明没有 orphan row。

- [ ] **Step 9: Run all Task 2 tests and lint**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py -q
micromamba run -n qi-p0 ruff check backend/app/candidates/models.py backend/app/candidates/routing_evidence.py backend/alembic/versions/0014_symbol_provider_failure_diagnostics.py backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py
```

Expected: PASS; v1 replay hashes unchanged; rollback tests prove no orphan attempt/terminal.

- [ ] **Step 10: Review and commit Task 2**

```bash
git add backend/alembic/versions/0014_symbol_provider_failure_diagnostics.py backend/app/candidates/models.py backend/app/candidates/routing_evidence.py backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py
git diff --cached --check
git commit -m "feat(evidence): persist sanitized provider failures atomically"
```

Expected: one migration/evidence commit; no Advisor behavior changed yet.

### Task 3: Single Advisor Disposition And Persisted/Propagated Equality

**Files:**
- Modify: `backend/app/candidates/advisor.py`
- Test: `backend/tests/unit/candidates/test_advisor.py`
- Test: `backend/tests/integration/test_symbol_recognition_pipeline.py`

**Interfaces:**
- Consumes: Task 1 `ClassifiedProviderFailure.fact` 与 `VisualSymbolProviderError.fact/request_id/usage/failure_stage/diagnostic`；Task 2 diagnostics 和 `RoutingEvidenceRepository.record_failure_terminal(...) -> str`.
- Produces: validated `AdvisorFailureClassification`、separate `AdvisorBoundaryFailureClassification`、`classify_provider_failure(fact) -> AdvisorFailureClassification`、`ProductionRetryCoordinator.authorize_schema_retry(carrier, identity, duration_ms) -> bool`、`CandidateAdvisorFailure.classification`、`failure_event_sha256`；Task 4 scheduler 和 Task 5 pipeline 只消费这些 properties。

- [ ] **Step 1: Write the frozen disposition matrix RED test**

```python
def provider_fact_for_test(category: str) -> ProviderFailureFact:
    origin_by_category = {
        "timeout": "sdk_timeout",
        "transport": "sdk_connection",
        "schema": "response_schema",
        "authentication": "sdk_http_status",
        "request_rejected": "sdk_http_status",
        "rate_limited": "sdk_http_status",
        "service_failure": "sdk_http_status",
        "metadata_invalid": "response_metadata",
        "unclassified": "provider_boundary",
    }
    status_by_category = {
        "authentication": 401,
        "request_rejected": 422,
        "rate_limited": 429,
        "service_failure": 503,
    }
    return ProviderFailureFact(
        category=category,
        origin=origin_by_category[category],
        http_status=status_by_category.get(category),
        provider_request_id=None,
        request_id_state="absent",
    )


@pytest.mark.parametrize(
    ("category", "stage", "scope", "cause"),
    (
        ("timeout", "provider_timeout", "roi_localized", None),
        ("transport", "provider_transport_failure", "roi_localized", None),
        ("schema", "provider_schema_invalid", "roi_localized", None),
        ("authentication", "provider_authentication_failed", "project_blocking", "invalid_configuration"),
        ("request_rejected", "provider_request_rejected", "project_blocking", "processing_defect"),
        ("rate_limited", "provider_rate_limited", "project_blocking", "transient_provider_failure"),
        ("service_failure", "provider_service_failure", "project_blocking", "transient_provider_failure"),
        ("metadata_invalid", "provider_metadata_invalid", "project_blocking", "processing_defect"),
        ("unclassified", "provider_unclassified_failure", "project_blocking", "processing_defect"),
    ),
)
def test_provider_failure_disposition_is_frozen(
    category: str, stage: str, scope: str, cause: str | None
) -> None:
    classification = classify_provider_failure(
        provider_fact_for_test(category)
    )
    assert (
        classification.failure_stage,
        classification.scope,
        classification.pipeline_cause_category,
    ) == (stage, scope, cause)


def test_advisor_failure_classification_rejects_mapping_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="^Advisor Provider failure classification is invalid$",
    ):
        AdvisorFailureClassification(
            fact=provider_fact_for_test("rate_limited"),
            failure_stage="provider_transport_failure",
            scope="roi_localized",
            pipeline_cause_category=None,
        )
```

- [ ] **Step 2: Run the disposition test to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py -k 'provider_failure_disposition_is_frozen' -q
```

Expected: FAIL because the typed mapping does not exist.

- [ ] **Step 3: Implement the single immutable Advisor mapping**

在 `advisor.py` 增加 frozen dataclass；mapping 是唯一 category-to-stage/scope/cause owner：

```python
@dataclass(frozen=True)
class AdvisorFailureClassification:
    fact: ProviderFailureFact
    failure_stage: str
    scope: Literal["roi_localized", "project_blocking"]
    pipeline_cause_category: str | None

    def __post_init__(self) -> None:
        if (
            self.failure_stage,
            self.scope,
            self.pipeline_cause_category,
        ) != _PROVIDER_FAILURE_DISPOSITIONS[self.fact.category]:
            raise ValueError(
                "Advisor Provider failure classification is invalid"
            )

    @property
    def category(self) -> ProviderFailureCategory:
        return self.fact.category

    @property
    def provider_request_id(self) -> str | None:
        return self.fact.provider_request_id


@dataclass(frozen=True)
class AdvisorBoundaryFailureClassification:
    failure_stage: Literal[
        "provider_factory_failed",
        "provider_contract_failure",
        "advisor_result_missing",
    ]
    provider_work_started: bool
    scope: Literal["project_blocking"] = "project_blocking"
    pipeline_cause_category: Literal[
        "processing_defect"
    ] = "processing_defect"

    def __post_init__(self) -> None:
        expected_started = self.failure_stage != "provider_factory_failed"
        if self.provider_work_started is not expected_started:
            raise ValueError("Advisor boundary failure is invalid")


def classify_provider_failure(
    fact: ProviderFailureFact,
) -> AdvisorFailureClassification:
    stage, scope, cause = _PROVIDER_FAILURE_DISPOSITIONS[fact.category]
    return AdvisorFailureClassification(
        fact=fact,
        failure_stage=stage,
        scope=scope,
        pipeline_cause_category=cause,
    )
```

删除 Provider path 对 `_localized_provider_failure_category()` 的 generic attr/built-in inference；legacy callers若仍需要 helper，必须限制在非 visual-symbol path。

在同一 RED/GREEN cycle给 `ProductionRetryCoordinator` 增加唯一 production eligibility API：

```python
def authorize_schema_retry(
    self,
    failure: VisualSymbolProviderError,
    identity: VisualExecutionIdentity | None,
    primary_duration_ms: int,
) -> bool:
    if (
        failure.fact.category != "schema"
        or failure.fact.origin != "response_schema"
        or failure.failure_stage != "tool_arguments_schema_invalid"
    ):
        return False
    return self._authorize_retry_budget(
        identity=identity,
        primary_duration_ms=primary_duration_ms,
    )
```

将现有 `authorize()` 的 identity/wall/budget reservation body原样下移为 private `_authorize_retry_budget()`；production `_visual_review_result()` 新增 `production_retry_coordinator: ProductionRetryCoordinator | None`，在 `evidence_context is not None` 时必须非空。production submit不再传 `allow_schema_retry=True` 或 `retry_authorizer=...`；它只传 coordinator。任何 typed schema carrier都直接交给 `authorize_schema_retry()`，Advisor不先检查 stage/eligibility。无 routing evidence 的 legacy/shadow call继续使用现有 `allow_schema_retry` boolean，不调用 production coordinator、不改变 behavior。

新增 owner test：用 `message_shape_invalid` 与 `tool_arguments_schema_invalid` 两个 typed carriers，spy证明 production Advisor两者都调用 coordinator；coordinator前者返回 `False` 且不 reserve，后者在 budget允许时唯一返回 `True`。source gate要求 production submit中没有 `allow_schema_retry=True`、没有旧 `retry_coordinator.authorize`；legacy-only predicate由 focused test证明不进入 production branch。

- [ ] **Step 4: Write persisted/propagated equality and privacy RED tests**

在 integration fixture 启用 routing DB，令 Provider 抛 classified rate-limit 与 unclassified facts，捕获 Advisor exception 后机械比较：

```python
assert attempt.diagnostic["failure_category"] == error.failure_category
assert attempt.diagnostic["failure_stage"] == attempt.event_code
assert attempt.event_code == error.failure_stage
assert attempt.diagnostic["scope"] == error.failure_scope
assert attempt.event_sha256 == error.failure_event_sha256
assert attempt.provider_request_id == error.provider_request_id
assert private_marker not in json.dumps(attempt.diagnostic)
assert private_marker not in str(error)
```

另加 `record_failure_terminal` 抛错 case：期待 `CandidateAdvisorFailure.failure_origin == "routing_evidence"`、没有 localized classification、没有 partial result。

- [ ] **Step 5: Run equality tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_recognition_pipeline.py -k 'persisted_provider_failure_matches_propagated or routing_failure_does_not_localize' -q
```

Expected: FAIL because current code persists `provider_transport_failure` independently and propagates `failure_category=None`.

- [ ] **Step 6: Replace all visual-symbol fallback writes with one classification object**

`CandidateAdvisorFailure` 不再接收 free-form category；它验证 classification/event SHA pair：

```python
AdvisorClassification = (
    AdvisorFailureClassification | AdvisorBoundaryFailureClassification
)


class CandidateAdvisorFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        classification: AdvisorClassification | None = None,
        failure_event_sha256: str | None = None,
        failure_origin: str | None = None,
    ) -> None:
        super().__init__(message)
        if (classification is None) != (failure_event_sha256 is None):
            raise ValueError("CandidateAdvisor failure evidence is invalid")
        if failure_event_sha256 is not None and not _valid_sha256(
            failure_event_sha256
        ):
            raise ValueError("CandidateAdvisor failure evidence is invalid")
        if failure_origin not in {None, "routing_evidence"}:
            raise ValueError("CandidateAdvisor failure evidence is invalid")
        if failure_origin == "routing_evidence" and (
            classification is not None or failure_event_sha256 is not None
        ):
            raise ValueError("CandidateAdvisor failure evidence is invalid")
        self.classification = classification
        self.failure_event_sha256 = failure_event_sha256
        self.failure_origin = failure_origin

    @property
    def failure_category(self) -> str | None:
        return (
            self.classification.category
            if isinstance(self.classification, AdvisorFailureClassification)
            else None
        )

    @property
    def failure_stage(self) -> str | None:
        return (
            None
            if self.classification is None
            else self.classification.failure_stage
        )

    @property
    def failure_scope(self) -> str | None:
        return None if self.classification is None else self.classification.scope

    @property
    def provider_request_id(self) -> str | None:
        return (
            self.classification.provider_request_id
            if isinstance(self.classification, AdvisorFailureClassification)
            else None
        )

    @property
    def pipeline_cause_category(self) -> str | None:
        return (
            None
            if self.classification is None
            else self.classification.pipeline_cause_category
        )
```

`call_once()` catches `ClassifiedProviderFailure`，只调用一次 `classify_provider_failure()`；`_visual_review_result()` 从同一个 classification 生成 `ProviderFailureDiagnostic(retry_decision="not_authorized")`，用 Task 2 atomic method commit event+terminal，取得 SHA 后再抛 `CandidateAdvisorFailure`。

schema path必须单独、完整保留：`call_once()` catches `VisualSymbolProviderError` 并返回 typed carrier；production Advisor不检查 stage，直接调用 `ProductionRetryCoordinator.authorize_schema_retry(carrier, identity, duration)`。若授权，先通过 Task 2 pair writer commit carrier.fact派生的 `provider_schema_invalid` v2 event（`retry_decision="authorized_schema_retry"`）和相邻 `retry_scheduled`，commit成功后再做第二次 call；若未授权或第二次仍 schema failure，则从同一个 `.fact` 生成 ROI-localized classification，以 `retry_decision="not_authorized"` atomic terminalize 后传播。现有 safe schema request/response/call-record evidence继续使用 carrier的 `request_id/usage/failure_stage/diagnostic`，不读取 raw exception。

Provider factory exception、Provider protocol抛出非 typed exception、defensive `result is None` 分别创建 `AdvisorBoundaryFailureClassification`，写 Task 2 exact advisor-boundary diagnostic并 atomic terminalize；它们不创建 `ProviderFailureFact`，不携带 Provider category，统一 project-blocking `processing_defect`。factory/protocol `except` block只赋 classification，退出 block后才持久化并抛 `CandidateAdvisorFailure`；tests对三条 paths都断言 cause/context为空。删除三处 `else "provider_transport_failure"` fallback。

- [ ] **Step 7: Run Advisor/evidence regression and lint**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_recognition_pipeline.py backend/tests/integration/test_symbol_routing_evidence.py -q
micromamba run -n qi-p0 ruff check backend/app/candidates/advisor.py backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_recognition_pipeline.py
```

Expected: PASS; source search finds no visual-symbol unknown fallback to `provider_transport_failure`.

- [ ] **Step 8: Prove old-path retirement and commit Task 3**

Run:

```bash
rg -n 'else "provider_transport_failure"|failure_category=None' backend/app/candidates/advisor.py
rg -n 'retry_coordinator\.authorize\b|allow_schema_retry=True' backend/app/candidates/advisor.py
git diff --check
```

Expected: both `rg` commands exit `1` with no matches; `authorize_schema_retry` 是唯一 production retry eligibility symbol；`git diff --check` exits `0`. Then:

```bash
git add backend/app/candidates/advisor.py backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_recognition_pipeline.py
git commit -m "fix(advisor): align provider failure evidence and propagation"
```

### Task 4: Deterministic Stop, Drain, And Never-Submitted Terminals

**Files:**
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/candidates/routing_evidence.py`
- Test: `backend/tests/unit/candidates/test_advisor.py`
- Test: `backend/tests/integration/test_symbol_routing_evidence.py`
- Test: `backend/tests/integration/test_symbol_recognition_pipeline.py`

**Interfaces:**
- Consumes: Task 3 `CandidateAdvisorFailure.classification.scope` and `failure_event_sha256`; Task 2 scheduler diagnostic and atomic failure terminal write.
- Produces: deterministic first blocking failure by minimum job index; classification-typed scheduler stop reason；event `not_started_after_project_failure`; group outcome `cancelled`; observation outcome `cancelled_after_project_failure`; no Provider/crop/request/call/cache artifacts for never-submitted jobs.

- [ ] **Step 1: Extend the existing concurrency RED test to eight admitted groups**

不要改变其它 tests 共享的 three-item fixture。新增 `eight_visual_escalation_fixture()`，沿用 `three_visual_escalation_fixture()` 的 PDF/page/snapshot construction pattern，生成 stable IDs `fixture-visual-0` 至 `fixture-visual-7` 与八个不重叠 bbox；只让本 test 使用它。保持 barrier 使两个 futures 都实际 submitted；第一个按 job index产生 project-blocking `ClassifiedProviderFailure(ProviderFailureFact(category="rate_limited", origin="sdk_http_status", http_status=429, ...))`，第二个按实际结果 drain，剩余六个 never submitted：

```python
assert provider.calls == list(observation_ids[:2])
assert error.failure_scope == "project_blocking"
assert error.failure_event_sha256 == blocking_attempt.event_sha256
assert len(cancelled_attempts) == 6
assert [row.escalation_group_id for row in cancelled_attempts] == [
    planned_groups[index].escalation_group_id for index in range(2, 8)
]
assert {row.event_code for row in cancelled_attempts} == {
    "not_started_after_project_failure"
}
assert all(row.provider_request_id is None for row in cancelled_attempts)
assert all(
    row.diagnostic["blocking_event_sha256"]
    == blocking_attempt.event_sha256
    for row in cancelled_attempts
)
```

对每个 cancelled group 断言一个 terminal、每个 member 都是 `cancelled_after_project_failure`，并断言 storage 中没有该六组的 crop/request/response/cache/call artifacts。

再用同一个 eight-job fixture增加 Advisor-boundary case：第一个 submitted job产生 `AdvisorBoundaryFailureClassification(failure_stage="provider_factory_failed", provider_work_started=False)`，第二个 drain，六个 queued取消。断言 blocking event是 `provider_factory_failed`，六个 scheduler diagnostics全部是 `stop_reason="project_blocking_advisor_boundary_failure"`；rate-limit case仍全部为 `project_blocking_provider_failure`，两类不能 replay成彼此。

- [ ] **Step 2: Run scheduler terminal test to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py -k 'failure_stops_before_queued_job_provider_call' -q
```

Expected: FAIL because current collector raises the worker failure before terminalizing queued jobs.

- [ ] **Step 3: Add exact cancellation codes and validation**

在 `routing_evidence.py` 添加：

```python
ATTEMPT_EVENT_CODES = ATTEMPT_EVENT_CODES | {
    "not_started_after_project_failure"
}
OBSERVATION_OUTCOME_CODES = OBSERVATION_OUTCOME_CODES | {
    "cancelled_after_project_failure"
}
```

`not_started_after_project_failure` 必须 `attempt_index=0`、`provider_request_id=None`、无 cache ID、使用 exact scheduler diagnostic；terminal group outcome必须是 `cancelled`。Provider classification只允许 `project_blocking_provider_failure`，Advisor-boundary classification只允许 `project_blocking_advisor_boundary_failure`。不得复用任何带 `budget` 的 code。

同时把 `EscalationOutcome.__post_init__()` 的 derived group-code validation扩为两条互斥 cancellation family：`all_codes == {"cancelled_after_project_budget"}` 或 `all_codes == {"cancelled_after_project_failure"}` 都派生 `cancelled`；同一 group混用两种 code必须拒绝。budget branch本身不改名、不改语义。

- [ ] **Step 4: Implement stop-new-work, drain-current-work, then cancel-queued**

collector 保留 outstanding futures 直到 drain；只有 `scope="roi_localized"` 且 event SHA valid 才加入 `localized_failure_stages`。对 blocking failures记录 `(job_index, error)`，停止 submit loop；drain 完成后选 minimum job index，按 original stable job order terminalize `next_job_index:`：

```python
first_blocking_index = min(project_blocking_failures)
first_blocking = project_blocking_failures[first_blocking_index]
if isinstance(
    first_blocking.classification,
    AdvisorFailureClassification,
):
    stop_reason = "project_blocking_provider_failure"
elif isinstance(
    first_blocking.classification,
    AdvisorBoundaryFailureClassification,
):
    stop_reason = "project_blocking_advisor_boundary_failure"
else:
    raise first_blocking
for queued_job in production_jobs[next_job_index:]:
    self._record_not_started_after_project_failure(
        context=queued_job.context,
        blocking_event_sha256=first_blocking.failure_event_sha256,
        stop_reason=stop_reason,
    )
raise first_blocking
```

`_record_not_started_after_project_failure()` 必须验证 stop reason与 blocking classification type对应，再通过 Task 2 atomic method一次写 event+terminal；任一 persistence failure 转成 `failure_origin="routing_evidence"` 的 project-blocking exception。不能调用 crop builder、Provider factory、Provider、call record 或 cache writer。

- [ ] **Step 5: Add integration assertions for exact terminal completeness and false-success**

在 production pipeline integration test 中断言：

```python
assert len(admitted_groups) == 8
assert len(provider.calls) == 2
assert len(terminal_rows) == 8
assert len(cancelled_rows) == 6
assert db_session.scalar(
    select(func.count()).select_from(AutomaticResult).where(
        AutomaticResult.project_id == project.id
    )
) == 0
assert db_session.scalar(
    select(func.count()).select_from(ReviewWorkingCopy).where(
        ReviewWorkingCopy.project_id == project.id
    )
) == 0
written_paths = {
    str(path.relative_to(storage.root))
    for path in storage.root.rglob("*")
    if path.is_file()
}
assert not any(
    marker in path
    for path in written_paths
    for marker in ("pause", "symbol-report", "receipt")
)
```

另加 mixed completion order case：高 job index先失败也不得覆盖 minimum job index的 deterministic first blocking failure；already-submitted sibling的 success/failure evidence按真实结果保留。

- [ ] **Step 6: Run scheduler, routing, and localized regressions**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py -k 'production_failure or concurrent or localized' -q
micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_symbol_recognition_pipeline.py -k 'project_failure or scheduler_stop or localized_provider_failure' -q
```

Expected: PASS; exactly two Provider calls for an eight-job concurrency-two fixture; all eight admitted groups have one terminal.

- [ ] **Step 7: Review and commit Task 4**

```bash
git add backend/app/candidates/advisor.py backend/app/candidates/routing_evidence.py backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_symbol_recognition_pipeline.py
git diff --cached --check
git commit -m "fix(advisor): terminalize queued work after provider failure"
```

Expected: scheduler/evidence-only commit; concurrency and budget constants unchanged.

### Task 5: Pipeline Cause Projection And End-To-End Fail-Closed Gates

**Files:**
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/tests/integration/test_project_status_api.py`
- Modify: `.agent/bug-memory.md`
- Modify: `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`

**Interfaces:**
- Consumes: Task 3 `CandidateAdvisorFailure.pipeline_cause_category` and `failure_origin`; Task 4 complete terminal evidence.
- Produces: exact ErrorRecord cause without widening automatic retry; complete offline verification and documentation closeout. This task does not authorize live execution.

- [ ] **Step 1: Write exact pipeline projection RED tests**

扩展现有 `test_vision_failure_is_sanitized_without_result_layers` 的 task/session/storage setup；将旧 generic runtime/typed-schema参数替换为 validated classification，并直接 monkeypatch `CandidateAdvisor.review()` 抛已持久化形状的 sanitized exception，从而只测试 pipeline projection而不调用 Provider：

```python
def _status_fact(status: int) -> ProviderFailureFact:
    return ProviderFailureFact(
        category=provider_failure_category_for_http_status(status),
        origin="sdk_http_status",
        http_status=status,
        provider_request_id=None,
        request_id_state="absent",
    )


def _metadata_fact() -> ProviderFailureFact:
    return ProviderFailureFact(
        category="metadata_invalid",
        origin="response_metadata",
        http_status=None,
        provider_request_id=None,
        request_id_state="absent",
    )


def _unclassified_fact() -> ProviderFailureFact:
    return ProviderFailureFact(
        category="unclassified",
        origin="provider_boundary",
        http_status=None,
        provider_request_id=None,
        request_id_state="absent",
    )


@pytest.mark.parametrize(
    ("fact", "expected_cause"),
    (
        (_status_fact(401), "invalid_configuration"),
        (_status_fact(429), "transient_provider_failure"),
        (_status_fact(503), "transient_provider_failure"),
        (_status_fact(422), "processing_defect"),
        (_metadata_fact(), "processing_defect"),
        (_unclassified_fact(), "processing_defect"),
    ),
)
def test_vision_failure_is_sanitized_without_result_layers(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
    fact: ProviderFailureFact,
    expected_cause: str,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(setup, storage, tmp_path)
    setup.close()
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=[],
    )
    classification = classify_provider_failure(fact)

    def fail_review(
        _advisor: CandidateAdvisor,
        _source: Path,
        _pages: Sequence[object],
        _snapshot: CandidateSnapshot,
        **_kwargs: object,
    ) -> CandidateSnapshot:
        raise CandidateAdvisorFailure(
            "Visual symbol Advisor call failed",
            classification=classification,
            failure_event_sha256="a" * 64,
        )

    monkeypatch.setattr(CandidateAdvisor, "review", fail_review)
    with pytest.raises(CandidateAdvisorFailure) as raised:
        inventory_project.run(
            str(project.id),
            source.resource_ref,
            f"product-process:{project.id}",
        )

    verify = task_session_factory()
    error = verify.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert error.code == "vision_provider_call_failed"
    assert error.cause_category == expected_cause
    assert _counts(verify, project.id)["raw"] == 0
    assert _counts(verify, project.id)["working"] == 0
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    verify.close()
```

在同一 test module新增 concrete helpers：`_status_fact(status)` 调用 Task 1 `provider_failure_category_for_http_status(status)` 并构造 `origin="sdk_http_status"` fact；`_metadata_fact()` 构造 `metadata_invalid/response_metadata`；`_unclassified_fact()` 构造 `unclassified/provider_boundary`；三者 request ID 均 absent。另断言 `failure_origin="routing_evidence"` 固定投影 `symbol_routing_evidence_failed + processing_defect`，不会被 Provider category覆盖。

- [ ] **Step 2: Write end-to-end private-marker RED tests**

Task 1 已把同一个 marker放入 SDK error message/body/unsafe request ID/unknown exception；Task 3 把该 case贯穿 attempt DB。Task 5 延续同一 marker，验证 ErrorRecord、storage 和 returned status surface；在捕获 exception、查询 DB和扫描 storage后执行：

```python
private_marker = "private://customer/token-do-not-leak"
assert raised.value.__cause__ is None
assert raised.value.__context__ is None
assert private_marker not in str(raised.value)
assert private_marker not in error.message
for artifact in storage.root.rglob("*"):
    if artifact.is_file():
        assert private_marker.encode("utf-8") not in artifact.read_bytes()

```

在 `test_project_status_api.py` 使用现有 `_seed_project_status()`/`StatusContext` 单独 parameterize `invalid_configuration|transient_provider_failure|processing_defect`，message设为该 marker，然后对每个 case执行：

```python
response = status_context.client.get(
    f"/api/v1/projects/{project_id}/status"
)
assert response.status_code == 200
assert private_marker not in response.text
assert response.json()["error"] == {
    "code": "vision_provider_call_failed",
    "stage": "candidate_advisor",
}
assert "cause_category" not in response.text
assert "diagnostic" not in response.text
assert "provider_request_id" not in response.text
```

保持现有 retryable projection：只有 `transient_provider_failure` 为 `True`，另两类为 `False`；response不得返回 cause、message、request ID、diagnostic 或 marker。

- [ ] **Step 3: Run projection/privacy tests to verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_project_status_api.py -k 'vision_failure or routing_evidence_failed or provider_failure_status_privacy' -q
```

Expected: FAIL because current pipeline只以 localized-category membership二分 transient/processing defect。

- [ ] **Step 4: Project the Advisor-owned cause without adding retry**

在 `pipeline.py` 保持 routing evidence优先；其它 CandidateAdvisor failure 只读取 validated property：

```python
cause_category = (
    "processing_defect"
    if exc.pipeline_cause_category is None
    else exc.pipeline_cause_category
)
```

timeout/transport/schema localized path不应到达 document failure；若 invariants破坏而到达，fail closed为 `processing_defect`。不要修改 `ProjectService` retryable set，也不要调用 retry coordinator。

- [ ] **Step 5: Run focused and full offline verification**

Run in this exact order:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_qwen_symbol_provider.py -q
micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py -q
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_recognition_pipeline.py backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_project_status_api.py -q
micromamba run -n qi-p0 ruff check backend/app/providers/base.py backend/app/providers/qwen_vl.py backend/app/candidates/models.py backend/app/candidates/routing_evidence.py backend/app/candidates/advisor.py backend/app/processing/pipeline.py backend/tests/contract/test_qwen_symbol_provider.py backend/tests/unit/candidates/test_advisor.py backend/tests/integration/test_symbol_routing_evidence.py backend/tests/integration/test_schema.py backend/tests/integration/test_migration_reconciliation.py backend/tests/integration/test_symbol_recognition_pipeline.py backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_project_status_api.py
make test-backend
micromamba run -n qi-p0 python .agent/harness/check-contracts.py
git diff --check
```

Expected: all commands exit `0`; no command calls a Provider or live runtime. If `make test-backend` already includes an earlier focused command, still run both because the focused evidence is the review gate.

- [ ] **Step 6: Run privacy and old-path static gates**

```bash
rg -n 'else "provider_transport_failure"|failure_category=None' backend/app/candidates/advisor.py
rg -n 'response\.body|exc\.body|exc\.headers|str\(exc\)|repr\(exc\)' backend/app/providers/qwen_vl.py backend/app/candidates/advisor.py backend/app/candidates/routing_evidence.py
rg -n 'not_started_budget_exhausted|cancelled_after_project_budget' backend/app/candidates/advisor.py
```

Expected: first command has no matches; second has no new failure-path reads; third only shows unchanged budget paths and no project-failure branch. Any unexpected match blocks completion until inspected and covered by a fixed-literal/privacy test.

- [ ] **Step 7: Arrange the mandatory independent implementation review**

Dispatch one read-only `reviewer` with exact scope: the companion plan commit range, Provider/Advisor/routing/pipeline owners, migration, focused test evidence and privacy surfaces. Reviewer must not edit, call Provider, alter runtime, create GDT-10D, or delegate. Required output:

```text
Verdict: accept | accept with concerns | reject
Blocking issues:
Non-blocking concerns:
Evidence from files/tests:
Owner and old-path retirement:
Privacy/retry/budget/false-success assessment:
Recommended minimal follow-up:
Files and commands inspected:
```

Expected: `accept` before documentation closeout. `accept with concerns` requires parent verification that every concern is non-blocking; `reject` returns to the exact failed task and reruns its focused gate.

- [ ] **Step 8: Update durable docs only after accepted implementation review**

在 `.agent/bug-memory.md` 追加 date/root cause/fix/prevention，明确 GDT-10C sealed evidence不重写、新 schema只适用于未来 attempts；在 parent plan记录 Task 1–5 commit IDs、commands 与 reviewer verdict。Parent plan 的 GDT-10状态保持：

```text
GDT-10 Step 4 remains blocked pending explicit authorization for a new plan-bounded live cycle. Offline classification/evidence implementation does not prove Provider runtime success and does not authorize GDT-10D or Step 5.
```

同一 closeout 必须记录：`0014` v1 default仍是 temporary compatibility bridge；production promotion additionally blocked pending separately approved `0015_drop_symbol_attempt_v1_default` after all-writers-v2 runtime proof and a no-new-v1 observation window。本 implementation不得把 bridge存在报告为 promotion-ready。

- [ ] **Step 9: Commit Task 5 documentation and pipeline projection**

```bash
git add backend/app/processing/pipeline.py backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_symbol_recognition_pipeline.py backend/tests/integration/test_project_status_api.py .agent/bug-memory.md docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md
git diff --cached --check
git commit -m "fix(pipeline): fail closed on classified provider failures"
```

Expected: final implementation commit contains only verified projection/tests and closeout records; worktree clean afterward.

## Final Acceptance Gate

- [ ] Every Provider status/metadata/unknown case maps to the exact safe category in the design matrix.
- [ ] Provider fact and Advisor disposition remain separate owners; retry/budget/concurrency constants are unchanged.
- [ ] Persisted diagnostic category/stage/scope/event SHA equals propagated `CandidateAdvisorFailure` fields.
- [ ] One atomic transaction owns each Provider failure event+terminal; replay conflict and rollback tests pass.
- [ ] Under concurrency `2`, two actual calls are accounted and six admitted-but-never-submitted groups receive explicit cancellation terminals without Provider/crop/request/call/cache artifacts.
- [ ] Project-blocking failure creates no AutomaticResult、working copy、pause、symbol report or receipt.
- [ ] Privacy tests cover exception、DB JSONB、storage、ErrorRecord and returned payload; no raw or hashed private detail persists.
- [ ] Active immutable trigger下 `0013 -> 0014` 无 UPDATE backfill、v1-only downgrade、v2-present downgrade veto和 v1 replay compatibility全部通过。
- [ ] New writers全部显式写 v2；v1 default被记录为 temporary bridge，future `0015` retirement gate在完成前持续阻断 production promotion。
- [ ] Focused tests、`make test-backend`、Ruff、offline `check-contracts.py` and `git diff --check` pass.
- [ ] Independent reviewer verdict is accepted and parent directly verifies important claims.
- [ ] No Provider/live invocation、`make verify-p0-live`、credential/runtime mutation、GDT-10D、budget expansion or production promotion occurred.
- [ ] GDT-10 Step 4 stays blocked until the user separately authorizes a future plan-bounded live cycle.
