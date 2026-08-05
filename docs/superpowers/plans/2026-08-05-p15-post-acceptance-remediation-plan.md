# P15 验收后修复实施计划

日期：2026-08-05

状态：**REVIEW DRAFT**。本文只记录修复顺序和验收边界；不授权产品代码修改、
真实在线调用、fresh/held-out 执行、fast-context 对比或默认启用 P15。

仓库：`/Users/flobby/vibe_coding/context-search-tool`

问题陈述：
`docs/superpowers/specs/2026-08-03-p15-post-acceptance-problem-statement.md`

复用的验收设计：
`docs/superpowers/specs/2026-08-02-p15-v7-minimal-online-causal-acceptance-design.md`

## 1. 决策摘要

本计划将 P15 修复拆成两个不能混合的阶段：

1. **离线仓库修复**：恢复证据身份、测试可信度、产品状态说明和 trace 可见性，
   形成一个准确绑定当前 candidate 的新 DRAFT 合同；该阶段不得发起在线调用。
2. **重新验收**：在离线修复完成并获得单独批准后，用新 attempt identity 执行
   fresh、held-out、release 和 governance 门。

在重新验收完成前，唯一允许的顶层处置是：

> **P15 local efficacy observed; full acceptance and release closure pending.**

实现策略采用以下默认决定，任何改变都必须先修订本计划：

- 当前 ranking 行为先保持不变，不在修复证据链时调整 bonus、TopK、图预算或
  promotion cutoff；
- 当前 semantic-pair fallback 明确记录为一种独立 promotion mode，不再把它
  描述成 exact planner identity match；
- P15 保持实验性 opt-in，默认 `query_planner.enabled=false`、
  `retrieval.consume_dependency_hints=false`；
- 旧 v7 attempt-007 合同保留为历史 DRAFT，不原地刷新哈希；最终 candidate 使用
  新版本合同和新 attempt ID；
- fast-context 是否继续作为硬门必须在新 attempt 冻结前明确批准。推荐将它降为
  report-only comparator；若仍是硬门，服务失败必须得到 `blocked/INCOMPLETE`，
  不能静默豁免。

## 2. 范围与非目标

### 2.1 本计划包含

- 跟踪 post-acceptance 问题陈述和 `local_efficacy_only` 处置；
- 消除 candidate、合同、runner/test projection 之间的身份漂移；
- 明确 exact source hint、exact target hint 和 semantic-pair fallback 三种行为；
- 让 query 输出和显式 trace 能说明 P15 是否启用、是否提升以及未生效原因；
- 修复默认 pytest 收集入口；
- 区分当前产品回归、固定运行时 characterization 和历史封存验收；
- 建立一个干净 checkout 可运行的产品 full-suite 与 CI gate；
- 记录受支持的 opt-in 配置、在线依赖、fallback 和覆盖限制；
- 用新 attempt identity 重新绑定并在获批后重新验收。

### 2.2 本计划不包含

- 调整 `_EXACT_IMPORTED_SYMBOL_BONUS` 或 promotion 排名公式；
- 扩展到 `import module as m`、star/dynamic import、re-export、方法、嵌套函数、
  通用调用图或其他语言；
- 更换 planner/embedding provider 以挽救一次失败的 attempt；
- 扩大 TopK、候选预算、图遍历预算或 promotion 数量；
- 删除、重写或伪造历史 `.quality` 原始证据；
- 把历史封存测试全部标记跳过来制造绿色 full-suite；
- 在没有正式支持配置的 fresh/held-out 证据前默认启用 P15。

## 3. 成功标准

### 3.1 离线修复完成

离线修复只有在以下条件同时满足时才能记为
`offline_remediation_complete`：

- 问题陈述和 interim disposition 均为 tracked 文件；
- `c69e4be...` 被准确标注为包含 P15 的审计 HEAD，而不是 A/B control commit；
- attempt-005 的 tracked 投影明确写出原始证据哈希、manifest、外部仓库提交、
  指标、未完成门，以及 **candidate identity 未被原始 attempt 加密绑定**；
- 旧 v7 合同保持历史 DRAFT，新合同使用新 attempt ID；
- 新合同只要求干净 checkout 中可获得的 tracked 输入；
- 新合同绑定 candidate commit/tree、产品文件、行为测试、配置、prompt/schema、
  manifest、promotion modes、所有门和批准状态；
- focused P15 tests 全绿；
- 默认产品 full-suite 在干净 checkout 和声明运行时全绿；
- archival/runtime-pinned tests 有独立入口、所需环境和非发布门语义；
- CI 运行与本地产品 full-suite 相同的命令；
- README 说明 P15 是 opt-in、给出受支持配置和限制；
- trace 能区分 disabled、planner/fallback/intent/graph/hint/no-candidate no-op，
  并分别计数 exact-source、exact-target、semantic-pair promotion；
- 没有发起真实 planner、embedding、fast-context 或 held-out 调用。

### 3.2 P15 完整关闭

`offline_remediation_complete` 不等于 P15 完整关闭。完整关闭仍要求：

- 新 attempt 的完整 fresh matrix 执行完毕；
- held-out 按预先冻结的规则执行并通过，或产生如实失败处置；
- comparator 按预先批准的硬门/report-only 规则完成；
- 正式支持配置的 efficacy、precision/noise、latency、privacy、fallback 和
  availability 门完成；
- focused、产品 full-suite 和 CI 对最终 candidate 全绿；
- tracked final disposition 绑定全部输入、结果、报告和提交；
- 顶层处置只能是 `ship`、`local_efficacy_only`、`reject` 或 `blocked`。

## 4. 任务与提交顺序

| Task | 内容 | 主要验证 | 建议提交 |
| ---: | --- | --- | --- |
| 0 | 冻结入口状态和修复口径 | 基线命令可复现 | `docs: record P15 post-acceptance state` |
| 1 | 固定 promotion 语义和诊断 | behavior/trace tests | `test: freeze P15 promotion modes` |
| 2 | 跟踪 interim disposition | canonical tracked projection | `docs: record P15 local efficacy disposition` |
| 3 | 修复 pytest、测试分层和 CI | clean product suite | `test: separate product and archival gates` |
| 4 | 文档化 opt-in 并接入 trace | CLI/trace/docs tests | `feat: expose P15 activation diagnostics` |
| 5 | 创建新 DRAFT 合同并绑定 candidate | hash/contract tests | `test: bind P15 remediation candidate` |
| 6 | 离线总验收和冻结 | clean checkout 全绿 | `docs: record P15 offline remediation` |
| 7 | 经批准的新在线验收 | fresh/held-out matrix | 单独授权后决定 |
| 8 | 最终 disposition | tracked closure | 由 Task 7 结果决定 |

每个提交只包含该任务直接拥有的文件。Task 5 冻结后，不得再修改合同绑定的
产品或行为测试；任何必要修改都创建新 attempt ID。

## 5. Task 0 — 冻结入口状态和修复口径

### 5.1 从干净 tracked tree 复现

在当前工作树之外创建临时、可丢弃的干净 worktree，避免 `.DS_Store`、
`.quality`、pytest cache 或旧 `/tmp` 指针影响分类。不得清理或覆盖用户当前工作树。

记录：

- `HEAD`、父提交和当前分支；
- Python、SQLite、pytest 和依赖版本；
- tracked、untracked、ignored 状态；
- 问题陈述列出的四个 SHA-256；
- focused、默认 full-suite 和补充 `PYTHONPATH` full-suite 的退出码及摘要。

基线命令：

```bash
CST_REPO_ROOT="$(pwd -P)"
CST_RUNTIME="${CST_RUNTIME:-$CST_REPO_ROOT/.venv/bin/python}"

git rev-parse HEAD
git status --short --ignored
"$CST_RUNTIME" --version
"$CST_RUNTIME" -c 'import sqlite3; print(sqlite3.sqlite_version)'

.venv/bin/pytest -q \
  tests/test_python_graph.py \
  tests/test_exact_imported_symbol_bonus.py \
  tests/test_dependency_replay.py \
  tests/test_p15_metric_replay.py \
  tests/test_p15_pre_corpus_governance.py \
  tests/test_p15_attempt_007_governance.py \
  tests/test_query_planner.py

.venv/bin/pytest -q -m "not slow"
PYTHONPATH=.:src .venv/bin/pytest -q -m "not slow"
```

预期入口信号是已观察结果，而不是新的通过门：focused `280 passed, 1 failed`；
默认 full-suite 在 `scripts` import 收集处失败；补充根路径后为
`3721 passed, 65 failed, 5 skipped, 6 deselected, 10 errors`。如果干净 worktree
结果不同，先记录差异来源，不得直接刷新本文数字。

### 5.2 修正文档身份用语

更新问题陈述：

- 将 `基线: c69e4be...` 改为 `审计 HEAD: c69e4be...`；
- 单独记录 `P15 implementation commit: 974aadc...`；
- 将 A/B control 定义为同一 replay state 下
  `consume_dependency_hints=false`，而不是 `c69e4be...`；
- 将 v7 contract baseline `10ab7ab...` 标为该合同自己的历史 baseline；
- 明确问题陈述本身在 Task 0 后必须 tracked。

### 5.3 Stop rule

若 focused failure 不再只由合同绑定产生，或干净 worktree 出现新的 P15 产品行为
失败，停止后续任务，先为新失败建立独立最小复现。Task 0 不修改产品代码。

## 6. Task 1 — 固定 promotion 语义和诊断

### 6.1 先冻结当前行为

在 `tests/test_exact_imported_symbol_bonus.py` 和
`tests/test_dependency_replay.py` 中先增加/收紧以下测试：

- exact source-module/source-symbol hint 命中并提升；
- exact imported-target hint 在闭合 source evidence 下提升；
- source hints 为空、target hint 不匹配，但强 direct source/target pair 触发
  semantic-pair fallback；
- 相同 fallback 在 weak pair 下 no-op；
- generic `symbol_hints`/`grep_keywords` 不激活；
- `imported_module_hints` 单独存在不激活；
- graph fault、planner fallback、非 `follow_imports`、无闭合 witness 均 no-op；
- promotion 最多两个路径、rank 1 不变、幂等且输入顺序无关；
- mode 诊断不改变 rank、score、Top12 或 promotion delta。

当前 `anyio-q06` 与 `multidict-q01` 必须归类为
`semantic_pair_fallback`，不能归类为 exact planner identity match。

### 6.2 最小诊断接缝

保持 `apply_planner_dependency_hint_promotions()` 的 list 返回值和普通调用方不变。
增加一个默认关闭的内部 observation callback，记录一次调用的：

- `status`: `disabled`、`graph_unavailable`、`planner_not_ok`、
  `intent_mismatch`、`missing_activation_hint`、
  `no_eligible_closed_candidate` 或 `promoted`；
- `exact_source_hint_promoted`；
- `exact_target_hint_promoted`；
- `semantic_pair_fallback_promoted`；
- `promoted_path_count`。

诊断必须由实际 eligibility 分支产生，不得在 trace 层复制 promotion 判定算法。
callback 不能参与排序、改变异常处理或产生持久状态。

### 6.3 修正用户可见措辞

现有 reason `planner exact dependency target` 对 fallback 过强。将它改为中性的
`planner dependency target promotion`；具体 mode 只在显式 trace 和验收报告中
展开。不得增加新的 ranking score 或调整总分。

### 6.4 验证

```bash
.venv/bin/pytest -q \
  tests/test_exact_imported_symbol_bonus.py \
  tests/test_dependency_replay.py \
  tests/test_retrieval_pipeline.py
```

要求所有已有 ranking 结果保持一致；允许的变化只有诊断字段和上面的 reason 文本。

## 7. Task 2 — 跟踪 interim disposition 和必要证据投影

### 7.1 新增 tracked disposition

新增：

- `docs/superpowers/specs/2026-08-05-p15-local-efficacy-disposition.md`；
- `tests/fixtures/p15_post_acceptance/local-efficacy-summary.json`；
- `tests/test_p15_post_acceptance_disposition.py`。

tracked JSON 只保存无秘密、无源码正文的必要投影：

- disposition `local_efficacy_only`；
- attempt-005/006 ID、状态和原因；
- raw `.quality` artifact path 与 SHA-256；
- manifest path、SHA-256 和 DRAFT/non-executable 状态；
- anyio/multidict immutable commits；
- overall/per-repository Recall@12、MRR@12、latency 和 baseline loss；
- fast-context `7 success / 1 failed / 4 not run`；
- focused/full/CI/default-config 门状态；
- `candidate_identity.status = "not_cryptographically_bound_by_attempt_005"`；
- promotion mode 复核结果；
- 审计 HEAD、P15 implementation commit 和生成时间。

不得把当前 HEAD 或当前文件哈希倒填成“attempt-005 当时已绑定的 candidate”。
tracked summary 是诚实的事后审计投影，不是追溯性防篡改证明。

### 7.2 默认测试不得依赖 ignored evidence

默认测试验证 tracked JSON 的 closed shape、canonical bytes、内部计数和所有 tracked
引用。它不得要求 `.quality` 存在。原始证据存在时可用一个显式 audit 命令复核
SHA；缺失原始证据不应使干净 checkout 的产品 suite 失败。

### 7.3 验证

```bash
.venv/bin/pytest -q tests/test_p15_post_acceptance_disposition.py
git diff --check
```

## 8. Task 3 — 修复 pytest、测试分层和 CI

### 8.1 先对全部红灯分类

从 Task 0 的干净 worktree 报告逐个分类，不按文件名批量豁免：

1. **product regression**：当前受支持产品行为；必须修代码或当前测试；
2. **workspace contamination**：例如 OS metadata 或 ignored 文件进入冻结 inventory；
   修复输入过滤或测试隔离；
3. **archival acceptance**：依赖已 supersede 的合同、封存 payload 或历史 runner；
4. **runtime-pinned characterization**：只在冻结 Python/SQLite 身份下有意义；
5. **missing durable fixture**：默认测试读取易失 `/tmp` 或本地 pointer；应迁移为
   tracked fixture，或明确转入 archival gate；
6. **genuine unsupported runtime**：与 `requires-python >=3.11` 冲突时必须修复或收窄
   声明，不能只改 expected hash。

将分类表记录到 interim disposition。每个失败节点必须有唯一类别和处置。

### 8.2 修复默认收集入口

将 `pyproject.toml` 的 pytest path 改为同时包含仓库根与 `src`，使
`tests/test_profile_retrieval.py` 能在 README 命令下导入顶层 `scripts`：

```toml
pythonpath = [".", "src"]
```

增加 collection smoke，证明 README 的直接入口不需要调用者补
`PYTHONPATH=.:src`。

### 8.3 明确三种测试门

在 `pyproject.toml` 注册：

- `archival_acceptance`：历史合同/封存证据审计；
- `runtime_pinned`：要求固定 Python/SQLite 的 characterization。

只允许在完成 8.1 分类后添加 module/test marker。若一个模块同时包含当前产品测试
和历史验收测试，先把当前测试提取到独立文件，不能整模块标记 archival。

定义命令：

```bash
# 当前产品发布门
.venv/bin/pytest -q \
  -m "not slow and not archival_acceptance and not runtime_pinned"

# 固定运行时 characterization 门
.venv/bin/pytest -q -m "runtime_pinned"

# 历史证据审计；运行前必须显式提供持久 evidence root
.venv/bin/pytest -q -m "archival_acceptance"
```

archival/runtime-pinned 门不得被称为默认 full-suite，也不得通过无说明 skip 隐藏。

### 8.4 移除易失证据依赖

- 默认产品测试不得读取 `/tmp/context-search-*`；
- `.quality/*-run-root.txt` 不得是 clean checkout 的唯一输入；
- 仍属于当前产品门的最小输入迁移到 tracked fixture；
- 只属于历史审计的输入改为显式环境/CLI 参数，并在缺失时 preflight fail；
- 不删除用户现存 `.quality` 或历史密文。

### 8.5 建立普通 CI

新增 `.github/workflows/ci.yml`，至少在 Ubuntu + Python 3.13 上：

- 安装 frozen dev dependencies；
- 运行与 8.3 完全相同的产品发布门；
- 单独运行 focused P15 suite；
- 保存 JUnit 和运行时身份 artifact；
- 不访问在线模型、Ollama、fast-context 或 held-out；
- 不使用仓库 secrets。

现有 P5/P6 专项矩阵保持不变；P15 修复不复制其专用 evidence pipeline。

## 9. Task 4 — 文档化 opt-in 并接入 trace

### 9.1 README 产品状态

在 README 增加 P15 章节，明确：

- 状态是 experimental opt-in；
- 默认 planner、dependency-hint consumption 和 hash embedding 不走已观察收益路径；
- 支持配置需要 `query_planner.enabled=true`、受支持 online planner、受支持 embedding
  和 `retrieval.consume_dependency_hints=true`；
- API key 只通过环境变量/既有 secret 配置，不写进示例或 trace；
- planner timeout/fallback、图 fault 和不支持的 Python import 形态；
- 本地 promotion 开销与端到端 online latency 分开；
- `local_efficacy_only` 不是发布承诺。

在新验收通过前不得把当前默认值改为 true。

### 9.2 RetrievalTrace 可见性

在 ranking 与 context expansion 之间记录一个
`dependency_promotion` trace stage。该 stage 始终可见：

- feature off 时记录 `disabled=1`；
- feature on 但 no-op 时记录一个明确 status；
- promotion 时记录三个 mode count 和 promoted path count；
- top-candidate preview 使用既有 trace 上限和脱敏规则；
- 不输出 source body、绝对路径、authorization header 或 raw exception。

普通 `query` 的 ranks、scores 和结果 schema 不变；显式 `trace` 的 stage sequence 和
reason 文本按本计划有意更新。RetrievalTrace schema v1 已允许开放 stage name，
因此除非实现证明 closed payload 需要新字段，否则不升级顶层 schema。

### 9.3 验证

```bash
.venv/bin/pytest -q \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_cli_commands.py \
  tests/test_config_paths.py \
  tests/test_exact_imported_symbol_bonus.py
```

更新 trace characterization 时，只接受新增 stage、诊断 counts 和已批准 reason 文本
变化；结果路径、排名、分数、内容、预算和其他 stage 决策必须保持一致。

## 10. Task 5 — 创建新 DRAFT 合同并绑定最终 candidate

### 10.1 不修补 v7 attempt-007

旧文件
`tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json` 保持历史 DRAFT。
不得把当前文件哈希直接写回旧 attempt，也不得把 attempt-005 的结果挂到新哈希上。

新增：

- `docs/superpowers/specs/2026-08-05-p15-v8-closure-acceptance-design.md`；
- `tests/fixtures/p15_v8_closure/attempt-contract.schema.json`；
- `tests/fixtures/p15_v8_closure/attempt-contract.json`；
- `tests/test_p15_v8_contract.py`。

初始 ID 使用 `p15-v8-attempt-001`，状态必须为 `DRAFT`、
`execution_eligible=false`、`approval_receipt.received=false`。

### 10.2 两提交冻结流程

1. 先提交 Tasks 0–4 的产品、测试、文档和 CI，得到 immutable candidate commit/tree；
2. 从该 clean candidate 计算 product/test/config/prompt/schema projection；
3. 在后续合同提交中写入 candidate commit/tree 和 projection；
4. 合同提交不得再次修改任何 candidate-bound 文件；
5. 合同验证必须在没有 `.quality` 的 clean checkout 中通过。

这避免“同一提交中先生成合同、随后继续修改被绑定文件”的再次发生。

### 10.3 新合同必须绑定

- candidate commit 和 tree；
- product files、行为测试、runner、配置和文档的 SHA-256；
- 只包含 tracked、clean-checkout 可用的 required path；
- control/treatment 唯一差异仍是 `consume_dependency_hints=false -> true`；
- exact-source、exact-target、semantic-pair 三种 promotion mode；
- fallback/no-op status 枚举和 per-query mode report；
- rank-1、最多两个路径、幂等、closed exact witness 和 graph-fault no-op；
- planner/embedding identity、prompt/schema、TopK、预算和 privacy；
- fresh/held-out corpus、完整有限 schedule、门和 stop rule；
- focused、产品 full-suite、CI 和受支持 opt-in 配置；
- comparator policy：`hard_gate` 或 `report_only`，不得留作结果后决定；
- outcome、release、governance 分离；
- 单一未来批准 receipt 和所有 reapproval triggers。

ignored raw evidence 可以通过 path + digest 被引用，但不能作为默认合同测试要求存在的
runner/test 输入。

### 10.4 验证

```bash
.venv/bin/pytest -q \
  tests/test_p15_v8_contract.py \
  tests/test_p15_post_acceptance_disposition.py \
  tests/test_exact_imported_symbol_bonus.py \
  tests/test_dependency_replay.py \
  tests/test_query_planner.py
```

合同的行为字段必须由测试逐项对应实际实现，不能只验证文件哈希。

## 11. Task 6 — 离线总验收和冻结

从无 `.quality`、无 `.context-search`、无 ignored OS metadata 的 clean worktree 运行：

```bash
# Focused P15
.venv/bin/pytest -q \
  tests/test_python_graph.py \
  tests/test_exact_imported_symbol_bonus.py \
  tests/test_dependency_replay.py \
  tests/test_p15_post_acceptance_disposition.py \
  tests/test_p15_v8_contract.py \
  tests/test_query_planner.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py

# 当前产品 full-suite
.venv/bin/pytest -q \
  -m "not slow and not archival_acceptance and not runtime_pinned"

git diff --check
```

同时要求新普通 CI 对同一 commit 全绿。保存 JUnit、运行时身份、命令、退出码和报告
SHA 到 `.quality/p15-v8-offline-remediation/`，并把不含秘密的必要投影写入 tracked
offline disposition。

Task 6 完成后：

- 新合同仍保持 DRAFT/non-executable；
- P15 仍保持 opt-in；
- 顶层状态仍是 `local_efficacy_only`；
- 停止，不自动进入 Task 7。

## 12. Task 7 — 经单独批准的新在线验收

**本任务当前不授权。** 只有新合同、candidate、schedule 和批准 receipt 全部冻结后
才能执行。

复用 v7 的 same-plan 因果设计：

- 两个 candidate-blind Python 仓库；
- 每个仓库 2 个 guard + 4 个 efficacy case；
- 12 个 case、每 case 2 个真实 planner sample；
- 24 个 planner sample、96 个 local arm replay；
- 同一 sample 的 plan、embedding、base roster 和 pre-treatment state 完全共享；
- planner fallback 保留在 denominator，不能像 attempt-006 一样提前停止；
- complete matrix 后再决定 outcome；
- 不换 repo、query、gold、model、endpoint、阈值或 case；
- 不作结果依赖 retry、追加 sample 或 replacement；
- provider outage 按冻结规则得到 `blocked`，不伪造成产品无收益。

每个 case/sample 必须额外报告：

- control/P15 Top12 和 gold rank delta；
- added/removed paths；
- exact-source、exact-target、semantic-pair promotion mode；
- closed witness；
- promoted path 的 relevance/noise 分类；
- rank-1 和 baseline required-hit loss；
- planner、embedding、local replay、end-to-end latency；
- fallback/no-op 原因；
- request budget。

fresh outcome 继续使用 v7 已冻结的核心门：至少 3 个稳定 causal new targets、至少
3 个 efficacy cases、两个仓库均有收益、required loss 为 0、rank-1 变化为 0、
Precision@12 下降不超过 0.02，且 treatment-only irrelevant
`(case, sample, path)` 不超过 1。

fresh 通过后才允许打开预先封存的 held-out；held-out 至少 2 个稳定收益、覆盖至少
2 个 case、required loss 为 0。

fast-context 若为：

- `hard_gate`：必须完成冻结 manifest 的全部 comparator slots，否则 attempt 为
  `blocked/INCOMPLETE`；
- `report_only`：仍按冻结预算执行并报告服务错误，但不覆盖本地 outcome；该政策必须
  在任何结果产生前写入合同并批准。

## 13. Task 8 — 最终 disposition

生成 tracked final disposition，至少绑定：

- candidate/contract/approval/manifest/schedule commit 和 SHA；
- fresh、held-out、comparator、focused、full-suite、CI 报告；
- 支持配置和默认配置；
- promotion mode 分布与 noise 分类；
- planner/embedding/local/E2E latency 和 availability；
- outcome、release、governance 的独立状态；
- 剩余覆盖限制。

顶层规则：

- `ship`：fresh + held-out + release + governance 全部通过；
- `local_efficacy_only`：仅本地机制收益可信，完整验收或发布门未闭合；
- `reject`：完整有效矩阵执行后 outcome 门失败；
- `blocked`：冻结外部依赖或输入不可用，且禁止替换。

若不是 `ship`，README 必须继续把 P15 标为 experimental opt-in。不得使用
`complete P15`、`fully accepted` 或等价提交/发布措辞。

## 14. 全局 stop rules

以下任一情况发生时立即停止当前 attempt：

- 合同绑定后修改 candidate、行为测试、prompt/schema、模型、query、gold、门或预算；
- 结果产生后刷新合同哈希或改变 comparator hard/report-only 政策；
- 为通过 full-suite 而未分类地标记、删除或跳过失败测试；
- 为恢复 Recall 调整 bonus、TopK、候选/图预算或 promotion 数量；
- online failure 后替换 provider、repo、case、query 或追加 retry；
- held-out 打开后修改产品或验收规则；
- tracked evidence 出现 secret、authorization header、源码正文、绝对本地路径或 raw
  provider exception；
- 默认启用未经正式支持配置验证的 P15 路径。

发生 stop rule 后，只能保留现有证据、生成如实 disposition，并以新 candidate 和新
attempt ID 重新开始；不得覆盖原 attempt。
