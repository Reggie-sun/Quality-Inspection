# GDT-10E Credential Readiness And Replacement Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before commits/completion claims.

**Goal:** 在不泄露 credential、不增加原 `50.000000 CNY` 总包络、不创建 direct Provider diagnostic 的前提下，把 operator account readiness 与将要注入的 credential bundle 做私有绑定，并以一个新的 one-use full-run cycle完成父计划 GDT-10 Step 4/5，或形成完整 fail-closed terminal。

**Architecture:** 新的 private `provider-account-readiness/1` document只保存短时 operator attestation与private salted credential-bundle binding；repository/run evidence只保存document SHA和sanitized state。现有 cycle authorization绑定该readiness SHA、GDT-10D historical cost与`46.473344 CNY` incremental ceiling；`ProviderUsageLedger`从active issuance读取更严格ceiling。Paid path仍只有literal full-run project admission -> reservation -> adapter permit -> Provider submission；`run-p0.py`在既有request/response/call validator证明首个authenticated response后唯一写immutable run-bound acceptance fact，public state才单向提升为`runtime_accepted`。

## Execution Approval Record — 2026-08-02

- Selected lane: Heavy
- Selected companion: 2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md
- Historical cost: 3.526656 CNY
- Incremental ceiling: 46.473344 CNY
- Overall envelope: 50.000000 CNY
- Provider starts: one
- Resume: only one literal same-run resume after accepted pause
- Still blocked: direct Provider diagnostic, second replacement, `0015_drop_symbol_attempt_v1_default`, production promotion
- Cleanup-proof amendment: user selected option `A` on 2026-08-02. Task 2 is paused because review found no canonical lifecycle-proof schema; it may resume only after an independent read-only amendment review returns `accept`. This amendment does not complete Task 2, GDT-10 Step 4, Step 5, or the parent objective.

## Pricing Verification Amendment — 2026-08-03

- User approval：用户于 `2026-08-03` 明确批准 pricing amendment 和后续既定计划执行；该批准不扩大原 `50.000000 CNY` 总包络。
- Independent review：本地 `reviewer` profile 对两个官方公开页面、committed snapshot、运行门禁和最小 amendment 做只读复核，verdict 为 `accept`，无 blocking 或 non-blocking finding。
- Public verification：腾讯云 `GeneralAccurateOCR` 国内后付费首档仍为 `0.50 CNY/submission`；阿里云 `qwen3-vl-plus-2025-12-19` 华北2（北京）三档输入/输出仍为 `1/10`、`1.5/15`、`3/30 CNY per million tokens`，最大输入/输出仍为 `260096/32768`。
- Official sources：`https://cloud.tencent.com/document/product/866/17619`、`https://help.aliyun.com/zh/model-studio/qwen3-vl-plus`。
- Immutable snapshot：继续复用 `provider-pricing-gdt10d/1`；文件 bytes SHA-256 仍为 `40893337440fde3bb7e9c572b5ba341fc4fe9782850a1c9c38e971a3fa317e19`，canonical content SHA-256 仍为 `c6b37f8a811d38444ccd89a5862d676343e414db21dbc02d9ca9979496364a2b`。不得修改 snapshot bytes 或 historical GDT-10D evidence。
- Renewed issuance boundary：GDT-10E 只允许在 `2026-08-03T23:59:59+08:00` 前 issue；超过该时点继续 fail closed，并重新要求 read-only public pricing verification、reviewed plan amendment和用户明确批准。

## Successor DB-Identity And Pricing Binding Amendment — 2026-08-03

- User approval：Step 0 archive 与 Step 1 read-only baseline 完成后，用户于 `2026-08-03` 明确批准先完成本 DB-identity/pricing amendment 的 review，再继续 plan-bounded successor execution。该批准不授权 main/non-target mutation、Provider work before zero-paid `GO`、第二 replacement、budget expansion、`0015_drop_symbol_attempt_v1_default`、Task 6 before one-use issuance/consume gate 或 production promotion。
- Historical identity：sealed GDT-10D/E evidence 继续以当时 feature chain 的 DB revision `0014` 为 immutable truth，不修改 run、receipt、Harness tree、migration history或历史描述，也不把历史 evidence 重标为 `0016`。
- Collision truth：successor target 的单行 `alembic_version=0014` 来自旧 feature chain `0012 -> old 0013_structured_geometric_tolerance -> old 0014_symbol_provider_failure_diagnostics`，不是 merged canonical `0014_project_lifecycle`。只读检查证明 current `0013_project_catalog` 三列与 `0014_project_lifecycle` 三列、四约束和一索引均缺失；同时 current `0016` 的三 diagnostic columns/check 已 exact present，`394 = 196 v1 + 198 v2` attempts 全部满足约束。旧 `0013/0014` migration bodies 与 current `0015/0016` 除 revision docstring、`revision` 和 `down_revision` 外完全一致。
- Canonical target：只允许当前 Compose project `structured-geometric-tolerance-recognition-qa` 从 collided feature identity 收敛到 `0013_project_catalog -> 0014_project_lifecycle -> 0015_structured_geometric_tolerance -> 0016_symbol_provider_failure_diagnostics`。不得直接 `upgrade head`，因为它会跳过 collided `0013/0014` 并在 `0016` 重复创建 diagnostic DDL。
- Runtime contract convergence：current `run-p0.py`、Harness issuance与backend cycle validator仍把GDT-10D的`0014`硬编码应用到GDT-10E，若先迁移会在zero-paid、issuance、run start、active/terminal/empty-close paths拒绝`0016`。DB mutation前必须先以TDD只修改本plan列出的六个code/test paths，并机械更新唯一runtime-closure manifest：exact GDT-10E cycle唯一写入/接受`0016`，generic/historical GDT-10D继续唯一接受`0014`；任何caller-supplied arbitrary revision、`0014|0016` broad allowlist或fallback均禁止。完整focused suite、Ruff、working/index/HEAD runtime-closure checks、parent diff和fresh independent implementation review必须通过并单独commit。
- Exact reconciliation：固定 reconciliation root `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-db-reconciliation/` 与 backup `pre-canonical-0016.dump` 当前均 absent。只在上述code/test/review commit、clean successor HEAD、target-only api/worker writer quiescence、empty Celery/Redis、zero other PostgreSQL client sessions/prepared transactions/ungranted locks、exact schema/count/digest preflight、committed migration SHA verification和该root下verified private `pg_dump --format=custom` backup 后继续。先把该backup restore到一次性 tmpfs PostgreSQL 17并用committed read-only migration mounts完整演练 metadata-only `alembic stamp 0012`、canonical `alembic upgrade 0015`、intermediate verification、metadata-only `alembic stamp 0016`和final verification；演练失败不得触碰target，演练成功并清理disposable runtime后才可对target执行同一state machine。三个 `0015` data-transform target tables在 preflight 必须均为零行，因此重复执行旧/current identical body是可证明的 vacuous transform；任一非零或 shape mismatch 均停止而不是迁移。
- Recovery boundary：不执行 `alembic downgrade`，不删除 target volume，不自动 destructive restore。任何 backup、writer、schema、count、intermediate或final postcondition失败都在 issuance/Provider work 前 fail closed并保留 private backup；restore或backup删除需要独立 reviewed closeout authority。main/non-target IDs、volumes和DB保持不变。
- Pricing binding：继续复用上方已reviewed `provider-pricing-gdt10d/1` snapshot，bytes SHA `40893337440fde3bb7e9c572b5ba341fc4fe9782850a1c9c38e971a3fa317e19`、content SHA `c6b37f8a811d38444ccd89a5862d676343e414db21dbc02d9ca9979496364a2b`、`3.526656 + 46.473344 = 50.000000 CNY` 和 rate table全部不变。DB reconciliation不是 issuance；任何 issuance 仍必须早于 `2026-08-03T23:59:59+08:00`，过期先重新完成 public pricing只读复核、reviewed amendment和明确批准。

**Tech Stack:** Python 3.11、pytest、Ruff、Decimal、SHA-256、`O_CREAT|O_EXCL|O_NOFOLLOW`、JSON Schema、Docker Compose、PostgreSQL 17、repository Harness、Chrome headed QA、Micromamba `qi-p0`。

## Global Constraints

- Selected lane：`Heavy`，因为计划改变credential/account authorization gate、cycle authorization/evidence schema、budget Owner与runtime activation contract。
- Design source：`docs/superpowers/specs/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle-design.md`。
- Parent plan：`docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`。
- Sealed predecessor：GDT-10D run `20260802T101404291929Z-884bec62`、evidence commit `daa3e6f`、committed cost `3.526656 CNY`，全部immutable。
- Exact cycle ID：`gdt10e-auth-remediated-live-20260802`。
- Overall envelope：`50.000000 CNY`；GDT-10E incremental ceiling：`46.473344 CNY`。不得round、rollover或重新分配完整`50.000000`。
- Pricing：复用 committed `provider-pricing-gdt10d/1` snapshot和exact SHA；`2026-08-03` 只读复核确认公开费率未变，不读取account invoice/free tier/discount。
- Qwen identity：`qwen3-vl-plus-2025-12-19`、`cn-beijing`、`production_uncertainty/symbol-uncertainty-router/1`。
- Retry：timeout/transport/authentication/request-rejected/rate-limited/service/metadata均`0`；only `ProductionRetryCoordinator`可为schema-invalid授权一次second submission，且单独reserve。
- Pricing freshness：committed snapshot `retrieved_date=2026-08-02` 经 `2026-08-03` 独立只读公开价格复核、reviewed plan amendment和user approval后，只允许在`2026-08-03T23:59:59+08:00`前issue；超过时点再次fail closed，不得自动刷新/沿用。
- No Provider work before Task 5 final independent `GO` and one-use issuance/consume。Task 6只允许一次`make verify-p0-live` start；Task 7仅允许accepted paused literal run的一次same-run resume。
- Tasks 1-8 implementation/live boundary已获用户明确批准；所有既有 plan gates 仍为强制前置条件，不得从本 plan 存在推断超出已批准边界的 execution authority。
- direct Provider diagnostic、second replacement、budget expansion、`0015_drop_symbol_attempt_v1_default` 与 production promotion仍被阻断；本 amendment 只授权 reviewed 后的 exact successor target DB reconciliation，main/non-target runtime/DB mutation与model fallback不授权。
- The historical cleanup-proof docs-only amendment preserves blocks on credential/runtime mutation, Provider calls and paid execution; it changed only cleanup-proof ownership/contract before Task 2 implementation resumed. The current successor DB-identity/pricing amendment separately authorizes only its reviewed Step 1A code/test convergence and Step 1B exact target reconciliation under the gates above；它不授权Provider或paid execution。
- Single retry archive amendment：在唯一一次新的 Task 5 zero-paid retry 前，`live_cycle_authorization.py` 的 `retire-no-issuance-receipt` 是 archive/replay 的唯一 Owner。它只允许固定 `no_issuance` receipt source `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json` 与 fixed archive `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt-zero-paid-retry.json`，并固定 bytes SHA `67b901bff1dd44431fb3bda6cf1aa0cbcbe79f62ce7302486a1c80f32d3281bb`、content SHA `15e4865a81244962b6e20438fa0bf577084ad63a878f3e6f7e1072605210a532`、cycle/schema/branch、current uid/gid 与 `0600`。它用 no-overwrite hard-link、parent fsync、inode/device/bytes revalidation、source unlink 和 final parent fsync；仅 source-only、same-inode source+archive、archive-only 三态可安全 replay。任何 alias/symlink/identity/private-target reappearance或 archive conflict fail closed；不得创建新 schema或退役 future receipt。
- Reviewer/explorer严格read-only；一个write-capable executor按Task 1 -> Task 8顺序执行。

## Problem Boundary Record

- Single account-readiness Owner：`.agent/harness/scripts/provider_account_readiness.py`，只拥有private attestation schema/expiry/binding and exact readiness disposal after validating Task 3's intent; it never creates, repairs, rewrites or infers lifecycle proof.
- Cycle lifecycle Owner：`.agent/harness/scripts/live_cycle_authorization.py`与`backend/app/providers/cycle_authorization.py`，继续拥有issuance/consume/run/project/resume/terminal。Task 3 `live_cycle_authorization.py` is the sole writer and semantic Owner of `provider-cycle-cleanup-intent/1`, including intent/receipt/blocker replay, repair and lifecycle blocking.
- Cost Owner：`backend/app/providers/usage_ledger.py`，从validated active issuance读取`max_total_cny`。
- Provider fact Owner：`QwenVisionProvider`，保持HTTP status safe classification；不验证console/account readiness。
- Runtime acceptance fact Owner：`.agent/harness/scripts/run-p0.py::_seal_runtime_account_acceptance()`；`.agent/harness/scripts/live_evidence_policy.py`只验证/投影，不成为第二truth Owner。
- Old path to replace：credential key presence作为充分readiness；多个模块hard-code`50.000000`而忽略plan-specific tighter issuance ceiling；unowned prose-only runtime acceptance；expired-attestation renewal会改写consumed issuance的路径。
- Unchanged contract：endpoint/model、timeout/SDK retry、Provider permit、routing/review/GD&T semantics、historical evidence DB `0014`、successor runtime exact head `0016`、current-four inputs、close bridge、same-run export/receipt。
- Rollback first verification：revalidate sealed GDT-10D run with `validate_paid_cycle_evidence(require_success=False)`，then run focused Harness/Provider tests。

---

### Task 1: Accept The Reviewed Boundary After Explicit User Approval

**Files:**

- Modify: `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`
- Modify: `docs/superpowers/specs/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle-design.md`
- Modify: `docs/superpowers/plans/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md`

**Interfaces:**

- Consumes: explicit user approval of behavior、zero-paid activation and one paid cycle boundary。
- Produces: one selected companion plan; no credential/runtime/Provider mutation。

- [x] **Step 1: Record exact approval without broadening it**

Add a dated parent-plan selection record with:

```text
Selected lane: Heavy
Selected companion: 2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md
Historical cost: 3.526656 CNY
Incremental ceiling: 46.473344 CNY
Overall envelope: 50.000000 CNY
Provider starts: one
Resume: only one literal same-run resume after accepted pause
Still blocked: direct Provider diagnostic, second replacement, `0015_drop_symbol_attempt_v1_default`, production promotion
```

- [x] **Step 2: Re-run documentation self-review**

```bash
rg -n 'TODO|TBD|FIXME|50\.000000|46\.473344|3\.526656|direct Provider|replacement|0015' \
  docs/superpowers/specs/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle-design.md \
  docs/superpowers/plans/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md \
  docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md
git diff --check
```

Expected：无placeholder；三组Decimal一致；direct Provider、second replacement和`0015_drop_symbol_attempt_v1_default`只作为prohibition出现。

- [x] **Step 3: Commit approved execution boundary**

```bash
git add docs/superpowers/specs/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle-design.md \
  docs/superpowers/plans/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md \
  docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md
git diff --cached --check
git commit -m "docs(gdt): approve credential-ready replacement cycle"
```

Expected：clean docs-only commit；no runtime、credential、DB、authorization或Harness run mutation。

---

### Task 2: Implement Private Operator Account Readiness Binding

**Files:**

- Create: `.agent/harness/scripts/provider_account_readiness.py`
- Modify: `backend/tests/contract/harness/test_live_run_contract.py`
- Modify: `backend/tests/contract/harness/test_contract_architecture.py`

**Interfaces:**

- Produces: `issue_account_readiness(...) -> dict[str, object]`、`validate_account_readiness(...) -> AccountReadinessEvidence`、`dispose_account_readiness(...) -> CleanupEvidence`。The last surface consumes only Task 3's exact immutable `provider-cycle-cleanup-intent/1` and removes only exact `account-readiness.json`。
- `AccountReadinessEvidence`只暴露`schema_version`、`content_sha256`、`issued_at`、`expires_at`、`operator_state=operator_attested`、`all_operator_checks_passed`、`credential_binding_matches`；不暴露private salt/binding/credential/account fields。Runtime acceptance不是此helper的Owner。
- CLI exact surface：`issue`、`validate --phase start|resume`、`dispose`。`issue` and `validate` require `--root` equal to the one exact private-root literal；wrong/missing root fails，while `dispose` rejects `--root` and derives the fixed root only from the accepted intent contract. Credential/workspace/model/operator只从`QI_QWEN_API_KEY`、`QI_QWEN_WORKSPACE_ID`、`QI_QWEN_MODEL`、`QI_P0_OPERATOR_ID`读取；CLI禁止secret/workspace argv，stdout只有single-line sanitized JSON。`validate --phase resume` retains `--runtime-acceptance` as an exact Harness file path for the run-bound acceptance fact and requires `--expected-content-sha256`; start rejects that argument. `dispose` instead requires `--cleanup-intent` and must not overload `--runtime-acceptance` as lifecycle proof。

- [ ] **Step 1: Write RED private-file and expiry tests**

Add tests proving non-current owner、directory not `0700`、file not `0600`、symlink、duplicate file、wrong cycle/model/region、expiry over `1800s`、expired document、missing/false operator boolean and invalid content hash all fail closed。

```python
def test_account_readiness_requires_all_operator_checks(tmp_path, monkeypatch):
    source = private_source(
        tmp_path,
        remediation_completed=False,
    )
    with pytest.raises(ValueError, match="account readiness"):
        module.validate_account_readiness(
            source,
            cycle_id="gdt10e-auth-remediated-live-20260802",
            model="qwen3-vl-plus-2025-12-19",
            max_incremental_cny="46.473344",
            environment=qwen_environment(),
        )
```

- [ ] **Step 2: Write RED credential-bundle binding and privacy tests**

Use a high-entropy marker as fake API key and a distinct fake workspace。Assert exact bundle passes；key/workspace/model/cycle mutation fails；helper CLI stdout/stderr、exception text、dataclass repr、captured logs and public evidence do not contain marker、workspace、salt或private binding。Recursively traverse the currently tracked run/live/receipt schemas rather than checking only top-level properties. Actual GDT-10E run/live/receipt writer projection cannot be tested before Task 3 creates the v3 schema/writer surfaces, so that integration privacy test is a required Task 3 Step 3/5 gate and is not simulated by Task 2。

```python
def test_readiness_public_evidence_never_exposes_private_bundle(...):
    evidence = module.validate_account_readiness(...)
    rendered = json.dumps(evidence.public_dict(), sort_keys=True)
    assert secret_marker not in rendered
    assert workspace_marker not in rendered
    assert set(evidence.public_dict()) == {
        "schema_version",
        "content_sha256",
        "issued_at",
        "expires_at",
        "operator_state",
        "all_operator_checks_passed",
        "credential_binding_matches",
    }
```

- [ ] **Step 3: Implement exact private schema and length-delimited binding**

Use `secrets.token_bytes(32)` salt。Hash length-delimited UTF-8 fields in exact order：schema domain、cycle ID、model、workspace、API key。Write private document with `O_CREAT|O_EXCL|O_NOFOLLOW`、mode `0600`，then `fsync(file)` and `fsync(parent)`。Do not print document or private fields。

```python
def _bundle_binding(*, salt: bytes, cycle_id: str, model: str,
                    workspace_id: str, api_key: str) -> str:
    digest = hashlib.sha256(b"provider-account-readiness/1\0")
    for value in (salt.hex(), cycle_id, model, workspace_id, api_key):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()
```

The private document may contain salt/binding；`public_dict()` may not。Implement argparse subcommands with exact safe args：`--root`、`--cycle-id`、`--region`、`--max-incremental-cny`、`--expires-in-seconds`、operator boolean flags、`--expected-content-sha256`、`--phase`、`--runtime-acceptance` for resume only and `--cleanup-intent` for dispose only。Reject `--api-key`、`--workspace-id` and unknown args。

`validate --phase start` requires unexpired age `<=1800s` and exact live bundle binding。`validate --phase resume` requires original document SHA/binding plus the exact-path, exact-schema, canonical-bytes same-run `provider-account-runtime-acceptance/1` fact frozen below; it does not renew expiry or issue a new document。`dispose` accepts only `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json`, exact canonical stored bytes/schema/content hash/current owner/mode/non-symlink, exact cycle/readiness SHA, one exact branch tuple, exact allowlisted safe-path hashes and fixed expected steps. Task 3's intent is the sole lifecycle proof: Task 2 does not parse or reinterpret issuance/cancellation/terminal/Harness documents, and instead requires exact state-specific root children `{readiness}` or `{readiness, authorization}` before unlink and `{}` or `{authorization}` on replay; an allowed authorization child must be a current-owner/group non-symlink `0700` directory. Bare mappings, caller-selected disposal roots/paths, foreign intent, aliases, symlinks, wrong owner/mode/hash or branch tuple fail closed without deleting readiness. It holds stable parent/root/intent/readiness descriptors through validation and unlink, uses `openat`/`fstat`-equivalent identity and inode/device consistency, relative unlink and parent-directory `fsync`; before a valid durable intent every failure leaves readiness untouched, and after its destructive commit point any write/fsync/close/resource failure returns only `account_readiness_cleanup_incomplete`。All immutable JSON readers reject duplicate keys and require exact canonical full JSON plus one newline. Issuance uses a complete write loop: every positive partial write advances the offset and retries the remainder；a zero-byte write or an exception/final incomplete total fails issuance。

- [ ] **Step 4: Run focused GREEN and privacy architecture gate**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  -k 'account_readiness or credential_binding' -q
micromamba run -n qi-p0 ruff check \
  .agent/harness/scripts/provider_account_readiness.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py
```

Expected：all pass；architecture gate recursively forbids private salt/binding fields in tracked run/live/receipt schemas and proves helper CLI/error/repr/log surfaces are sanitized. Task 3 must additionally execute the actual v3 run/live/receipt writer privacy gate after those writers exist。

---

### Task 3: Bind The Remaining Budget And Readiness To One-Use Authorization

**Files:**

- Modify: `backend/app/providers/cycle_authorization.py`
- Modify: `backend/app/providers/usage_ledger.py`
- Modify: `.agent/harness/scripts/live_cycle_authorization.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/live_evidence_policy.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/scripts/check-contracts.py`
- Modify: `.agent/harness/policy/gdt10d-runtime-closure.txt`
- Modify: `.agent/harness/schemas/run.schema.json`
- Modify: `.agent/harness/schemas/live-run-evidence.schema.json`
- Create: `.agent/harness/schemas/provider-account-runtime-acceptance.schema.json`
- Modify: `Makefile`
- Modify: `backend/tests/unit/providers/test_provider_usage_ledger.py`
- Modify: `backend/tests/contract/harness/test_live_run_contract.py`
- Modify: `backend/tests/contract/harness/test_receipt_policy.py`
- Modify: `backend/tests/contract/harness/test_contract_architecture.py`

**Owner/File Closure Amendment (2026-08-02):** `provider-account-runtime-acceptance.schema.json` must be registered by the existing authoritative schema inventory in `check-contracts.py`, and the Task 3 changes to `backend/app/providers/cycle_authorization.py` and `usage_ledger.py` must be represented by the existing runtime-closure manifest. These two paths close existing control-plane Owners only; they do not add a new schema Owner, runtime behavior, Provider access, or lifecycle surface.

**Interfaces:**

- Issuance adds exact `plan_ref`、`prior_cycle_evidence_sha256`、`historical_committed_cny`、`overall_envelope_cny`、`readiness_sha256` and plan-bound `max_total_cny`。
- `ActiveCycleAuthorization.max_total_cny` becomes the only ledger ceiling input。
- GDT-10E uses `run/3` and `live-run-evidence/3`；GDT-10D remains byte-valid `run/2` + `live-run-evidence/2`。
- Run/live public evidence adds exact `provider-account-readiness-evidence/1` with `operator_state=operator_attested`、`runtime_state=not_yet_accepted|runtime_accepted`、readiness SHA、binding boolean、nullable runtime-acceptance SHA and exact three Decimal fields。
- `.agent/harness/scripts/run-p0.py::_seal_runtime_account_acceptance()` is the sole writer of `reports/provider-account-runtime-acceptance.json`; it creates one immutable `provider-account-runtime-acceptance/1` fact after existing Qwen response evidence validation。`live_evidence_policy.py` only validates/projects that fact。
- `live_cycle_authorization.py abort-preconsume` is the sole orchestration entry for zero-paid NO-GO and issued-but-unconsumed cancellation/cleanup。
- `live_cycle_authorization.py` Task 3 is the sole writer and semantic Owner of `provider-cycle-cleanup-intent/1`; Task 2 only validates the exact intent and deletes exact readiness.

- [ ] **Step 1: Write RED issuance/budget tests**

Cover exact `46.473344` success；`0`、negative、more than policy `50`、wrong six-decimal shape、historical + incremental != overall、wrong readiness SHA、wrong predecessor evidence SHA、unsafe plan ref and stale readiness all reject beforeconsume。

```python
def test_gdt10e_issuance_carries_forward_original_envelope(...):
    issuance = issue(
        historical_committed_cny="3.526656",
        max_total_cny="46.473344",
        overall_envelope_cny="50.000000",
    )
    assert Decimal(issuance["historical_committed_cny"]) + Decimal(
        issuance["max_total_cny"]
    ) == Decimal(issuance["overall_envelope_cny"])
```

- [ ] **Step 2: Write RED ledger dynamic-ceiling tests**

Create active issuance at `3.526656` and `46.473344` test ceilings。Assert ledger reserve usesexact active authorization ceiling，snapshot remaining uses the same value，journal reopen/close revalidate it，and no code path silently falls back to`50.000000`。

```python
def test_ledger_rejects_reservation_above_issuance_ceiling(...):
    ledger = open_cycle_ledger(max_total_cny="3.526656")
    reserve_qwen(ledger, subject_id="first")
    reserve_qwen(ledger, subject_id="second")
    with pytest.raises(ProviderBudgetExceeded):
        reserve_ocr(ledger, subject_id="third")
    assert ledger.snapshot().committed_total_cny == "3.526656"
    assert ledger.snapshot().remaining_cny == "0.000000"
```

- [ ] **Step 3: Write RED versioned schema/evidence tests**

Require tracked GDT-10D run `20260802T101404291929Z-884bec62` still validates unchanged as exact v2。Implement `schema_version`-discriminated `oneOf`: legacy `run/1|run/2` and `live-run-evidence/2` definitions remain exact；GDT-10E requires `run/3` + `live-run-evidence/3` and the new required readiness/budget fields。Reject v3 missing any field、v2 carrying v3 fields、v3 using legacy paid-cycle shape、v2 using v3 shape、wrong cycle/version pairing and arithmetic/hash drift。Private salt/binding/workspace/account fields are forbidden from both versions andreceipt。

- [ ] **Step 4: Implement issuance-specific budget and readiness binding**

Parse all amounts with `Decimal` from six-decimal strings。Require:

```python
Decimal("0.000000") < incremental <= Decimal(policy_hard_ceiling)
historical + incremental == overall == Decimal("50.000000")
```

`ProviderUsageLedger._scan_locked()`、`reserve()` and `snapshot()` must use `authorization.max_total_cny` obtained under existing process->OS lock order。Do not add another config/env budget source。

`live_cycle_authorization.py` validates the safe relative `plan_ref` against committed HEAD and revalidates private readiness immediately before issuance、consume、activation and final preflight。Only readiness content SHA andsanitized verdict enter run evidence。

Add exact GDT-10E CLI subcommands without changing the historical GDT-10D args：

- `prepare-zero-paid --authorization --override --safe-override --readiness --report` creates/validates private controls、applies safe runtime andO_EXCL writes a sanitized preparation report；authorization must be absent。
- `zero-paid-preflight --authorization --override --safe-override --readiness --preparation-report --report` validates the immutable preparation report、calls the existing preflight directly andO_EXCL writes a distinct sanitized no-delta report；authorization remains absent and override unapplied。
- `issue-gdt10e --authorization --readiness --zero-paid-report --cycle-id --plan-ref --prior-cycle-evidence-sha256 --historical-committed-cny --max-total-cny --overall-envelope-cny --expires-in-seconds` derives all committed runtime/pricing/current-four/image hashes from the validated report，never from shell-computed untrusted values。
- `validate-unconsumed --authorization --override --readiness --zero-paid-report` revalidates exact issuance/readiness/freshness/no-delta immediately before start without mutation。
- `prepare-resume --authorization --override --safe-override --readiness --runtime-acceptance --run-id` recreates fresh controls only after exact original readiness SHA/binding、runtime-acceptance fact andpause handoff validation；it does not renewattestation orauthorization。
- `bound-run-id --authorization` validates the sole durable run binding andprints only its literal run ID；it never selects a directory or`latest`。
- `abort-preconsume --authorization --override --safe-override --readiness --preparation-report --zero-paid-report --cleanup-intent --cleanup-receipt --cleanup-blocker --review-deadline` owns both no-issuance and issued-unconsumed cleanup branches。
- `dispose-terminal --authorization --readiness --run-id --cleanup-intent --cleanup-receipt --cleanup-blocker --review-deadline` deletes remaining exact private readiness/authorization state only after sealed run-bound terminal、safe runtime、healthyDB andcopy/hash proof。

Path validation has three disjoint classes：

1. `--root` must equal the exact non-symlink directory `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d`；mutable private inputs (`authorization`、`override`、`safe-override`、`readiness`、`preparation-report`、`zero-paid-report`) must be their exact named absolute paths under that root。Wrong-root、trailing-alias、symlink andresolved-outside cases fail closed andhave focused tests；
2. `runtime-acceptance` must resolve without symlink under `/home/reggie/vscode_folder/Quality_Inspection/.worktrees/structured-geometric-tolerance-recognition/.agent/harness/runs/` to the exact child `reports/provider-account-runtime-acceptance.json`；its run-directory segment must match `^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$` and equal the validated authorization binding；
3. cleanup outputs must respectively equal the exact root-sibling absolute paths `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json`、`/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json` and `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-blocker.json`。

`plan-ref` remains the one exact safe repository-relative path already shown in the issuance command。No subcommand accepts any other path、glob、symlink、secret argv or automatic run selection；output is fixed action/status、sanitized SHA or`bound-run-id` literal only。

- [ ] **Step 5: Implement the single runtime-acceptance transition Owner**

Add exact schema `provider-account-runtime-acceptance/1` with `additionalProperties=false` and exactly these fields/types: `schema_version` const；exact `cycle_id`；literal-regex `run_id`；non-empty `project_id`；SHA-256 strings `readiness_sha256`、`submission_started_sha256`、`settlement_sha256`、`call_evidence_sha256` and `content_sha256`；exact `model`；integer-minimum-1 `ledger_attempt_index`；and non-empty `accepted_at` copied byte-for-byte from settlement `settled_at`。Forbid request-ID value、workspace、usage、prompt/response andsecret fields。Use canonical content hash excluding itself and require canonical full stored JSON plus one newline；readers reject duplicate keys, reordered/whitespace variants and symlinks。

`run-p0.py::_seal_runtime_account_acceptance()` first uses existing Qwen request/response/call validators、matching ledger started/settled facts andexact same-run storage/project facts。It deterministically selects the lowest ledger attempt index with a validated successful primary/retry response；`accepted_at` is copied from that immutable settlement's `settled_at`，never from a new wall-clock read。Only this input may O_EXCL-create the report withmode`0600` and file+directory `fsync`。A schema-invalid response may qualify only when its safe response evidence proves an authenticated Provider response；401/403、transport/timeout/metadata、reserved-only orsubmission-started-without-response never qualify。Concurrent calls derive identical bytes；existing exact bytes are verified replay only after schema/content-hash check，conflicting bytes fail closed。The actual run/live/receipt serializer tests must project only the seven-field `provider-account-readiness-evidence/1` public object and prove high-entropy credential/workspace/salt/binding markers are absent recursively from serialized run/live/receipt bytes, exception text and captured logs；this is the Task 3 integration counterpart to Task 2's helper-surface privacy gate。

Exact active-path insertion in `start_live_run()` is immediately after `_execute_selector_in_run(...)` has returned `exit_code=0` and `result_state=passed` and `project_id = str(sample["project_id"])` is assigned，but before frontend/project URL output、`_freeze_sample_after_item_verdict()`、ledger refresh or`pause_live_run()`：

```python
runtime_acceptance = _seal_runtime_account_acceptance(run_dir, project_id=project_id)
_project_runtime_account_acceptance(run_dir, runtime_acceptance)
```

`_project_runtime_account_acceptance()` is the one run-p0 host call site that asks `live_evidence_policy.account_readiness_projection(...)` to validate the fact andatomically rewrite the unsealed live evidence；it cannot create acceptance facts。`run/3` is immutable initial projection and always remains `operator_attested + not_yet_accepted + null`。`live-run-evidence/3` is the current projection and changes to`runtime_accepted + exact fact SHA` only through that policy after fact validation。`pause_live_run()` requires exact run-initial/readiness/fact/live-current consistency；resume andformal receipt revalidate the same triple。A failed terminal may have no fact andremainnot-yet-accepted，or may bind one pre-failure validated fact；it may never claim runtime acceptance without the fact。Tests cover active call ordering before freeze/pause、dead-writer detection、run/live/fact pause/resume/terminal consistency、valid primary、schema-invalid authenticated retry、401/403、timeout/transport、missing/mismatched started/settled/call evidence、foreign run/project/readiness/model、stable timestamp、concurrent exact/conflicting create and marker-secret privacy。Architecture gate permits the fact writer only at `_seal_runtime_account_acceptance` andthe live projection writer only at `_project_runtime_account_acceptance`。

- [ ] **Step 6: Retire the consumed GDT-10D resume surface**

Replace `resume-gdt10d-live` / `GDT10D_RUN_ID` with `resume-gdt10e-live` / `GDT10E_RUN_ID`。The old GDT-10D authorization is terminal and private root deleted；there is no real consumer。Keep historical sealed schemas, but do not keep an executable stale resume alias。

```make
resume-gdt10e-live:
	@micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py execute-resume \
		--authorization "$${QI_LIVE_CYCLE_AUTHORIZATION_REF:?}" \
		--override "$${QI_LIVE_CYCLE_OVERRIDE_REF:?}" \
		--run-id "$${GDT10E_RUN_ID:?}"
```

- [ ] **Step 7: Implement pre-consume abort and private-state cleanup**

Add `live_cycle_authorization.py abort-preconsume --authorization --override --safe-override --readiness --preparation-report --zero-paid-report --cleanup-intent --cleanup-receipt --cleanup-blocker --review-deadline`。No-issuance mode requires authorization root absent。Issued-but-unconsumed mode requires issuance exact and consumption/run/project/resume/terminal/activation all absent，then O_EXCL/fsyncs `provider-cycle-unconsumed-cancellation/1` before cleanup。

Before any deletion, Task 3 validates every expected path/owner/mode/symlink/hash and branch lifecycle fact, copies exact `provider-account-readiness/1.expires_at` into intent `readiness_expires_at`, rejects `created_at > readiness_expires_at`, then creates the exact root-sibling `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json` with `O_CREAT|O_EXCL|O_NOFOLLOW`, actual `0600`, exact current uid/gid, canonical content hash, file `fsync` and parent-directory `fsync`. The implementation must use the design's frozen `provider-cycle-cleanup-intent/1` contract verbatim: `additionalProperties=false`; const schema/cycle; branch enum; SHA-256 string fields; nullable SHA-256 issuance/cancellation/terminal fields; nullable literal-run-ID field; exact safe-path map; exact ordered steps; canonical UTC-seconds `created_at` and `readiness_expires_at`; exact deadline; actual non-negative uid/gid; `mode="0600"`; and content hash. Canonical `content_sha256` excludes itself and hashes UTF-8 JSON with `ensure_ascii=False`, `sort_keys=True`, `separators=(",", ":")`, no trailing newline; the stored canonical full JSON has exactly one trailing newline. Path hashes are `sha256(canonical_absolute_path.encode("utf-8")).hexdigest()` for the already allowlisted lexical absolute string only: no resolve, symlink following, alias, relative path, glob or trailing-slash normalization.

Implement the exact safe-path map from the design: every branch has exactly the 18 named private-root, readiness, live/safe override, authorization root/children (including legacy child blocker), reports and root-sibling journal paths; only `terminal` additionally has exactly the six literal-run Harness root/document/live-evidence/runtime-acceptance/quiescence/close-bridge paths under `/home/reggie/vscode_folder/Quality_Inspection/.worktrees/structured-geometric-tolerance-recognition/.agent/harness/runs/${run_id}`. Non-terminal mappings reject those six keys; terminal requires them. `expected_steps` is exactly `["safe_runtime_proved","live_override_absent","safe_override_absent","preparation_report_absent","zero_paid_report_absent","account_readiness_absent","authorization_root_absent","private_root_absent"]` with no extra, missing, duplicate or reordered item.

The correlations are exact: `no_issuance` proves authorization root absent before intent creation and has null issuance/cancellation/terminal/run values with consumption/run/project/resume/terminal/activation absent; `issued_unconsumed` validates exact `provider-cycle-issuance/1` plus exact `provider-cycle-unconsumed-cancellation/1`, has non-null issuance/cancellation hashes, null terminal/run values and the same absence proof; `terminal` validates exact issuance, run binding and `provider-cycle-terminal/1`, has non-null issuance/terminal hashes and literal run ID, null cancellation hash, and keeps lifecycle-owned cycle/run/run-SHA/status/quiescence validation. Every other nullability or cross-document combination fails before deletion.

Then the one allowed order is: prove safe runtime/no activation -> fsync-delete live/safe overrides -> fsync-delete preparation/zero-paid reports -> call Task 2 `dispose --cleanup-intent` to fsync-delete exact readiness -> delete authorization files/root -> remove empty private root -> O_EXCL/fsync cleanup receipt -> fsync-delete cleanup intent. Task 2 never deletes authorization files/root, private root, intent, receipt, blocker, override or reports. No later step may depend on deleted readiness bytes; all expected hashes are frozen in the intent first.

Preserve `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization/cleanup-blocker.json` unchanged as legacy `provider-cycle-cleanup-blocker/1` with exact `{schema_version, cycle_id, run_id, status, failure_codes, content_sha256}` and existing consumers; reject `/1` at the root-sibling path and reject `/2` inside authorization root. The root-sibling blocker is `provider-cycle-cleanup-blocker/2`, `additionalProperties=false`, with exactly schema/cycle/branch, `cleanup_intent_sha256`, `account_readiness_sha256`, `safe_path_sha256s_sha256`, enumerated fixed failure code, eight-boolean `completed_steps`, canonical UTC `observed_at` and `readiness_expires_at` copied exactly from/cross-checked against intent (never read from readiness after intent creation), exact deadline, actual uid/gid/mode and canonical hash. The root-sibling receipt is `provider-cycle-cleanup-receipt/1`, `additionalProperties=false`, with exactly schema/cycle/branch, the same three cross-hashes, all-true eight-boolean `completed_steps`, canonical UTC `completed_at`, deadline, actual uid/gid/mode and canonical hash. `safe_path_sha256s_sha256` uses the same canonical JSON hash settings as the intent; receipt/blocker use `O_EXCL|O_NOFOLLOW`, actual `0600`, file/parent fsync and exact replay only, without raw paths/secrets.

Freeze the design's seven-state journal behavior verbatim: fresh creation only when all three journal files are absent; intent-only resume at first false ordered invariant; durable intent plus failure creates immutable blocker `/2` from the expiry frozen in intent; intent+blocker validates cross-hashes, expiry equality and actual state without rewriting stale-but-not-false snapshots; all invariants true deletes blocker then writes receipt then deletes intent; intent+receipt deletes only intent, receipt-only is terminal replay-only success, and blocker+receipt or target reappearance conflicts; Task 2 validates the intent expiry against readiness while it exists, then unlink-before-directory-fsync returns only `account_readiness_cleanup_incomplete` and needs exact intent/branch validation plus later private-directory fsync before readiness absence is complete, without opening deleted readiness. Task 3 remains the sole journal/replay Owner.

Focused tests must prove Task 2's exact five operator claims; exact cycle/model/region/amount; `issued_at <= now <= expires_at`; fresh intent/readiness expiry mismatch rejection; expiry coverage by intent content hash; exact intent path/schema/hash/owner/mode/no-symlink; all three exact branch tuples/nullability combinations and their state-specific private-root child sets; rejection of forged bare mapping/caller-selected disposal root, wrong safe-path hash/steps, foreign intent branch tuple and root-child mismatch; stable-fd race safety; privacy across helper CLI/error/repr/log plus recursive current run/live/receipt schemas; Task 2 never parses lifecycle-owned documents, writes intent or removes authorization/private root; and partial deletion returns fixed incomplete code. Task 3 tests must additionally cover actual v3 run/live/receipt writer privacy, every frozen journal transition, legacy `/1` at sibling rejection, `/2` in authorization-root rejection, exact keys/types/order/hash/mode, branch maps, readiness-deleted then blocker-create-interrupted intent-only replay followed by exact blocker creation from intent, blocker/intent expiry mismatch rejection, proof that no post-readiness step opens deleted readiness, stale-true blocker snapshot, blocker+receipt conflict, intent+receipt crash replay, receipt-only terminal replay, durable intent before every deletion, cancellation/terminal correlation, interruption after intent and every deletion/fsync, and no issuance/runtime/Provider delta.

- [ ] **Step 8: Run focused GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers/test_provider_usage_ledger.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_receipt_policy.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  -k 'account_readiness or runtime_acceptance or abort_preconsume or gdt10e or max_total_cny or historical_gdt10d' -q
micromamba run -n qi-p0 ruff check \
  backend/app/providers/cycle_authorization.py \
  backend/app/providers/usage_ledger.py \
  .agent/harness/scripts/provider_account_readiness.py \
  .agent/harness/scripts/live_cycle_authorization.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/scripts/generate-receipt.py
git diff --check
```

---

### Task 4: Full Offline Verification And Independent Implementation Review

**Files:** all implementation/test files from Tasks 2-3 only, including Task 3's authoritative schema inventory and runtime-closure manifest.

**Interfaces:**

- Produces: clean committed implementation; no private state、runtime、credential、DB或Provider mutation。

- [ ] **Step 1: Run complete Harness and Provider gates**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness -q
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/providers \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/unit/candidates/test_advisor.py -q
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source working
git diff --check
```

- [ ] **Step 2: Run full backend gate**

```bash
make test-backend
```

Expected：full pass。若known Docker address-pool blocker在DB creation前复现，使用与GDT-10D相同的explicit loopback/tmpfs PostgreSQL 17 fallback，先`alembic upgrade head`再运行exact `backend/tests` suite，并清理临时container；不得把partial suite报告为full pass。

- [ ] **Step 3: Run independent implementation review**

Read-only reviewer必须检查：operator-claim vs runtime-proof separation、single runtime-acceptance writer/transition、private binding privacy、start-only expiry与same-document resume、owner/mode/symlink、historical arithmetic、pricing freshness、dynamic issuance ceiling、ledger lock/reopen/close、v2/v3 schema discrimination、one-use ordering、NO-GO/issued-unconsumed/terminal cleanup、retry invariants、old resume retirement、literal CLI和no direct network path。Required verdict：`accept`。

- [ ] **Step 4: Commit exact implementation files**

Stage literal files only；then validate prospective index runtime closure：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source index
git diff --cached --check
git commit -m "feat(provider): bind account readiness to remaining budget"
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source HEAD
git status --short
```

Expected：clean committed HEAD；no private state、runtime、credential、DB或Harness run delta。

---

### Task 5: Create Operator Attestation And Prove Zero-Paid GO

**Files/State:**

- Private root: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/`
- Readiness: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json`
- Live/safe override: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env` and `safe.env`
- Authorization: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization/`
- Sanitized preparation report: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/preparation.json`
- Sanitized zero-paid report: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/zero-paid-readiness.json`
- Sanitized cleanup intent: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json`
- Sanitized cleanup receipt: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json`
- Sanitized cleanup blocker: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-blocker.json`
- DB reconciliation root: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-db-reconciliation/`
- DB backup: `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-db-reconciliation/pre-canonical-0016.dump`
- Harness/run tree: read-only; no new run before GO/issuance。
- Runtime: feature `api/worker` safe-identity only after approved rebuild。

**One-time retry entry amendment:** Before this retry only, run `retire-no-issuance-receipt` after implementation, focused verification and independent implementation review all pass. Its required postcondition replaces the ordinary all-absent receipt baseline only for this Task 5 Step 1: fixed archive exact present; fixed source receipt absent; private root/readiness/intent/blocker/authorization/live/safe controls/preparation/zero-paid reports absent; GDT-10E run count `0`. It is not an issuance, cleanup receipt rewrite, Provider action, paid attempt, DB mutation or Harness evidence mutation. Do not execute it again after archive-only success.

- [x] **Step 0: Retire the immutable no-issuance receipt exactly once**

**Deferred integration boundary — 2026-08-03:** 用户要求本轮不再新增 receipt archive/retry 功能，只合并已完成、已复审、已提交的功能。Step 0、Task 5 retry 与 Tasks 6-8 均保持未完成且本轮不得执行；未提交的 archive implementation/tests 不进入 `main`。恢复时仍须从本 Step 0 的 code/test/review gate 开始，并继续遵守一次 retry、exclusive-writer、pricing freshness 与全部 Provider/paid boundaries。

Partial integration 保留 `main` 的 `0013_project_catalog -> 0014_project_lifecycle`，并将 completed GDT migrations 线性重挂为 `0015_structured_geometric_tolerance -> 0016_symbol_provider_failure_diagnostics`；不创建或执行 forbidden `0015_drop_symbol_attempt_v1_default`。本 companion 的历史 `0014` live identity 不自动改写为 `0016`。因此 future resume 除上述 Step 0 gates 外，还必须先有 reviewed DB-identity/pricing amendment 和新的明确批准。

**Successor Step 0 selection record — 2026-08-03:** Selected lane remains `Heavy`; selected plan remains this companion; selection evidence is the user's instruction to branch from selection-time `main` base `76f2d48ae86fbe631fc406219f165891a0b1dcfc` and execute the deferred prior task. At the first amendment review, local `main` had advanced by one descendant commit to `ac5ccf56ef5c370a24c446fd77d6fbd9408eaed1`; successor HEAD remains the explicitly approved base, and this record does not authorize merging, rebasing or absorbing that later commit. Successor path/branch/HEAD are `.worktrees/gdt10e-retry-archive-continuation`, `feature/gdt10e-retry-archive-continuation`, and `76f2d48ae86fbe631fc406219f165891a0b1dcfc`; startup focused baseline is `369 passed`. Validation action is `continue` for Step 0 only. Writer order is docs owner -> independent read-only amendment reviewer -> docs commit -> one fresh `tdd_developer` -> parent verification -> independent implementation reviewer -> one literal archive command. Old feature-worktree WIP is excluded. The next verification is independent amendment `accept`; downstream Task 5 runtime/DB work, Provider and paid issuance remain blocked by the merged `0016` identity/pricing amendment and explicit-approval boundary above.

Run only after the code/test/review gates for this amendment are closed and the parent has established an operator-controlled exclusive-writer window. From the first fixed parent/source/archive validation through final parent `fsync` and terminal source/private/archive rechecks, no concurrent same-UID/root process、agent、operator or lifecycle command may create、rename、replace、unlink or rewrite either receipt or any private target. This is a required threat-model precondition, not an advisory-lock guarantee; do not run if exclusive ownership is uncertain.

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py retire-no-issuance-receipt \
  --receipt /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json \
  --archive /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt-zero-paid-retry.json
```

Expected：only the fixed source/archive three-state replay succeeds; archive bytes are exactly the immutable source bytes, source is absent, and all private targets remain absent. Observable entry/device/inode replacement before destructive commit, terminal source/private reappearance, or archive mismatch fails closed. Tests do not simulate a concurrent replacement inside the final stat-to-unlink syscall gap because that violates the approved exclusive-writer precondition and `unlinkat` has no expected-inode condition. Archive-only replay with any different future source remains a conflict and never unlinks it. No Provider/paid/DB/Harness delta is permitted. Any failure is a hard stop; never delete, copy, rename or hand-write either receipt.

Execution record：docs commit `d5b9d8f`、TDD/reviewed implementation commit `46ebb24`、parent two-file suite `399 passed`、Ruff和`git diff --check`全部通过；independent implementation reviewer final verdict `accept`。Literal archive command仅执行一次并返回 `status=ok`；source absent，fixed archive exact present with bytes/content SHA、schema/cycle/branch、uid/gid、mode and original inode all exact；private targets remain absent，GDT-10E run count remains `0`，Harness/runtime snapshot hashes and target container IDs stayed exact，DB remained reported `0014`。该 reported revision 随后在 Step 1 supplemental schema audit 中被识别为 old-feature collided identity，不是 canonical merged `0014_project_lifecycle`。

**Interfaces:**

- Consumes: operator-provided Qwen credential source and console readiness facts without exposing values。
- Produces: private readiness SHA、sanitized zero-paid report、independent `GO|NO-GO`；authorization remainsunissued/unconsumed。

- [x] **Step 1: Capture immutable baseline before mutation**

Record clean HEAD、target/non-target container IDs、volumes、ports、health、reported DB revision、Celery/Redis emptiness、GDT-10D tree hash、provider/storage/run inventories and absence ofworktree `.env`。For this one retry, require the exact archive from Step 0 present and exact source receipt absent; require private root、cleanup intent/blocker、authorization/cancellation andrun ID all absent before creation。Any other pre-existing path, archive mismatch or private target reappearance is a hard stop，not a reusable attempt。Do not read or print credential values。

Execution record：baseline artifact `.superpowers/sdd/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle/task-5-step-1-read-only-baseline.md` records clean `46ebb24`、exact archive/source/private state、target/non-target IDs/volumes/ports/health、empty Celery/Redis、stable Harness/GDT-10D/storage hashes/counts and zero Provider/paid/DB/Harness mutation。Supplemental schema audit found the collision truth frozen in `Successor DB-Identity And Pricing Binding Amendment` above；therefore Step 1 is complete as an immutable observation, but its reported `0014` must not be treated as canonical `0014_project_lifecycle` or as permission to run `upgrade head`。

- [ ] **Step 1A: Bind exact GDT-10E `0016` through the existing lifecycle Owner using TDD**

**Allowed code/test paths:**

- `.agent/harness/scripts/live_cycle_authorization.py`
- `.agent/harness/scripts/run-p0.py`
- `backend/app/providers/cycle_authorization.py`
- `backend/tests/contract/harness/test_live_run_contract.py`
- `backend/tests/contract/harness/test_contract_architecture.py`
- `backend/tests/unit/providers/test_provider_usage_ledger.py`

**Required mechanical inventory path:**

- `.agent/harness/policy/gdt10d-runtime-closure.txt`

Start only after this three-doc amendment receives fresh independent `accept` and is committed。Use one fresh `tdd_developer` with no nested delegation。RED must first prove current exact GDT-10E cycle rejects successor `0016` in zero-paid runtime identity、issuance、run creation and backend active/terminal/empty-close validation。GREEN makes `.agent/harness/scripts/live_cycle_authorization.py` the fixed policy writer of GDT-10E `expected_db_revision=0016`; `run-p0.py` and backend cycle authorization only enforce that cycle-scoped fact/current DB。Generic `issue`、GDT-10D and every non-GDT-10E path remain exact `0014`。

Required negative matrix：GDT-10E accepts only `0016` and rejects `0014`/arbitrary values；generic GDT-10D accepts only `0014` and rejects `0016`/arbitrary values。Only the GDT-10E fixtures in `test_provider_usage_ledger.py` move to`0016`; its generic/GDT-10D fixtures stay`0014`。No CLI flag, environment override, `{"0014", "0016"}` broad allowlist, fallback、schema change、migration change或second DB Owner is allowed。After the six code/test paths reach focused GREEN and final production bytes are stable, update only the existing `cycle_authorization.py` SHA row in `gdt10d-runtime-closure.txt`; this manifest remains a mechanical full-runtime inventory and may not encode cycle policy。Parent must run the complete two approved Harness files plus the complete `backend/tests/unit/providers/test_provider_usage_ledger.py`，Ruff on all six code/test paths, `check-contracts.py --runtime-closure-source working`, `git diff --check`, inspect the full seven-file diff and obtain a fresh independent implementation-review `accept`。Then stage exactly seven files, require `check-contracts.py --runtime-closure-source index`, commit them together, and require `check-contracts.py --runtime-closure-source HEAD` plus a clean worktree；no runtime/DB mutation occurs in this step。

- [ ] **Step 1B: Reconcile the collided successor DB identity before private readiness**

This step starts only after this amendment receives fresh independent read-only `accept`、the three docs are committed、Step 1A TDD/parent verification/fresh implementation review all pass、the six code/test paths plus the mechanical runtime-closure manifest are committed together and HEAD runtime-closure verification is clean。Revalidate exact public tuple、clean HEAD、fixed archive、private-target absence、zero GDT-10E runs、pricing deadline state、target/non-target identities、health、Celery/Redis emptiness、DB counts and the collision shape。Record the exact target PostgreSQL container ID、image ID and sole volume，then stop target `api/worker` and that exact PostgreSQL container without removing or recreating any of them；Redis、frontend and every non-target container/volume remain exact。Verify the original PostgreSQL container is stopped、its Compose `pg_isready` healthcheck is no longer executing、and the fixed names `quality-inspection-gdt10e-db-reconciliation-postgres` / `quality-inspection-gdt10e-db-reconciliation-network` are absent。Create the fixed internal-only network and start exactly one temporary PostgreSQL target container from the original exact `postgres:17-alpine` image ID with the sole target data volume、`--no-healthcheck`、no published port、no Compose network and no other mount except the fixed reconciliation root when required；the original container remains stopped and keeps its ID/config unchanged。After the temporary target reports SQL-ready through the sole parent inspection session and that session closes，run the final target preflight and establish one continuous operator-controlled exclusive target DB writer/session window that remains unbroken through backup creation、the entire disposable rehearsal and final temporary-target `0016` proof。No other agent、operator、service、lifecycle command or client may join the isolated network、open a target DB session or mutate the target；only the single parent-controlled serialized backup、verification or Alembic action may own one target client session at a time，and the disposable rehearsal may open sessions only against its separate isolated disposable DB。Each target action must close its session before the next begins；any unexpected or overlapping target client terminates the sequence fail-closed with the backup retained。

Inside that already-active exclusive target window，create only the fixed absent reconciliation root `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-db-reconciliation/` as exclusive mode `0700` and its fixed `pre-canonical-0016.dump` through an O_EXCL mode-`0600` custom-format PostgreSQL backup without overwriting any existing path；the `pg_dump` connection is the sole target client。After it closes，recheck zero target clients/prepared transactions/ungranted locks，fsync file and parent、verify owner/mode/size/SHA and `pg_restore --list`。Record only sanitized path identity、size and SHA，never DB rows or credential/private binding。Compare working migration bytes with committed HEAD and verify the old/current body equivalence before mutation。Restore this exact backup into one disposable tmpfs PostgreSQL 17 on a separate fixed internal-only network and prove the full state machine plus counts/hashes there before target mutation，while the exclusive temporary-target window remains active with zero target sessions；after the disposable runtime/network are removed and their endpoints proved closed，recheck target zero-session state before the first target metadata transition。This makes the backup the exact pre-mutation target state rather than a stale earlier snapshot。This root is not the account-readiness root and is never removed by `abort-preconsume`；restore or deletion remains blocked pending an independent reviewed closeout decision。

With committed `backend/alembic`、`alembic.ini` and `backend/app` mounted read-only into one fixed one-shot migration container joined only to the isolated reconciliation network，run exactly this state machine against the no-healthcheck temporary target DB：

```text
collided feature 0014
-> alembic stamp 0012
-> alembic upgrade 0015
-> verify canonical 0013/0014 objects, zero-row 0015 targets and unchanged diagnostic evidence
-> alembic stamp 0016
-> verify exact canonical head and all invariants
```

Preconditions require project-catalog/lifecycle objects absent、diagnostic objects exact present、attempts exactly `394 = 196 v1 + 198 v2` with zero invalid rows、immutable trigger enabled and `automatic_results = review_working_copies = reviewed_results = 0`。Intermediate `0015` must add exact project catalog/lifecycle objects and backfill the three existing projects consistently while preserving every pre-count/hash and diagnostic row；final `0016` is metadata recognition of the already-applied byte-identical diagnostic body, not DDL replay。Any mismatch stops with target writers still quiesced and backup retained；never downgrade、delete a volume、auto-restore、issue、consume or call Provider。

Writer/session preflight must run after target `api/worker` are stopped and before backup creation，and require all of the following exact SQL counts to be zero from the sole inspection session：other `pg_stat_activity` client backends for the target database、`pg_prepared_xacts` for the target database and ungranted `pg_locks`。The parent-controlled exclusive window starts with this pre-backup final target preflight and remains unbroken until final proof。Repeat the same zero-other-client/prepared/ungranted-lock check immediately after the backup closes、before and after the disposable rehearsal、immediately before each of `stamp 0012`、`upgrade 0015` and `stamp 0016`，immediately after each action before accepting its postcondition，and once more immediately before the final `0016` claim；the inspection session itself must be the sole target client and must close before the next serialized target backup/Alembic session starts。Capture two SHA-256 digests without printing row contents：(1) ordered `projects(id,state,version,recognition_mode,recognition_router_version)`；(2) ordered full `symbol_escalation_attempt_events` rows。Use the same literal digest queries before/after on disposable and target；the project-original-fields digest and attempt digest must remain exact，while whole-DB equality is not expected because `0013` intentionally writes transaction-time timestamps。

```sql
SELECT count(*) FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND backend_type = 'client backend';             -- expected 0
SELECT count(*) FROM pg_prepared_xacts
WHERE database = current_database();               -- expected 0
SELECT count(*) FROM pg_locks WHERE NOT granted;   -- expected 0
```

The digest commands must run as one Bash process with `pipefail` enabled，must make `psql` stop on SQL errors，and must pipe `COPY ... TO STDOUT` directly to SHA-256 without rendering rows。Any upstream nonzero、missing output or output not matching exactly one lowercase 64-hex digest fails closed；the separately verified exact row counts make an empty successful result invalid：

```text
set -o pipefail
if ! project_digest_line="$(docker exec "$target_pg_container" psql -X -v ON_ERROR_STOP=1 -U qi -d qi -qAt -c "COPY (SELECT jsonb_build_object('id',id,'state',state,'version',version,'recognition_mode',recognition_mode,'recognition_router_version',recognition_router_version)::text FROM projects ORDER BY id) TO STDOUT" | sha256sum)"; then
  exit 1
fi
if [[ ! "$project_digest_line" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]-$ ]]; then
  exit 1
fi
project_digest="${BASH_REMATCH[1]}"
if ! attempt_digest_line="$(docker exec "$target_pg_container" psql -X -v ON_ERROR_STOP=1 -U qi -d qi -qAt -c "COPY (SELECT row_to_json(t)::text FROM (SELECT * FROM symbol_escalation_attempt_events ORDER BY id) AS t) TO STDOUT" | sha256sum)"; then
  exit 1
fi
if [[ ! "$attempt_digest_line" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]-$ ]]; then
  exit 1
fi
attempt_digest="${BASH_REMATCH[1]}"
printf 'projects_sha256=%s\nattempts_sha256=%s\n' "$project_digest" "$attempt_digest"
```

Intermediate and final SQL postconditions are exact：all three projects keep the original-field digest, have `source_filename IS NULL`、non-null `created_at/last_opened_at`、`lifecycle_status='unlisted'`、`predecessor_project_id IS NULL` and `deleted_at IS NULL`；the three project-catalog columns、three lifecycle columns、four named constraints and `uq_projects_reprocessing_predecessor` exist once；`prevent_automatic_result_update_delete`、`prevent_reviewed_result_update_delete` and `prevent_symbol_escalation_attempt_events_update_delete` are enabled；all three `0015` target tables stay at zero rows；attempt digest/counts and `196 v1 + 198 v2 + 0 invalid` stay exact。Final Alembic table must contain exactly one row `0016`。

The disposable rehearsal and target execution must use the same committed read-only `backend/alembic`、`backend/alembic.ini` and `backend/app` mounts and the same three literal Alembic actions/verification boundaries。For each database, run and record only sanitized counts/hashes from this sequence：

```text
verify collided pre-shape, zero sessions and both digests
recheck exclusive window and zero other sessions
alembic -c alembic.ini stamp 0012
recheck zero other sessions; verify exactly one revision row = 0012 and no schema/data digest change
recheck exclusive window and zero other sessions
alembic -c alembic.ini upgrade 0015
recheck zero other sessions; verify exactly one revision row = 0015 plus every intermediate postcondition above
recheck exclusive window and zero other sessions
alembic -c alembic.ini stamp 0016
recheck zero other sessions; verify exactly one revision row = 0016 plus every final postcondition above; close with one final zero-other-session claim
```

After the temporary target final proof，close its last inspection session、stop and remove only the fixed temporary target container and isolated reconciliation network，then restart the original exact Compose PostgreSQL container by recorded ID without recreation。Require the same recorded image ID and sole volume、healthy Compose healthcheck、exact canonical `0016` and all final schema/count/digest invariants；the expected `pg_isready` probe is allowed only after the exclusive migration window has closed。Target `api/worker` remain stopped，Redis/frontend and every non-target ID/volume stay exact，and no readiness、issuance、Provider、run or Harness artifact may change。Failure before temporary-container removal keeps the original target PostgreSQL stopped and the private backup retained；failure after restart remains fail-closed and does not authorize downgrade、volume deletion、automatic restore or container recreation。

- [ ] **Step 2: Create private readiness document through operator boundary**

Operator confirms in Provider console：remediation complete、workspace/account binding、compatible-mode、exact model entitlement、`cn-beijing`、billing/quota at least`46.473344 CNY`。The helper reads Qwen key/workspace only in its private process and writes`account-readiness.json`；terminal output is limited tocontent SHA andboolean success。

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/provider_account_readiness.py issue \
  --root /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d \
  --cycle-id gdt10e-auth-remediated-live-20260802 \
  --region cn-beijing \
  --max-incremental-cny 46.473344 \
  --expires-in-seconds 1800 \
  --remediation-completed \
  --workspace-account-binding-verified \
  --compatible-mode-enabled \
  --model-entitlement-verified \
  --billing-and-quota-verified
```

Required environment keys are checked forpresence but never echoed；key/workspace values are forbidden in argv。

- [ ] **Step 3: Build safe committed runtime only**

Quiesce target writers and run the sole preparation command：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py prepare-zero-paid \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
  --safe-override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/safe.env \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/preparation.json
```

It recreates onlyfeature `api/worker` with safe mode/model。Four credentials、cycle keys andauthorization mount remainabsent。Feature PostgreSQL/Redis/frontend、volumes and allmain IDs remainexact；DB must stay at the reviewed successor exact head `0016` established by Step 1B。

- [ ] **Step 4: Prepare but do not apply private live override**

The same `prepare-zero-paid` command creates exact mode`0600` live/safe overrides，validates four credential key names、mode/model、future cycle ID/root、read-only mount andprivate bundle binding withoutprinting values。No authorization root/issuance exists；the live override remainsunapplied。

- [ ] **Step 5: Run zero-paid preflight**

Require:

```text
readiness all booleans true
readiness age <= 1800s
private credential binding match true
historical + incremental = overall = 50.000000
API/worker runtime closure N/N
mode/router/model exact
DB 0016
safe runtime credential/cycle/mount absence
policy/retry/wall/in-flight unchanged
Celery/Redis empty
GDT-10D bytes unchanged
run/project/upload/ledger/provider deltas all zero
```

Run the literal no-network entrypoint：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py zero-paid-preflight \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
  --safe-override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/safe.env \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --preparation-report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/preparation.json \
  --report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/zero-paid-readiness.json
```

It calls `preflight_full_p0_live(..., input_artifacts=current artifacts)` directly andatomically records safe no-delta evidence。Assert no issuance、consumption、run、project、upload、ledger或Provider fact。

- [ ] **Step 6: Independent zero-paid review**

Reviewer receives only safe IDs/hashes/counts/key names/readiness booleans and exact Decimal arithmetic。It must explicitly state：`GO` means local binding + operator attestation ready；Provider account validity remainsunproven until first real response。

For any `NO-GO` run exactly：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py abort-preconsume \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
  --safe-override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/safe.env \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --preparation-report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/preparation.json \
  --zero-paid-report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/zero-paid-readiness.json \
  --cleanup-intent /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json \
  --cleanup-receipt /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json \
  --cleanup-blocker /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-blocker.json \
  --review-deadline 2026-08-09T23:59:59+08:00
```

Require readiness/live/safe/auth root absent andsanitized cleanup receipt passed；cleanup blocker is a hard stop andmust be copied to parent truth without private values。

---

### Task 6: Issue, Consume And Execute The Sole Replacement Cycle

**Files/State:** generated only through reviewed lifecycle/Harness commands.

**Interfaces:**

- Consumes: Task 5 `GO`、fresh readiness document still within `1800s`、clean committed runtime。
- Produces: one new literal GDT-10E run with accepted pause or fully evidenced terminal。

- [ ] **Step 1: Issue one-use authorization after GO**

Issuance binds exact cycle ID、plan/readiness/predecessor/pricing/runtime/current-four/image hashes、successor DB exact head `0016`、historical`3.526656`、incremental`46.473344`、overall`50.000000` andshort expiry。Require no prior issuance/consume/run/project/resume/terminal for GDT-10E andpricing deadline not passed。

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py issue-gdt10e \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --zero-paid-report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/zero-paid-readiness.json \
  --cycle-id gdt10e-auth-remediated-live-20260802 \
  --plan-ref docs/superpowers/plans/2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md \
  --prior-cycle-evidence-sha256 db7c74f7fd0623c34a496309c744da3d32fd9614786fbde485e569968939749a \
  --historical-committed-cny 3.526656 \
  --max-total-cny 46.473344 \
  --overall-envelope-cny 50.000000 \
  --expires-in-seconds 1800
```

- [ ] **Step 2: Freeze live window and revalidate readiness**

Recheck clean HEAD、readinessnot expired、private binding、no concurrent writer/Harness、Celery/Redis empty、target/non-target IDs andunconsumed issuance：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py validate-unconsumed \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --zero-paid-report /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/zero-paid-readiness.json
```

Any failure uses the exact `abort-preconsume` command above；it must proveunconsumed cancellation andprivate deletion before stop。On pass start read-only identity monitor。

- [ ] **Step 3: Invoke exactly once**

```bash
QI_LIVE_CYCLE_AUTHORIZATION_REF=/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
QI_LIVE_CYCLE_OVERRIDE_REF=/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
make verify-p0-live
```

Do not invoke again for any exit。Lifecycle consumes/binds run beforecredential activation；final preflight revalidates readiness and issuance。Every Provider submission still requiresproject admission、ledger reservation andadapter permit。

- [ ] **Step 4: Seal the first validated authenticated response as runtime acceptance**

- Successful authenticated response that passes exact same-run request/response/call andsubmission-started validators：`_seal_runtime_account_acceptance()` writes the sole immutable fact，then live evidence projects`runtime_accepted` and continues within existing budgets。Do not persist or expose request-ID value。
- `provider_authentication_failed`：zero retry、project/cycle stop、cancel never-started admitted groups、close/deactivate and continue Task 8；do not rotate credential or resume/reissue。
- Other failure：apply existing classification/retry/terminal contract；onlyschema-invalid may receive onecoordinator-owned retry。

- [ ] **Step 5: Seal exact evidence and decide next state**

For every post-consume exit，includingauthentication/other failure，bind the shell variable only from the sole lifecycle authorization Owner：

```bash
GDT10E_RUN_ID="$(micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py bound-run-id \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization)"
export GDT10E_RUN_ID
case "$GDT10E_RUN_ID" in
  20??????T????????????Z-????????) ;;
  *) echo 'invalid bound GDT-10E run id' >&2; exit 2 ;;
esac
```

`bound-run-id` revalidates issuance/consumption/run binding andprints onlytheliteral ID；it never scans Harness directories。Collect authorization/readiness/pricing/ledger/routing/storage/monitor/quiescence/command evidence for that exact ID。Accepted pause + all parent Step 4 evidence -> Task 7。Any failure/incomplete/identity drift/budget terminal -> Task 8 using the same variable。Do not reinterpret operator attestation orbudget compliance asStep 4 success。

---

### Task 7: Complete Parent Step 5 On The Literal Paused Run

Conditional on Task 6 exact `visual_qa_pending:first-pdf-balloons` only.

- [ ] **Step 1: Capture run-bound API proof**

Prove authenticated calls、typed Case A/B、required non-GD&T results、exact automatic/working/reviewed linkage、readiness evidence hash andcycle budget evidence。

- [ ] **Step 2: Run headed Chrome QA**

On literal paused project provevisible Case A/B、structured A -> B edit、save/reload、freeze gate andno frontend raw-text parser。Do not steal another operator lock。

- [ ] **Step 3: Export from the same reviewed result**

Generate ballooned PDF and SIP Excel；verify manifest IDs/hashes andbasic content allbind the exact frozen `reviewed_result`。

- [ ] **Step 4: Resume the literal run once**

Do not renew or replace `account-readiness.json`。Keep its exact SHA/private binding through pause。Reuse the exported `GDT10E_RUN_ID` obtained only through Task 6 `bound-run-id`；automatic/manual directory selection and`latest` are forbidden。Recreate onlyfresh live/safe overrides from the same credential environment after validating original readiness SHA/binding、same-run runtime-acceptance fact andpause handoff：

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py prepare-resume \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
  --safe-override /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/safe.env \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --runtime-acceptance "/home/reggie/vscode_folder/Quality_Inspection/.worktrees/structured-geometric-tolerance-recognition/.agent/harness/runs/${GDT10E_RUN_ID:?}/reports/provider-account-runtime-acceptance.json" \
  --run-id "${GDT10E_RUN_ID:?}"
QI_LIVE_CYCLE_AUTHORIZATION_REF=/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
QI_LIVE_CYCLE_OVERRIDE_REF=/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/live.env \
make resume-gdt10e-live GDT10E_RUN_ID="${GDT10E_RUN_ID:?}"
```

The original attestation may be older than`1800s` at resume；it is used only for same-bundle continuity，not asfresh operator claim。`runtime_accepted` from the paused run is mandatory。Credential/readiness SHA change、missing fact orfailed binding stops beforeactivation anddoes not rewrite issuance。`execute-resume` exclusive-consumes one resume fact beforeactivation。Any exit consumes resume and forbids another。Receipt must revalidate readiness、runtime acceptance、authorization、pricing、historical/incremental/overall arithmetic、ledger、routing、same-reviewed-result export andall current-four results。

---

### Task 8: Cleanup, Independent Review And Parent Closeout

- [ ] **Step 1: Verify lifecycle cleanup**

Require Harness returned、Celery active/reserved/scheduled empty、Redis queue zero、four credentials/cycle keys/auth mount absent、safe mode/model/runtime closure/health/successor DB `0016` exact、non-target IDs unchanged、worktree `.env` absent。Repair only an allowlisted content-hashed cleanup blocker usingexisting network-none close bridge；never reactivate Provider forrepair。

- [ ] **Step 2: Dispose private state only after run-bound proof**

Accepted closeout：after healthy DB、safe runtime andrun-bound copies，run:

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py dispose-terminal \
  --authorization /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/authorization \
  --readiness /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/account-readiness.json \
  --run-id "${GDT10E_RUN_ID:?}" \
  --cleanup-intent /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json \
  --cleanup-receipt /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json \
  --cleanup-blocker /var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-blocker.json \
  --review-deadline 2026-08-09T23:59:59+08:00
```

Require exact GDT-10E private readiness/live/safe/auth state absent andcleanup receipt passed before reporting non-recoverability。Blocked cleanup retains exact mode/path SHA/hash/expiry withowner/review deadline；do not auto-delete or expose raw path。Never delete or rewrite GDT-10D evidence。

- [ ] **Step 3: Run fresh validation**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness -q
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py \
  --runtime-closure-source HEAD
micromamba run -n qi-p0 ruff check \
  .agent/harness/scripts/provider_account_readiness.py \
  .agent/harness/scripts/live_cycle_authorization.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/scripts/generate-receipt.py
git diff --check
git status --short --branch
```

Validate both immutable GDT-10D failure and new GDT-10E evidence with their correct `require_success` value。

- [ ] **Step 4: Independent final review**

Reviewer checks one issuance/consume/start、optional one literal same-run resume、operator-attested vs runtime-accepted truth、exact `3.526656 + 46.473344 = 50.000000` envelope、per-submission ledger、authentication zero retry、all admitted terminals、credential/private cleanup、GDT-10D immutability、same-reviewed-result evidence and`0015_drop_symbol_attempt_v1_default`/promotion block。Required verdict：`accept`。

- [ ] **Step 5: Update parent truth and commit exact evidence**

If GDT-10E reaches pause + Step 5 + final receipt，mark parent GDT-10 Step 4/5 complete。If it fails，record exact terminal andkeep parent incomplete。Stage only parent/companion docs、`.agent/bug-memory.md` when a new recurrence exists, andliteral Harness-generated GDT-10E files。

```bash
git diff --cached --check
git commit -m "feat(gdt): seal credential-ready replacement evidence"
```

Even onparent success，`0015_drop_symbol_attempt_v1_default` andproduction promotion remainseparately blocked。

## Spec Coverage Matrix

| Design requirement | Plan owner |
| --- | --- |
| Private operator attestation and credential binding | Task 2 |
| Operator-claim vs runtime-proof separation | Tasks 2, 5, 6 |
| Single runtime-acceptance fact writer and state transition | Task 3 |
| Versioned v3 evidence with sealed v2 compatibility | Task 3 |
| Historical cost carry-forward and exact remaining ceiling | Task 3 |
| Existing one-use authorization and ledger reuse | Tasks 3, 6 |
| No secret output/private evidence boundary | Tasks 2, 5, 8 |
| Zero-paid readiness with no Provider call | Task 5 |
| Authentication zero retry and cycle stop | Task 6 |
| Literal same-run headed QA/export/receipt | Task 7 |
| Cleanup, immutable predecessor and no promotion | Task 8 |
| Zero-paid and issued-unconsumed abort cleanup | Tasks 3, 5, 6 |

## Self-Review Record

- Spec coverage：Problem、Goals、Options、Owners、Private Contract、Zero-Paid Gate、Budget/Retry、Authorization、Evidence、Cleanup和Acceptance均映射到具体Task。
- Placeholder scan：`TODO|TBD|FIXME`只出现在Task 1 future scan command，不是未解决marker；无未命名file/interface/command。Runtime-generated run ID只能由`bound-run-id`从validated authorization binding导出，禁止operator手工填写、目录扫描或`latest`。
- Type/value consistency：cycle ID、model、region、`1800s`、`3.526656`、`46.473344`、`50.000000`在spec/plan中一致；public hard ceiling与tighter issuance ceiling职责分离。
- Old-path convergence：presence-only readiness被replace；GDT-10D resume target无consumer并retire；`run/3 + live-run-evidence/3`与exact legacy v2 definitions分离，sealed GDT-10D保持byte-compatible。
- Privacy：private salt/binding/credential/account fields不进入run/live/receipt/log/review；public evidence只有SHA、sanitized state/booleans和non-secret arithmetic。
- Truth transition：`run-p0.py::_seal_runtime_account_acceptance()`是唯一immutable fact writer；evidence policy只投影`not_yet_accepted -> runtime_accepted`。Original readiness SHA/binding跨pause保留，resume不renew、不改写issuance。
- Failure/cleanup boundary：zero-paid GO不宣称account valid；首个validated authenticated response才是runtime acceptance；authentication terminal不retry、不resume、不replacement。NO-GO、issued-unconsumed和sealed-terminal disposal都有literal CLI、exact target、cleanup receipt与blocker deadline。
- Pricing boundary：`2026-08-03` reviewed amendment恢复的issuance window晚于`2026-08-03T23:59:59+08:00`自动失效；只能通过新的read-only public pricing verification、reviewed plan amendment和user approval恢复，total envelope不自动改变。
- Independent docs review：前三轮`reject`逐项关闭runtime-acceptance Owner/call site、immutable resume、preconsume cleanup、literal CLI、v2/v3、pricing、path policy、cleanup journal和run-ID source；final verdict `accept`，无blocking或non-blocking finding。The later cleanup-proof amendment selected as option `A` pauses Task 2 until a separate independent read-only amendment review accepts the sole Task 3 intent Owner, exact schema and three-branch correlations.
- Execution boundary：用户已明确批准 Tasks 1-8 implementation/live boundary；所有既有 plan gates 仍为强制前置条件，且 direct Provider diagnostic、second replacement、budget expansion、`0015_drop_symbol_attempt_v1_default` 与 production promotion仍被阻断。

## Completion Contract

本 companion plan只有同时满足以下条件才可报告completed：

- reviewed implementation和zero-paid `GO`；
- exact one-use GDT-10E issuance/consume/start，incremental committed cost `<=46.473344`且overall envelope未超过`50.000000`；
- new literal run达到parent Step 4 accepted pause；
- headed Case A/B、structured edit、freeze、same-reviewed-result PDF/Excel和literal same-run resume/receipt全部通过；
- credentials/private controls清理、successor DB `0016`/safe runtime/non-target identities/GDT-10D historical `0014` immutability通过；
- independent final verdict `accept`。

如果新run再次authentication-failed或未达到pause，本 companion cycle可以作为fully evidenced fail-closed closeout完成，但父计划仍未完成，且不自动授权another replacement。
