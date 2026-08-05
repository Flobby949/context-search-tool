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
