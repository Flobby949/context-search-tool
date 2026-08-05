# P15 本地有效性 disposition

日期：2026-08-05

状态：LOCAL EFFICACY ONLY

## 1. 决定

P15 当前唯一可支持的 disposition 是 **local_efficacy_only**。固定 2 个仓库、12 个查询的本地 paired replay 已观察到 dependency hint promotion 相对同状态 baseline 的局部收益；这不等于完整 comparator、held-out、发布或 CI 验收通过，也不授权把 P15 记录为已发布。

本 disposition 落实[问题陈述](./2026-08-03-p15-post-acceptance-problem-statement.md)所要求的诚实证据边界，并按[修复计划](../plans/2026-08-05-p15-post-acceptance-remediation-plan.md)保存一个无秘密、无源码正文的 tracked 投影。

## 2. 本地已观察结果

attempt-005 的本地双臂记录是 **COMPLETE**，但 attempt 整体仍为 **INCOMPLETE**。同一 plan、embedding、候选 roster 和 replay state 下，只切换 **consume_dependency_hints=false → true**，得到：

| 范围 | Baseline Recall@12 | P15 Recall@12 | Baseline MRR@12 | P15 MRR@12 | 中位延迟变化 | Baseline 命中损失 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 10/12（0.8333） | 12/12（1.0000） | 0.3154 | 0.3980 | +1.51 ms / +4.57% | 0 |
| anyio | 5/6（0.8333） | 6/6（1.0000） | 0.3583 | 0.4417 | +1.54 ms / +3.83% | 0 |
| multidict | 5/6（0.8333） | 6/6（1.0000） | 0.2726 | 0.3544 | +0.11 ms / +0.46% | 0 |

仓库输入固定为 anyio **003e5d6bc3eba8f4e75bf2b2b5fb3f7dd11e6330** 和 multidict **41c1b9144b13dcdfa4c18085aedc874cc9d24006**。

## 3. 尚未通过的边界

- fast-context 只得到 **7 success / 1 failed / 4 not run**，因此比较门是 **NOT_EVALUATED**；attempt-005 整体状态必须保持 **INCOMPLETE**。
- attempt-006 在 **multidict-q01** planner fallback 后停止，状态同样是 **INCOMPLETE**。
- v7 attempt-007 合同仍是 **DRAFT**、**execution_eligible=false**，没有形成可执行的最终候选合同。
- focused gate 在 remediation commit **668611066780426a203d81cd59c2b035b89a3b5b** 上观察到 **287 passed, 1 failed**，剩余项是 historical v7 contract binding；这个 commit 只标识 gate 观察点，不是 attempt-005 candidate 的身份倒填。full suite 未通过；正常 CI 尚未建立。
- 默认配置关闭 query planner 和 dependency hint consumption，并使用 **hash-v1** embedding；默认产品路径上的收益未验证。

这些门在后续任务真正关闭前，不得把本地有效性改写成完整验收、release-ready 或 ship-ready。

## 4. 候选身份与证据性质

tracked summary 记录审计 HEAD **c69e4be790921ac74bf2e7da1d7312b266798c5d** 和 P15 implementation commit **974aadc32edc4a7cbebed70a9cacd13a286ed471**，但 attempt-005 没有把实际 candidate commit 做加密绑定。因此：

**candidate_identity.status = "not_cryptographically_bound_by_attempt_005"**

当前 HEAD 或当前文件哈希不得被倒填成 attempt-005 当时已经绑定的候选身份。**local-efficacy-summary.json** 是生成于 **2026-08-05T03:10:22Z** 的诚实事后审计投影，不是追溯性防篡改证明。

原始 **.quality** artifact 仍是 ignored、local-only 证据；tracked summary 只保存其仓库相对路径和 SHA-256。默认测试只读取 tracked 文件，并不要求干净 checkout 中存在 **.quality**。若需要复核原始字节，应由显式 audit 流程完成，不能把它变成产品 suite 的隐式输入。

## 5. Promotion 模式复核

Task 1 的行为测试识别三种成功 promotion mode：**exact_source_hint**、**exact_target_hint** 和 **semantic_pair_fallback**。**disabled**、**graph_unavailable**、**intent_mismatch**、**missing_activation_hint**、**no_eligible_closed_candidate**、**planner_not_ok** 是独立的 no-op status，不是 promotion mode。attempt-005 的两个新增命中 **anyio-q06** 与 **multidict-q01** 都只能归类为 **semantic_pair_fallback**；两项均不 claim exact source 或 exact target。

## 6. Tracked 投影

[local-efficacy-summary.json](../../../tests/fixtures/p15_post_acceptance/local-efficacy-summary.json) 是本 disposition 的机器可检验投影。它冻结 attempt 状态、原始 artifact 哈希、DRAFT 输入、仓库提交、overall/per-repository 指标、fast-context 计数、门状态、候选身份限制和 promotion 复核结果。其 canonical bytes 与 closed shape 由 [test_p15_post_acceptance_disposition.py](../../../tests/test_p15_post_acceptance_disposition.py) 验证。

## 7. Clean baseline 失败分类

本节是 Task 3 追加的测试分类账，不改写前述 Task 2 的证据观察点。在固定
commit **2426e5c2437a62208d723435c04bf0aefdd11390** 的 clean worktree 上，
rooted full observation 为 **3700 passed, 112 failed, 5 skipped, 6
deselected**。112 个失败节点各自只进入一个初始类别：

| 初始类别 | 失败节点数 |
| --- | ---: |
| product/current | 3 |
| archival | 105 |
| runtime-pinned | 2 |
| missing durable fixture | 2 |
| contamination | 0 |
| unsupported runtime | 0 |

完整的 112 节点闭集见
[failure-classification.json](../../../tests/fixtures/p15_post_acceptance/failure-classification.json)。
它逐项保存 `node_id`、唯一 `category` 和非空 `disposition`，同时冻结上述 baseline
commit、命令和结果；canonical JSON bytes 与 closed shape 由
`tests/test_p15_failure_classification.py` 检验。

### 7.1 当前产品失败及处置

三个 `product/current` 节点均保留在产品门，并做了定点测试修复：

| 节点 | 处置 |
| --- | --- |
| `tests/test_exploration_boundaries.py::test_only_reviewed_production_change_roots_are_used` | 将 `src/context_search_tool/dependency_replay.py` 加入精确、单文件的 P15 reviewed-production overlay，并新增 overlay 闭集断言。 |
| `tests/test_p5_graph_contract.py::test_fresh_and_reverse_order_structural_projections_match_expected_bytes[p5_generic_tests]` | 重新冻结当前 producer 的 canonical generic-tests 投影；新增断言，将四个 Python module assignment 明确固定为 variable signals。 |
| `tests/test_retrieval_trace_pipeline.py::test_trace_repository_reports_missing_index_without_changing_bundle` | 测试 seam 从旧的 `Path.stat` 对齐到当前 missing-index preflight 实际使用的 `Path.exists`；未改变产品执行路径。 |

### 7.2 Archival 失败源与最终 marker 布局

`archival=105` 只来自以下 5 个 archival 失败源模块，而不是来自最终 marker
布局中的全部模块：

| 失败源模块 | archival 失败节点数 |
| --- | ---: |
| `tests/test_p13_bge_provider_measurement.py` | 16 |
| `tests/test_p15_python_import_symbol_acceptance.py` | 4 |
| `tests/test_p15_v2_python_import_symbol_acceptance.py` | 48 |
| `tests/test_p15_v3_exact_provenance_bonus_acceptance.py` | 36 |
| `tests/test_p15_metric_replay.py` | 1 |

最终 gate 使用以下 9 个最终 marker 模块；它们不属于默认产品发布门：

- `tests/test_p8_real_python_graphs_acceptance.py`
- `tests/test_p13_bge_provider_measurement.py`
- `tests/test_p14_definition_owner_acceptance.py`
- `tests/test_p15_python_import_symbol_acceptance.py`
- `tests/test_p15_v2_python_import_symbol_acceptance.py`
- `tests/test_p15_v3_exact_provenance_bonus_acceptance.py`
- `tests/test_p15_pre_corpus_governance.py`
- `tests/test_p15_attempt_007_governance.py`
- `tests/test_p15_metric_replay.py`

后四个非失败源模块进入 marker 布局，是因为它们整体属于历史验收或治理审计；这不改变
clean baseline 中 105 个 archival 失败节点的来源和计数。

### 7.3 Runtime 与 durable fixture 边界

两个 `runtime-pinned` 失败节点位于
`tests/test_retrieval_core_characterization.py`，只在冻结的 Python、OS 和 SQLite
身份下有意义。

P8 的两个 missing durable fixture 节点是：

- `tests/test_p8_real_python_graphs_acceptance.py::test_hash_v4_requires_static_descriptor_identity_and_zero_ollama`
- `tests/test_p8_real_python_graphs_acceptance.py::test_bge_truncation_bounds_every_embedded_text`

它们在初始分类中仍唯一计为 `missing durable fixture=2`。当前 hash factory 的离线
行为已迁移到独立产品测试
`tests/test_embeddings_vector_store.py::test_default_hash_provider_factory_is_offline`；当前
BGE head/tail truncation 行为也由独立产品测试
`tests/test_embeddings_bge.py::test_bge_provider_applies_exact_head_tail_transform_at_2001`
和
`tests/test_embeddings_bge.py::test_bge_provider_prepares_6924_dense_cjk_by_exact_code_points`
覆盖。随后整个 P8 历史模块转入 archival gate。因此这两个节点在门的最终布局中随模块
执行，但不重复计入 archival=105，也不把易失 pointer 重新包装成 clean-checkout
产品 fixture。

### 7.4 修复后观察

本次验证身份记录为：

- verification_base_commit = `2426e5c2437a62208d723435c04bf0aefdd11390`
- verification_candidate = `uncommitted Task 3 working tree immediately before the documentation-only observation update`

candidate 当时是未提交工作树，因此没有为它虚构 commit 或 tree 标识。修复后的严格
收集为 **3868 tests collected**。当前产品表达式
`not slow and not archival_acceptance and not runtime_pinned` 的观察结果为
**3342 passed, 5 skipped, 521 deselected**。这两个数字是 Task 3 的后置验证，
不替换前文 Task 2 的 focused gate 或 attempt 证据身份。
