# P15 验收后问题陈述

日期：2026-08-03

状态：OPEN。本文随 Task 0 纳入版本控制，作为 tracked artifact。

审计 HEAD：`c69e4be790921ac74bf2e7da1d7312b266798c5d`

P15 implementation commit：`974aadc32edc4a7cbebed70a9cacd13a286ed471`

v7 合同历史 baseline：`10ab7ab0cd4c32012293e16d37a46fa9af7a2c97`。
该提交只属于 v7 合同自己的历史身份，不是本文本地 paired replay 的 A/B control。

## 1. 结论

P15 已经证明一个有效的局部机制：对于 Python 跨文件依赖查询，当目标文件已经通过静态精确导入关系进入候选尾部、但仍落在 Top12 之外时，消费 planner dependency hints 并对带有闭合精确来源的候选做有界提升，可以恢复目标文件，而且本地额外延迟很小。

2026-08-02 的最完整本地 A/B 记录显示。这里的 control 是同一 plan、embedding、
候选 roster 和 replay state 下的 `consume_dependency_hints=false`；treatment 只把该值
改为 `true`。它不是 `c69e4be...` 或其他 Git commit 与 candidate 之间的提交对比。

| 指标 | Baseline | P15 | 结果 |
| --- | ---: | ---: | --- |
| Top12 命中 | 10/12 | 12/12 | `+2` |
| Recall@12 | 0.8333 | 1.0000 | 提升 |
| MRR@12 | 0.3154 | 0.3980 | 提升 |
| 本地中位延迟 | 32.99 ms | 34.50 ms | `+1.51 ms` / `+4.57%` |
| Baseline 命中损失 | — | 0 | 通过 |

新增的两个目标是：

- `anyio-q06`：`src/anyio/_core/_eventloop.py` 从 Top12 外提升到第 2 名；
- `multidict-q01`：`multidict/_compat.py` 从 Top12 外提升到第 2 名。

但是，当前只能将 P15 记录为“本地核心 A/B 收益已观察到”，不能记录为“完整验收和发布门全部通过”。fast-context 对比没有完成，最新运行仍为 `INCOMPLETE`，v7 合同仍为 DRAFT，合同绑定哈希与当前代码不一致，聚焦测试和全套测试也未全绿。

## 2. P15 主要解决的问题

P8 已经能够建立 Python 仓库内模块导入关系，但旧关系主要指向目标模块，而不是被导入声明所在的精确 chunk。查询如果描述调用方行为、没有直接包含目标符号或目标路径，目标声明即使具有真实结构关系，也可能停留在候选尾部，无法进入最终 Top12。

P15 的演进记录说明，单纯“建边”不是充分条件：

| 阶段 | 机制 | 结果 | 暴露的问题 |
| --- | --- | --- | --- |
| v1/v2 | 精确 imported-symbol relation | 0 个新增必需项，0 个精确排名提升 | 结构存在但不能穿过最终选择边界 |
| v3 | 对一个精确来源候选增加固定 `0.04` bonus | Recall 增量 0，新增必需项 0 | 小幅权重不足以跨过 Top12 cutoff |
| v4 | 在线 planner dependency hints | 14 命中提升到 15 命中 | 方向有效，但收益不足且只覆盖一个仓库 |
| 最小 A/B attempt-005 | 同一 plan、embedding 和候选状态下，有界提升精确依赖目标 | 10 命中提升到 12 命中 | 首次达到本地 `+2` 门槛 |

因此，P15 最终解决的是：

> 让已被静态结构证实、但排名不足的 Python 直接依赖目标，在依赖意图明确时有机会穿过 Top12 cutoff，同时保护原 Top12 路径和 rank 1。

它不是通用调用图、通用语义推理或任意跨模块检索方案。

## 3. 证据边界

### 3.1 已观察通过

- 固定 2 个仓库、12 个查询的本地 baseline/P15 paired replay 完成；
- P15 比 baseline 多 2 个命中；
- 两个仓库各贡献 1 个新增命中；
- 没有丢失 baseline 已命中的目标；
- 总体 MRR@12 没有下降；
- 本地中位开销满足“相对不超过 10% 或绝对不超过 5 ms”的门槛；
- planner、embedding 和本地 replay 调用数符合 attempt-005 的固定预算。

### 3.2 未观察通过

- 12/12 fast-context 对比未完成；
- `P15 Recall@12 >= fast-context Recall@12` 未评估；
- v7 fresh 24 planner sample / 96 local replay 完整矩阵未执行；
- held-out outcome 未执行；
- v7 release 和 governance disposition 未生成；
- 当前提交上的 focused/full/CI ship gates 未全部通过；
- 默认用户配置上的 P15 收益未验证。

### 3.3 本地证据身份

以下 `.quality` 文件当前是本地、未跟踪证据。SHA-256 用于识别本次审计读取的确切字节：

| 文件 | SHA-256 |
| --- | --- |
| `.quality/p15-minimal-retrieval-attempt-005/attempt-summary.json` | `30a9c452c0e7e20c32493bcd80efea6a12e0da8cdb1ba54d01ecc0ad7035c594` |
| `.quality/p15-minimal-retrieval-attempt-005/local-arms.json` | `0c0e941476ab52215f5dea81d51273fadd31de201cbc6866cbe604948e9f32d8` |
| `.quality/p15-minimal-retrieval-attempt-006/attempt-summary.json` | `ba619e1d7f2ff352310d5ced24a811b42800f4b9cbfa523aab5608c48f5da1e2` |
| `tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json` | `f7fd4711cdc7ed049c2c7cff6dfa8eed871f44d1795ea4fd4b33b30dc0f88fcf` |

### 3.4 Task 0 clean-worktree 基线（2026-08-05）

本节记录修复开始前的入口状态，不把它提升为新的通过门。测试在由审计 HEAD 创建的
临时 detached clean worktree 中运行，Python/pytest 来自原工作树的既有 `.venv`；
没有执行 planner、embedding、fast-context、held-out 或其他网络调用。

Git 身份：

| 项目 | 值 |
| --- | --- |
| 来源分支 | `codex/p15-post-acceptance-remediation` |
| 临时 worktree 分支状态 | detached HEAD |
| 审计 HEAD | `c69e4be790921ac74bf2e7da1d7312b266798c5d` |
| 父提交 / P15 implementation commit | `974aadc32edc4a7cbebed70a9cacd13a286ed471` |

临时 worktree 创建后、运行测试前，`git status --short --ignored` 无输出。来源工作树
没有 tracked 修改；有本文和修复计划两个 untracked 文档，并保留既有 ignored
`.DS_Store`、`.context-search/`、`.pytest_cache/`、`.quality/`、`.venv/`、
`.worktrees/` 和 Python cache。Task 0 未清理或复制这些内容。

运行时与依赖身份：

| 项目 | 值 |
| --- | --- |
| Python | `3.14.6 (main, Jun 10 2026, 10:03:53) [Clang 21.0.0 (clang-2100.0.123.102)]` |
| Python executable | 来源工作树既有 `.venv/bin/python` |
| SQLite | `3.53.2` |
| pytest | `9.0.3` |
| pip | `26.1.2`（Python 3.14） |
| `pyproject.toml` SHA-256 | `6342b0bb2661fa6e99e51f068a8d6250474442112b20413d29581e369e8fa3cc` |
| `uv.lock` SHA-256 | `32f5b7c92ee1008efa9113ba2898a81fe79e7ce8a455530722b4fb22dcf3230e` |
| `pip freeze --all` SHA-256 | `898789b7ebf33d3d4fdff38505689127bd2551a07d9d4c0c6db0c7102d2bf442` |
| editable project identity | `context-search-tool @ c69e4be790921ac74bf2e7da1d7312b266798c5d` |

问题陈述列出的三个 `.quality` 文件不属于 tracked clean tree，所以在临时 worktree
中均为 absent；来源工作树中的既有文件经只读核对，字节哈希仍分别为
`30a9c4...`、`0c0e94...` 和 `ba619e...`。tracked v7 contract 在两个 worktree 中
均为 `f7fd47...`。因此，本节不会把 ignored evidence 误记为 clean-checkout 输入。

测试结果：

| 命令 | 退出码 | 摘要 |
| --- | ---: | --- |
| focused P15（本问题 P0-2 所列 7 个文件） | 1 | `280 passed, 1 failed in 0.99s`；唯一失败是 `test_p15_v7_attempt_contract_binds_candidate_runner_tests_and_gates` 的 candidate/runner/test SHA 绑定 |
| `.venv/bin/pytest -q -m "not slow"` | 2 | `6 deselected, 1 error in 2.72s`；`tests/test_profile_retrieval.py` 收集时无法导入顶层 `scripts` |
| `PYTHONPATH=.:src .venv/bin/pytest -q -m "not slow"` | 1 | `3683 passed, 113 failed, 5 skipped, 6 deselected in 82.39s` |

focused stop rule 没有触发：未观察到合同绑定之外的新 P15 产品行为失败。补充
`PYTHONPATH` full-suite 与此前记录的
`3721 passed, 65 failed, 5 skipped, 6 deselected, 10 errors` 不同，但两次总规模均为
3807；本次为 38 个更少的 passed、48 个更多的 failed、10 个更少的 errors。
可直接观察的输入差异包括 clean worktree 没有 `.quality/p13-run-root.txt` 等 ignored
evidence，以及当前 Python 3.14 / SQLite 3.53.2 与冻结 characterization 的
Python 3.13 / SQLite 3.51.2 不同。失败输出还包括历史 P15 v2/v3 contract、P5/P6/P8
冻结输入、P9 trace hash 和其他历史/运行时断言；Task 0 不重新分类或豁免它们，留给
Task 3 逐项处理。

## 4. 问题清单

### P0-1：验收状态与证据状态冲突

**现状**

- attempt-005 的本地四项门槛观察通过，但总状态是 `INCOMPLETE`；
- fast-context 在 `multidict-q02` 返回 `resource_exhausted`，只完成 7 个成功调用；
- `P15 Recall@12 >= fast-context Recall@12` 明确为 `NOT_EVALUATED`；
- attempt-006 在第 7 个 planner 调用返回 fallback 后停止，仍为 `INCOMPLETE`；
- tracked v7 contract 是 `DRAFT`、`execution_eligible=false`、`approval_receipt.received=false`。

**影响**

“P15 已验收”目前存在两种不兼容含义：

1. 本地 P15 对 baseline 的核心 A/B 收益通过；
2. 计划中定义的完整 comparator、held-out、release、governance 验收通过。

现有证据只支持第一种。

**关闭标准**

- 明确选择并记录唯一验收口径；
- 如果保留 fast-context 为硬门，完成同一冻结 manifest 的完整有效 attempt；
- 如果改为本地 A/B 验收，必须先修订并批准计划，不得在结果产生后静默豁免 comparator；
- 生成一个 tracked final disposition，绑定 attempt、候选提交、manifest、结果和所有门状态。

### P0-2：v7 合同未绑定最终实现

**现状**

当前合同保存的文件 SHA 与工作区中的 5 个文件不一致：

- `src/context_search_tool/dependency_replay.py`
- `src/context_search_tool/retrieval_core/context_expansion.py`
- `src/context_search_tool/retrieval_core/ranking.py`
- `tests/test_dependency_replay.py`
- `tests/test_exact_imported_symbol_bonus.py`

聚焦命令：

```bash
.venv/bin/pytest -q \
  tests/test_python_graph.py \
  tests/test_exact_imported_symbol_bonus.py \
  tests/test_dependency_replay.py \
  tests/test_p15_metric_replay.py \
  tests/test_p15_pre_corpus_governance.py \
  tests/test_p15_attempt_007_governance.py \
  tests/test_query_planner.py
```

结果：`280 passed, 1 failed`。唯一失败是 v7 candidate/runner/test SHA 绑定检查。

**影响**

合同描述的 candidate 不是实际产生 attempt-005 收益的确切实现，因而不能作为最终防篡改或可复现身份。

**关闭标准**

- 为最终 candidate 创建新的 attempt identity 或经批准的 append-only rebind；
- 重新计算完整 product/test projection；
- 合同的行为字段与实际实现逐项一致；
- 聚焦 P15 测试全部通过。

### P0-3：full-suite 和 CI 发布门没有关闭

**现状**

README 记录的直接测试入口：

```bash
.venv/bin/pytest -q -m "not slow"
```

在收集阶段因 `tests/test_profile_retrieval.py` 无法导入顶层 `scripts` 而失败。

补充仓库根目录到导入路径后：

```bash
PYTHONPATH=.:src .venv/bin/pytest -q -m "not slow"
```

结果：`3721 passed, 65 failed, 5 skipped, 6 deselected, 10 errors`。

失败包括旧 P15 v2/v3 封存合同、P5/P8/P13 冻结输入与临时证据、运行时 Python/SQLite 身份、P15 v7 哈希漂移等多类问题。该结果不能直接归因于一个 P15 产品缺陷，但它明确证明当前 full-suite ship gate 不成立。

**影响**

- 无法证明 P15 没有破坏受保护阶段；
- 旧封存验收测试和当前产品回归测试混在同一默认 suite，降低信号质量；
- 部分测试依赖已消失的 `/tmp` 证据或单一运行时版本，不具备干净环境可复现性。

**关闭标准**

- 修复默认 pytest 导入路径；
- 将历史只读封存验证与当前产品回归测试明确分层；
- 移除对易失 `/tmp` 路径的默认 suite 依赖，或把证据变成可获取、可校验的固定输入；
- 在声明支持的固定运行时上跑绿 focused、full suite 和 CI；
- 保存可审计的测试报告和运行时身份。

### P0-4：已验证路径不是默认产品路径

**现状**

默认配置为：

- `retrieval.consume_dependency_hints = false`；
- `query_planner.enabled = false`；
- embedding 使用 `hash-v1`；
- planner 如果启用，默认是本地 Ollama `qwen3.5:4b-mlx`。

产生 `+2` 收益的 attempt-005 使用 SiliconFlow Qwen planner、SiliconFlow BGE-M3 embedding，并显式对比 `consume_dependency_hints=false -> true`。

**影响**

普通用户使用默认配置时不会走经过收益验证的 P15 路径；仅合入代码不等于用户已获得 P15 的主要收益。

**关闭标准**

- 明确 P15 是实验性 opt-in 还是默认能力；
- 文档给出完整、可复制的受支持配置；
- 至少对一个准备发布的实际配置完成相同的 baseline/P15 验证；
- 若保持 opt-in，输出和 trace 能明确说明 P15 是否启用、为什么未生效。

### P1-1：端到端延迟和稳定性由在线依赖主导

**现状**

attempt-005 的 12 次 planner 调用：

- 最小延迟：5.704 s；
- 中位延迟：8.073 s；
- 最大延迟：9.302 s；
- 平均延迟：7.934 s。

相比之下，P15 本地 replay 中位延迟是 34.50 ms，P15 相对 baseline 只增加 1.51 ms。attempt-006 因一次 planner fallback 中止；attempt-005 因 fast-context `resource_exhausted` 无法完成。

**影响**

P15 本地算法不是主要性能瓶颈。用户感知延迟、验收可完成性和可用性主要受在线 planner、embedding 与 comparator 服务控制。

**关闭标准**

- 分别报告 planner、embedding、本地 replay 和端到端延迟；
- 产品运行允许严格验证失败后的可观察 fallback，而不是把整个查询变成无结果；
- 验收协议区分“产品 fallback 正常”与“实验因果样本不可用”；
- 为支持的部署形态定义超时、fallback 和可用率目标。

### P1-2：P15 覆盖范围较窄

**现状**

当前主要覆盖静态、仓库内、可唯一解析的 Python `from module import name [as alias]`，并要求目标对应一个现有顶层 `type`、`function` 或受支持的 `variable` signal。以下结构仍不在主要证明范围：

- `import module as m; m.attr`；
- star import 和动态 import；
- re-export 链；
- 方法和嵌套函数；
- 通用 Python 调用图和类型推断；
- 跨语言调用链；
- 目标未进入候选/关系扩展状态的场景。

单次依赖提升最多两个路径；planner 必须返回 `status=ok`、`dependency_intent=follow_imports` 和可用 hints；图读取故障时安全 no-op。

**影响**

当前 2 个仓库、12 个查询上的成功不能外推为一般 Python 跨模块检索已经解决。

**关闭标准**

- 在新的 candidate-blind 语料上按 failure taxonomy 报告不可表示、未解析、未获取、已获取但排名不足等比例；
- 只有某类残差在真实语料上重复出现并且有稳定收益时，才扩展语法或关系范围；
- 不通过放宽 TopK、图预算或无证据加权掩盖 coverage 问题。

### P1-3：局部排名和噪声仍可能退化

**现状**

attempt-005 中：

- `multidict-q05` 的 gold 从第 10 名降到第 11 名；
- P15 为该查询引入 `multidict/_compat.py`，移除 `towncrier.toml`；
- `anyio-q06` 在恢复 gold 的同时还引入 `src/anyio/_core/_testing.py`；
- 当前聚合 MRR 上升且无 Top12 命中损失，但没有证明每个查询的相关结果排名都不退化。

**影响**

“新增命中”和“局部排序质量”不是同一个门。只看总 Recall 可能隐藏个别查询的 rank 下降或额外关系邻居。

**关闭标准**

- 每个查询报告新增路径、移除路径、gold rank delta 和 relevance/noise 分类；
- 保留零必需项损失和 rank 1 保护；
- 对局部 rank 退化设置明确的可接受规则，而不是只依赖总体 MRR；
- held-out 验证必须使用同一规则。

### P2-1：证据、文档和产品状态没有统一入口

**现状**

- 最关键的 attempt-005/006 结果只存在于被忽略的 `.quality`；
- tracked v7 文档和合同仍写 DRAFT/未授权；
- README 没有说明 P15 的能力、启用条件、已验证配置和限制；
- commit message `complete P15 exact import retrieval` 比仓库内证据表达得更强。

**影响**

后续维护者无法仅从仓库跟踪内容判断 P15 是已发布、实验性、局部通过还是完整通过。

**关闭标准**

- 跟踪一份最终 disposition/summary，不包含秘密或源码正文；
- README 记录支持状态、配置和已知限制；
- 设计、合同、测试、结果和提交身份互相引用；
- 本地原始证据可保留在 `.quality`，但其必要投影和哈希必须进入 tracked summary。

## 5. 建议处理顺序

1. **先关闭证据一致性**：确定验收口径，绑定最终 candidate，生成 tracked disposition。
2. **恢复测试可信度**：修复默认 pytest 入口，分离历史封存测试与当前回归测试，跑绿 focused/full/CI。
3. **决定产品化状态**：明确 opt-in/default，补配置和 trace 可见性，并验证实际支持配置。
4. **再处理运行时瓶颈**：优化 planner 超时、fallback、缓存或调用策略；不要先调整 import bonus 数值。
5. **最后扩展覆盖**：依据新语料的 failure taxonomy 决定是否支持 re-export、module attribute、更多声明种类或其他语言。

## 6. P15 关闭定义

只有同时满足以下条件，P15 才能记录为完整关闭：

- 一个 tracked final disposition 明确写出 `ship`、`local_efficacy_only`、`reject` 或 `blocked`；
- disposition 绑定准确的候选提交、配置、manifest、结果和测试报告；
- 本地 paired efficacy 门全部通过；
- comparator 门完成，或经结果无关的批准修订后从硬门中移除；
- focused、full suite 和 CI 在声明运行时全绿；
- 合同哈希与最终实现一致；
- 默认或正式支持的 opt-in 配置有文档并经过验证；
- 剩余覆盖、在线依赖和局部排名风险被明确记录，不被描述为已解决能力。

在这些条件完成之前，推荐状态是：

> **P15 local efficacy observed; full acceptance and release closure pending.**

## 7. 参考

- [P15 v1 设计](2026-07-31-p15-python-exact-imported-symbol-relations-design.md)
- [P15 v3 设计](2026-08-01-p15-v3-exact-provenance-bonus-design.md)
- [P15 v7 设计](2026-08-02-p15-v7-minimal-online-causal-acceptance-design.md)
- [P15 v7 计划](../plans/2026-08-02-p15-v7-minimal-online-causal-acceptance-plan.md)
- [P15 最小检索 benchmark 计划](../plans/2026-08-02-p15-minimal-retrieval-benchmark-plan.md)
- [v7 attempt contract](../../../tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json)
- [默认配置](../../../src/context_search_tool/config.py)
- [P15 dependency promotion](../../../src/context_search_tool/retrieval_core/ranking.py)
- [P15 exact imported-symbol producer](../../../src/context_search_tool/python_graph.py)
