# Soft Rerank：修复 rank_tier 绝对压制 score 的排序错位

- 分支：`codex/query-planner`
- 范围：`src/context_search_tool/retrieval.py` + `tests/test_retrieval_pipeline.py`
- 不碰：planner、embedding、Java plugin
- 日期：2026-06-14

## 1. 问题（已读代码验证）

默认 BGE-M3 + planner 开启时，排序结果错位：高分 direct 命中被低分
relation expansion 压在后面。典型 case：`SmsUtils` 分数 2.401 排第 4，
而低分的 `WxMiniLoginClient/AuthService/RedisCache` 排在前面。

### 根因（已定位到行）

`retrieval.py:747-756` 的排序键：

```python
return sorted(
    ranked,
    key=lambda item: (
        item.rank_tier,        # ← 第一排序键，整数 0-4，绝对压过 score
        -item.score,
        item.chunk.file_path.as_posix(),
        item.chunk.start_line,
        item.chunk.chunk_id,
    ),
)
```

`rank_tier` 由 `_rank_tier` (`retrieval.py:1050`) 给出粗粒度整数：

| 条件 | base_tier |
|------|-----------|
| signal 且 endpoint | 0 |
| relation > 0 | 1 |
| signal（非 endpoint） | 2 |
| 其它 | 3 |
| planner-hint-only 再 +1 | base+1 |

SmsUtils 走 `_chunk_has_signal_kind != endpoint` → `base_tier=2`；relation
扩出来的候选 → `base_tier=1`。`1 < 2`，所以低分 relation **整体**排在
SmsUtils 前面，`-item.score` 根本来不及参与比较。这就是错位机制。

**关键结论：headline bug 纯粹是排序问题。** 把 `rank_tier` 从主排序键移走，
这条 case 立刻修好。boost/penalty 是在此之上的精修，不是修 bug 的必要条件。

## 2. 现有可复用资产（不要重复造）

代码里已存在分类/provenance 机制，新逻辑必须建在它们之上，避免双套判断漂移：

| 计划提到的新函数 | 已存在的等价物 | 行号 |
|------------------|----------------|------|
| `_is_original_direct` | 不能直接等价于 `_has_original_query_evidence`；需新增 direct-only helper | `retrieval.py:1085` |
| `_is_planner_only_relation` | `_is_planner_hint_only` | `retrieval.py:1099` |
| planner/original relation 标记 | `score_parts["planner_relation"]` / `["original_relation"]` | `retrieval.py:604-607` |
| planner-hint 判定 | `_has_planner_hint` | `retrieval.py:1073` |

注意：`_has_original_query_evidence` 包含 `original_relation`，只能作为"有原始 query
来源"的宽口径 helper。判断 `original_direct` 时必须使用 direct-only helper，避免把
relation expansion 误当成 direct 命中。

`_combined_score` (`retrieval.py:1026`) **未归一化**——semantic*0.55 等加权后可
到 2.4+。这是 penalty/boost 量级必须对齐的原因（见 §4）。

## 3. 目标排序语义

默认 BGE-M3 + planner 开启时：

- 高分 semantic/lexical/signal 不被低分 relation expansion 压住。
- relation expansion 只补链路，不抢 Top1/Top3。
- planner-only（无原始证据）的结果**不得**压过 strong original_direct——见下方
  排序性格抉择。
- 输出能解释"为什么排在这里"，且展示的 score 与排序一致。

### 排序性格（决策：混合 = rerank 主键 + planner-only 上界 clamp）

纯 soft（只靠 penalty 拉开名次）无法**保证** planner-only 不超过 strong
original_direct——高 rerank_score 的 planner-only 仍可能压过 direct，这与目标冲突。
纯 hard（evidence_class 当主键）又退回 `rank_tier` 那种粗粒度压制。取折中：

- 主键仍是 `rerank_score`，保留 soft 的细粒度区分。
- 但对所有 planner-only / weak 结果施加**动态可证明上界**：
  `planner_direct` / `planner_relation` / `weak_or_generic` 的 `rerank_score`
  clamp 到 `< min(本轮 strong original_direct 的 rerank_score)`。
- 结果：original direct 之间、planner 之间各自按 rerank_score 细排；但
  planner-only **永不**穿到 strong original_direct 之上。这是 P2 语义冲突的解。
- 如果本轮没有 strong original_direct，不做 planner-only clamp，避免 planner
  召回在原始 query 召回失败时被误杀。

新排序键：

```text
rerank_score(已 clamp)  ->  evidence_class  ->  score  ->  path  ->  start_line  ->  chunk_id
```

clamp 已把"硬边界"折进 `rerank_score`，所以 `evidence_class` 仍只做精确并列
tiebreaker，不会自相矛盾。`rank_tier` 保留为 explain/debug 字段，不再决定顺序。

### 5 类证据分层（建在 §2 现有函数之上）

> ⚠️ 分类**先判 relation 再判 direct**。`_has_original_query_evidence`
> (`retrieval.py:1085`) 的 key 列表里**包含** `"original_relation"`，若直接调它
> 判 `original_direct`，原始 relation 候选会被误归到 direct 类，破坏
> "original_relation 不压高分 direct"的语义。需要 direct-only helper（排除
> `original_relation` 的判定），或在 classifier 里按下表从上到下短路匹配。

| class | 定义（按此顺序判定） | 优先级 |
|-------|------|--------|
| `original_relation` | `score_parts["original_relation"] > 0` —— **先判这条** | 可进 Top5，不压高分 direct |
| `planner_relation` | `score_parts["planner_relation"] > 0` 且非 original_relation | 默认降权 + 上界 clamp（当前噪声主源） |
| `original_direct` | direct-only evidence：semantic/lexical/path_symbol/signal/token_coverage（**不含** original_relation） | 最高 |
| `planner_direct` | planner hint 直接命中 lexical/path/symbol/signal，无 relation | 中；有 strong original_direct 时上界 clamp |
| `weak_or_generic` | 仅泛词 / 低 token overlap / 无原始证据 | 有 strong original_direct 时上界 clamp，尽量不进 Top5 |

### 输出契约（决策：score = rerank_score 且 score_parts 全暴露）

避免 MCP/JSON 消费端看到"低 score 排在高 score 前"：

- `RetrievalResult.score` / `_ExpandedResult.score` = **rerank_score**（展示与排序一致）。
- `score_parts` 只暴露数值项：`combined_score`（旧分，调试用）、`rerank_score`、
  主要 boost/penalty 明细，以及可选的数值 `evidence_priority`。
- `evidence_class` 是字符串，不放进 `score_parts`，避免破坏当前
  `dict[str, float]` 契约；它保存在 `_RankedChunk` / `_ExpandedResult` 字段中，
  并通过 reason 文本解释给 Markdown/JSON 消费端。
- `_reasons` 补一句 rerank 归因。
- 影响面：`_ExpandedResult` 构造 (`retrieval.py:797`)、merge 后重建
  (`retrieval.py:922`)、`query()` 里 `RetrievalResult` 组装 (`retrieval.py:161`)。

## 4. rerank_score 公式（决策：先归一化再加减权重）

```text
base = normalize(combined_score)            # 归一到 [0,1]，消除 2.4+ 量级问题
rerank_score = base
  + original_direct_boost                   # semantic/lexical/path_symbol/signal/token_coverage 命中
  + endpoint_or_controller_boost
  + implementation_chain_boost              # 有真实调用链支持（has_relation_support）
  - planner_only_penalty                    # _is_planner_hint_only 为真
  - relation_only_penalty                   # 仅 relation、无 original evidence
  - generic_symbol_penalty                  # Service/Controller/Manager/message/device 等泛词

# 然后按 §3 排序性格施加动态上界 clamp：
if evidence_class in {planner_direct, planner_relation, weak_or_generic} and planner_ceiling is not None:
    rerank_score = min(rerank_score, planner_ceiling)
```

**归一化方式（实现时确定具体值，先写测试驱动）：** 因 `_combined_score`
理论上无硬上界，用 min-max 或除以本次结果集 max 把 base 收进 [0,1]，再让
boost/penalty 用 ~0.05-0.3 的加法量级。归一化后量级才可比，否则 -0.3 penalty
对 2.4 分几乎无效，rerank 会**静默不改名次**——这是唯一可能"看似实现却没生效"
的点，回归测试必须覆盖。

**`planner_ceiling` 取值：** 不使用全局常量；常量下界不可靠，因为
`token_coverage` 可能随 query token 数变得很小，lexical/path/signal 也没有稳定理论
下界。实现时先算所有候选的 unclamped rerank，再找本轮 strong original_direct 的最小
unclamped rerank：

```text
strong_original_direct =
  original_direct 且 (
    semantic > 0
    or lexical > 0
    or path_symbol > 0
    or signal > 0
    or token_coverage >= 0.5
  )

planner_ceiling =
  min(strong_original_direct.rerank_score) - 1e-6
```

如果没有 strong original_direct，`planner_ceiling = None`，planner-only 不 clamp。
这把 §3 的硬边界变成可单测的不变式：
`max(planner-only rerank) < min(strong original_direct rerank)`。

## 5. 实施步骤

> 决策：步骤 1-4 为第一批（含两处排序点 + 契约）；步骤 5（收窄 expansion）
> 拆成第二批，smoke 后再定。

### 批次一：soft rerank（本次落地）

**步骤 1 — 先写失败测试** (`tests/test_retrieval_pipeline.py`)

照现有 harness（`replace_relations` + 直接调 `_relation_expansion_candidates`，
见 line 247/414/503）加 rerank 回归：

1. 高分 direct（如 score 2.4 的 signal chunk）必须排在低分 relation-only 前面
   —— 直接复现 SmsUtils case。
2. planner-only relation（`_is_planner_hint_only` 为真）不能压过 strong original direct
   —— 断言 §4 不变式 `max(planner-only) < min(strong original_direct)`。
3. planner_direct（例如 `planner_signal` / `planner_lexical`）同样不能压过
   strong original direct，避免只修 relation 漏掉 direct planner 噪声。
4. 没有 strong original_direct 时，planner-only 不 clamp，仍可进入结果，保证召回。
5. endpoint/controller 有 boost，但不能无视分数（高分非 endpoint 仍可超低分 endpoint）。
6. relation expansion 仍能补出 Service/Impl，不被完全杀掉。
7. **归一化生效**：构造 base 量级差异大的两个候选，验证 penalty/boost 确实改变名次
   （守住 §4 的静默失效风险）。
8. **二次排序一致**（P1）：经 `query()` 全链路（含 `_merge_overlapping_results`）
   后，`visible_results` 顺序仍与 rerank 一致——复现并锁死"被 tier 压回去"。
9. **original_relation 不误分**（P1）：构造 `original_relation>0` 的候选，断言
   `_evidence_class` 返回 `original_relation` 而非 `original_direct`。
10. **输出契约**（P2）：`RetrievalResult.score == rerank_score`；
    `score_parts` 含 `combined_score` / `rerank_score` 等数值项，但不含字符串
    `evidence_class`。

先跑，确认全红。

**步骤 2 — evidence classifier（复用现有函数 + direct-only helper）**

在 `retrieval.py:1050` 附近加薄封装：

- `_evidence_class(score_parts) -> str`：按 §3 表**从上到下短路**，先判
  `original_relation` / `planner_relation`，再判 direct。
- `_has_original_direct_evidence(score_parts) -> bool`：**新增 direct-only**
  helper，复制 `_has_original_query_evidence` 但**排除** `"original_relation"`
  key（修 P1 误分）。`_has_original_query_evidence` 本身保留不动（其它调用点仍用）。
- `_has_strong_original_direct_evidence(score_parts) -> bool`：用于动态
  `planner_ceiling`，只把 semantic/lexical/path_symbol/signal 或较高
  `token_coverage` 当成足够强的原始 direct 证据。
- `_generic_hint_penalty(chunk, score_parts) -> float`。
- `_rerank_score(score, score_parts, chunk, *, planner_ceiling) -> float`（§4 公式 + clamp）。

**步骤 3 — 替换主排序策略** (`retrieval.py:747`)

- `_rank_chunks` 新排序键 `rerank_score(clamp) -> evidence_class -> score -> path -> start_line -> chunk_id`。
- `_RankedChunk` 带上 `rerank_score` / `evidence_class`（供下游二次排序与展示）。
- `_rank_chunks` 分两步计算：先为所有候选计算 unclamped rerank 和 evidence class，
  再按本轮 strong original_direct 计算 `planner_ceiling`，最后对 planner-only /
  weak 类应用 clamp 并排序。
- `rank_tier` 不再进主键；保留供 explain/debug。

**步骤 4 — 同步第二处排序 + 输出契约**（P1 + P2，**不可省**）

- `_ExpandedResult` 增加 `rerank_score` / `evidence_class` 字段；构造点
  (`retrieval.py:797`)、merge 后重建点 (`retrieval.py:922`) 一并透传。
- `_merge_overlapping_results` (`retrieval.py:966`) 排序键换成
  `rerank_score(clamp) -> evidence_class -> score -> path -> start_line`，
  不再用 `rank_tier`。**这是 P1 漏层的核心**：否则 `visible_results =
  expanded[:final_top_k]` 会把 §3 排序压回去。
- `_merge_expanded_result` (`retrieval.py:991`) 的 `score=max(left,right)`
  同步改为按 rerank_score 选优（保证合并后仍取 rerank 更高的那条的归因）。
- `query()` 组装 `RetrievalResult` (`retrieval.py:161`)：`score = rerank_score`，
  `score_parts` 暴露 `combined_score` / `rerank_score` / boost·penalty 等数值明细；
  `evidence_class` 不进 `score_parts`，由字段和 reason 承载。
- `_reasons` (`retrieval.py:1150`) 补一句 rerank 归因。
- 跑步骤 1 的 10 条测试转绿。

### 批次二：收窄 relation expansion（smoke 后再定，可能不需要）

仅当批次一 smoke 后噪声仍明显才做。改的是"哪些候选存在"，与排序解耦：

- 只让强 direct candidate 触发 expansion：有 original evidence，或 `score >= 0.35`。
- planner-only relation 限数量，且必须有 token overlap 或真实 symbol 支持。
- 位置：`_relation_expansion_candidates` (`retrieval.py:519`)、
  `_candidate_relation_seed` (`retrieval.py:642`)。
- 常量：`_MIN_RELATION_CONFIDENCE=0.5` / `_RELATION_SCORE_DECAY=0.8` (`retrieval.py:37-38`)。

一批一改，便于归因是哪个改动动了哪条指标。

## 6. 验收

### BGE-M3 smoke（operation-client-api，三条 query）

- `账号密码登录注册` Top5 ⊇ {`AuthService`,`AuthServiceImpl`,`AuthController`,`AccountLoginDto`,`User`} 至少 4 个。
- `驿站设备列表` Top5 ⊇ {`StationController`,`StationService`,`StationServiceImpl`,`StationEquipmentService`,`StationEquipmentServiceImpl`} 至少 4 个。
- `发布意见反馈 发送短信` Top5 ⊇ {`FeedbackServiceImpl`,`SmsUtils`,`FeedbackController`,`FeedbackService`,`FeedbackDto`} 至少 4 个。
- `WxMiniLoginClient/AuthService/RedisCache` **不得**进入"反馈短信"Top3。

### 完整验证

```bash
pytest tests/test_retrieval_pipeline.py -v
pytest tests/test_query_planner.py -v
pytest -q
# + BGE-M3 operation-client-api smoke
# + Fast Context 三条对照（人工质量比较，不作 CI 阻塞）
```

## 7. 风险

- **relation 降权过狠 → 调用链补全变弱。** 缓解：不删 expansion；只降
  `planner_relation`，`original_relation` 保留。批次二独立验证，便于回退。
- **归一化/量级没对齐 → rerank 静默失效。** 由步骤 1 第 5 条测试守住。
- **双套分类逻辑漂移。** 由步骤 2"复用现有函数"约束。
