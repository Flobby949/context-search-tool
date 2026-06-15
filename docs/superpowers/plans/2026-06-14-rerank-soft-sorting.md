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
rerank_score(已 clamp)  ->  evidence_priority(数值0-4)  ->  score  ->  path  ->  start_line  ->  chunk_id
```

clamp 已把"硬边界"折进 `rerank_score`，所以 `evidence_priority`（数值 0-4，见下表）
仅做精确并列 tiebreaker，不会自相矛盾。`rank_tier` 保留为 explain/debug 字段，不再决定顺序。

> ⚠️ **P2 修正**：从字符串 `evidence_class` 改为数值 `evidence_priority` 作为排序键，
> 避免字典序隐式约束（如 "original_direct" > "planner_relation" 按字母排序不符合语义优先级）。
> `evidence_class` 字符串仍保留用于 reason 解释和调试，但排序键使用明确的数值优先级。

### 5 类证据分层（建在 §2 现有函数之上）

> ⚠️ 分类**按优先级表从 priority 0 向下短路**。`_has_original_query_evidence`
> (`retrieval.py:1085`) 的 key 列表里**包含** `"original_relation"`，若直接调它
> 判 `original_direct`，原始 relation 候选会被误归到 direct 类，破坏
> "original_relation 不压高分 direct"的语义。需要 direct-only helper（排除
> `original_relation` 的判定）保证纯 relation chunk 不误入 direct 类。
> **双证据 chunk**（如 lexical>0 且 original_relation>0，由 `_merge_candidates`
> 合并产生）被 direct-only helper 判定为 original_direct，符合"direct 命中优先"语义。

| class | 定义（按此顺序判定） | 优先级 | 数值优先级（用于排序） |
|-------|------|--------|--------|
| `original_direct` | direct-only evidence：semantic/lexical/path_symbol/signal/token_coverage（**不含** original_relation） | 最高；不受 clamp | 0（最优先） |
| `original_relation` | `score_parts["original_relation"] > 0` —— **先判这条** | 补链路；有 strong original_direct 时上界 clamp | 1 |
| `planner_direct` | planner hint 直接命中 lexical/path/symbol/signal，无 relation | 中；有 strong original_direct 时上界 clamp | 2 |
| `planner_relation` | `score_parts["planner_relation"] > 0` 且非 original_relation | 默认降权 + 上界 clamp（当前噪声主源） | 3 |
| `weak_or_generic` | 仅泛词 / 低 token overlap / 无原始证据 | 有 strong original_direct 时上界 clamp，尽量不进 Top5 | 4（最低） |

> ⚠️ **设计张力（可接受的边角）**：`original_direct` 类只要 `token_coverage > 0` 即触发（L114），
> 但 `_has_strong_original_direct_evidence`（用于 ceiling）要求 `token_coverage >= 0.5`。
>
> **后果**：`token_coverage=0.1` 的 chunk 既是 `original_direct`（priority 0，不受 clamp）
> 又不算 strong（不定义 ceiling）。这意味着一个几乎没命中的 direct chunk 优先级高于
> 真实的 `original_relation`（priority 1）。
>
> **实践影响**：罕见（rerank 主键 `-rerank_score` 会把弱 direct 压下去，priority 只在
> 精确并列时起作用）。但如遇到精确并列，弱 direct 会盖过真 relation——可接受的边角，
> 代价是避免引入更多分类（如 `strong_original_direct` vs `weak_original_direct`）。
>
> **如需修复**：将 `original_direct` 类也要求 strong 门槛（如 `semantic>0 or lexical>0.3 or token_coverage>=0.5`），
> 不达标的掉进 `weak_or_generic`。批次一暂不改，smoke 后若发现弱 direct 噪声再调整。

> ⚠️ **P1 修正：strong original_direct 必须有阈值，不等同于任意 direct evidence。**
> 当前 lexical/FTS、path_symbol 和 token_coverage 只要有一点命中就会产生正分；如果
> `_has_strong_original_direct_evidence` 也用 `lexical > 0` / `path_symbol > 0` /
> `signal > 0`，弱泛词 direct 会错误定义 `planner_ceiling`，把真正有价值的
> planner/relation 召回压住。批次一实现时保留 `original_direct` 的宽口径分类，
> 但 ceiling 只由 strong direct 触发（见 §4 阈值），并用单测覆盖
> "weak lexical 不触发 clamp"。

> ⚠️ **P1 修正**：`original_relation` 也纳入上界 clamp 机制。虽然它来自原始 query，
> 但语义上仍是"relation expansion 补链路"，不应压过高分 direct 命中抢 Top1/Top3。
> clamp 逻辑从 `{planner_direct, planner_relation, weak_or_generic}` 扩展为
> `{original_relation, planner_direct, planner_relation, weak_or_generic}`，
> 只有 `original_direct` 不受 clamp 约束。

### 输出契约（决策：score = rerank_score 且 score_parts 全暴露）

避免 MCP/JSON 消费端看到"低 score 排在高 score 前"：

**最终决策（P1 兼容性权衡）：**

- `RetrievalResult.score` / `_ExpandedResult.score` = **rerank_score**（展示与排序一致）。
- `score_parts` 暴露：`combined_score`（旧分，调试/兼容用）、`rerank_score`、
  主要 boost/penalty 明细，以及可选的数值 `evidence_priority`（0-4，见 §3 表格）。
- `evidence_class` 是字符串，不放进 `score_parts`，避免破坏当前
  `dict[str, float]` 契约；它保存在 `_RankedChunk` / `_ExpandedResult` 字段中，
  并通过 reason 文本解释给 Markdown/JSON 消费端。
- `_reasons` 补一句 rerank 归因。
- 影响面：`_ExpandedResult` 构造 (`retrieval.py:797`)、merge 后重建
  (`retrieval.py:922`)、`query()` 里 `RetrievalResult` 组装 (`retrieval.py:161`)。

> ⚠️ **P1 兼容性决策**：直接将 `RetrievalResult.score` 改为 `rerank_score`。
>
> **理由**：
> - 当前是内部工具，无外部 API 稳定性承诺，可承受一次性破坏性变更
> - "展示分与排序分不一致"是更严重的用户困惑，必须修复
> - `score_parts["combined_score"]` 保留旧值，需要的消费端可显式读取
>
> **兼容计划**：
> 1. 步骤 4 实施前先 grep 所有测试用例中的 `result.score` / `.score >` / `.score <` 断言
> 2. 更新测试断言为 `result.score_parts["combined_score"]`（若需旧语义）或接受新语义
> 3. 检查 MCP tool 的 JSON schema 是否有 score 字段说明，若有需同步更新注释
> 4. 如发现无法一次性迁移的外部消费端（步骤 4 实施时确认），回退到后备方案：
>    保留 `score = combined_score`，新增 `display_score = rerank_score`，
>    排序键/展示改用 `display_score`，一个迭代后再切换 `score` 语义
>
> **阻塞条件**：步骤 4 执行前必须完成兼容计划 1-3，否则不得提交。

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
if evidence_class in {original_relation, planner_direct, planner_relation, weak_or_generic} and planner_ceiling is not None:
    rerank_score = min(rerank_score, planner_ceiling)
```

**归一化公式（严格定义，消除边界歧义）：**

```python
def normalize_score(scores: list[float]) -> list[float]:
    """
    将 combined_score 归一化到 [0, 1]，使 boost/penalty 量级可比。

    边界条件：
    - 全 0：返回全 0（无需 boost/penalty，原本就无区分度）
    - 全相等（非零）：返回全 1（base 无区分度，让 boost/penalty 决定）
    - 含负值：先 clip 到 0（combined_score 理论非负，防御性处理）
    - 含 NaN/inf：clip 到 0（防御异常传播）
    - 单一候选：返回 1（无需归一化）
    - 正常情况：score / max(scores)，保留相对比例
    """
    if not scores:
        return []

    # 防御性：clip 异常值（NaN/inf/负数）到 0
    scores = [max(0.0, s) if not (math.isnan(s) or math.isinf(s)) else 0.0 for s in scores]
    max_score = max(scores)

    if max_score == 0.0:
        return [0.0] * len(scores)  # 全 0

    return [s / max_score for s in scores]  # 正常归一化
```

> ⚠️ **P2 修正**：明确归一化的数学边界条件和退化分支，避免实现差异导致测试抖动。
> 全 0 / 全相等 / 单候选等边界 case 必须有确定行为，否则测试 #8（归一化生效）无法稳定验证。
>
> ⚠️ **P3 强化（可选）**：增加 NaN/inf 防护。虽然 `_combined_score` 理论不应产生异常值，
> 但防御性编程避免异常传播污染整个 rerank pipeline。如遇 NaN/inf，treat as 0 并在
> `_reasons` 补充 "invalid score detected" 说明（实现时可选，测试非必须覆盖）。

**归一化方式（实现时确定具体值，先写测试驱动）：** 因 `_combined_score`
理论上无硬上界，需归一到 [0,1] 再让 boost/penalty 用 ~0.05-0.3 的加法量级。

**推荐用 `score / max(scores)` 而非 min-max `(score - min) / (max - min)`**：
- `score / max` 保留相对比例，不归零，对离群高分稳健
- min-max 在有 pathological 高分（如 2.4 与其余 0.1-0.3）时会把非离群值压到 [0, ε]，
  导致 penalty/boost 的 ±0.05~0.3 相对放大失衡
- 测试 #8 必须覆盖离群场景（如 `[0.1, 0.2, 2.4]`）验证归一化稳健性

归一化后量级才可比，否则 -0.3 penalty 对 2.4 分几乎无效，rerank 会**静默不改名次**
——这是唯一可能"看似实现却没生效"的点，回归测试必须覆盖。

**`planner_ceiling` 取值：** 不使用全局常量；常量下界不可靠，因为
`token_coverage` 可能随 query token 数变得很小，lexical/path/signal 也没有稳定理论
下界。实现时先算所有候选的 unclamped rerank，再找本轮 strong original_direct 的最小
unclamped rerank：

```text
strong_original_direct =
  original_direct 且 (
    semantic >= 0.35
    or lexical >= 0.25
    or path_symbol >= 1.0
    or signal >= 0.5
    or token_coverage >= 0.5
  )

planner_ceiling =
  min(strong_original_direct.rerank_score) * (1.0 - 1e-6)
```

如果没有 strong original_direct，`planner_ceiling = None`，planner-only 不 clamp。
这把 §3 的硬边界变成可单测的不变式：
`max(planner-only rerank) < min(strong original_direct rerank)`。

> ⚠️ **P1 修正：阈值必须写进测试。** 至少覆盖两类边界：
> 1. `lexical=0.05` / `token_coverage=0.1` 这种弱 direct 仍可归为
>    `original_direct`，但**不触发** `planner_ceiling`。
> 2. `lexical>=0.25` 或 `signal>=0.5` 的 strong direct 才触发 clamp。
> 这些阈值是批次一的实现常量；若 smoke 发现过严或过松，调整常量必须伴随同名测试更新。

> ⚠️ **P2 修正**：从 `- 1e-6` 改为 `* (1.0 - 1e-6)`，使用相对 epsilon 而非绝对值。
> 理由：防止 min(strong_direct) 极小时 `x - 1e-6` 变成负数，导致 planner-only
> 被压成负分。相对 epsilon 保证 ceiling 非负且与 x 同量级，避免浮点边界失效。
>
> **平局策略（严格 < 的 tiebreak）**：当 clamped rerank_score 出现平局时，
> 排序键的后续项（`evidence_priority` 数值优先级、`score`、`path`、`start_line`）
> 保证稳定全序，不会出现不确定排序。`evidence_priority` 已在 §3 表格定义为
> 0（original_direct）到 4（weak_or_generic）的数值，直接用于排序键第二位。

## 5. 实施步骤

> 决策：步骤 1-4 为第一批（含两处排序点 + 契约）；步骤 5（收窄 expansion）
> 拆成第二批，smoke 后再定。

### 批次一：soft rerank（本次落地）

**步骤 1 — 先写失败测试** (`tests/test_retrieval_pipeline.py`)

用现有 harness（`replace_relations` + `_relation_expansion_candidates`，见 line
247/414/503）构造候选，然后**调用 `_rank_chunks` 或 `query()` 全链路**进行排序断言：

> ⚠️ **关键修正**：`_relation_expansion_candidates` (retrieval.py:519-635) 只产生候选，
> 不做排序。排序发生在 `_rank_chunks` (retrieval.py:747) 和
> `_merge_overlapping_results` (retrieval.py:966)。排序测试必须调用这两个函数之一，
> 不能只调 `_relation_expansion_candidates` 断言顺序。

测试用例：

1. 高分 direct（如 combined_score 2.4 的 semantic/path/signal 组合 chunk）必须排在低分 relation-only 前面
   —— 直接复现 SmsUtils case。**调用 `_rank_chunks`**。
   > ⚠️ **测试构造注意**：`_rank_chunks` (L736) 会从 `score_parts` 重算 `combined_score`，
   > 忽略 `RetrievalCandidate.score`。而 `_combined_score` 对 `signal` 调
   > `_bounded_score`，单独设置 `score_parts["signal"]=2.4` 最多只能贡献 1.0。
   > 构造"combined_score≈2.4"时，应使用 `semantic`（可直接承载 BGE-M3 的高分）
   > 或 `semantic + signal + path_symbol + token_coverage` 组合，并先断言
   > `_combined_score(score_parts) > relation_score`，避免测试夹具本身失真。
   >
   > **简化策略**：测试直接断言**相对顺序**（如 `results[0].chunk_id == "sms_utils"`），
   > 而非精确分数值，避免逆向 `_combined_score` 权重。
2. planner-only relation（`_is_planner_hint_only` 为真）不能压过 strong original direct
   —— 断言 §4 不变式 `max(planner-only) < min(strong original_direct)`。**调用 `_rank_chunks`**。
3. planner_direct（例如 `planner_signal` / `planner_lexical`）同样不能压过
   strong original direct，避免只修 relation 漏掉 direct planner 噪声。**调用 `_rank_chunks`**。
4. 弱 direct（如 `lexical=0.05` 或 `token_coverage=0.1`）不触发 `planner_ceiling`；
   planner-only 仍可按 rerank_score 进入结果，保证弱原始证据不会误杀召回。**调用 `_rank_chunks`**。
5. 没有 strong original_direct 时，planner-only 不 clamp，仍可进入结果，保证召回。**调用 `_rank_chunks`**。
6. endpoint/controller 有 boost，但不能无视分数（高分非 endpoint 仍可超低分 endpoint）。**调用 `_rank_chunks`**。
7. relation expansion 仍能补出 Service/Impl，不被完全杀掉。**调用 `_rank_chunks`**。
8. **归一化生效**：构造 `[0.1, 0.2, 2.4]` 量级差异大（含离群高分）的候选，
   验证归一化后 penalty/boost 确实改变名次，且不受离群值压缩影响
   （守住 §4 的静默失效风险）。**调用 `_rank_chunks`**。
9. **二次排序一致**（P1）：经 `query()` 全链路（含 `_merge_overlapping_results`）
   后，`visible_results` 顺序仍与 rerank 一致——复现并锁死"被 tier 压回去"。**调用 `query()`**。
10. **original_relation 不误分**（P1）：构造 `original_relation>0` 的候选，断言
   `_evidence_class` 返回 `original_relation` 而非 `original_direct`。**调用 `_evidence_class`**。
11. **输出契约**（P2）：`RetrievalResult.score == rerank_score`；
    `score_parts` 含 `combined_score` / `rerank_score` 等数值项，但不含字符串
    `evidence_class`。**调用 `query()`**。
12. **merge 字段一致性**（P2）：构造两个 overlap result，其中较低 `rerank_score`
    有更高 `combined_score` 或更差 `evidence_priority`，断言 merge 后的
    `rerank_score` / `evidence_class` / `evidence_priority` / `reasons` /
    `score_parts["evidence_priority"]` 都来自同一个 winner。**调用 `_merge_overlapping_results`**。

先跑，确认全红。

**步骤 2 — evidence classifier（复用现有函数 + direct-only helper）**

在 `retrieval.py:1050` 附近加薄封装：

- `_evidence_class(score_parts) -> str`：按 §3 优先级表**从 priority 0 (original_direct) 向下短路**。
- `_has_original_direct_evidence(score_parts) -> bool`：**新增 direct-only**
  helper，复制 `_has_original_query_evidence` 但**排除** `"original_relation"`
  key（修 P1 误分）。`_has_original_query_evidence` 本身保留不动。
- `_has_strong_original_direct_evidence(score_parts) -> bool`：用于动态
  `planner_ceiling`，使用 §4 的阈值；不能用 `lexical > 0` / `path_symbol > 0`
  / `signal > 0` 这种宽口径，否则弱 direct 会误触发 clamp。
- `_generic_hint_penalty(chunk, score_parts) -> float`。
- `_rerank_score(score, score_parts, chunk, flags, *, planner_ceiling) -> float`（§4 公式 + clamp）。
  `flags` 是 `_rank_chunks` 内预先算好的轻量结构，至少包含
  `has_endpoint_signal`、`is_controller`、`has_relation_support`。不要在
  `_rerank_score` 内重复查询 `store`，避免排序函数同时承担 I/O 和打分职责。

**`_evidence_class` 实现**（按优先级表从高到低短路）：

```python
_STRONG_SEMANTIC_EVIDENCE = 0.35
_STRONG_LEXICAL_EVIDENCE = 0.25
_STRONG_PATH_SYMBOL_EVIDENCE = 1.0
_STRONG_SIGNAL_EVIDENCE = 0.5

def _evidence_class(score_parts) -> str:
    """
    按优先级表从高到低短路分类。

    双证据 chunk（如 lexical>0 且 original_relation>0，由 _merge_candidates
    合并产生）被 _has_original_direct_evidence 判定为 original_direct
    （priority 0），符合"direct 命中优先于 relation expansion"的语义。
    """
    if _has_original_direct_evidence(score_parts):   # direct-only, 排除 original_relation
        return "original_direct"                      # priority 0
    if score_parts.get("original_relation", 0.0) > 0:
        return "original_relation"                    # priority 1
    if _has_planner_direct_evidence(score_parts):     # planner lexical/path/signal, 无 relation
        return "planner_direct"                       # priority 2
    if score_parts.get("planner_relation", 0.0) > 0:
        return "planner_relation"                     # priority 3
    return "weak_or_generic"                          # priority 4

def _has_strong_original_direct_evidence(score_parts) -> bool:
    return (
        score_parts.get("semantic", 0.0) >= _STRONG_SEMANTIC_EVIDENCE
        or score_parts.get("lexical", 0.0) >= _STRONG_LEXICAL_EVIDENCE
        or score_parts.get("path_symbol", 0.0) >= _STRONG_PATH_SYMBOL_EVIDENCE
        or score_parts.get("signal", 0.0) >= _STRONG_SIGNAL_EVIDENCE
        or score_parts.get("token_coverage", 0.0) >= 0.5
    )
```

> ⚠️ **调用点说明**：`_has_original_query_evidence` 唯一调用点是
> `_is_planner_hint_only` (retrieval.py:1100)，它必须保留宽口径（planner-only =
> 无任何原始证据，含 `original_relation`），不得改用 direct-only helper。

**步骤 3 — 替换主排序策略** (`retrieval.py:747`)

**新排序键**（替换当前 `retrieval.py:747-756`）：

```python
return sorted(
    ranked,
    key=lambda item: (
        -item.rerank_score,        # 降序：归一化 + boost/penalty 后，越大越好
        item.evidence_priority,    # 升序：0 (original_direct) > 1 (original_relation) > ... > 4 (weak)
        -item.score,               # 降序：combined_score tiebreaker（保留用于精确并列）
        item.chunk.file_path.as_posix(),
        item.chunk.start_line,
        item.chunk.chunk_id,
    ),
)
```

> ⚠️ **方向确认**：`rerank_score` 和 `score` 都取负（降序，越大越好），
> `evidence_priority` 不取负（升序，数值小的优先，0 最高）。

- `_RankedChunk` 带上 `rerank_score` / `evidence_class` / `evidence_priority`（供下游二次排序与展示）。
- `_rank_chunks` 分两步计算：先为所有候选计算 unclamped rerank 和 evidence class/priority，
  再按本轮 strong original_direct 计算 `planner_ceiling`，最后对 non-original-direct 类
  （`original_relation` / `planner_*` / `weak_or_generic`）应用 clamp 并排序。
- `rank_tier` 不再进主键；保留供 explain/debug。

**步骤 4 — 同步第二处排序 + 输出契约**（P1 + P2，**不可省**）

- `_ExpandedResult` 增加 `rerank_score` / `evidence_class` / `evidence_priority` 字段；构造点
  (`retrieval.py:797`)、merge 后重建点 (`retrieval.py:922`) 一并透传。
- `_merge_overlapping_results` (`retrieval.py:966`) 排序键换成
  `rerank_score(clamp) -> evidence_priority -> score -> path -> start_line`，
  不再用 `rank_tier`。**这是 P1 漏层的核心**：否则 `visible_results =
  expanded[:final_top_k]` 会把 §3 排序压回去。
- `_merge_expanded_result` (`retrieval.py:991`) 的 `score=max(left,right)`
  同步改为按 rerank_score 选优：`rerank_score = max(left.rerank_score, right.rerank_score)`。
  **不重算 rerank_score**；clamp 不变式由 per-chunk 排序时保证，merge 只取 max 不破坏。
  **同时取 rerank_score 更高的那一侧的 `reasons` 和 `evidence_class/priority`**，
  保证展示的归因与选中的 rerank_score 一致（避免"显示理由 A 但实际用了分数 B"）。
  `score_parts` 不能继续无脑 `_merge_score_parts` 后结束：`combined_score` 可取 max，
  原始来源项（semantic/lexical/relation 等）可继续 max 合并，但
  `rerank_score` / `evidence_priority` 必须由 winner 覆盖，且
  `evidence_priority` 不能用 max（数值越小越优）。

  **等分值 tiebreak（P2 边界）**：当 `left.rerank_score == right.rerank_score` 时，
  按完整排序键 `(evidence_priority, score, file_path, start_line)` 比较，
  取字典序更小的那一侧（与主排序逻辑一致），保证稳定 merge 顺序。
  Python 实现：`winner = min(left, right, key=lambda x: (x.evidence_priority, -x.score, x.file_path, x.start_line))`。
- `query()` 组装 `RetrievalResult` (`retrieval.py:161`)：`score = rerank_score`，
  `score_parts` 暴露 `combined_score` / `rerank_score` / `evidence_priority` / boost·penalty 等数值明细；
  `evidence_class` 不进 `score_parts`，由字段和 reason 承载。
- `_reasons` (`retrieval.py:1150`) 补一句 rerank 归因。
- 跑步骤 1 的 12 条测试转绿。

> ⚠️ **P3 风险**：merge 时除了取 `max(rerank_score)`，还需确保 `reasons` / `evidence_class` /
> `evidence_priority` 来自同一侧（rerank_score 更高的那侧），否则展示的归因与实际选中的分数不一致。
> 测试 #11/#12（输出契约 + merge 字段一致性）应覆盖 merge 后的一致性断言。

### 批次二：收窄 relation expansion（smoke 后再定，可能不需要）

仅当批次一 smoke 后噪声仍明显才做。改的是"哪些候选存在"，与排序解耦：

- 只让强 direct candidate 触发 expansion：有 strong original_direct evidence，或 `score >= 0.35`。
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
pytest tests/test_formatters.py tests/test_mcp_tools.py -v
pytest tests/test_query_planner.py -v
pytest -q
# + BGE-M3 operation-client-api smoke
# + Fast Context 三条对照（人工质量比较，不作 CI 阻塞）
```

### 回滚触发条件

- BGE-M3 smoke 三条 query 中任意一条 Top5 覆盖 < 3/4
- 单测 #1-12 任意一条 flaky（10 次运行中 > 1 次失败）
- 全量测试 regression > 5%

### 回滚步骤

1. `git revert <commit-sha> --no-commit`
2. 恢复 `_rank_chunks` / `_merge_overlapping_results` 的排序键为 `rank_tier`
3. 恢复 `RetrievalResult.score = combined_score`
4. 跑 `pytest` 确认恢复

## 7. 风险

- **relation 降权过狠 → 调用链补全变弱。** 缓解：不删 expansion；
  `original_relation` 虽纳入 clamp，但仍优先于 `planner_relation` / `weak_or_generic`
  （evidence_priority = 1 vs 3/4），且只在有 strong original_direct 时受限，
  保留在"原始 query 召回失败"时的兜底能力。批次二独立验证，便于回退。
- **归一化/量级没对齐 → rerank 静默失效。** 由步骤 1 第 8 条测试守住。
- **双套分类逻辑漂移。** 由步骤 2"复用现有函数"约束。
