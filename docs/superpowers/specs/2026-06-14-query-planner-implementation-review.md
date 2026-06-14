# Query Planner Implementation Plan Review

**Review Date:** 2026-06-14  
**Reviewed Document:** `docs/superpowers/plans/2026-06-14-query-planner.md`  
**Reviewer:** Claude Code  
**Status:** Critical issues found - requires revision before implementation

---

## Executive Summary

实现计划整体质量高，TDD 流程完整，任务分解清晰。8 个独立 task 的增量提交策略便于 review 和回滚。

**关键发现：**
- ✅ 10/10 任务分解质量（8 个独立 task，职责清晰）
- ✅ 10/10 TDD 流程（每个 task 都是完整的测试循环）
- 🔴 3 个 Critical Issues（实现前必须修正）
- 🟡 4 个 High Priority Issues（实现时需要注意）
- 🟢 3 个 Medium Priority 优化建议

**建议行动：**
1. 修正 3 个 Critical Issues（预计 2 小时）
2. 注意 4 个 High Priority 问题（实现时处理）
3. 按 Task 1-8 顺序执行实现
4. 补充边界条件测试（预计 1 小时）

---

## Critical Issues（实现前必须修正）

### C1. Task 4 Step 5 - `_signal_candidates` 函数签名变更不完整

**位置:** Task 4 "Wire Planner Into Retrieval" → Step 5

**问题描述:**

计划修改了 `_signal_candidates` 签名，添加 `planner_hint` 参数：

```python
def _signal_candidates(
    store: SQLiteStore,
    tokens: list[str],
    config: ToolConfig,
    planner_hint: bool = False,
) -> list[RetrievalCandidate]:
    ...
    source = "planner_signal" if planner_hint else "signal"
    score_key = "planner_signal" if planner_hint else "signal"
    candidates.append(...)
```

**关键问题：**

1. **现有调用点可能遗漏**：计划只提到 `_initial_candidates` 和 `_planner_hint_candidates` 的调用，但现有代码中可能还有其他调用点
2. **函数内部实现未完整展示**：`...` 省略了关键逻辑，实现时容易遗漏如何构造 `RetrievalCandidate`

**影响:**
- 运行时参数不匹配错误
- 测试可能通过但实际使用时崩溃
- Signal matching 逻辑可能不完整

**修正方案:**

在 Task 4 Step 5 之前，补充检查步骤：

```markdown
**Step 5a: Check all existing call sites**

Before modifying `_signal_candidates`, find all current call sites:

```bash
rg "_signal_candidates\(" src/context_search_tool/retrieval.py
```

Update each call site to pass `planner_hint=False` explicitly.

**Step 5b: Implement the full `_signal_candidates` modification**

```python
def _signal_candidates(
    store: SQLiteStore,
    tokens: list[str],
    config: ToolConfig,
    planner_hint: bool = False,
) -> list[RetrievalCandidate]:
    """Find signal-based candidates (e.g., test files, common patterns)."""
    candidates: list[RetrievalCandidate] = []
    source = "planner_signal" if planner_hint else "signal"
    score_key = "planner_signal" if planner_hint else "signal"
    
    # [Preserve existing signal matching logic]
    # The key change: use the dynamic source and score_key
    for signal in store.find_signals(tokens):
        score = _compute_signal_score(signal)
        candidates.append(
            RetrievalCandidate(
                chunk_id=signal.chunk_id,
                score=score,
                source=source,
                score_parts={score_key: score},
            )
        )
    
    return candidates
```

If `store.find_signals` doesn't exist, adapt to the actual signal-finding method.
```

**优先级:** Critical  
**工作量:** 30 分钟（查找调用点 + 完整实现）

---

### C2. Task 4 Step 6 - `_rank_tier` 修改逻辑不完整

**位置:** Task 4 "Wire Planner Into Retrieval" → Step 6

**问题描述:**

计划提到修改 `_rank_tier` 以降低 planner-hint-only 结果的排名：

```python
planner_hint_only = _has_planner_hint(score_parts) and not _has_original_query_evidence(score_parts)
...
base_tier = 0 or 1 or 2 or 3
return base_tier + 1 if planner_hint_only else base_tier
```

**关键问题：**

1. `base_tier = 0 or 1 or 2 or 3` 是伪代码，未展示现有 `_rank_tier` 的实际结构
2. 如果现有函数有多个 return 分支，每个分支都需要应用 `+1` 逻辑
3. 实现时容易只修改一个分支，导致部分 planner_hint_only 结果仍然排序过高

**影响:**
- Ranking 逻辑不完整，违背设计目标（原始匹配优先于 planner hints）
- 设计文档中的 C2 问题（Symbol hints 压制精确匹配）未彻底解决

**修正方案:**

在 Task 4 Step 6 中，提供完整的 `_rank_tier` 实现示例：

```markdown
**Step 6: Add planner-hint scoring and reason**

Update `_rank_tier` to demote planner-hint-only results. The key principle: **every return path** must apply the tier offset.

```python
def _rank_tier(score_parts: dict[str, float]) -> int:
    """
    Assign ranking tier based on evidence quality.
    Lower tier = higher priority.
    
    Tier 0: Semantic match (original query only)
    Tier 1: Signal match (original or planner)
    Tier 2: Lexical/path/symbol match
    Tier 3: Relation expansion only
    Tier 4+: Planner-hint-only results (demoted by +1)
    """
    # Determine base tier from evidence type
    if score_parts.get("semantic", 0.0) > 0:
        base_tier = 0
    elif score_parts.get("signal", 0.0) > 0:
        base_tier = 1
    elif (score_parts.get("path_symbol", 0.0) > 0 
          or score_parts.get("lexical", 0.0) > 0):
        base_tier = 2
    else:
        base_tier = 3
    
    # Demote planner-hint-only results by one tier
    planner_hint_only = (
        _has_planner_hint(score_parts)
        and not _has_original_query_evidence(score_parts)
    )
    
    return base_tier + 1 if planner_hint_only else base_tier
```

**If the existing `_rank_tier` uses a different tier structure**, adapt the logic above while ensuring:
- The tier offset is applied at the **final return**, not inside branches
- All possible execution paths apply the same offset logic

Add a unit test to verify tier demotion:

```python
def test_rank_tier_demotes_planner_hint_only_results() -> None:
    original_match = {"lexical": 1.0}
    planner_only = {"planner_lexical": 1.0}
    mixed = {"lexical": 1.0, "planner_lexical": 1.0}
    
    assert _rank_tier(original_match) == 2
    assert _rank_tier(planner_only) == 3  # demoted from 2
    assert _rank_tier(mixed) == 2  # has original evidence, no demotion
```
```

**优先级:** Critical  
**工作量:** 45 分钟（理解现有逻辑 + 完整实现 + 测试）

---

### C3. Task 4 Step 3 - `QueryBundle` Default Factory 可能引发循环导入

**位置:** Task 4 "Wire Planner Into Retrieval" → Step 3

**问题描述:**

计划使用 lambda 作为 `QueryPlan` 的默认工厂：

```python
@dataclass(frozen=True)
class QueryBundle:
    # ...
    planner: QueryPlan = field(default_factory=lambda: QueryPlan(original_query=""))
```

**关键问题：**

1. **循环导入风险**：`QueryPlan` 在 `models.py`，`QueryBundle` 在 `retrieval.py`，如果互相导入可能循环
2. **Sentinel 值不够语义化**：空字符串 `original_query=""` 作为 disabled plan 不够明确
3. **违反设计原则**：设计文档明确了 `disabled_plan()` helper，应该复用

**影响:**
- 导入错误
- Disabled plan 的语义不清晰
- 代码重复（已有 `disabled_plan()` helper）

**修正方案:**

**方案 A（推荐）：** 使用 `QueryPlan` 类方法作为 default factory

在 Task 2 Step 3 中，修改 `QueryPlan` 定义：

```python
# In src/context_search_tool/models.py
@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    rewritten_queries: list[str] = field(default_factory=list)
    grep_keywords: list[str] = field(default_factory=list)
    symbol_hints: list[str] = field(default_factory=list)
    intent: str = "unknown"
    status: str = "disabled"
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    latency_ms: int | None = None
    error: str | None = None
    
    @staticmethod
    def disabled_default() -> QueryPlan:
        """Factory for disabled plan as a dataclass default."""
        return QueryPlan(original_query="", status="disabled")
```

在 Task 4 Step 3 中，使用这个 factory：

```python
# In src/context_search_tool/retrieval.py
from context_search_tool.models import QueryPlan

@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)
```

**方案 B（更简单）：** 不使用 default，要求显式传入

移除 `planner` 的 default factory，在每个 `QueryBundle` 构造点显式传入 `planner=plan`。

计划中已经提到 "Use explicit `planner=plan` in every `QueryBundle` return"，所以这个方案更一致。

```python
@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    planner: QueryPlan  # No default - must be explicit
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
```

**推荐方案 B**，因为计划已经要求显式传入，无需 default factory。

**优先级:** Critical  
**工作量:** 15 分钟（移除 default factory 或添加 staticmethod）

---

## High Priority Issues（实现时需要注意）

### H1. Task 2 Step 4 - `_clean_string_list` 有 Off-by-One Bug 风险

**位置:** Task 2 "Add QueryPlan Model And Planner Cleanup" → Step 4

**问题描述:**

```python
def _clean_string_list(payload: dict[str, Any], key: str, limit: int) -> list[str]:
    # ...
    if len(cleaned) >= max(0, limit):
        break
```

**关键问题：**

1. `max(0, limit)` 的语义不清晰
2. 当 `limit = 0` 时，条件永远为真，会在第一个元素后立即 break
3. `limit = 0` 的预期行为是什么？"无限制"还是"不允许任何元素"？
4. `limit < 0` 的处理也不明确

**影响:**
- 边缘场景行为不符合预期
- 用户配置 `max_keywords = 0` 时可能得到意外结果

**修正方案:**

明确 `limit <= 0` 的语义并补充测试：

```python
def _clean_string_list(payload: dict[str, Any], key: str, limit: int) -> list[str]:
    """
    Clean and deduplicate a string list from planner payload.
    
    Args:
        payload: Raw planner response
        key: Field name to extract
        limit: Maximum items to return (0 or negative = unlimited)
    """
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    
    cleaned: list[str] = []
    seen: set[str] = set()
    
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain only strings")
        
        stripped = item.strip()
        normalized = stripped.lower()
        
        if not stripped or normalized in seen:
            continue
        
        cleaned.append(stripped)
        seen.add(normalized)
        
        # Stop at limit (0 or negative means unlimited)
        if limit > 0 and len(cleaned) >= limit:
            break
    
    return cleaned
```

补充单元测试到 Task 2 Step 1：

```python
def test_clean_planner_payload_handles_zero_limit() -> None:
    """Zero limit should return empty lists."""
    plan = clean_planner_payload(
        original_query="query",
        payload={
            "grep_keywords": ["A", "B", "C"],
        },
        config=QueryPlannerConfig(max_keywords=0),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )
    
    assert plan.status == "ok"
    assert plan.grep_keywords == []  # Zero limit = no keywords


def test_clean_planner_payload_handles_negative_limit_as_unlimited() -> None:
    """Negative limit should allow all items."""
    plan = clean_planner_payload(
        original_query="query",
        payload={
            "grep_keywords": ["A", "B", "C", "D", "E"],
        },
        config=QueryPlannerConfig(max_keywords=-1),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )
    
    assert plan.status == "ok"
    assert len(plan.grep_keywords) == 5  # Negative = unlimited
```

**优先级:** High  
**工作量:** 30 分钟（修正逻辑 + 补充测试）

---

### H2. Task 3 Step 3 - Session 单例生命周期不明确

**位置:** Task 3 "Add Local Ollama Planner Client" → Step 3

**问题描述:**

计划中提到了类变量单例模式：

```python
class OllamaQueryPlanner:
    _session: requests.Session | None = None
    
    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
            cls._session.trust_env = False
        return cls._session
```

但实际的构造函数实现是：

```python
def __init__(self, config: QueryPlannerConfig, session: requests.Session | None = None) -> None:
    self.config = config
    self.session = session or requests.Session()
    self.session.trust_env = config.use_system_proxy
```

**关键问题：**

1. **代码不一致**：定义了 `get_session` 类方法但从未调用
2. **配置冲突风险**：如果多个 `OllamaQueryPlanner` 实例使用不同的 `use_system_proxy`，单例会导致配置冲突
3. **Session 生命周期**：何时关闭 session？进程结束自动关闭？

**影响:**
- 配置不一致
- 潜在的资源泄漏（虽然影响小）
- 代码复杂度不必要增加

**修正方案:**

**推荐方案：** 移除单例，每个实例独立 session

修改 Task 3 Step 3，移除 `get_session` 类方法，使用简单的实例变量：

```python
class OllamaQueryPlanner:
    def __init__(
        self,
        config: QueryPlannerConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        if session is None:
            session = requests.Session()
            session.trust_env = config.use_system_proxy
        self.session = session
    
    def plan(self, query: str) -> QueryPlan:
        # ... existing implementation
```

**理由：**
- 更简单，无全局状态
- 配置隔离，避免冲突
- 测试友好（可注入 fake session）
- Session 随实例生命周期管理

如果担心连接复用性能，可以在文档中说明：

```markdown
**Note on Session lifecycle:**
Each `OllamaQueryPlanner` instance creates its own `requests.Session`.
For production use with high query volume, consider creating a singleton
planner instance and reusing it across queries. The session's connection
pool will automatically reuse HTTP connections to the Ollama server.
```

**优先级:** High  
**工作量:** 15 分钟（移除单例逻辑 + 更新文档）

---

### H3. Task 4 Step 5 - `_merge_candidates` 函数未定义

**位置:** Task 4 "Wire Planner Into Retrieval" → Step 5

**问题描述:**

计划中使用了 `_merge_candidates` 函数：

```python
direct_candidates = _merge_candidates(
    [*initial_candidates, *signal_candidates, *planner_candidates]
)
```

但这个函数在计划中从未定义或导入。

**关键问题：**

1. 如果现有代码中已存在，需要明确说明
2. 如果不存在，需要提供实现
3. 实现时会因为缺少这个函数而卡住

**影响:**
- 实现阻塞
- 可能导致实现者自行实现，逻辑不一致

**修正方案:**

在 Task 4 Step 5 开始前，补充检查和实现步骤：

```markdown
**Step 5a: Check if `_merge_candidates` exists**

```bash
rg "def _merge_candidates" src/context_search_tool/retrieval.py
```

**If exists:** Verify it merges candidates by `chunk_id` and combines `score_parts`. No changes needed.

**If not exists:** Add this implementation before the planner integration:

```python
def _merge_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """
    Merge candidates by chunk_id, combining score_parts from all sources.
    
    When multiple sources (semantic, lexical, planner_lexical, etc.) return
    the same chunk, merge them into one candidate with combined score_parts.
    """
    by_chunk: dict[str, RetrievalCandidate] = {}
    
    for candidate in candidates:
        if candidate.chunk_id not in by_chunk:
            by_chunk[candidate.chunk_id] = candidate
        else:
            existing = by_chunk[candidate.chunk_id]
            # Merge score_parts (later sources override on key collision)
            merged_parts = {**existing.score_parts, **candidate.score_parts}
            # Use max score
            merged_score = max(existing.score, candidate.score)
            # Keep first source for metadata
            by_chunk[candidate.chunk_id] = RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=merged_score,
                source=existing.source,
                score_parts=merged_parts,
            )
    
    return list(by_chunk.values())
```

Add a unit test:

```python
def test_merge_candidates_combines_score_parts() -> None:
    candidates = [
        RetrievalCandidate(chunk_id="c1", score=1.0, source="lexical", 
                          score_parts={"lexical": 1.0}),
        RetrievalCandidate(chunk_id="c1", score=0.5, source="planner_lexical",
                          score_parts={"planner_lexical": 0.5}),
    ]
    
    merged = _merge_candidates(candidates)
    
    assert len(merged) == 1
    assert merged[0].chunk_id == "c1"
    assert merged[0].score == 1.0  # max
    assert merged[0].score_parts == {"lexical": 1.0, "planner_lexical": 0.5}
```
```

**优先级:** High  
**工作量:** 30 分钟（检查 + 实现 + 测试）

---

### H4. Task 8 Step 3 - Smoke Test 命令过于复杂

**位置:** Task 8 "Run Full Verification And Manual Smoke" → Step 3

**问题描述:**

单行命令过长且难以调试：

```bash
if [ -d /Users/flobby/work/code/operation-admin-api ]; then cst index /Users/flobby/work/code/operation-admin-api && cst query /Users/flobby/work/code/operation-admin-api "数据看板统计图表功能" --planner --json; else cst index /Users/flobby/work/code/irs-portal-base && cst query /Users/flobby/work/code/irs-portal-base "数据看板统计图表功能" --planner --json; fi
```

**关键问题：**

1. 一行命令太长，难以阅读和调试
2. 如果两个 repo 都不存在，行为不明确
3. 错误处理不清晰
4. 验收标准依赖于特定 repo 路径

**影响:**
- 手动验证时容易出错
- CI/CD 集成困难

**修正方案:**

改为分步骤的清晰脚本：

```markdown
**Step 3: Run optional real Ollama smoke if model is installed**

First check if the model exists:

```bash
ollama list | grep "qwen3.5:4b-mlx"
```

If not found, record "Skipped: qwen3.5:4b-mlx not installed" and continue to Step 4.

If found, choose a test repo:

```bash
# Try operation-admin-api first (has DashboardController)
if [ -d /Users/flobby/work/code/operation-admin-api ]; then
    TEST_REPO="/Users/flobby/work/code/operation-admin-api"
    EXPECT_DASHBOARD=true
# Fallback to irs-portal-base
elif [ -d /Users/flobby/work/code/irs-portal-base ]; then
    TEST_REPO="/Users/flobby/work/code/irs-portal-base"
    EXPECT_DASHBOARD=false  # May not have Dashboard classes
else
    echo "Skipped: Neither test repo exists"
    # Record skip reason and continue to Step 4
    exit 0
fi

echo "Using test repo: $TEST_REPO"
```

Run the smoke test:

```bash
cst index "$TEST_REPO"
cst query "$TEST_REPO" "数据看板统计图表功能" --planner --json > /tmp/planner_smoke.json

# Extract key planner diagnostics
cat /tmp/planner_smoke.json | jq '{
  planner_status: .planner.status,
  planner_latency: .planner.latency_ms,
  grep_keywords: .planner.grep_keywords,
  symbol_hints: .planner.symbol_hints,
  top_5_files: .results[:5] | map(.file_path)
}'
```

**Expected results:**

- `planner.status` is `"ok"` (not `"fallback"`)
- `planner.latency_ms` < 10000 (under 10 seconds)
- `planner.grep_keywords` or `planner.symbol_hints` contain Dashboard-related terms

If `EXPECT_DASHBOARD=true`:
- At least one of the top 5 results contains "Dashboard" in the file path

If `EXPECT_DASHBOARD=false`:
- Treat as planner health check only (no Dashboard expectation)

**Record result:**

Append a note to this plan's end (only if you actually run the smoke):

```markdown
## Manual Smoke Test Result

- Date: 2026-06-14
- Model: qwen3.5:4b-mlx available: [yes/no]
- Test repo: [path or "none available"]
- Planner status: [ok/fallback/skipped]
- Top result: [file or N/A]
```
```

**优先级:** High  
**工作量:** 20 分钟（重写脚本 + 测试）

---

## Medium Priority（建议优化）

### M1. Task 1 Step 3 - Config Rendering 插入位置不明确

**位置:** Task 1 "Add Query Planner Config" → Step 3

**问题描述:**

```python
In `render_config`, add a `[query_planner]` section after `[embedding]`:
```

"after `[embedding]`" 的意思模糊：紧跟在后面？还是文件末尾？

**影响:**
- 实现时可能插入错误位置
- Config 文件结构混乱

**建议方案:**

明确插入位置：

```markdown
In `render_config`, insert the `[query_planner]` section immediately after the `[embedding]` section and before any trailing comments:

```python
def render_config(config: ToolConfig) -> str:
    sections = [
        # ... existing [index], [retrieval], [embedding] sections
        
        # Query planner section (insert here)
        "[query_planner]",
        f"enabled = {_toml_bool(config.query_planner.enabled)}",
        f"provider = {_toml_string(config.query_planner.provider)}",
        # ... rest of planner fields
        "",
    ]
    return "\n".join(sections)
```

The `[query_planner]` section should appear in this order:
1. `[index]`
2. `[retrieval]`
3. `[embedding]`
4. `[query_planner]` ← new section
5. Any other sections
```

**优先级:** Medium  
**工作量:** 5 分钟（明确位置）

---

### M2. Task 5 Step 3 - Markdown Line 截断逻辑可能丢失重要 Hint

**位置:** Task 5 "Add Planner Diagnostics To Formatters" → Step 3

**问题描述:**

```python
hints = [*plan.grep_keywords, *plan.symbol_hints][:3]
```

只显示前 3 个 hints，可能丢失最重要的信息。

**影响:**
- 如果最重要的 symbol hint 在第 4 个位置，用户看不到
- 没有视觉提示表明有更多 hints 被截断

**建议方案:**

优先显示 symbol hints，并添加截断提示：

```python
def _planner_markdown_line(plan: QueryPlan) -> str:
    """Generate a concise planner expansion line for Markdown output."""
    if plan.status != "ok":
        return ""
    
    # Prioritize symbol hints (more specific) over grep keywords
    hints = [*plan.symbol_hints[:2], *plan.grep_keywords[:2]][:3]
    
    if not hints:
        return f"Query expanded by {plan.model}."
    
    hint_str = ", ".join(hints)
    total_hints = len(plan.symbol_hints) + len(plan.grep_keywords)
    
    # Add ellipsis if truncated
    if total_hints > 3:
        hint_str += f", ... (+{total_hints - 3} more)"
    
    return f"Query expanded by {plan.model}: {hint_str}"
```

示例输出：

```text
Query expanded by qwen3.5:4b-mlx: DashboardController, DashboardService, Dashboard, ... (+5 more)
```

**优先级:** Medium  
**工作量:** 10 分钟（优化逻辑 + 测试）

---

### M3. 缺少 Type Hints 导入说明

**位置:** 多个新建文件

**问题描述:**

计划中多处使用了 `list[str]`, `dict[str, Any]` 等现代类型注解，但未明确是否需要 `from __future__ import annotations`。

**影响:**
- Python 3.9/3.10 可能需要 future import
- 不确定项目的 Python 版本要求

**建议方案:**

在计划开头的 "Tech Stack" 中明确 Python 版本：

```markdown
**Tech Stack:** Python 3.11+ (uses native `list[T]` and `dict[K, V]` annotations), dataclasses, Protocol, Typer, requests.Session, SQLite-backed retrieval, pytest, existing fake-session test style.

**Note:** If the project must support Python 3.9 or 3.10, add `from __future__ import annotations` at the top of every new Python file.
```

或者，如果项目已经在 3.9/3.10，在每个新建文件的模板中添加：

```python
from __future__ import annotations

import ...
```

**优先级:** Medium  
**工作量:** 5 分钟（明确版本要求）

---

## 测试覆盖度评估

### 已覆盖的测试场景 ✅

| 场景类型 | 测试位置 | 覆盖内容 |
|---------|---------|---------|
| Config rendering | `test_config_paths.py` | 默认值、加载、自定义值 |
| QueryPlan cleanup | `test_query_planner.py` | Strip、dedupe、truncate、intent 验证 |
| Ollama client | `test_query_planner.py` | Valid JSON、timeout、HTTP error、invalid JSON、proxy bypass |
| Retrieval with planner | `test_retrieval_pipeline.py` | Hint match、fallback、ranking priority |
| Formatter output | `test_formatters.py` | JSON diagnostics、Markdown line、fallback silence |
| CLI overrides | `test_cli_commands.py` | Flag 冲突、config override |
| MCP integration | `test_mcp_tools.py` | Payload metadata、feedback logging |

### 缺失的测试场景（建议补充）

| 场景 | 优先级 | 建议补充位置 | 工作量 |
|-----|--------|------------|--------|
| `limit = 0` 和 `limit < 0` | High | `test_query_planner.py` | 15 min |
| Intent 非字符串类型 | Medium | `test_query_planner.py` | 10 min |
| Empty rewritten_queries | Medium | `test_query_planner.py` | 10 min |
| `_rank_tier` demotion | High | `test_retrieval_pipeline.py` | 15 min |
| `_merge_candidates` logic | High | `test_retrieval_pipeline.py` | 15 min |
| Markdown truncation with ellipsis | Low | `test_formatters.py` | 10 min |

**总测试时间增加：** ~1.5 小时

---

## 实施路径

### Phase 1 - 修正计划（预计 2.5 小时）

**Critical Issues（必须修正）：**
- [ ] C1: 补充 `_signal_candidates` 完整实现和调用点检查（30 min）
- [ ] C2: 补充 `_rank_tier` 完整逻辑和单元测试（45 min）
- [ ] C3: 移除 `QueryBundle.planner` 的 default factory（15 min）

**High Priority Issues（强烈建议）：**
- [ ] H1: 明确 `_clean_string_list` 的 `limit <= 0` 语义（30 min）
- [ ] H2: 移除 Session 单例，简化为实例变量（15 min）
- [ ] H3: 检查并补充 `_merge_candidates` 实现（30 min）
- [ ] H4: 重写 smoke test 为分步骤脚本（20 min）

**总计:** ~2.5 小时

---

### Phase 2 - 执行实现（按计划）

按照 Task 1 → Task 8 的顺序执行，每个 task 完成后 commit：

1. ✅ Task 1: Add Query Planner Config（~30 min）
2. ✅ Task 2: Add QueryPlan Model And Planner Cleanup（~45 min）
3. ✅ Task 3: Add Local Ollama Planner Client（~1 hour）
4. ✅ Task 4: Wire Planner Into Retrieval（~2 hours）
5. ✅ Task 5: Add Planner Diagnostics To Formatters（~30 min）
6. ✅ Task 6: Add CLI Planner Overrides（~30 min）
7. ✅ Task 7: Add Planner Metadata To MCP（~30 min）
8. ✅ Task 8: Run Full Verification（~1 hour）

**总计:** ~6.5 小时

---

### Phase 3 - 补充测试（预计 1 小时）

完成实现后，补充缺失的边界条件测试（见上表）。

---

## 总结评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 任务分解 | 10/10 | 8 个独立 task，职责清晰，依赖明确 |
| TDD 流程 | 10/10 | 每个 task 都是完整的 test → fail → implement → pass → commit 循环 |
| 测试覆盖 | 9/10 | 主路径和异常路径覆盖完整，缺少少量边界条件 |
| 代码质量 | 8/10 | Token expansion 和 ranking 逻辑清晰，但部分实现细节不完整 |
| 可执行性 | 7/10 | 需要修正 3 个 Critical 和 4 个 High Priority 问题 |
| 文档质量 | 9/10 | 代码示例清晰，但部分伪代码需要完整化 |

**总体评价:** 可以开始实施，但**必须先修正 Phase 1 中的 7 个问题**。修正后，这是一份高质量的可执行实现计划。

---

## 附录：设计文档问题的解决情况

回顾设计文档 review 中提出的问题，本实现计划的解决情况：

| 设计文档问题 | 实现计划解决方案 | 状态 |
|------------|----------------|------|
| C1: Token expansion 策略模糊 | Task 4 明确了 `expand_query_plan_tokens()` 逻辑 | ✅ 已解决 |
| C2: Symbol hints 压制精确匹配 | Task 4 Step 6 通过 tier demotion 实现优先级 | ⚠️ 需补充完整 `_rank_tier` |
| H1: Semantic retrieval 成本未评估 | Assumptions 明确"不做 multi-query semantic search" | ✅ 已解决 |
| H2: Timeout 策略缺失 | Task 3 明确 no retry 策略 | ✅ 已解决 |
| H3: Prompt 不记录难以调试 | Task 7 记录 prompt_hash，可配置 | ⚠️ 实际未实现 prompt 缓存 |
| H4: Intent 字段用途未定义 | Assumptions 明确"observability-only" | ✅ 已解决 |
| M1: Proxy bypass 默认行为 | Task 3 通过 `use_system_proxy` 配置控制 | ✅ 已解决 |
| M2: Prompt 负样本约束 | Task 2 Step 4 补充了完整的 DO/DO NOT | ✅ 已解决 |
| M3: CLI flag 缺失 | Task 6 实现了 `--planner` / `--no-planner` | ✅ 已解决 |

**总结:** 实现计划很好地解决了设计文档中的大部分问题，仅有 2 个需要在本 review 中进一步完善。

---

## 推荐行动

### 立即行动（必须）

1. **修正 C1-C3**：补充完整的函数实现和类型定义
2. **修正 H1-H4**：处理边界条件和简化复杂脚本

### 短期行动（强烈建议）

3. **补充 M1-M3**：优化用户体验细节
4. **补充缺失测试**：覆盖边界条件

### 长期行动（可选）

5. **Prompt 缓存机制**：实现本地 prompt hash → full prompt 映射（设计文档 H3）
6. **性能监控**：记录 planner latency 分布，评估是否需要优化

---

## 结论

这是一份**高质量的实现计划**，体现了扎实的工程实践：

✅ **优点：**
- 严格的 TDD 流程
- 增量提交策略
- 测试覆盖完整
- 代码示例清晰

⚠️ **需要改进：**
- 3 个 Critical Issues 必须修正
- 4 个 High Priority 问题需要注意
- 部分伪代码需要完整化

**总体建议：** 先花 2.5 小时修正 Phase 1 中的问题，然后按计划执行实施。预计总工作量 ~10 小时，可分 2-3 个工作日完成。

