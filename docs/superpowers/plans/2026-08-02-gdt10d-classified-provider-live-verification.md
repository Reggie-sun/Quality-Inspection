# GDT-10D Classified Provider Live Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before commits/completion claims.

**Goal:** 在不改写 GDT-10C、不扩大 Provider ceiling、不触碰 main runtime的前提下，为一个 one-use GDT-10D cycle补齐保守计价与durable usage/terminal evidence，激活feature `0014` runtime，并在唯一cycle start成功pause时完成literal same-run headed QA/export/receipt。

**Architecture:** cycle-scoped `ProviderUsageLedger`在每个真实OCR/Qwen submission前以固定公开原价预留最坏成本，在安全usage可用时向下结算；open/unknown reservation仍按最坏值累计，所以跨四个project、失败或worker中断都不会低估。独立的Harness authorization owner先生成literal run ID，原子consume一次性cycle并durably bind该run，之后才激活credential runtime；Harness只能adopt显式 `--authorized-run-id`。每个project先把pending identity写入run evidence，再由host durable admission，最后才允许processing/runtime reservation。Exact-cycle Provider adapter必须在literal SDK seam原子consume matching opaque reservation permit并创建submission-started fact，重复或并发复用在network前失败。Runtime activation先quiesce target writers、private backup、additive `0014` migration并完成credential-free zero-paid review；paid start后只recreate feature `api/worker`。

**Tech Stack:** Python 3.11、pytest、Ruff、Decimal、`fcntl.flock`、`threading.Lock`、`O_CREAT|O_EXCL` append journal、JSON Schema、Alembic、PostgreSQL 17、Docker Compose、repository Harness、Chrome headed QA、Micromamba `qi-p0`。

## Global Constraints

- Design source：`docs/superpowers/specs/2026-08-02-gdt10d-classified-provider-live-verification-design.md`。
- Parent plan：`docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`；其old GDT-10 Steps 4-7由本plan Tasks 1-10显式supersede。
- Stable Owner：`docs/contracts/MAIN_CONTRACT_MATRIX.md` `PROV-005`；本plan不得建立第二套pricing semantics。
- User option `A`批准versioned list-price snapshot、usage ledger、one-use authorization和本plan的single paid cycle；不批准production promotion、main mutation、budget increase、direct Provider call或replacement cycle。
- Sealed GDT-10C run `20260801T153347947042Z-0fea7c81`与commit `91e02b5` immutable。
- Exact cycle ID：`gdt10d-classified-live-20260802`；ceiling `50.000000 CNY`；unknown Qwen reservation `1.763328 CNY`；OCR reservation `0.500000 CNY`。
- Timeout/transport retry `0`；only `ProductionRetryCoordinator`可为schema-invalid授权一次retry，即每logical call最多two submissions，且第二次必须单独reserve。Harness policy升级为unambiguous v2 fields，移除误导性的 `max_retries_per_call: 2`。
- No Provider work before Task 7 final `GO`；Task 8只允许一次 `make verify-p0-live` start。Task 9仅允许同一accepted paused run的一次literal resume，不是第二cycle或replacement。
- Reviewers/explorers严格只读；single parent writer拥有下列implementation/plan files。

---

## File Map

### Stable policy and design

- Modify `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`
- Modify this plan only for checked evidence/status

### Production pricing and durable ledger

- Create `backend/app/providers/provider_pricing_gdt10d_v1.json` — exact rate snapshot and official source identity
- Create `backend/app/providers/pricing.py` — strict snapshot loader and Decimal calculators
- Create `backend/app/providers/cycle_authorization.py` — read-only consumed/run/project/resume/terminal validator shared by runtime and Harness writer
- Create `backend/app/providers/usage_ledger.py` — cycle-scoped cross-process reserve/settle/recovery Owner
- Modify `backend/app/providers/base.py` — cycle submission permit contract
- Modify `backend/app/providers/qwen_vl.py` — reject exact-cycle submission without matching permit
- Modify `backend/app/providers/tencent_ocr.py` — reject exact-cycle submission without matching permit
- Modify `backend/app/providers/call_records.py` — authorized-cycle cost binding only
- Modify `backend/app/config.py` — optional safe cycle authorization ID/root
- Modify `backend/app/storage/local.py` only for reusable safe path primitives required by the ledger; ledger append entries must not use replace semantics
- Modify `backend/app/processing/tasks.py` — reopen the one cycle ledger for each admitted project
- Modify `backend/app/processing/runtime_recognition.py` — OCR reserve/settle
- Modify `backend/app/candidates/advisor.py` — Vision reserve/settle/budget terminal
- Test `backend/tests/unit/providers/test_provider_pricing.py`
- Test `backend/tests/unit/providers/test_provider_usage_ledger.py`
- Test `backend/tests/contract/test_provider_call_records.py`
- Test `backend/tests/unit/pdf/test_runtime_ocr.py`
- Test `backend/tests/unit/candidates/test_advisor.py`
- Test `backend/tests/integration/test_symbol_recognition_pipeline.py`

### Harness authorization and evidence

- Create `.agent/harness/scripts/live_cycle_authorization.py`
- Private issuance/journal/handoff facts use exact closed validators in `live_cycle_authorization.py` and `backend/app/providers/cycle_authorization.py`; private control bytes are not copied into public schema artifacts。
- Create `.agent/harness/policy/gdt10d-runtime-closure.txt` — exact full tracked `backend/app/**/*.py|*.json` manifest
- Modify `.agent/harness/policy/provider-call-policy.yaml`
- Modify `.agent/harness/scripts/run-p0.py`
- Modify `.agent/harness/scripts/live_evidence_policy.py`
- Modify `.agent/harness/scripts/generate-receipt.py`
- Modify `.agent/harness/scripts/check-contracts.py`
- Modify `.agent/harness/schemas/run.schema.json`
- Modify `.agent/harness/schemas/live-run-evidence.schema.json`
- Modify `.agent/harness/schemas/receipt.schema.json` only if receipt embeds the paid-cycle aggregate rather than its run-bound hash
- Modify `Makefile`
- Test `backend/tests/contract/harness/test_live_run_contract.py`
- Test `backend/tests/contract/harness/test_receipt_policy.py`
- Test `backend/tests/contract/harness/test_contract_architecture.py`

### Runtime/evidence artifacts

- Private state `/var/tmp/quality-inspection-gdt10d-20260802-<worktree-path-sha256-prefix>/`
- Harness-generated `.agent/harness/runs/<literal-gdt10d-run-id>/`
- Existing root `design-qa.md` only through exact paused-run workflow
- Modify `.agent/bug-memory.md` only after terminal evidence

## Exact Runtime Closure

`gdt10d-runtime-closure.txt` must ultimately equal every clean-HEAD tracked `backend/app/**/*.py` and `backend/app/**/*.json` path。To make the implementation gate executable, `check-contracts.py` has three explicit sources with identical path/hash rules：`working` compares the manifest with present non-ignored implementation files during TDD；`index` compares staged paths and staged blob hashes immediately before commit；`HEAD` compares committed paths/blobs immediately after commit and is the only mode accepted by runtime/zero-paid gates。Everymode rejects missing/extra/duplicate/unsafe paths；API/worker hash every HEAD-listed runtime file and prove no tracked runtime source drift。This replaces the incomplete 25-file subset and necessarily covers storage durability、routing、planner、cache、Provider and processing owners。Migration identity remains separate。

---

### Task 1: Accept The Contract And Supersede The Stale Parent Steps

**Files:** design、this plan、parent plan、`MAIN_CONTRACT_MATRIX.md` only.

**Interfaces:**

- Consumes: user option `A` and rejected reviewer findings.
- Produces: one reviewed behavior boundary; no runtime or implementation mutation.

- [x] **Step 1: Amend `PROV-005`**

Move versioned public list-price snapshot、one-use paid-cycle identity、pre-submission reservation、conservative cost aggregate into required evidence. Keep raw token detail、discount/free-tier、account invoice reconciliation and private Provider detail in excluded evidence. Keep status `P0-partial`.

- [x] **Step 2: Supersede old GDT-10 Steps 4-7**

In the parent plan, mark old Steps 4-7 as superseded by this exact companion plan rather than leaving stale `0013`/same-command instructions active. Preserve historical GDT-10A/B/C facts and the GDT-10C sealed IDs.

- [x] **Step 3: Self-review**

```bash
rg -n 'TODO|TBD|FIXME|direct Provider|replacement|0015' \
  docs/superpowers/specs/2026-08-02-gdt10d-classified-provider-live-verification-design.md \
  docs/superpowers/plans/2026-08-02-gdt10d-classified-provider-live-verification.md \
  docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md \
  docs/contracts/MAIN_CONTRACT_MATRIX.md
git diff --check
```

Expected: no placeholder；`0015`/direct/replacement只作为prohibition出现。

- [x] **Step 4: Independent design/plan review**

Read-only reviewer必须检查：single Owner、fixed rates/math、cycle-wide/open-reservation safety、OS-process concurrency/recovery、per-submission authorization、Make ordering、full runtime closure completeness、writer quiescence、private backup、credential/mount allowlist、generic terminal reconciliation、same-run Step 5、cleanup/retention/no-promotion。

Review record：多轮只读复审依次关闭PROV cache语义、runtime closure commit ordering、lifecycle finalizer、sole close bridge、reservation/submission-started区分、resume O_EXCL、terminal fsync/replay、adapter-side process-local capability与全局锁序；最终 verdict `accept`。Contract checker `69/111/101/10`、all drift `0`，Decimal literals `0.049169` / `1.763328` 独立复算通过。

- [x] **Step 5: Commit planning boundary**

```bash
git add docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/specs/2026-08-02-gdt10d-classified-provider-live-verification-design.md \
  docs/superpowers/plans/2026-08-02-gdt10d-classified-provider-live-verification.md \
  docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md
git diff --cached --check
git commit -m "docs(gdt): authorize auditable classified live cycle"
```

Expected: clean committed docs；Provider/runtime/DB unchanged。

---

### Task 2: Freeze Pricing And Implement Conservative Calculators

**Files:** pricing snapshot/module and their focused tests.

**Interfaces:**

- Produces:
  - `load_pricing_snapshot() -> ProviderPricingSnapshot`
  - `qwen_reservation_cny(snapshot) -> Decimal("1.763328")`
  - `qwen_usage_cost_cny(snapshot, usage) -> Decimal | None`
  - `ocr_submission_cost_cny(snapshot) -> Decimal("0.500000")`

- [x] **Step 1: Write RED snapshot/math tests**

Tests use literal expected values independent of production helpers:

```python
def test_qwen_unknown_usage_reserves_official_maximum() -> None:
    assert qwen_reservation_cny(load_pricing_snapshot()) == Decimal("1.763328")

def test_qwen_cost_uses_prompt_tier_and_rounds_up_to_micro_cny() -> None:
    usage = {"prompt_tokens": 32_769, "completion_tokens": 1}
    assert qwen_usage_cost_cny(load_pricing_snapshot(), usage) == Decimal("0.049169")

def test_qwen_incomplete_or_out_of_range_usage_cannot_reduce_reservation() -> None:
    assert qwen_usage_cost_cny(load_pricing_snapshot(), {"total_tokens": 4}) is None
    assert qwen_usage_cost_cny(
        load_pricing_snapshot(),
        {"prompt_tokens": 260_097, "completion_tokens": 1},
    ) is None
```

The second literal is hand-derived with `ROUND_CEILING`: `32769*1.5/1e6 + 1*15/1e6 = 0.0491685 -> 0.049169`; do not reuse production calculation in the assertion. Add literal boundary cases for input `32768/32769/131072/131073/260096/260097` and completion `0/32768/32769` so everytier edge and output maximum is independently pinned。

- [x] **Step 2: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers/test_provider_pricing.py -q
```

Expected: import/file failures only。

- [x] **Step 3: Implement strict snapshot loader and Decimal math**

Use immutable dataclasses and exact-key validation. Reject float、extra/missing fields、wrong source/model/region/version、non-monotonic tiers or hash mismatch. Do not fetch network at runtime。

- [x] **Step 4: Run GREEN and mutation negatives**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers/test_provider_pricing.py -q
micromamba run -n qi-p0 ruff check \
  backend/app/providers/pricing.py \
  backend/tests/unit/providers/test_provider_pricing.py
```

---

### Task 3: Implement The Shared Durable Usage Ledger

**Files:** `usage_ledger.py`、call records/config and focused tests.

**Interfaces:**

- `ProviderUsageLedger.open(*, cycle_id, storage_root, authorization_root, project_id) -> ProviderUsageLedger` validates the project admission、derives literal run/order from that read-only fact and rebuilds the same cycle journal for every project/task process.
- `ProviderUsageLedger.reserve(*, provider, operation, page_index, subject_kind, subject_id, retry_index, crop_expansion_count) -> ReservationPermit` revalidates the bound admission and writes its verified run/project/order into the entry；callers cannot supply or spoof those fields.
- `ReservationPermit.consume_for_adapter(*, provider, operation) -> None` is called only inside the matching Provider adapter at the literal SDK seam。The permit is a module-private-constructor、non-copyable/non-serializable process-local capability registered by exact object identity in the issuing ledger instance；consumption atomically retires that registry entry、revalidates active authorization and exclusive-creates/fsyncs submission-started before network。Repeat、concurrent、forged/reconstructed or mismatched permit consumption fails before network。
- `ProviderUsageLedger.settle(reservation, *, usage, request_id) -> LedgerEntry` requires the durable matching submission-started fact.
- `ProviderUsageLedger.retain_unknown(reservation, *, request_id_state) -> LedgerEntry` requires the same fact.
- `ProviderUsageLedger.journal_ref: str`
- `ProviderBudgetExceeded` means no Provider call was authorized.

Production architecture checks must forbid `consume_for_adapter` call sites outside `qwen_vl.py`、`tencent_ocr.py` and the focused ledger/provider tests；forbid permit fields/types in JSON schemas、call records、logs and Harness evidence。Even if a caller invokes it early，the real adapter's second atomic consume fails before network；there is no public started permit that can bypass the adapter transition。

- [x] **Step 1: Write RED ledger tests**

Cover: cycle journal exists before network seam、two projects share one ceiling、OCR fixed charge、Qwen downward settlement、missing usage retains max、two independent OS processes atomically contend at ceiling、two independently opened same-process ledger handles race reserve-vs-consume without deadlock under a bounded timeout、repeat adapter consumption/settlement rejected、cache/factory paths create no entry、immutable reservation/submission-started/settlement bytes and hashes、new-instance reopen after reserved-only crash keeps full charge but zero submission count and cannot recover a permit、reopen after submission-started crash reports acceptance unknown/full charge、constructor/copy/deepcopy/pickle/JSON reconstruction rejected、a forged/reconstructed object before first legitimate consume produces zero submission-started/network、partial/duplicate/gap/sequence rollback/unexpected file/final-component symlink journal fails closed、parent-directory fsync is exercised、lock open never truncates holder diagnostics、contenders share one stable inode after release、sensitive fields and unsafe IDs rejected。The same-process multi-handle test is mandatory in addition to the OS-process case。

```python
def test_unknown_qwen_attempt_keeps_full_reservation() -> None:
    ledger = ledger_with_limit("2.000000")
    reservation = ledger.reserve(
        provider="qwen-vl",
        operation="review_symbols",
        page_index=0,
        subject_kind="escalation_group",
        subject_id="a" * 64,
        retry_index=0,
        crop_expansion_count=0,
    )
    reservation.consume_for_adapter(provider="qwen-vl", operation="review_symbols")
    entry = ledger.retain_unknown(reservation, request_id_state="absent")
    assert entry.charged_cny == "1.763328"
    assert ledger.snapshot().committed_total_cny == "1.763328"
    assert ledger.snapshot().submission_started_count == 1
```

- [x] **Step 2: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers/test_provider_usage_ledger.py \
  backend/tests/contract/test_provider_call_records.py -q
```

- [x] **Step 3: Implement minimal cross-process durable ledger**

Use a cycle-global `asset://provider-usage-cycles/<cycle-id>/` journal and `fcntl.flock(LOCK_EX)` on a dedicated lock file。All same-process handles for one canonical journal obtain the same module-registry `threading.RLock`；the registry-map mutex is released before that lock is acquired。Every runtime path needing both layers uses only `cycle process lock -> OS flock` and reverse release；no path may hold OS flock while acquiring either process lock，while the one-off close bridge uses OS flock only。Create private directories as `0700` and open the stable lock inode with `O_RDWR|O_CREAT|O_NOFOLLOW`、never `O_TRUNC` before flock；verify regular-file/owner/mode with `fstat`，and never unlink、replace or recreate the lock file。Reserve holds the cycle process lock across OS-locked durable fact creation/fsync and subsequent process-local permit registration，so it never reacquires process lock under flock。The module-private factory registers the exact non-copyable/non-serializable permit object in that issuing ledger instance。Only the matching Provider adapter may call `consume_for_adapter` at its SDK seam；under the cycle process lock it validates exact ledger/object/registry/provider/operation、retires the capability for any attempted consume，then under the OS lock revalidates authorization and exclusive-creates/fsyncs submission-started。Only that success may proceed to network；repeat/concurrent/forged/reconstructed use fails before network，and reopen never recreates capability。Settlement requires the durable started fact。All facts use `O_CREAT|O_EXCL|O_NOFOLLOW` plus file/directory `fsync`；do not use `LocalFileStorage.write_verified()` replacement path。Every open/reopen separately rebuilds reserved-only、submission-started unknown、settled and committed cost。Never expose delete/discount/sequence-reset methods。

- [x] **Step 4: Bind call records without breaking history**

Authorized-cycle records require a non-null cost matching ledger entry; legacy/noncycle fixtures remain valid with `estimated_cost=None`. Do not add raw usage or rate details to `ProviderCallRecord` if ledger owns them。

- [x] **Step 5: Run GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers/test_provider_pricing.py \
  backend/tests/unit/providers/test_provider_usage_ledger.py \
  backend/tests/contract/test_provider_call_records.py -q
```

---

### Task 4: Wire OCR And Vision Through The Ledger

**Files:** tasks/runtime recognition/advisor and focused unit/integration tests.

**Interfaces:**

- `inventory_project()` reopens the same cycle-scoped journal only for exact cycle ID/root and passes one process-local handle to OCR and Advisor.
- Every SDK-seam Provider attempt has exactly one durable reservation plus one submission-started fact；exact-cycle Provider adapters accept only the exact process-local `ReservationPermit` object still registered by its issuing ledger and atomically consume it themselves at their network seam。The same object used serially/concurrently、a forged/reconstructed permit before first consume、a reopened-ledger permit attempt or any identity mismatch yields zero additional network calls and no forged started fact。A reserved-only fact is charged conservatively but is not counted as a submission。
- `ProviderBudgetExceeded` produces no network call and a project-blocking budget terminal.

- [x] **Step 1: Write RED OCR tests**

Assert each eligible region reserves before fake provider invocation, adapter-side consumption creates submission-started immediately before network, success settles `0.500000`, 16/page remains exact, provider failure retains charge, and budget rejection leaves provider call count unchanged。Before the legitimate first consume，constructor/copy/deepcopy/pickle/JSON/reopened-ledger reconstruction attempts must fail with zero submission-started and zero network；afterward the same permit object reused serially/concurrently and adapter/operation mismatch must fail with zero additional network calls。The fake provider is only the external boundary; assertions target real ledger bytes and RuntimeRecognition result/failure。

- [x] **Step 2: Write RED Vision tests**

Cover success、schema retry (two submissions/two entries)、transport/status/metadata failure with no usage (full reservation)、provider factory failure (zero entry)、cache hit (zero entry)、text crop expansion `1`、visual batch expansion `0`、per-page/per-subject limits、budget rejection before `review_symbols()`、direct exact-cycle adapter call without permit、same-permit serial/concurrent reuse、forged/reconstructed-before-first-consume、reopened-ledger or identity-mismatched permit。Pre-first-consume forgery produces zero submission-started/network；all later rejected cases produce zero additional network calls。

- [x] **Step 3: Write RED project-blocking integration reconciliation**

Extend the existing 8-admitted/2-started/6-cancelled test to assert:

```python
assert admitted_groups == submission_started_groups | never_started_groups
assert submission_started_groups.isdisjoint(never_started_groups)
assert terminal_groups == admitted_groups
assert ledger_submission_started_groups == submission_started_groups
assert reserved_only_groups == set()
assert all(no_paid_artifacts(group) for group in cancelled_groups)
```

Also assert exact two submission-started/acceptance-unknown reservations, six `not_started_after_project_failure` terminals with no reservation fact, no AutomaticResult/working copy, and committed total below `50.000000`。Add a separate reserve-before-SDK crash case where `reserved_only_groups` has one member、submission-started count stayszero、full charge remains and Step4 success isblocked。

- [x] **Step 4: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  -k 'usage_ledger or cost_budget or project_blocking' -q
```

- [x] **Step 5: Implement OCR/Advisor wiring**

Reserve immediately before the actual Provider method call and pass the opaque reservation permit into the adapter。The adapter itself calls `consume_for_adapter()` at the literal SDK seam before any network operation；no started permit is exposed for caller reuse。In `call_once()` settle every branch：schema failure may use safe usage；classified/boundary failure retains max；unexpected failure before adapter consumption must remain reserved-only and must not claim provider work。Schema retry must reserve and adapter-consume separately。When cycle budget is exhausted，the rejected group uses existing attempt `not_started_budget_exhausted`、observation `routing_budget_exhausted`、group `budget_exhausted`；queued admitted siblings use attempt/observation `cancelled_after_project_budget` and group `cancelled`。Raise internal typed `ProviderBudgetExceeded` to stop the project scheduler，but do not add `provider_cost_budget_exhausted` or another routing vocabulary。Cancelled/budget-denied never-started groups have zero reservation/crop/request/response/call/cache evidence；reserved-only crash is a distinct blocked state, not cancellation。

- [x] **Step 6: Run focused GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py -q
```

---

### Task 5: Add One-Use Harness Authorization And Paid Evidence Validation

**Files:** authorization script、schemas/policy、Harness scripts/Makefile/tests.

**Interfaces:**

- `live_cycle_authorization.py issue` creates one immutable issuance，including the zero-paid-proved exact backend image ID.
- `live_cycle_authorization.py consume` creates one exclusive consumption bound to a random non-secret invocation identity；repeat/concurrent consume exits nonzero，且foreign loser不得close/deactivate winner。
- `live_cycle_authorization.py bind-run/admit-project` exclusively appends the only run and each project admission；host `close` can write terminal only by launching the one-off、network-none、credential-free cycle-close bridge with feature storage `/data:rw` and private authorization `/auth:rw`；normal runtime mount remains read-only.
- `live_cycle_authorization.py execute-start` installs signal/finally cleanup before consuming，then activates、checks HEAD contracts and starts Harness；everyexit deactivates credentials。
- `live_cycle_authorization.py execute-resume --run-id <literal>` is the only same-cycle resume orchestrator；before activation it requires a durable clean-pause handoff with no cleanup blocker，then exclusive-creates/fsyncs one `resume-consumed` fact bound to the literal accepted-pause run/evidence and random invocation identity。Pre-consume rejection has zero mutation/activation；foreign loser only removes its fresh private controls with zero activation/network/close/deactivate；after own consumption every exit closes/deactivates and removes fresh private overrides.
- `run.json.cycle_authorization` and `live-run-evidence.paid_cycle` bind exact hashes、pre-bound literal run、each pending/admitted project、conditional resume-consumed fact、cycle-wide ledger and terminal aggregate。Pending project暂以 `admission_sha256: null` durable写入；formal success禁止任何pending project。

- [x] **Step 1: Write RED authorization tests**

Use private `tmp_path` with real OS processes. Assert owner/mode/symlink/expiry/head/plan/pricing/current-four mismatches fail；zero-paid preflight does not consume/deploy credentials；two concurrent cycle consumers yield exactly one success；run bind is single；each project admission requires that run and unique order/project/source identity before that project's processing；terminal blocks new admissions/reservations；runtime read-only verifier rejects missing/mismatched consumption/run/project/expiry/terminal。Run `execute-start` as a child process with controlled fake activation/contracts/run seams；partial activation、activation error、contracts error、preflight/run error、SIGINT、SIGTERM all leave consumption evidence but zero credentials/cycle/auth mount。Accepted pause also deactivates while leaving authorization nonterminal。Then run two independent OS-process full `execute-resume` contenders for the same literal pause；exactly one exclusive `resume-consumed` fact succeeds and owns activation/run/close/deactivation，the loser performs zero activation/network/close/deactivate and only cleans its fresh controls。Wrong run/evidence、repeat resume and any post-consume resume failure all prohibit another resume；resume success/failure/signal always closes/deactivates。Inject interruption immediately after each exclusive fact fsync to prove only the matching invocation owner performs lifecycle cleanup。

- [x] **Step 2: Write RED schema/evidence tests**

Historical fixture/task runs remain valid without cycle fields. New full-live start requires them。Accepted pause remains valid without resume-consumed；any resumed/terminal receipt must bind the exact resume-consumed hash，while direct failure before pause must prove it absent。Reject ledger totals over `50`、unknown snapshot hash、duplicate attempt index、OCR/Vision/project-page/project-subject/crop limit breaches、ledger entry for cancelled group、missing terminal；for exact current-four sample order `1` only，reject `total_decisions != 199` or `escalated_groups != 198 = 190 denied + 8 admitted` as Step4 success，without applying those counts to samples 2-4。Provider policy v2 must assert `max_coordinator_retries_per_logical_call: 1` and `max_submissions_per_logical_call: 2`；the old ambiguous `max_retries_per_call` key is forbidden。

- [x] **Step 3: Write RED failure-project capture test**

Replace the controlled `_PREPARE_PROJECT_PROGRAM` with separate create/upload and process protocols. Assert run binding exists first；create/upload returns project ID without queueing/processing；Harness writes project ID to `paid_cycle.projects` and exclusive host admission with directory `fsync`；only then may process start。On processing failure, Harness must still collect the sanitizedcycle ledger and routing aggregate and seal/close a failed run without AutomaticResult/pause/report/receipt。

- [x] **Step 4: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_receipt_policy.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  -k 'authorization or pricing or usage_ledger or terminal_reconciliation or runtime_identity' -q
```

- [x] **Step 5: Implement authorization and Make ordering**

Use exclusive mode-safe files plus fsync。The Make recipe must not express `check-contracts` as a prerequisite and must delegate the whole lifecycle to one orchestrator whose first state mutation isconsume and whose `finally` runs for normal/exception/signal exits：

```make
verify-p0-live:
	@micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py execute-start \
		--authorization "$${QI_LIVE_CYCLE_AUTHORIZATION_REF:?}" \
		--override "$${QI_LIVE_CYCLE_OVERRIDE_REF:?}"

resume-gdt10d-live:
	@micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py execute-resume \
		--authorization "$${QI_LIVE_CYCLE_AUTHORIZATION_REF:?}" \
		--override "$${QI_LIVE_CYCLE_OVERRIDE_REF:?}" \
		--run-id "$${GDT10D_RUN_ID:?}"
```

No shell/Python line may print credentials or authorization document content。`execute-start` installs `SIGINT/SIGTERM` handlers，generates one literal run ID and random invocation identity，then atomically consumes and binds that exact run before activation；Harness start must receive `--authorized-run-id <literal>` and may not mint another identity。`execute-resume` installs handlers before exclusive `resume-consumed` creation，whose fsynced fact binds the random invocation identity、is its first state mutation and precedes activation。Only the exact fact owner may close/deactivate，including interruption after durable create but before function return；foreign repeat/concurrent losers perform zero activation/network/close/deactivate and only clean fresh controls。Both owners set deactivation-required before activation starts so partial recreation is covered。`activate-runtime` validates private override owner/mode、exact eight environment keys、one read-only authorization mount，only recreates feature `api/worker`，并从两个container读取sanitized key-presence/actual mount `ro`/mode/model facts证明live identity；`deactivate-runtime`同样证明four credentials、cycle keys和auth mount都absent且safe mode/model exact。On abnormal exit the orchestrator checks Harness/Celery/Redis；API proof unavailable或worker不空时stop only feature worker，再recheck worker absent与queue zero，之后使用sole close bridge并apply safe runtime。Every exit then fsync-deletes exact private live/safe overrides and unsets inherited child-process controls。Accepted pause只apply safe runtime而不close，且必须再写durable clean-pause handoff；cleanup blocker或缺少handoff禁止resume。Cleanup error forces nonzero exit and exact redacted `provider-cycle-cleanup-blocker/1` evidence；blocker persistence error不可吞掉。Active authorization must reject any blocker，while both admitted-project and pre-first-project close-only paths precisely validate issuance/consumption/run/root and an allowlisted/content-hashed blocker so Task 10 can repair or exactly replay terminal close。Real child-process tests在activation/run/quiescence phases发送both `SIGINT`/`SIGTERM`，并覆盖resume signal and full contender ownership。Neither start nor resume target may be reinvoked after its consumption fact exists。

- [x] **Step 6: Implement ledger/routing collection and policy validation**

Pending project evidence write must fsync the exclusive temporary file，replace，then fsync the parent before host admission。

Collect only sanitized JSON from the single-cycle journal plus exact project DB evidence. Validate sample-1 exact baseline continuity plus generic reconciliation separately per project and for the cycle aggregate。`not_started_budget_exhausted`的v2 event只允许exact diagnostic `visual-symbol-budget-control/1`，其中 `budget_origin=routing_plan|provider_cycle_reservation`；前者进入plan-denied，后者保持admitted并另列 `provider_cycle_reservation_denied_group_ids`。任何nonempty Provider reservation rejection都可在failed evidence中持久化，但必须阻断formal success。Embed/harden hashes before pause/failure；receipt revalidates the same documents rather than recomputing from mutable runtime。At every success/failure/abort completion，first prove Harness/process/Celery/queue quiescence，then invoke the sole cycle-close bridge：one-off exact committed backend image、`--network none --rm`、zero credentials、feature storage `/data:rw`、private authorization `/auth:rw`。Bridge alone acquires the cycle ledger lock、rebuilds journal、validates quiescence identity，then writes terminal、applies `fchown`/`fchmod(0600)` before final `fsync(fd)` and parent-directory `fsync`。Existing terminal is successful replay only when full schema、cycle/run/status/quiescence/content hashes are exact；conflict fails closed。Tests cover first/exact/conflicting/concurrent close and lock exact image/volume/mount/network/credential/uid behavior。Accepted pause remains nonterminal solely for literal same-run resume。

- [x] **Step 7: Upgrade runtime identity**

Set exact DB revision `0014` and full `backend/app` runtime closure in API/worker identity. Add working/index/HEAD source checks；runtime accepts only clean committed HEAD mode。Add mismatch matrix for each service、missing/extra/duplicate manifest path、at least one storage/routing/planner/cache/provider file hash mutation、`0013`、multiple revision rows、invalid output and stale cycle/auth mount identity。All fail before registration/run/upload/Provider work。

- [x] **Step 8: Run full offline gates**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness -q
micromamba run -n qi-p0 ruff check \
  .agent/harness/scripts/live_cycle_authorization.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/check-contracts.py \
  backend/tests/contract/harness
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source working
git diff --check
```

---

### Task 6: Full Offline Verification, Independent Review And Implementation Commit

- [x] **Step 1: Run full backend verification**

```bash
make test-backend
```

`make test-backend` reached the environment bootstrap gate but could not allocate another Docker subnet。The same test configuration was then executed against an ephemeral host-network PostgreSQL 17 after `alembic upgrade head`：`1930 passed, 14 warnings`；the container was removed and its port was proved free。No Provider、feature runtime or credential state was touched。

- [x] **Step 2: Run focused smoke test**

Per `auto-feature-smoke-test`, run the smallest affected backend behavior tests; UI smoke is not applicable because Tasks 2-5 do not change UI。

Focused Provider/Advisor exact-cycle smoke：`46 passed, 147 deselected`。Full Harness after the final lifecycle/image/durability/invocation-ownership changes：`283 passed`；Provider unit suite `47 passed`；Ruff、working runtime closure (`94` files)、contract mapping and `git diff --check` all passed。

- [x] **Step 3: Independent implementation review**

Reviewer checks actual diff, TDD evidence, pricing literals/math, cycle-wide OS-process ledger concurrency/reopen/crash durability, retry accounting, exact existing budget terminal semantics, schema backward compatibility, per-submission authorization, post-consume activation/Make ordering, privacy and full runtime closure. Required verdict `accept`。

Final reviewer verdict：`accept`。复审覆盖invocation ownership、durable-create interruption、真实双进程resume contenders、admitted/no-project cleanup-blocker repair/replay、active fail-closed、runtime closure与privacy/scope；无剩余 blocker。

- [x] **Step 4: Stage and verify the prospective commit**

Stage exact files from Tasks 2-5 and tests；never `git add .`。Before commit validate the staged prospective tree, so new runtime modules are included even though current HEAD does not yet contain them：

```bash
git add <literal implementation and test files from Tasks 2-5>
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source index
git diff --cached --check
git commit -m "feat(provider): enforce auditable live cost budget"
```

Exact 44-file index passed runtime closure (`94` files)、contract drift `0`、cached diff check and no-unstaged-state check before commit。

- [x] **Step 5: Verify the real committed HEAD immediately**

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source HEAD
git status --short
```

Expected: clean committed implementation whose manifest exactly matches HEAD；no private state、runtime、credential、DB or Harness run mutation yet。A post-commit HEAD mismatch is a blocker and requires a new reviewed fix commit；it cannot be waived。

Implementation commit：`7e49e3413f90f882c6ef7c7fc70cb2492d6d5403`。HEAD runtime closure (`94` files) passed and the worktree was clean；no private state、runtime、credential、DB or Harness run mutation had occurred。

---

### Task 7: Quiesce, Backup, Migrate And Prove Zero-Paid GO

- [x] **Step 1: Capture baseline and prove no writers**

Record target/non-target container IDs、volumes、ports、health、DB `0013`、GDT-10C hashes、DB row/event counts、storage ledger inventory and Harness run inventory. Require Celery active/reserved/scheduled all empty and feature Redis processing queue `0`。

- [x] **Step 2: Stop only feature api/worker**

Verify those two are stopped；feature PostgreSQL/Redis/frontend and all main IDs remain exact。

- [x] **Step 3: Create private state and backup**

Create exact mode `0700` state root with `umask 077`; require target nonexistence. Use the design's `set -o noclobber; exec 3>"$backup_path"` exclusive FD before streaming `pg_dump` default stdout，close FD，reopen non-symlink path to `fsync` file and parent，then `pg_restore --list`；require file owner current uid、mode `0600`，record size/SHA only。Blocked retention Owner is `GDT-10D execution owner`，review deadline `2026-08-09T23:59:59+08:00` and delete/restore triggers are fixed by Task 10。

- [x] **Step 4: Verify committed migration identity and upgrade**

Compare host file SHA against `git show HEAD:backend/alembic/versions/0014_...py` bytes immediately before one-off migration. Mount committed `backend/alembic` and `alembic.ini` read-only; execute only `alembic -c alembic.ini upgrade 0014` on feature network。

- [x] **Step 5: Verify migration invariants**

Require exact `0014`、three columns/check、old counts unchanged、inherited attempts v1 with SQL NULL diagnostic/hash、no v2 row yet、GDT-10C project/evidence unchanged、no run/result/provider artifact mutation。

- [x] **Step 6: Build and activate credential-free target services**

Ban worktree `.env` file/symlink. Build current `api/worker` and recreate only feature `api/worker` with safe mode/model override；four credentials、cycle ID and authorization mount must beabsent。Separately create but do not apply a mode-`0600` private live override containing exact four credentials + mode/model/cycle ID/auth root and one read-only authorization mount；validate onlysanitized resolved key/mount sets。Non-target IDs/volumes remain unchanged。

- [x] **Step 7: Issue but do not consume authorization**

Issuance binds clean HEAD、plan/pricing/runtime-closure/current-four hashes、Compose project、exact zero-paid-proved backend image ID、DB `0014`、ceiling and expiry。Run/project IDs do not exist yet and must be bound later by exclusive `bind-run`/`admit-project` state transitions。Require no pre-existing issuance/consumption/run/project/pause-handoff/resume-consumed/terminal for the ID。

- [x] **Step 8: Run fresh zero-paid preflight**

Require API/worker full committed runtime closure `N/N` hashes、exact rates/policy-v2/runtime constants、health/ports、safe runtime credential/cycle/auth-mount absence、private live override exact sanitizedkey/mount set、host four credential booleans、GDT-10C identity、DB/storage/run counts unchanged。Call `preflight_full_p0_live(..., input_artifacts=current artifacts)` directly；assert authorization remainsissued/unconsumed，live override remainsunapplied，and zero newledger/run/upload/Provider fact。

- [x] **Step 9: Independent zero-paid GO/NO-GO**

Reviewer receives sanitized IDs/hashes/counts/key/mount sets only. `NO-GO` deletes theunapplied private live override、unsets host credentials and stops；only `GO` permits Task 8 consume/activation。

Execution record：baseline DB `0013`、zero queue/writers、GDT-10C tree and target/non-target identities were frozen before mutation。The first `pg_dump --file=-` attempt created zero bytes and stopped before migration；commit `1dcdf04` corrected the reviewed default-stdout contract，then verified private backup SHA `40243df2a2f76e8c09b9dd339b9a0fa31f621d709313f20d963404207a20677e` and `pg_restore --list`。Migration SHA `622ddf1c...9b45d` upgraded only feature DB to `0014` with inherited counts unchanged and zero v2 rows。Safe API/worker images were `sha256:064c51b...` / `sha256:d8b2a170...`，full runtime closure `94/94`。Two unused zero-paid issuances (`86c4a81c...`、`d7f8a1c1...`) were deleted only after exact no-consume/no-bind/no-activation assertions；the final issuance raw SHA `d30bcd25...` bound commit `4b3e182` and passed direct preflight。Compose v5 bare image-ID remediation commits `1128f05` / `4b3e182` passed `172` Harness tests；independent reviewer final gate `GO / accept`。

---

### Task 8: Consume And Execute The Sole Paid Cycle

- [x] **Step 1: Freeze the live window**

Recheck no concurrent writer/live process、Celery/Redis empty before launch and target/non-target IDs. Start read-only identity monitor。

- [x] **Step 2: Invoke exactly once**

With exact host environment and literal authorization ref:

```bash
make verify-p0-live
```

Do not call the start target again for any exit/status。The recipe consumes first，then activates onlyfeature `api/worker` with the privatecredential/cycle/read-only-auth override，then runs contracts/final preflight/start。Failure at any point consumes thecycle and enters Task 10；runtime reservation still requiresliteral run/project admission, so activation alone cannot authorize Provider work。

- [x] **Step 3: Seal terminal evidence**

Record registration/full run IDs if created、proof that each project admission was durable before that project's processing began、command exit、monitor、authorization hashes、pricing hash、cycle-wide ledger aggregate、routing reconciliation、DB/storage/run deltas。The lifecycle orchestrator must have already closed authorization through the sole bridge and deactivated runtime on failure/abort；accepted pause keeps authorization nonterminal but must already have deactivated credentials/cycle/auth mount before returning。This step audits those facts and repairs only a reported cleanup blocker；it is not the primary cleanup mechanism。

- [x] **Step 4: Decide next state without reinterpretation**

- Pause + all Step4 acceptance evidence: continue Task 9。
- Any failure/incomplete/identity drift/budget terminal: Step4 remains blocked；do not rerun；continue Task 10 cleanup/closeout。
- Project-blocking failure: require exact admitted reconciliation；if two started fail from first batch, the other six must be terminal cancelled with zero paid artifacts。

Execution record：literal `make verify-p0-live` was invoked exactly once。It created full run `20260802T101404291929Z-884bec62` plus current-four `20260802T101410283666Z-12d482b3` and symbol `20260802T101417588825Z-07a91d32` registrations。The run-bound project `55dbd769-8fab-44a2-bcbd-768b8bbf4312` was admitted before processing。Two Qwen submissions were reserved、adapter-consumed and durably submission-started，then classified `provider_authentication_failed` with `request_id_state=accepted` for sanitized Provider request IDs；ledger retained conservative unknown-usage `reserved_unknown` charges totalling `3.526656 CNY` with `2/2` settled、zero reserved-only/unsettled。Routing reconciliation is exact：`199` decisions；`198 = 190` plan-denied `+ 8` admitted；admitted `8 = 2` started/failed `+ 6` `not_started_after_project_failure` cancelled；storage contains exactly the two started crops。The current-four registration receipt passed，but the full run has no AutomaticResult、pause、symbol report or full-run/formal receipt，so Task 9 did not become applicable and Step 4 remains blocked without reinterpretation or rerun。

---

### Task 9: Complete Exact Same-Run Headed QA And Receipt

Conditional on Task 8 exact accepted pause only.

Not applicable：Task 8 terminated before an accepted pause。No headed QA、export、resume consumption or second Provider activation was attempted。

- [ ] **Step 1: Capture API proof**

Prove typed Case A/B、labels/value/datum、exact automatic/working/reviewed linkage and paid-cycle evidence hash。

- [ ] **Step 2: Run headed Chrome QA**

Use Chrome/browse on literal paused project. Prove visible Case A/B、structured A -> B edit、save/reload、freeze gate and no frontend parsing ownership。Do not steal another operator lock。

- [ ] **Step 3: Export from the same reviewed result**

Generate ballooned PDF and SIP Excel; verify manifest IDs/hashes and basic content from the exact frozen `reviewed_result`。

- [ ] **Step 4: Resume literal run**

After run-bound `design-qa.md` passes, recreate fresh mode-`0600` live/safe overrides from the same approved root credential source，validate their exact sanitized shape without applying them，then invoke exactly once with the literal paused run ID：

```bash
make resume-gdt10d-live GDT10D_RUN_ID=<literal-paused-run-id>
```

The `execute-resume` orchestrator first exclusive-creates/fsyncs the one-use `resume-consumed` fact bound to this literal run and accepted-pause evidence；only its winner may reactivate feature credentials/cycle/read-only auth mount。Each remaining current-four project must follow create/upload → host admission → process，reuse the same cycle ledger/ceiling and revalidate authorization per reservation；never select `latest`。Receipt must revalidate authorization/pricing/ledger/routing and overall pass。Normal、failure or signal exit always closes through the sole bridge and deactivates in `finally`；cleanup failure is a durable blocker and nonzero exit。Any exit after resume consumption forbids another resume。

---

### Task 10: Cleanup, Final Review And Closeout

- [x] **Step 1: Verify finalizer cleanup and repair only if blocked**

`execute-start`/`execute-resume` is the primary cleanup Owner and must return only after safe deactivation；Task 10 first verifies its terminal/deactivation evidence。For any non-paused closeout，require Harness command returned and Celery active/reserved/scheduled + queue empty；if the orchestrator reported cleanup failure or quiescence is not provable，stop only feature worker and use the same sole close bridge replay contract，then apply safe-identity runtime。The active validator continues to reject `cleanup-blocker.json`；both admitted-project and no-project close-only validators must exactly validate issuance/consumption/run/root plus blocker schema/cycle/run/status/allowlisted codes/content hash before repair/replay。An existing terminal counts as idempotent success only after exact schema/cycle/run/status/quiescence/content-hash verification；any mismatch blocks。Require four credentials、cycle ID and authorization mount absent，mode/model/full runtime closure/health/DB exact；delete private live/safe overrides；unset host credential/Harness variables；prove worktree `.env` absent。A failed repair remains a durable blocker and may not be reported as safe cleanup。

- [x] **Step 2: Dispose or retain private state**

Accepted closeout: after run-bound copies and healthy DB evidence, delete exact private backup/auth files and report non-recoverability except live DB/Harness copies。Blocked: retain mode/path/hash/authorization expiry；write owner `GDT-10D execution owner`、review deadline `2026-08-09T23:59:59+08:00` and blocker into parent plan。Before deadline delete only after (a) blocker resolved with healthy `0014` DB + verified run copies or (b) user-authorized restore completed and a replacement backup exists。At deadline do not auto-delete；request user decision to renew orsecurely delete。

Cleanup record：the network-none close bridge wrote terminal content SHA `4400d41a...` and safe deactivation succeeded，but ledger live-binding failed because the schema regex rejected valid one-digit totals。RED reproduced `3.526656` / `9.999999` rejection；commit `86d5851` fixed the exact `[0, 50]` micro-CNY domain (`178 passed`)。Commit `ba5f821` added crash-safe recovery from the already content-hashed ledger report；review remediation `91a0ead` proves content-hash、run、cycle、pricing、journal and count tampering all fail closed (`179 passed`)。Storage SHA `34f85ac8...`、routing SHA `2f918deb...` then validated all terminals and finalized the run from `terminal_pending` to sealed `failed` at `2026-08-02T10:22:01.308582Z`。Post-finalize proof：API/worker safe identity，health `200`，Celery active/reserved/scheduled `0/0/0`，Redis queue `0`，DB `0014`，`0` AutomaticResults，feature/main non-target IDs unchanged，worktree `.env` absent，GDT-10C tree unchanged。After recording backup/auth hashes and confirming run-bound copies plus healthy DB，the exact private root was deleted；the original pre-0014 dump and raw private authorization bytes are no longer recoverable，and only the healthy post-migration live DB plus sanitized run-bound Harness evidence remain。

- [x] **Step 3: Final independent review**

Reviewer checks commits、migration/backup、single consume/start and literal same-run resume only if applicable、cycle-wide ledger ceiling、run/project authorization、routing terminals、headed evidence if applicable、credential/auth-mount cleanup、GDT-10C immutability、retention record、old-step supersession and `0015`/promotion block。Required verdict `accept` before completion claim。

Final review record：local `reviewer` profile (`gpt-5.6-sol`，high) independently rechecked exact authorization/run/project bindings、DB diagnostic categories、ledger/routing/storage/terminal evidence、network-none bridge、safe deactivation、GDT-10C tree、private-state deletion semantics and current docs。It found and closed two wording defects (`request_id_state=accepted` and registration receipt vs full-run receipt) plus the deleted-byte recoverability statement。Its non-blocking recovery-test concern was remediated by `91a0ead`。Fresh read-only gates were Harness `179 passed`、contract matrix `69/111/101/10`、runtime closure `94`、Ruff、diff、sealed schema/policy and safe DB/runtime checks；final verdict `accept` with no blocker or material risk。

- [x] **Step 4: Update actual truth and commit evidence**

Update parent plan、this plan、`.agent/bug-memory.md` and exact generated GDT-10D artifacts only. Preserve GDT-10C bytes。

```bash
git add .agent/bug-memory.md \
  docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md \
  docs/superpowers/plans/2026-08-02-gdt10d-classified-provider-live-verification.md
git add <literal GDT-10D Harness files listed by git status>
git diff --cached --check
git commit -m "feat(gdt): seal auditable classified live evidence"
```

- [x] **Step 5: Fresh completion verification**

Run plan-specified full tests/checks appropriate to final diff、`git status --short --branch`、sealed evidence validation and final reviewer gate。Only then report whether GDT Step 4/5 and the parent plan are complete。Even on success, `0015` and production promotion remain separately blocked。

Completion verification record：evidence/docs commit `daa3e6f` preserved the three exact sealed run directories。Fresh read-only gates passed：Harness `179 passed`；contract matrix `69/111/101/10` with runtime closure `94`；Ruff；failed-cycle `run.schema.json`、`live-run-evidence.schema.json` and `validate_paid_cycle_evidence(require_success=False)`；all three run trees non-writable and free of credential key names；GDT-10C tree unchanged。Live safe-state recheck proved API/worker credential keys `[]`、cycle keys `[]`、authorization mount absent、expected mode/model；DB `0014` with `0` AutomaticResults；Celery active/reserved/scheduled `0/0/0`、Redis queue `0`、`/api/v1/health` status `ok`、private root and worktree `.env` absent。The immutable current-four selector logs retain their receipt-bound trailing blank lines；all other staged whitespace checks passed and a whitespace-policy override proved no additional errors。Independent final reviewer verdict remains `accept`。

## Final Acceptance Gate

- [x] Contract/design/plan、implementation、zero-paid and final reviews accepted。
- [x] Pricing snapshot/rates/hash and Decimal calculations exact；free/discount/invoice not claimed。
- [x] Every actual submission was admitted、reserved、durably marked submission-started and permit-checked before call；submission-started/unsettled acceptance remains `unknown` and is charged conservatively；reserved-only is charged but has zero submission count and blocks Step 4 success；one cycle total across all projects `<= 50.000000`。
- [x] One authorization issued/consumed once、bound to one literal run；each project admission was durable before that project's processing；one Make start only，plus at most one O_EXCL-consumed literal same-run resume after accepted pause。
- [x] Writer quiescence、private backup and additive `0014` migration preserved GDT-10C。
- [x] API/worker exact full committed runtime closure and authorization identity proved before paid work。
- [x] Exact run has a complete pause+same-run receipt or a fully evidenced fail-closed terminal；no missing admitted terminal。
- [x] Credentials/cycle controls removed and non-target identities preserved。
- [x] Parent plan reflects runtime truth；worktree clean；`0015`/promotion still blocked。
