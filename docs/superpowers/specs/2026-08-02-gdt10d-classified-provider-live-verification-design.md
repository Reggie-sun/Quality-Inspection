# GDT-10D Classified Provider Live Verification Design

## Status

- 用户在 `2026-08-02` 先选择原 option `C`：继续完成整个 GDT plan，包括 isolated DB/runtime activation 与一个 reviewed、plan-bounded paid Provider live cycle。
- 独立 review 随后证明现有 `CNY 50` 只是静态 policy 值，不能机械证明实际 paid usage；用户再选择 option `A`：批准受限的 usage ledger、版本化官方费率、one-use authorization 与保守预算 gate。
- 本 design、companion plan、`PROV-005` contract amendment 与 parent-plan supersession 已完成独立只读 review，最终 verdict `accept`；它们必须单独 commit。实现必须 TDD、offline review；runtime activation还需 zero-paid reviewer `GO`。任何 gate失败都在 Provider work前停止。
- Parent plan：`docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`。
- Classification design：`docs/superpowers/specs/2026-08-02-provider-failure-classification-and-durable-evidence-design.md`。
- Sealed predecessor：GDT-10C run `20260801T153347947042Z-0fea7c81` 与 evidence commit `91e02b5`，保持 immutable。

## Problem

safe Provider classification、atomic v2 diagnostics 与 admitted-group cancellation terminals已离线实现，DB regression也已在 isolated PostgreSQL 17证明。但 live closure仍有四个独立缺口：

1. feature QA PostgreSQL revision仍是 `0013`，不能持久化 `0014` v2 diagnostic columns；
2. live Harness仍绑定 `0013 + 12 files`，没有覆盖完整 runtime Owner；
3. `make verify-p0-live` 没有跨进程 one-use authorization，Make prerequisite失败也没有 durable cycle-attempt fact；
4. policy中的 `CNY 50` 没有费率版本、OCR durable ledger或失败调用 reservation。Vision usage虽然存在，`ProviderCallRecord.estimated_cost`仍按旧设计合法为 `null`。因此不能把调用次数或 `estimated_cost=None`解释成成本证明。

## Goals

- 为 exact GDT-10D cycle建立一个先消费、不可重用、run-bound的 authorization。
- 使用固定的官方公开原价快照，为每个实际 OCR/Qwen submission先保守预留成本；已验证 usage可向下结算，缺失/异常 metadata或进程中断保留最坏预留。
- 将 OCR、Vision、retry、logical subject、page、crop-expansion和累计 CNY写入 redacted durable ledger；缓存命中与未提交 group不产生 paid entry。
- 在现有 feature Compose project `structured-geometric-tolerance-recognition-qa` 中先冻结 writers，再备份并 additive upgrade `0013 -> 0014`，只重建 feature `api/worker`。
- 把 live runtime identity升级为 exact `0014 + committed backend/app runtime closure`，通过 fresh zero-paid review后只消费一个 paid cycle；该 cycle只允许一次 start，并仅在同一 paused run成功时允许一次 literal resume。
- 若达到 exact pause，则完成 same-run headed Step 5/export/receipt；否则封存 exact terminal、清理 credentials并停止。

## Non-Goals

- 不执行或创建 `0015_drop_symbol_attempt_v1_default`，不做 production promotion、main runtime/DB mutation或 destructive restore。
- 不读取或复刻账户账单、免费额度、预付费包、折扣、税费或控制台私有价格；公开原价快照只用于保守 upper-bound evidence，不声称等同最终 invoice。
- 不增加 Provider budget、timeout/transport retry、model fallback、direct diagnostic call或 replacement cycle。
- 不把 pricing Owner放进 Provider SDK、frontend、business semantic model或 `AutomaticResult`；`AutomaticResult`缺失时 ledger仍必须可审计。
- 不改变 GD&T schema、normalizer、ReviewService、frontend parser或 export semantics。

## Stable Contract Amendment

`docs/contracts/MAIN_CONTRACT_MATRIX.md` 的 `PROV-005` 继续拥有 Provider-call policy。受批准的 amendment只增加以下稳定语义：

- paid verification cycle必须绑定 one-use authorization与版本化公开 list-price snapshot；
- 每次真实 network submission在调用前先占用保守 reservation；cache hit、provider factory failure和 admitted-but-never-submitted group不收费；
- success或带完整安全 usage的 schema failure可按同一 snapshot结算；missing/invalid usage、transport/status/metadata failure与进程中断保留 reservation；
- ledger累计值不得超过 policy ceiling，不能 reserve时禁止调用并形成 budget terminal；
- account-specific invoice reconciliation、discount/free-tier与原始 prompt/response/token detail仍不属于 P0。

这不是 production promotion。它只允许 feature branch与未来采用同一 contract的 runtime实现可审计 cost gating。

## Frozen Pricing Snapshot

Snapshot identity：`provider-pricing-gdt10d/1`，currency `CNY`，retrieved date `2026-08-02`。Snapshot作为 `backend/app/providers/provider_pricing_gdt10d_v1.json`进入 code/runtime identity；Harness policy只引用其 version与SHA256，不复制费率成为第二 Owner。

### Tencent OCR

- API operation：`GeneralAccurateOCR` / 通用文字识别（高精度版）。
- Conservative public list price：`0.500000 CNY/submission`，采用月调用量 `< 10,000` 的最高公开后付费 tier。
- 免费额度、resource package和更低 volume tiers不用于降低 reservation。
- Official sources：
  - `https://cloud.tencent.com/document/product/866/17619`
  - `https://cloud.tencent.com/document/product/866/34937`

### Qwen Vision

- Exact model/region：`qwen3-vl-plus-2025-12-19`，华北2（北京）。
- Official public list price per million tokens：

| Prompt-token tier | Input CNY / 1M | Output CNY / 1M |
| --- | ---: | ---: |
| `<= 32,768` | `1` | `10` |
| `32,768 < input <= 131,072` | `1.5` | `15` |
| `131,072 < input <= 260,096` | `3` | `30` |

- Official maximums used for reservation：input `260,096`、output `32,768`。
- One unknown-usage submission reservation：`1.763328 CNY` = `260096 * 3 / 1,000,000 + 32768 * 30 / 1,000,000`。
- Official source：`https://help.aliyun.com/zh/model-studio/qwen3-vl-plus`。

所有计算使用 `Decimal`。每个 entry向上量化到 `0.000001 CNY`，再求和；float不得成为 budget Owner。Prompt/completion counters不完整、超限或不能匹配 exact tier时不得向下结算。

## Provider Policy Version

`provider-call-policy.yaml` 升级为 `provider-call-policy/2`。为消除旧 `max_retries_per_call: 2` 的歧义，live policy使用两个exact fields：`max_coordinator_retries_per_logical_call: 1` 与 `max_submissions_per_logical_call: 2`。Timeout/transport/auth/status/metadata failure均为zero retry；只有 `ProductionRetryCoordinator` 可在schema-invalid时授权一次第二submission，且该submission单独reserve并计入actual/page/wall/cost budgets。旧key在v2中禁止出现。

## One-Use Cycle Authorization

Exact authorization ID：`gdt10d-classified-live-20260802`。

### Durable state

Authorization与DB backup共用一个 private non-repo state root；authorization control和backup分目录，runtime只获得authorization control的read-only bind mount：

```text
/var/tmp/quality-inspection-gdt10d-20260802-<worktree-path-sha256-prefix>/
```

- directory必须由当前 uid exclusive create，mode `0700`，不是 symlink；文件mode `0600`；
- issuance绑定 clean committed HEAD、plan SHA256、pricing snapshot SHA256、exact Compose project、current-four manifest identity、expected DB revision `0014`、`CNY 50`与到期时间；
- consume使用 `O_CREAT|O_EXCL|O_NOFOLLOW` 创建单一 consumption document并 `fsync` file/directory，并绑定非敏感、随机256-bit `invocation_id`。重复或并发 consume均 fail closed；只有fact中的 `invocation_id` 与本invocation一致时，durable-create返回前发生signal/exception的进程才可接管close/deactivate，loser只能清理本次fresh controls，不能接管winner生命周期；
- token在 `make verify-p0-live` recipe的第一条命令消费，早于 `check-contracts`。因此后续静态检查失败仍消耗 cycle，不允许重发；
- consume之后才允许用private override把四个credential、cycle ID和read-only authorization mount注入feature `api/worker`；zero-paid runtime不含这四个credential、cycle ID或authorization mount；
- `_open_live_run()`必须通过authorization Owner exclusive-create一个literal run binding；重复start或不同run ID fail closed。Harness将project create/upload和process拆开：project ID先写入run evidence，再由host authorization Owner exclusive-create `{run_id, order, project_id, source_sha256}` admission并 `fsync`，之后才允许触发processing；
- 每次ledger reservation必须重新验证consumption、literal run binding、project admission、expiry、未关闭terminal和read-only mount identity。任一缺失、错配或已terminal都fail closed；Provider adapter在exact cycle mode必须在literal SDK network seam前原子consume matching opaque reservation permit并再次验证active/nonterminal admission，防止绕过caller ledger或复用permit；
- accepted pause后，`execute-resume` 必须在任何credential/runtime activation之前用 `O_CREAT|O_EXCL|O_NOFOLLOW` 创建并fsync唯一 `resume-consumed` fact，绑定authorization identity、literal run ID、accepted-pause evidence hash、非敏感随机 `invocation_id` 与safe timestamp。重复、并发、不同run/evidence或terminal后的resume全部fail closed；只有exact invocation owner在durable-create边界被中断后可继续close/deactivate，foreign loser执行zero activation/network/close/deactivate并只清理本次fresh controls；fact创建后的任何contracts/preflight/run/cleanup failure都消费这次resume，禁止再次resume；
- pause不关闭authorization，因为same-run resume还要处理current-four其余projects。Success/failure/abort cleanup先证明Harness process已返回、Celery active/reserved/scheduled与queue均空，必要时先stop worker；然后在同一cycle ledger lock下exclusive-create terminal marker并 `fsync`，之后任何reservation/permit都拒绝。不得在可能仍有network call的情况下竞态close；
- zero-paid preflight只验证issuance仍unconsumed及private override未应用；post-consume final preflight才验证issuance/consumption、owner/mode/expiry/current HEAD、live runtime cycle/auth-mount identity。`_open_live_run()`把安全authorization evidence复制到run并写hash；
- 外部 state保留到 final closeout。accepted closeout且run内副本/receipt验证后才删除；blocked则保留并报告path/hash/expiry，不自动删除。

`cycle-close-bridge` 是terminal close的唯一bridge。Host `live_cycle_authorization.py close` 只能启动一次性、`--network none --rm`、无credential的exact committed backend image；zero-paid issuance必须durably绑定该exact `sha256:<64hex>` image ID，start validation与每次bridge launch都逐字节重验当前Compose API image等于issuance，不能只验证格式。Bridge同时mount feature storage named volume `/data:rw` 与private authorization control `/auth:rw`；普通API/worker继续只有 `/auth:ro`，且container probe必须从 `/proc/self/mountinfo` 证明actual mount option包含 `ro`。Bridge先取得 `/data/provider-usage-cycles/<cycle-id>/ledger.lock` 的 `flock`、重建journal并确认host提供的quiescence evidence identity，然后在 `/auth` 用 `O_CREAT|O_EXCL|O_NOFOLLOW`、mode `0600` 打开terminal，写完后先 `fchown`/`fchmod(0600)`，再最终 `fsync(fd)`、close并 `fsync(parent directory)`。Active authorization validator看到任何cleanup blocker仍fail closed；admitted-project与pre-first-project两条close-only路径都必须精确读取并重验issuance/consumption/run/root与allowlisted、content-hashed `provider-cycle-cleanup-blocker/1`，使Task 10能repair/replay terminal，任何schema/identity/failure-code偏差均拒绝。若terminal已存在，bridge仍需持ledger lock并重建journal，只在existing document通过完整schema且cycle/run/status/quiescence hash/content hash逐字节等价时返回verified replay；任何差异fail closed，绝不覆盖或修补existing bytes。Image ID、volume name、mount modes、network-none、uid/gid与terminal hash进入sanitized evidence；receipt policy重新比对bridge image与run-bound issuance image。禁止其它host/runtime path写terminal。Offline tests用两个OS processes制造reserve-vs-close与concurrent-close竞争，并覆盖first close、exact replay、conflicting replay、admitted/no-project cleanup-blocker repair；contract test锁定bridge exact mounts/network/credential absence。

`make verify-p0-live` 是cycle唯一start入口；禁止直接调用 `run-p0.py live` 绕过consumption。只有该start返回accepted pause时，literal same-run resume才是同一已消费cycle的允许后继；它不得创建第二个run、第二次consume或replacement cycle。

## Provider Usage Ledger

### Open-source precedents

只融合三类已验证语义，不新增第三方依赖或复制实现：`python-atomicwrites` 的file与parent-directory `fsync`；`filelock` Unix backend的stable lock inode、锁前不 `O_TRUNC`、`O_NOFOLLOW` 与跨进程竞争测试；CPython `_write_atomic()` 的exclusive-create/cleanup边界。`python-atomicwrites` 已归档且以replace为中心，CPython helper也明确只是best-effort；两者都不适合作为append-only ledger Owner。`filelock` 的近期symlink/TOCTOU修复进一步要求本设计把private `0700` directory、final-component `O_NOFOLLOW` 和lock inode生命周期写成合同，而不是依赖库默认值。

### Owner and wiring

新增 `ProviderUsageLedger` 是 paid-cycle cost与submission计数的唯一 Owner。它是cycle-scoped而不是project-scoped：每次 `processing.tasks.inventory_project()` 都从同一cycle journal恢复一个handle，并注入 `RuntimeRecognition`与`CandidateAdvisor`；所有current-four project共享一个committed total，project ID只是entry字段。其它模式/未授权runtime不创建ledger，历史 `estimated_cost=None` 保持兼容。

Ledger路径：

```text
asset://provider-usage-cycles/gdt10d-classified-live-20260802/
```

目录是append-only journal，而不是可覆盖的单一JSON。Linux shared-volume上的dedicated `ledger.lock` 使用 `fcntl.flock(LOCK_EX)` 提供API/worker多进程互斥；它必须在private `0700` directory中以 `O_RDWR|O_CREAT|O_NOFOLLOW` 打开，取得锁前禁止 `O_TRUNC`，并作为stable inode永久保留，任何路径都不得unlink、replace或recreate它。打开后必须用 `fstat` 验证regular file、expected runtime uid/gid与 `0600`。同一进程内所有指向同一canonical cycle journal的ledger handles共享一个module-registry `threading.RLock`；registry-map mutex只用于lookup/create该lock并在获取cycle lock前释放。所有同时需要两层锁的open/reopen/reserve/adapter-consume/settle/snapshot路径必须严格按 `cycle process lock -> OS flock` 获取、反序释放，禁止任何 `OS flock -> process lock/registry-map mutex` 路径；close bridge运行在独立one-off process且只获取OS flock。Process lock不是cost/concurrency evidence Owner，durable journal仍是唯一Owner。每个attempt有最多三个immutable facts：caller在上述统一锁序内扫描/验证journal、检查cycle ceiling并用 `O_CREAT|O_EXCL|O_NOFOLLOW` 创建 `NNNNNN-reserved.json`；exact-cycle Provider adapter收到opaque reservation permit后，在literal SDK seam前持同一锁序重新验证authorization与permit并exclusive-create `NNNNNN-submission-started.json`；response/known failure后exclusive-create `NNNNNN-settled.json`。同一permit的第二次adapter consumption因process registry与started fact而在network前fail closed。创建journal/lock directories时逐级验证non-symlink并 `fsync` parent；每个entry写完 `fsync` file和journal directory。不得调用 `LocalFileStorage.write_verified()` 的 replace语义，也不得重写/删除任何fact。Optional `summary.json`只可由journal重建，不是cost Owner。

`ReservationPermit` 还是process-local capability，而不是journal identity的可重建view。其constructor与capability sentinel是 `usage_ledger.py` module-private；对象禁止copy/deepcopy/pickle/JSON，capability值不写入journal、evidence或日志。只有当前 `ProviderUsageLedger.reserve()` 可创建permit并在仍持有cycle process lock、durable reservation已fsync后，把exact object identity登记在该ledger instance的未消费registry中；reserve全程遵守process→OS顺序，不会在持有OS flock时重新获取process lock。Adapter consumption必须在同一cycle process-lock临界区内同时验证exact ledger instance、exact object identity、registry membership、provider/operation binding，再取得OS ledger lock并重验durable authorization。开始consume后即从registry退休；只有同一临界区成功exclusive-create/fsync submission-started后才允许network，任何写入/校验失败都留下reserved-only且禁止重试该permit。Journal reopen只恢复cost/count state，绝不恢复active permit；依据reserved fact伪造或重建的对象在第一次合法consume之前也必须产生zero submission-started、zero network。

每次constructor/reopen都必须在持锁状态下从journal重建state；reserved-only、submission-started但unsettled都继续按full amount计费。Reserved-only明确表示SDK seam尚未开始；submission-started表示permit已durable consumed并进入SDK seam，但没有response时只能报告network acceptance `unknown`，不能声称Provider已接收。Partial、duplicate、gap、sequence回退、submission-without-reservation、settlement-without-submission、重复fact、unexpected file或symlink全部fail closed。测试必须覆盖new instance reopen、reserve后crash、submission-started后crash、两个OS process并发reserve和parent-directory durability；不能只测同进程two-thread。

Journal只包含 allowlisted literals/IDs/counters/Decimal strings/snapshot hashes；不包含 source/crop/prompt/response、raw exception/body/header/URL/path、credentials或其hash，也不包含process-local capability token/object identity。

### Reservation and settlement

每个 network submission遵循同一顺序：

```text
validate logical/page/crop budget
→ acquire ledger lock
→ revalidate consumed/run-bound/project-admitted/nonterminal authorization
→ reserve conservative CNY and exclusive-create+fsync journal entry/directory
→ release lock
→ pass the matching opaque reservation permit to Provider adapter
→ adapter atomically revalidates and durable-writes submission-started at the SDK seam
→ call Provider exactly once
→ settle to verified actual cost or retain reservation
→ exclusive-create+fsync settlement entry/directory
→ persist existing call/routing evidence
```

- OCR：每个 eligible local crop在 `recognize_png()`前reserve `0.500000`；成功后仍settle `0.500000`。
- Vision：每个真实 `review_symbols()` / legacy text `review_candidate()` submission前reserve `1.763328`。只有 `prompt_tokens + completion_tokens`安全、完整且限内时才按tier向下settle。
- schema retry是第二个actual entry和第二次reservation；timeout/transport不retry；cache hit不reserve。
- Provider factory failure发生在submission前，不reserve。
- 任一classified/boundary failure若 `provider_work_started=True` 且没有完整usage，entry保持 `reserved_unknown`，并按reservation计入 `committed_total_cny`。
- 如果进程在reservation/submission-started之间停止，reserved-only entry按full amount计入但不算submission；如果在submission-started/settlement之间停止，submission acceptance是unknown且同样按full amount计入。因此不会低估，也不会夸大actual-submission evidence。
- reservation会同时检查cycle-wide `committed_total_cny + requested_reservation <= 50.000000`。失败时不调用Provider；拒绝group复用existing attempt `not_started_budget_exhausted`、observation `routing_budget_exhausted`、group `budget_exhausted`，queued admitted siblings复用 `cancelled_after_project_budget` / group `cancelled`。内部typed `ProviderBudgetExceeded`停止project scheduler，但不得新增 `provider_cost_budget_exhausted` routing vocabulary。

### Ledger fields

每个 reservation至少包含：cycle ID、run ID、project ID、project order、monotonic cycle attempt index、provider/operation/model、page index、logical subject kind与safe ID、retry index、crop expansion count `0|1`、reservation/charged CNY、pricing hash。Submission-started fact只增加adapter-consumed状态、matching adapter/operation identity和safe timestamp；settlement增加usage state、允许的prompt/completion counters与safe request-ID state。Aggregate分别列出reserved-only、submission-started unknown、settled、committed total与remaining CNY，并包含all-project OCR/Vision counts keyed by `(project_id, page_index)`、Vision counts keyed by `(project_id, logical subject)`和crop expansions；per-page/per-subject limits不得把不同project错误合并。

Authorized cycle中凡已产生 `ProviderCallRecord`，其 `estimated_cost` 必须按 `Decimal(str(value))` 等于对应ledger settled/committed value；ledger仍是exact cost Owner。历史记录、cache reuse和非cycle runtime仍允许 `null`。

## Runtime Identity

Harness DB revision必须exact `0014`。不再维护人为的25-file subset。新增committed `gdt10d-runtime-closure.txt`，其内容必须机械等于clean HEAD中全部tracked `backend/app/**/*.py` 与 `backend/app/**/*.json` relative paths；`check-contracts.py`验证manifest没有missing/extra/duplicate/unsafe path，且pricing snapshot、storage durability、routing/planner/cache、Provider adapters和processing owners都被该full runtime source closure覆盖。API和worker必须分别证明manifest中每个file与clean committed HEAD逐字节SHA256一致、没有manifest外的tracked runtime source drift，并匹配mode/router/model/cycle/authorization-mount identity。Zero-paid report使用computed `N/N`，不得hard-code `25/25`。

Migration source不在 runtime image内，其 identity由 clean committed HEAD、host `0014` migration SHA256和applied exact DB revision共同证明。

## Database Activation

### Quiescence before backup

Backup前先记录 target/non-target container IDs，并机械证明：

- Celery `active`、`reserved`、`scheduled` 对feature worker均为空；
- feature Redis processing queue长度为 `0`；
- 没有 Harness live process或另一个 writer拥有target services；
- 然后只停止 feature `api/worker`，再次证明它们不再运行且PostgreSQL/Redis/frontend/main IDs不变。

任何非空或不可判定状态都停止，不backup、不migration。

### Private backup and migration

在private state directory中以 `umask 077`、Bash `noclobber`对FD 3执行exclusive `O_CREAT|O_EXCL`创建 `pre0014.dump`，再把pg_dump stdout直接写入已打开FD；禁止普通 `> existing_path`：

```bash
set -o noclobber
exec 3>"$backup_path"
docker compose -p structured-geometric-tolerance-recognition-qa \
  -f compose.yaml -f compose.qa-dev.yaml exec -T postgres \
  pg_dump --username=qi --dbname=qi --format=custom --file=- >&3
exec 3>&-
docker compose -p structured-geometric-tolerance-recognition-qa \
  -f compose.yaml -f compose.qa-dev.yaml exec -T postgres \
  pg_restore --list < "$backup_path" >/dev/null
```

关闭FD后必须以non-symlink path重新open并 `fsync` dump file与parent directory，再记录owner/mode/size/SHA256而不读取内容。迁移使用committed worktree的read-only `backend/alembic`与`alembic.ini` mounts，通过feature network执行 exact `alembic upgrade 0014`。迁移前即时比较working tree migration SHA与committed HEAD blob SHA；不一致则停止。

Migration后require exact revision/columns/check、旧row counts不变、inherited attempts全部v1 + SQL NULL diagnostic/hash、GDT-10C evidence/hash不变、无新run/result/provider artifact。失败不自动restore；backup保留等待新的destructive authority。

## Credential and Service Activation

禁止worktree `.env` regular file或symlink。Root credential source只加载到当前host shell，不打印values；结束时明确unset四个host变量与Harness controls。

Zero-paid阶段只以safe override启动feature `api/worker`，保持四个credential、cycle ID和authorization mount全部absent。Authorization consume成功后，`make verify-p0-live` 内的activation helper才用private live override给feature `api/worker`增加：

- exact four credential keys from `LIVE_CREDENTIAL_KEYS`；
- `QI_SYMBOL_RECOGNITION_MODE=production_uncertainty`；
- `QI_QWEN_MODEL=qwen3-vl-plus-2025-12-19`；
- `QI_PROVIDER_CYCLE_AUTHORIZATION_ID=gdt10d-classified-live-20260802`。
- `QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT=/run/qi-live-authorization`，并把exact private authorization control directory bind-mount为read-only。

`docker compose config --format json` 只打印target service resolved key sets和sanitized mount target/mode。live target key set必须等于baseline加上述exact eight keys；明确禁止DB/Redis override、host Harness controls、operator ID与任何额外credential/control key。只允许recreate feature `api/worker`；PostgreSQL/Redis/frontend/volumes/main IDs保持不变。若post-consume activation、contracts或preflight失败，cycle仍consumed，立即进入cleanup且不得rerun。

Start/resume都由单一Python lifecycle orchestrator拥有，不依赖Make shell链或后续人工cleanup。`execute-start` 在cycle consume前安装 `SIGINT`/`SIGTERM` handler并进入 `try/finally`，生成一个literal run ID和本invocation identity，随后依次exclusive consume、bind exact run，只有两者都durable后才允许activation；Harness必须adopt显式 `--authorized-run-id`，不得再生成run identity。`execute-resume` 在exclusive consume `resume-consumed` fact前安装同等handler，只接受literal paused run，并在fact fsync后才允许重新激活。Pre-consume validation rejection执行zero mutation/activation；foreign loser只能执行controls cleanup，不能close/deactivate；本invocation的fact一经创建则不可重用，之后任意exit都必须close并deactivate，包括signal发生在fact fsync与函数返回之间。Activation必须以sanitized facts证明API/worker exact credential/cycle key presence、actual read-only auth mount、mode/model；deactivation必须证明four credentials、cycle keys和auth mount全部absent且safe mode/model exact。Activation、contracts、preflight、run failure或signal时，orchestrator先检查Harness/Celery/Redis；API inspection不可用或worker不空时stop only feature worker并复核worker absent/queue zero，再通过唯一close bridge写failed/aborted terminal，最后用idempotent `deactivate-runtime`移除四credentials/cycle/auth mount。每次exit随后立即fsync-delete exact private live/safe overrides，并从orchestrator process环境移除four credentials、cycle keys与Harness controls；调用者shell的root credential source仍由同一bounded execution shell的trap负责unset，child process不得声称能修改parent environment。Accepted pause不close cycle，但只有deactivation和private-control cleanup都成功后，才可exclusive-create/fsync绑定run、pause evidence、safe proof与controls-removed proof的 `provider-cycle-pause-handoff/1`；`execute-resume`缺少handoff、存在cleanup blocker或pause hash不一致时必须在activation前fail closed。Task 9 resume前需从approved root credential source重新生成fresh live/safe overrides；resume exit再次立即删除。Cleanup helper failure必须保留nonzero exit并写只含allowlisted failure codes的content-hashed `provider-cycle-cleanup-blocker/1`，不能记录raw exception或被primary status吞掉；即使blocker写入自身失败，缺少positive handoff也禁止resume。Real child-process tests必须在activation/run/quiescence phases发送both `SIGINT`/`SIGTERM`，并覆盖resume signal、durable-create boundary ownership及两个完整 `execute-resume` contenders只选出一个lifecycle owner。

Cleanup override只保留baseline + mode/model identity；cycle ID、authorization mount与四credentials必须同时absent。live/safe override删除状态、host variable unset状态和不存在的worktree `.env`都需验证。Tests必须覆盖partial activation、post-activation contracts failure、preflight failure、run failure、INT/TERM与accepted-pause handoff后的absence；不能依赖后续人工Task 10消除暴露窗口。

## Zero-Paid Gate

paid work前必须全部满足：

- clean committed HEAD；design/plan/contract与implementation reviews accepted；
- authorization issued但尚未consumed；state dir/backup ownership/mode/hash正确；issuance中的backend image ID等于zero-paid-proved exact committed API image；
- exact target/ports/health、API/worker committed runtime closure `N/N` hashes、safe mode/router/model、DB `0014`；
- host-side credential booleans true、private live override exact key/mount allowlist、safe runtime中four credentials/cycle/auth mount absent；
- pricing snapshot version/hash/rates/Decimal reservation exact；policy ceiling仍 `50`；
- runtime call/retry/wall/in-flight constants未扩大；
- GDT-10C sealed hash与DB baseline unchanged；
- DB provider rows、storage ledger inventory与Harness run inventory在gate前后不变；
- manual `preflight_full_p0_live(..., input_artifacts=current artifacts)`完成，不registration、不run creation、不upload、不ledger、不Provider call、不consume authorization、不deploy credentials；
- independent reviewer基于sanitized facts返回 `GO`。

## Paid Execution and Terminal Evidence

唯一授权命令：

```bash
make verify-p0-live
```

recipe第一步安装finalizer并consume authorization，第二步只重建feature `api/worker`以激活credential/cycle/read-only auth mount，再运行contracts与Harness final preflight。任一失败都消费cycle并由同一进程的finalizer同步cleanup；禁止补跑。Accepted pause也先deactivate再交给Task 9。Runtime中每次reserve继续校验run/project admission，所以consume和project authorization之间的窗口不能调用Provider。

Orchestrator先pre-bind唯一literal run，Harness只能adopt该identity，再将project create/upload与processing拆成两个受控阶段。Project DB row创建后立即把run-bound project ID/source identity以 `admission_sha256: null` 写入Harness evidence；write使用exclusive temporary file，先 `fsync(file)`，`os.replace` 后再 `fsync(parent directory)`，随后host才可用 `O_CREAT|O_EXCL|O_NOFOLLOW` durable创建admission fact。Harness再回填其hash，只有两阶段都可重验后才触发processing。Failed evidence可保留pending project，formal success禁止pending；不能等待 `AutomaticResult` 才记录identity。不论success/failure，都收集并seal：authorization、pricing snapshot、cycle-wide usage ledger、routing decision/attempt/outcome aggregate、storage artifact inventory、container monitor与command exit。

### Exact current-input continuity

Sealed GDT-10C对current-four sample order `1` 的exact source有两个独立不变量：`total routing decisions = 199`；其中 `escalated groups = 198 = 190 plan-denied + 8 admitted`。不得把199作为190+8的分母，也不得把sample 1 counts套到其余三个project。新run的sample 1若routing input/implementation未变，应同时保持total-decision与escalated/admission identity；任何count drift阻止Step 4 success，但仍必须完成下述per-project generic terminal reconciliation与cycle aggregate。

### Generic reconciliation

```text
admitted_groups = submission_started_groups + never_submission_started_groups
submission_started_groups ∩ never_submission_started_groups = ∅
each admitted group has exactly one terminal outcome
ledger_submission_started_groups = submission_started_groups
ledger_reservation_groups = submission_started_groups + reserved_only_groups
```

- `submission_started`只证明one-shot permit已durable consumed并进入SDK seam；没有response/request ID时Provider network acceptance必须标记unknown，不能声称exact receipt。其fact count必须与scheduler started attempts一致；成功或response-bearing attempt还需existing crop/request/response/call evidence。
- reserved-only group表示预算已保守占用但SDK seam未开始；不得计入submission count，必须单独报告并阻止Step 4 success。它仍需要相应terminal；如果worker hard crash导致DB terminal缺失，cycle closeout只能报告blocked，不能伪造terminal。
- `not_started_after_project_failure` group必须有 cancellation attempt + terminal `cancelled`，且zero crop/request/response/call/cache/ledger entry。
- 若first in-flight batch的两个worker均project-blocking failure，remaining six admitted groups必须满足上述cancellation语义。
- plan-denied groups使用既有budget-exhausted terminal，不进入admitted分母。
- budget terminal的durable diagnostic必须区分 `routing_plan` 与 `provider_cycle_reservation`；只有前者属于plan-denied。Provider reservation拒绝的group仍属于admitted/never-submitted budget terminal，另列于routing aggregate，zero paid artifact，并阻止Step 4 success；禁止把unknown origin自动解释为localizable transport或plan denial。
- project-blocking run不得有 `AutomaticResult`、working copy、pause、symbol report或receipt。

Step 4 success仍要求authenticated calls、typed Case A/B、all required non-GD&T results、complete budget evidence与 `visual_qa_pending:first-pdf-balloons`；“成本没超”本身不构成success。

## Headed Step 5

只有exact GDT-10D run达到pause且所有Step 4 gates通过，才允许headed Chrome QA。API proof与真实UI proof分别记录Case A/B、label/value/datum、A -> B structured edit、save/reload、freeze gate和same-reviewed-result PDF/Excel export。只resume literal run ID；禁止 `latest` 或replacement。Final receipt必须重新验证authorization/pricing/ledger/routing evidence。

## Cleanup, Retention and Promotion Boundary

- Paid terminal后立即用safe override只重建feature `api/worker`，证明credentials、cycle ID和authorization mount absent，再删除override并unset host variables。
- accepted closeout后private backup/auth state可以删除；删除前require run-bound copies/hashes与healthy `0014` DB。Blocked retention Owner是 `GDT-10D execution owner`，必须把mode/path/hash/authorization expiry与review deadline `2026-08-09T23:59:59+08:00`写回parent plan。此前只在(a) blocker解除且healthy `0014` DB + run-bound copies已验证，或(b)用户另行批准restore且新backup取代它时删除；到deadline不得自动删除，必须请求用户选择renew或secure deletion。
- DB restore需要新的destructive authority；`0014 -> 0013`在存在v2 rows后不自动downgrade。
- `0015_drop_symbol_attempt_v1_default`与production promotion继续blocked，不因GDT-10D success自动批准。

## Acceptance

本design只有在以下全部成立时完成：contract/plan review accepted；pricing/ledger/authorization/runtime activation以TDD实现并offline review accepted；writers quiesced后backup/migration成功；zero-paid reviewer `GO`；one-use cycle产生可审计terminal；必要时same-run Step 5/receipt完成；credentials/cycle cleanup完成；final independent review接受；parent plan按runtime truth更新且worktree clean。
