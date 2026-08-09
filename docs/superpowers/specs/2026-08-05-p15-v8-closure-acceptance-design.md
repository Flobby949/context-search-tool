# P15-v8 Closure Acceptance Design

日期：2026-08-05

状态：**DRAFT / NOT EXECUTION ELIGIBLE**。

修订：2026-08-09。`p15-v8-attempt-001` 在任何执行或在线访问前因 candidate
绑定漂移而作废；当前静态合同使用 `p15-v8-attempt-002`，所有执行 counters 继续为零。

权威合同：
`tests/fixtures/p15_v8_closure/attempt-contract.json`

本设计只冻结一次未来验收所需的身份、行为、样本表、门和批准边界。它不授权
Task 7，不授权访问 fresh/held-out 源码，也不授权 planner、embedding、
fast-context、Ollama 或其他在线调用。当前顶层处置保持
`local_efficacy_only`；本文不能被引用为执行、完整验收或发布结论。

## 1. 两提交身份

P15-v8 attempt-002 使用两层提交：

1. 修复后 candidate 固定为 commit
   `c21d4cc039f6298f89d3040a0a6879d6a82eeb32`、tree
   `a159d5c4e025c82e12edab0f3343c0f4622a09ea`。它包含离线修复、闭合 evaluator
   foundation，以及已批准的 P14 r2 exact-owner tie 修正。
2. 本设计、闭合 schema、DRAFT 合同和合同测试位于后续合同提交。

合同从 candidate commit 的 Git object 读取字节，不从脏 worktree 回填。它分别绑定
product、behavior tests、tracked offline metric/closure evaluators、config/docs 和
prompt/response-schema 五个 closed projection。每个 projection 是排序后的
`path -> SHA-256` 条目及其 canonical JSON digest。所有 required path 必须在 candidate
中 tracked 且 clean checkout 可用；`.quality` 不得成为默认 runner 或测试输入。

合同层只绑定 design、schema 和 contract test 的 SHA-256。合同 JSON 不自哈希，避免
循环。旧 v7 attempt-007 保持历史 DRAFT，SHA-256 必须继续为
`f7fd4711cdc7ed049c2c7cff6dfa8eed871f44d1795ea4fd4b33b30dc0f88fcf`。

## 2. 唯一处理因子与当前实现语义

同一 query/sample 的 control 与 treatment 共享 candidate、planner/fallback plan、
embedding/index、base candidate roster、scores/order、TopK 和预算。唯一处理因子是：

- control：`consume_dependency_hints=false`；
- treatment：`consume_dependency_hints=true`。

promotion mode 闭合为：

- `exact_source_hint`；
- `exact_target_hint`；
- `semantic_pair_fallback`。

no-op status 闭合为：

- `disabled`；
- `graph_unavailable`；
- `planner_not_ok`；
- `intent_mismatch`；
- `missing_activation_hint`；
- `no_eligible_closed_candidate`。

每个 query 的 `dependency_promotion` trace stage 必须报告一个 no-op status，或三个
mode count 加 `promoted_path_count`。promotion 保护 rank 1，每次最多两个不同路径，
重复应用幂等。任何 credited gain 必须携带闭合的
source-signal/source-chunk/source-file/relation/target-signal/target-chunk/target-file
witness，relation 必须是 Python AST 产生的 `resolved_exact imports`。图 fault 必须
no-op；target-only module hints 不得单独激活 promotion。

## 3. 在线身份、请求与隐私

未来 acceptance identity 沿用 v7 预冻结身份，不能根据结果换 provider/model：

- planner：SiliconFlow OpenAI-compatible
  `Qwen/Qwen2.5-14B-Instruct`，temperature 0、seed 0、max tokens 512；
- embedding：SiliconFlow OpenAI-compatible `Pro/BAAI/bge-m3`，1024 维；
- prompt：candidate 的 `qwen-query-planner-v4-source-identity-v1` 及其字节 hash；
- response schema：candidate 的九个 exact JSON 字段、strict whole-object fallback 和
  当前 source/import hint limits。

acceptance planner 设置 `send_repo_profile=false`，payload 只有 query 与冻结 numeric
limits。embedding 会向冻结 provider 发送 source chunks；该事实必须明确，不能把远程
embedding 描述为“源码不离机”。control/treatment 共用同一 index/query embedding，
treatment 不增加 planner 或 embedding 请求。

证据和日志不得包含 credential、Authorization header、source body、绝对本地路径或
raw exception。ignored raw evidence 只允许以 path + digest 参考，合同测试不得要求这些
路径存在。

## 4. Corpus 与完整有限 schedule

### 4.1 Fresh

fresh 有两个独立 Python repository slot。每个 repository 按冻结、candidate-blind、
stdlib-AST 顺序取前六个 direct `from module import name` eligible cases：ordinal 1–2
为 guard，3–6 为 efficacy。不得扫描后续 ordinal、替换 case/repository，或用 planner、
candidate rank、promotion output、target hints 资格化样本。query 只能由 source 侧信息
机械生成，不能包含 target name/alias/module/path/signal/gold 派生词。primary target
denominator 固定为 8。

### 4.2 Held-out

held-out 有一个 repository slot、恰好四个 candidate-blind target-missing cases，使用
相同 gold/query 规则。其 identity、public seal、payload digest、query 和 gold 在 fresh
outcome 通过前保持 unopened。当前 DRAFT 不选择 identity、不读取 seal/payload。

### 4.3 Schedule

合同用有限 Cartesian schedule 冻结全部 slot：repository slots、case ordinals 和两个
sample 的 exact replay order。sample 1 顺序为 control-1、control-2、treatment-1、
treatment-2；sample 2 反向为 treatment-1、treatment-2、control-1、control-2。
fresh 共 24 planner samples / 96 local replays；held-out 共 8 planner samples / 32 local
replays。合同保存完整 expansion 的 count 和 digest，测试独立展开并验证。

所有 case/sample 必须完成后才能决策。禁止 result-dependent append、早停、额外 replay、
retry、replacement 或 provider/model substitution。

## 5. 预冻结门与 comparator

### 5.1 Outcome

fresh 延续 v7 的三项 stable causal gain / 三个 case / 两个 repository 门，required loss
与 rank-1 change 均为零；每个 gain 必须有 closed witness。24 个 planner sample 至少
22 个 valid plan；fallback 留在 denominator。Precision@12 最大下降 0.02，最多一个
treatment-only irrelevant `(case, sample, path)`。

held-out 固定至少两个 stable causal gain、两个 case、零 required loss。fresh 与 held-out
outcome 只回答 efficacy，不回答 release/governance。

### 5.2 Release 与 governance

release 独立要求：treatment 不增加在线请求；本地 treatment median regression 不超过
10% 或绝对增量不超过 5 ms；TopK/caps/budgets 不增加；privacy leak 为零；focused、
当前 product full-suite、CI 和 README 所列 supported opt-in config gate 通过。端到端在线
latency 必须报告，但不是本地 promotion latency gate的替代物。

governance 独立要求 candidate/contract identity 完整、seal 后不 tuning、证据完整、
receipt 与 execution manifest 精确匹配，并分别报告 outcome/release/governance。

fast-context 在新 attempt 产生结果前预先固定为 `report_only`。理由是历史服务
`resource_exhausted` 已证明可用性不能可靠充当 P15 因果 efficacy 硬门。fresh 12 cases
仍必须产生 comparator status/report；不可用时记录
`INCOMPLETE`，不得静默删除、替换或在结果后改成 hard gate/waiver。该 status 不改变
outcome 或 release 的预冻结门。

## 6. Stop rules 与处置分离

- 缺 approval 或 sealed execution manifest：任何访问前停止；
- candidate/contract binding 漂移：新 attempt；
- provider 或 sealed input 不可用：`blocked`，不替换；
- matrix 不完整：`blocked`，不提前判定；
- 完整 outcome 失败：`reject`；
- outcome 通过但 release/governance 失败：保持 `local_efficacy_only`；
- 全部门通过才允许未来 tracked disposition 使用 `ship`。

允许的最终顶层处置只有 `ship`、`local_efficacy_only`、`reject`、`blocked`。

## 7. 单一批准边界

当前合同只有一个未来 `approval_receipt`，且 `received=false`。一次未来批准可授权按
冻结规则选择并 seal identity/corpus，再连续执行 fresh，以及仅在 fresh 通过后打开
held-out 和评估 release。当前没有该批准，`execution_eligible=false`、
`task7_authorized=false`，所有执行 counters 为零。

candidate、合同层、处理因子、mode/status/report、limits/witness、planner/embedding、
prompt/schema、TopK/budget、privacy、corpus rule 或已 seal identity、schedule、gate、
comparator、runner/test/config/docs/CI、supported config 或 approval scope 的任何改变均使
receipt 失效并要求 reapproval/new attempt。初次按已批准规则填充 seal slots 不是
post-hoc plan change；seal 后修改任何绑定则必须重新批准。

## 8. 当前 stop point

Task 5 到此只创建静态 DRAFT 合同并运行离线测试。Task 7 仍未授权。不得解析 fresh
refs、读取 fresh/held-out source、打开 held-out、执行 acceptance runner、调用在线
planner/embedding/comparator/Ollama，或把本合同描述为 release closure。
