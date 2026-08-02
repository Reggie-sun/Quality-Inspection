# GDT-10E Credential Readiness And Replacement Cycle Design

## Status

- Parent plan：`docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`。
- Predecessor：GDT-10D full run `20260802T101404291929Z-884bec62` 与 evidence commit `daa3e6f`，保持 immutable。
- 用户已明确批准 reviewed GDT-10E implementation、zero-paid activation 和 one paid cycle boundary；本 Task 只记录该批准并单独提交 docs，不执行 credential/runtime/Provider mutation。
- 本 design 不授权读取或输出 credential value、direct Provider diagnostic、second replacement、`0015` 或 production promotion。
- 后续窗口只可按 companion plan 的 implementation、zero-paid activation、one-use authorization 和 one paid cycle gates 执行。
- Initial independent review verdict was `reject` for four docs-level gaps：unowned `runtime_accepted` transition、expiry/immutable-resume conflict、pre-consume private-state cleanup gap andmissing literal CLI。First remediation added the single acceptance-fact writer、same-document resume rule、two-branch abort/disposal contract、versioned schemas、pricing freshness andexact commands。
- Second review closed expiry/resume、sealed attribution、v2/v3 andpricing freshness，but remained`reject` for path-policy conflicts、cleanup order/blocker persistence andmissing active acceptance call-site/cross-file contract。Second remediation separated three path classes、added root-sibling intent/receipt/blocker journaling withone deletion order、bound failed/success run ID through theauthorization Owner andplaced deterministic acceptance projection beforefreeze/pause。
- Third review verified cleanup、acceptance wiring andbound-run handling，but remained`reject` because`--root` itself was not categorized andone self-review sentence still namedmanual operator input asrun-ID source。Third remediation made the exact root a first-class allowlisted path withnegative tests andmade`bound-run-id` the sole run-ID source。
- Final independent read-only review verdict：`accept`，with no blocking or non-blocking finding。It revalidated all three path classes、cleanup interruption/recovery、deterministic runtime acceptance、success/failure run binding、v2/v3 compatibility、expiry/resume、sealed evidence、budget/pricing、privacy anddocs-only authority。
- **Cleanup proof amendment — 2026-08-02:** 用户选择 amendment option `A`。Review subsequently found that Task 2 had no canonical lifecycle-proof schema. Task 2 is paused while this amendment makes Task 3 the sole Owner of `provider-cycle-cleanup-intent/1`; implementation may resume only after an independent read-only amendment review returns `accept`. This amendment does not complete Task 2, parent GDT-10 Step 4, Step 5, or the parent objective, and preserves every block on credential/runtime mutation, Provider calls, paid execution, second replacement, budget expansion, `0015`, and production promotion。

## Execution Approval Record — 2026-08-02

- Selected lane: Heavy
- Selected companion: 2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md
- Historical cost: 3.526656 CNY
- Incremental ceiling: 46.473344 CNY
- Overall envelope: 50.000000 CNY
- Provider starts: one
- Resume: only one literal same-run resume after accepted pause
- Still blocked: direct Provider diagnostic, second replacement, 0015, production promotion

## Problem

GDT-10D 已经证明本地 control plane、usage ledger、one-use authorization、routing terminal 与 cleanup 可以在真实 paid failure 下 fail closed，但没有证明 Qwen account ready。唯一 paid invocation 的两个实际 submission 都产生：

- `failure_category=authentication`；
- event code `provider_authentication_failed`；
- 其余六个 admitted groups 为 `not_started_after_project_failure`；
- 没有 AutomaticResult、accepted pause、symbol report 或 full-run/formal receipt。

当前实现将 HTTP `401|403` 统一分类为 `authentication`。该 evidence 能证明 Provider 拒绝了认证/授权，不能进一步区分 API key 无效、key 与 workspace 不匹配、workspace/account 没有 model entitlement、region/compatible-mode 未启用、billing/quota 不可用或其他 account-side policy。旧 credential bytes 与 private authorization root 已删除，也没有可用于比较的旧 credential fingerprint；因此不能机械证明未来 credential 已轮换。

现有 zero-paid gate 只能证明：

- `QI_QWEN_API_KEY`、`QI_QWEN_WORKSPACE_ID` 非空；
- workspace ID 满足受限 host-label shape；
- `OpenAI(api_key=..., base_url=https://<workspace>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1)` 装配正确；
- model/mode、api/worker runtime closure、DB revision、credential key presence、authorization mount 与 cycle binding 正确；
- pricing、budget、retry 与 one-use lifecycle 未漂移。

Presence 和 local binding 不能证明 account validity。GDT-10D 已经反证“zero-paid presence PASS 等于 account ready”。

## Goals

- 在不输出 secret、不调用 Provider 的前提下，把 local credential binding 与 operator-provided account readiness 变成一个短时、私有、可审计的 zero-paid gate。
- 让 attestation 与实际将要注入的 Qwen API key、workspace、model、cycle 精确绑定，但不把 credential value、credential hash 或 account detail复制到 repository/Harness evidence。
- 把 GDT-10D 已消费的 `3.526656 CNY` 从原 `50.000000 CNY` 总包络扣除；GDT-10E 的 incremental ceiling 固定为 `46.473344 CNY`。
- 复用现有 one-use authorization、per-submission permit、cycle-wide ledger、schema-only single retry、terminal reconciliation 与 same-run pause/resume contract。
- 第一个通过same-run started/settled/request/response/call validators的successful authenticated Qwen response作为最终 runtime account acceptance；submission-started或operator claim本身不够。Authentication failure zero retry、立即 project/cycle stop、完整封存，不开启另一个 replacement。
- 只有 exact accepted pause 才执行 parent Step 5 headed UI/export 和 literal same-run resume。

## Non-Goals

- 不从 401/403 推断具体 account root cause，不自动修复 credential/account。
- 不保存旧 credential fingerprint，不声称能够证明 credential rotation。
- 不增加 direct Provider diagnostic、canary endpoint、model list、billing API 或第二条 network path。
- 不增加 `50.000000 CNY` 总包络；给 replacement cycle 重新分配完整 `50.000000 CNY` 会把最坏总支出扩大到 `53.526656 CNY`，必须另获明确批准。
- 不改变 Qwen endpoint、model、`timeout=60.0`、SDK `max_retries=0`、primary/actual/page/project/wall/in-flight limits。
- 不执行 `0015_drop_symbol_attempt_v1_default`，不做 production promotion、main runtime/DB mutation或 destructive restore。
- 不改变 GD&T schema、normalizer、review、frontend 或 export semantics。

## Read-Only Audit Findings

### Proven authentication failure

- Sealed routing aggregate：`199` total decisions；`198 = 190` plan-denied `+ 8` admitted；admitted `8 = 2` submission-started/authentication-failed `+ 6` cancelled；`198` terminal groups完整。
- Sealed usage ledger：`2` reservations、`2` submission-started、`2` settled-as-unknown、`0` reserved-only、`0` unsettled，累计 `3.526656 CNY`。
- Run state：`failed`，`pause_identity=null`，sample count `0`，无 symbol report、design QA 或 full-run receipt。
- Source contract：`provider_failure_category_for_http_status(401|403) -> authentication`；`QwenVisionProvider.review_symbols()` 将 SDK `APIStatusError` 转为 redacted `ProviderFailureFact`。

这足以证明 GDT-10D 的两个实际 Qwen submission 是 Provider authentication family failure，并且 failure 被正确持久化/传播；不证明具体 credential/account defect。

### Operator-only readiness

以下事实只能由 operator 在 Provider console/account boundary提供，或由一个真实 Provider request最终验证：

- 当前 API key 对 exact workspace 有效；
- workspace 属于预期 account/tenant，且允许 compatible-mode endpoint；
- `qwen3-vl-plus-2025-12-19` 在 `cn-beijing` 已开通并可由该 workspace调用；
- billing/account 状态 active，quota/credit 足以覆盖 `46.473344 CNY` incremental ceiling；
- GDT-10D 失败后已经完成 credential/account remediation。

Repository 不读取 account ID、balance、invoice、credential value、console page content或 raw Provider error detail。

## Options Considered

### A. Private operator attestation plus local binding plus first full-run acceptance

推荐。Operator 在 private state root创建短时 readiness attestation，声明 account/workspace/model/billing/remediation checks已在 Provider console完成。一个 local helper只在内存中读取将要使用的 Qwen key/workspace，计算带随机 salt 的 private bundle binding，并把 binding留在 mode `0600` private document中。Zero-paid gate验证 attestation、expiry、private binding与live override一致，只向 reviewer输出 booleans和document SHA。首个通过既有 request/response/call identity validator 的真实 Qwen response形成immutable run-bound acceptance fact；这才把public projection从`operator_attested`单向提升为`runtime_accepted`。

优点：不新增 Provider call，不输出 secret，与现有 one-use lifecycle兼容；明确区分 operator claim和runtime proof。缺点：account-side readiness在首次真实 call前仍是 operator attestation，不是 Provider-authenticated proof。

### B. Presence-only local gate

拒绝。它只重复 GDT-10D 已通过的 gate，无法排除相同 authentication failure。

### C. Direct diagnostic/canary before full run

拒绝。它需要额外 Provider call和独立 acceptance/cost/retry/evidence语义，违反当前授权，并可能形成绕过 full-run project admission/ledger 的第二 network path。

## Ownership And Old-Path Action

- `QwenVisionProvider`继续只拥有 SDK/status/metadata safe fact classification；不拥有 account readiness。
- 新增 `.agent/harness/scripts/provider_account_readiness.py` 只拥有 private operator attestation schema、expiry与 credential-bundle binding；它不是 Provider、budget或cycle Owner。Its `dispose` surface never creates、repairs、rewrites or infers lifecycle proof: it validates the exact Task 3 cleanup intent and removes only the exact `account-readiness.json`。
- `.agent/harness/scripts/live_cycle_authorization.py` Task 3继续是 issuance/consume/run/project/resume/terminal lifecycle Owner，并且是 `provider-cycle-cleanup-intent/1` 的 sole writer and semantic Owner。它创建、验证、replay、repair and retires intent/receipt/blocker，and owns the complete ordered cleanup journal。
- `.agent/harness/scripts/run-p0.py::_seal_runtime_account_acceptance()`是唯一 run-bound acceptance-fact writer；`.agent/harness/scripts/live_evidence_policy.py`只从该immutable fact投影`operator_attested -> runtime_accepted`，不自行判断account readiness。`QwenVisionProvider`和既有Provider evidence仍是response fact source。
- `ProviderUsageLedger`继续是 actual submission/cost Owner；其 ceiling改为读取已验证 issuance 的 `max_total_cny`，不得再在多个模块复制 literal `50.000000`。
- `.agent/harness/policy/provider-call-policy.yaml` 的 public hard ceiling仍是 `50`；GDT-10E issuance 的 `46.473344` 是更严格的 plan-bound ceiling。
- Old path action：`replace` “credential keys present => ready”作为充分条件；presence保留为必要条件，并增加 private operator attestation/binding。`replace` hard-coded per-cycle `50.000000` validator为 `0 < issuance max_total_cny <= policy hard ceiling`，GDT-10E exact值固定 `46.473344`。
- Preserve：Qwen endpoint/model、Provider status classification、schema-only retry Owner、full-run project admission、usage ledger durability、close bridge、same-run resume与所有 GDT semantics。

## Private Account Readiness Contract

Private state root延续 GDT-10D 的 owner/mode/symlink纪律，但使用新的、不可复用目录：

```text
/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d/
```

`account-readiness.json` schema为 `provider-account-readiness/1`，exact fields：

- `schema_version`；
- `cycle_id=gdt10e-auth-remediated-live-20260802`；
- `operator_id`，只使用现有 safe operator identifier；
- `issued_at`、`expires_at`，最大有效期 `1800s`；
- `source=provider_console`；
- `remediation_completed=true`；
- `workspace_account_binding_verified=true`；
- `compatible_mode_enabled=true`；
- `model_entitlement_verified=true`；
- `billing_and_quota_verified=true`；
- `region=cn-beijing`；
- `model=qwen3-vl-plus-2025-12-19`；
- `max_incremental_cny=46.473344`；
- `binding_salt` 与 `credential_bundle_binding_sha256`，只存在private document；
- `content_sha256`。

`credential_bundle_binding_sha256` 对 exact cycle ID、model、workspace和API key做 length-delimited、salted SHA-256。它只用于同一 private root内比较，不复制到 run、logs、review report或Git。由于旧 credential bytes/fingerprint不存在，该 binding不能证明rotation；`remediation_completed`明确是operator attestation。

所有 private path必须current uid/gid、directory `0700`、file `0600`、final component非symlink。CLI和errors只输出固定状态码、safe document SHA和booleans；禁止输出document内容、salt、binding或credential value。Tests必须把 marker secret注入fixture并断言 stdout/stderr/log/repr均不含marker。

`provider_account_readiness.py`提供且只提供以下CLI：`issue`、`validate --phase start|resume`和`dispose`。`issue`从process environment读取`QI_QWEN_API_KEY`、`QI_QWEN_WORKSPACE_ID`、`QI_QWEN_MODEL`和`QI_P0_OPERATOR_ID`，禁止在argv接收key/workspace；`validate --phase resume`保留`--runtime-acceptance`，只用于run-bound acceptance fact；`validate`只输出sanitized JSON。`dispose`改为要求`--cleanup-intent`，不得把`--runtime-acceptance`重载为lifecycle proof。It accepts only the exact sibling intent path, validates its exact schema/content hash/current owner/mode/non-symlink, exact cycle/readiness SHA, branch correlation, allowlisted `safe_path_sha256s` and fixed `expected_steps`, then deletes only the exact readiness file with stable parent/root descriptors, `openat`/`fstat`-equivalent identity checks, inode/device consistency, relative unlink and parent-directory `fsync`。任何bare mapping、caller-selected root/path、foreign intent、alias、symlink、owner/mode/hash mismatch或branch mismatch均停止且不删除。

Path policy分三类且不得交叉：`--root`本身只能等于exact non-symlink `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d`，mutable controls/reports只能是其named absolute children；runtime-acceptance只能位于当前worktree `.agent/harness/runs/`下的authorization-bound literal run目录内，exact child为`reports/provider-account-runtime-acceptance.json`，且run segment通过exact regex/no-symlink/root containment；cleanup intent/receipt/blocker只能是companion plan列出的三个exact root-sibling absolute paths。Plan ref是唯一safe repository-relative exception。Wrong-root、alias、resolved-outside、其它absolute/relative path、glob或symlink都fail closed并有focused tests。

`1800s` expiry只控制initial issuance/consume/start。Accepted pause之前必须已有同一run的immutable `provider-account-runtime-acceptance/1` fact。Resume不允许签发新attestation、不改写consumed issuance，也不把过期document重新解释为fresh operator claim；它必须重验original document SHA、same private bundle binding、runtime-acceptance fact、pause handoff和literal run。若original private document缺失、credential bundle变化或runtime acceptance不存在，resume fail closed且不激活。

## Cleanup Intent Contract

Task 3 creates the only lifecycle proof at exact path `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-intent.json` before any deletion. Its immutable schema is `provider-cycle-cleanup-intent/1` with exactly `schema_version`、`cycle_id=gdt10e-auth-remediated-live-20260802`、`branch=no_issuance|issued_unconsumed|terminal`、`account_readiness_sha256`、nullable `issuance_sha256`、nullable `cancellation_sha256`、nullable `terminal_sha256`、nullable `run_id`、`safe_path_sha256s`、`expected_steps`、`created_at`、`review_deadline=2026-08-09T23:59:59+08:00`、`owner_uid`、`owner_gid`、`mode=0600` and `content_sha256`; unexpected fields fail closed. `safe_path_sha256s` is an exact-key mapping for every cleanup-inspected or cleanup-deleted path, whose values are SHA-256 hashes of already allowlisted canonical absolute path strings, never raw paths. `expected_steps` is the fixed ordered cleanup step names frozen before deletion. The intent never contains raw paths, credential values, workspace/account IDs, salt, private bundle binding, request/response content or authorization bytes.

The branch correlation is exact. `no_issuance` proves the authorization root absent before intent creation and requires null `issuance_sha256`、`cancellation_sha256`、`terminal_sha256` and `run_id`, with consumption/run/project/resume/terminal/activation absent. `issued_unconsumed` validates exact `provider-cycle-issuance/1` and `provider-cycle-unconsumed-cancellation/1`, has non-null issuance/cancellation hashes, null terminal/run values, and the same consumption/run/project/resume/terminal/activation absence. `terminal` validates exact `provider-cycle-issuance/1`, run binding and `provider-cycle-terminal/1`, has non-null issuance/terminal hashes and literal `run_id`, null cancellation hash, and preserves lifecycle-owned exact cycle/run/run-SHA/status/quiescence validation. Any other nullability or cross-document combination fails before deletion.

Task 3 validates every path/owner/mode/symlink/hash and branch fact, then creates the intent with `O_CREAT|O_EXCL|O_NOFOLLOW`、`0600`、exact current uid/gid、canonical content hash、file `fsync` and parent-directory `fsync`. Task 2 is not a second lifecycle Owner: it validates only that immutable proof and deletes only `account-readiness.json`. Before a valid durable intent and complete validation, every failure leaves readiness untouched. After Task 2 crosses its destructive commit point, failures return only sanitized fixed `account_readiness_cleanup_incomplete`; a valid replay may report idempotent disposal only after validating the exact intent and branch facts. The durable intent remains Task 3's recovery Owner even if blocker creation is interrupted; Task 3 records completed steps in the blocker and replay resumes only missing steps.

## Runtime Acceptance State Contract

GDT-10E `run/3`和`live-run-evidence/3`使用同一versioned public object shape：

- `schema_version=provider-account-readiness-evidence/1`；
- `readiness_sha256`；
- `operator_state=operator_attested`；
- `runtime_state=not_yet_accepted|runtime_accepted`；
- `binding_match=true`；
- `runtime_acceptance_sha256` is `null` or an exact 64-lowercase-hex SHA-256 string。

`run.json`是immutable initial projection，始终保持`not_yet_accepted + null`。`run-p0.py::_seal_runtime_account_acceptance()`只在exact same run/project的Qwen submission-started + settlement facts、request/response/call evidence、model/readiness/cycle identity和successful authenticated SDK response全部通过既有validator后，以`O_CREAT|O_EXCL|O_NOFOLLOW`、`0600`、file+directory `fsync`创建`reports/provider-account-runtime-acceptance.json`。Fact schema固定为`provider-account-runtime-acceptance/1`，绑定cycle/run/project、readiness SHA、model、lowest qualifying ledger attempt index、submission-started SHA、settlement SHA、sanitized call-evidence SHA、settlement-derived accepted timestamp和content SHA；不包含request ID value、workspace、token usage、prompt/response或secret。Schema-invalid response只在既有safe response evidence足以证明Provider authenticated response时可形成fact；401/403、transport/timeout/metadata failure不得形成。

State transition只允许`not_yet_accepted -> runtime_accepted`一次；duplicate/conflicting writer、foreign run/project/readiness/model、missing started/settlement/call fact均fail closed。`accepted_at`从lowest qualifying immutable settlement的`settled_at`复制，使concurrent writers生成相同bytes；不得读取new wall clock。Exact call site位于`start_live_run()` symbol selector outcome通过并assign project ID之后、任何project URL/freeze/ledger refresh/pause之前。`live_evidence_policy.py`只有在fact完整重验后才把current live evidence填为`runtime_accepted + exact SHA`；`pause_live_run()`、resume与receipt要求immutable run-initial、fact和live-current三者一致。Authentication terminal必须保持`not_yet_accepted + null`；failed terminal只有在pre-failure fact已valid时才可投影runtime accepted。Focused tests覆盖active-path ordering、pause/resume/terminal cross-file consistency、valid first response、schema-invalid authenticated response、401/403、transport、duplicate/concurrent write、tamper和privacy。

## Zero-Paid Readiness Gate

任何 issuance、consume、run binding、upload或Provider work前，按此顺序全部通过：

1. clean committed HEAD；本 design/plan已reviewed且用户已明确批准 implementation/live boundary；
2. sealed GDT-10D run/evidence bytes与 `daa3e6f`一致，历史 `3.526656 CNY`固定；
3. private root/attestation owner、mode、schema、content hash、cycle/model/region、`1800s` expiry和全部operator booleans通过；
4. future live override exact Qwen key/workspace非空、workspace shape安全，并在内存中重新计算private bundle binding；只返回match boolean；
5. live override exact八键、read-only authorization mount、safe/live override separation和worktree `.env` absence通过；
6. API/worker committed full runtime closure、mode/router/model、feature Compose project/ports/health、DB exact `0014`通过；
7. pricing snapshot/hash、public policy hard ceiling `50`、issuance incremental ceiling `46.473344`、reservation math与remaining budget通过；
8. timeout/transport/auth/status/metadata retry为`0`；只有 `ProductionRetryCoordinator`可为schema-invalid授权一次second submission；
9. Celery/Redis/Harness writers为空，DB/storage/run inventories未变化；
10. `preflight_full_p0_live(..., input_artifacts=current artifacts)`不创建registration/run/project/upload/ledger，不调用Provider，不consume authorization；
11. independent reviewer只接收sanitized IDs/hashes/counts/key names/booleans，返回 `GO`。

任一失败都按下述`abort-preconsume`合同收口并停止；不得issue/consume cycle或调用Provider。Zero-paid `GO`只能证明local binding与operator attestation完整，不能声明Provider account已authenticated。

Zero-paid `NO-GO`必须调用lifecycle Owner的`abort-preconsume`，而不是人工删除。Task 3 first creates the canonical intent described above for exactly `no_issuance` or `issued_unconsumed`, then owns the one allowed order：prove safe runtime/no activation -> remove live/safe overrides -> remove preparation/zero-paid reports -> call Task 2 `dispose --cleanup-intent` to delete exact readiness -> remove authorization files/root -> remove the empty private root -> create receipt -> remove intent。Task 2 never deletes authorization files/root, the private root, intent, receipt, blocker, override or reports. Success O_EXCL/fsyncs `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-receipt.json` before intent removal；failure/interruption retains intent and Task 3 O_EXCL/fsyncs `/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-cleanup-blocker.json`。Receipt/blocker互斥，existing file只接受exact schema/hash replay。Blocker记录execution owner、uid/gid、mode、safe path SHA、expiry、completed-step booleans和review deadline `2026-08-09T23:59:59+08:00`，绝不记录raw path/secret；blocker必须在parent plan登记且禁止issue/consume/start。

## Budget And Retry Contract

- Historical GDT-10D committed cost：`3.526656 CNY`，immutable。
- Overall plan envelope：`50.000000 CNY`。
- GDT-10E exact incremental ceiling：`46.473344 CNY`。
- Pricing snapshot与reservation仍复用 `provider-pricing-gdt10d/1` 和 exact SHA；未发生费率刷新授权。
- Snapshot `retrieved_date=2026-08-02`只允许GDT-10E在`2026-08-02T23:59:59+08:00`之前issue。超过该时点必须在Provider work前fail closed并请求新的read-only public pricing verification、reviewed snapshot/plan amendment和用户明确批准；不得自动刷新、沿用stale费率或改变`50.000000 CNY`总包络。
- Ledger每次reserve读取 active issuance `max_total_cny`；`committed + reservation > 46.473344` 在network前产生现有 Provider budget terminal。
- Qwen unknown reservation仍 `1.763328 CNY`，OCR reservation仍 `0.500000 CNY`。
- Authentication、request-rejected、rate-limited、service、metadata、timeout、transport failure均不retry；schema-invalid only由 `ProductionRetryCoordinator`最多retry一次，第二submission单独reserve。
- 第一个 `provider_authentication_failed` 是project-blocking和cycle-stop；所有已admit未submit group写 `not_started_after_project_failure`，zero paid artifact。不得换key后resume同一cycle、不得issue第二cycle。

## One-Use Authorization And Paid Boundary

Exact cycle ID：`gdt10e-auth-remediated-live-20260802`。

Issuance新增并绑定：

- reviewed design/plan SHA；
- sealed GDT-10D terminal/evidence SHA与historical cost；
- private account-readiness document SHA；
- pricing SHA、runtime closure SHA、current-four SHA、backend image ID；
- feature Compose project、DB `0014`；
- `max_total_cny=46.473344` 与expiry。

Schema strategy是显式version bump而非optional fields：GDT-10E写`run/3`与`live-run-evidence/3`；existing `run/1|run/2`和`live-run-evidence/2` definitions保持原样。两个JSON Schema使用`schema_version` discriminated `oneOf`：v2只接受原`paid_cycle` exact keys，v3要求readiness evidence、`historical_committed_cny`、`max_total_cny`、`overall_envelope_cny`和runtime acceptance SHA/state。`additionalProperties:false`在每个版本继续生效。Policy validator对GDT-10E exact cycle只接受v3，对tracked GDT-10D仍只接受v2；tests必须逐字节重验sealed GDT-10D并证明v3缺字段、v2夹带v3字段、跨版本混合全部拒绝。

Issuance仍在 zero-paid `GO` 后创建且未consume。Paid start仍只能由一次 literal：

```bash
make verify-p0-live
```

Lifecycle先consume并bind一个全新literal run，再激活feature `api/worker`、重验private readiness binding和runtime identity，最后进入Harness。不得复用GDT-10D run/project/authorization/journal。第一个真实submission必须走project admission、reservation、adapter permit和submission-started chain；它不是direct canary。若issuance后、consume前任何freeze/readiness/preflight失败，必须走上述issued-but-unconsumed `abort-preconsume`，不得遗留或复用issuance。

若第一个或后续submission返回authentication：zero retry、封存failed run、reconcile all admitted groups、close authorization、safe deactivate、删除private controls并停止。若达到 `visual_qa_pending:first-pdf-balloons` 且所有parent Step 4 evidence通过，才进入headed Step 5并最多一次literal same-run resume。

## Evidence And Privacy Boundary

Public/run-bound evidence可以包含：

- readiness document SHA、issued/expiry timestamps、source enum、all-ready boolean、binding-match boolean；
- cycle/run/project/pricing/runtime/current-four hashes；
- exact budget/historical/remaining Decimal strings；
- sanitized Provider failure category/status family/request-ID state；
- ledger/routing/storage/quiescence/close-bridge aggregates。

禁止包含：

- credential value、salt、private bundle binding、workspace/account ID、balance/quota detail；
- console screenshot/body、billing document、raw Provider body/header/exception/URL；
- private path、authorization bytes、prompt/response或token detail。

Account readiness在首个真实success response前必须保持 `operator_attested + not_yet_accepted`；只有上述run-bound immutable acceptance fact才能投影 `runtime_accepted`。两者不得互相替代。Committed closeout record曾报告GDT-10D sanitized Provider request-ID state，但sealed run tree本身不含request-ID state字段；本design只把sealed routing/ledger/run bytes直接证明的counts、classification和terminal状态称为sealed facts。

## Cleanup, Rollback And Promotion Boundary

- Runtime/DB change仅在用户批准后按companion plan执行。Zero-paid activation只重建feature `api/worker`；main/non-target IDs和volumes保持不变。
- Any consumed-cycle exit继续由现有 close bridge、quiescence与safe-deactivation contract收口；private readiness/live/safe/auth state只在run-bound copies、healthy DB和safe runtime proof后删除。
- 本plan不需要新migration；DB保持`0014`。若future implementation改变authorization/evidence schema，仅是file/JSON schema change，不执行`0015`。
- Code rollback按GDT-10E implementation commits逆序revert；第一项验证是 existing GDT-10D sealed evidence仍可通过 `require_success=False` validation，随后运行 Harness/Provider focused tests。
- `0015_drop_symbol_attempt_v1_default` 与 production promotion继续separately blocked。

## Acceptance

Design/plan acceptance只要求：read-only audit完整、方案/预算/Owner/retry/stop/evidence边界无歧义、独立review `accept`。The cleanup-proof amendment additionally requires an independent read-only amendment review `accept` before paused Task 2 may resume。它不等于execution approval。

Parent objective completion仍要求新的literal run实际达到parent GDT-10 Step 4 accepted pause、完成Step 5 headed UI/export、same-run receipt、fresh independent review；authentication terminal仍只能报告parent plan incomplete。
