# Evidence Anchors And Code Results Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split explanatory repository documents from primary code results so README/RISKS/pom matches can explain why code was found without stealing the top result slots.

**Architecture:** Keep evidence-anchor documents in retrieval and relation expansion, then split the final ranked stream into two payload surfaces: `results` for code results and `evidence_anchors` for explanatory anchors. This avoids more score penalty tuning and preserves the existing numeric `score_parts` contract.

**Tech Stack:** Python 3.11+, pytest, existing `context_search_tool.retrieval` pipeline, existing `RetrievalResult` JSON/MCP/Markdown formatters, SQLite-backed synthetic retrieval tests.

---

## 1. Problem Statement

Current ranking can surface useful README/RISKS/pom matches, but those files can occupy primary `results` positions. That is bad for agent code tracing because the main list should point at source files first. At the same time, these documents are valuable evidence: README/RISKS/pom often explain module ownership, risks, dependency wiring, or business vocabulary that helps justify why adjacent code was retrieved.

The fix should not delete anchors, hide anchor evidence, or stuff string labels into `score_parts`. It should separate display surfaces:

- `results`: primary code-oriented answer candidates, counted by `final_top_k`.
- `evidence_anchors`: supporting README/RISKS/pom matches, ranked and explained separately, not counted by `final_top_k`.

## 2. Scope

### In Scope

- Add an explicit evidence-anchor payload surface.
- Keep README/RISKS/pom anchor candidates usable for same-file/directory/relation expansion.
- Ensure `results` fills from non-anchor code candidates before anchor documents.
- Preserve anchor snippets, reasons, scores, and numeric `score_parts`.
- Update JSON, Markdown, and MCP query payloads.
- Add synthetic tests for README/RISKS/pom stealing top results.

### Out Of Scope

- Do not replace BGE-M3 or change embedding/index format.
- Do not add a new config flag.
- Do not make the query planner responsible for this split.
- Do not broaden the first pass to every documentation format beyond README/RISKS/pom.
- Do not change `score_parts` into mixed string/numeric metadata.

## 3. Target Semantics

1. README/RISKS/pom chunks can still become direct candidates when they match the query.
2. README/RISKS/pom chunks can still seed anchor expansion so nearby code can be found.
3. README/RISKS/pom chunks do not occupy `results` slots when code candidates are available.
4. README/RISKS/pom chunks appear under `evidence_anchors` with content, reasons, score, and numeric score parts.
5. `summary` is computed from `results`, not from `evidence_anchors`, so documentation files do not pollute entry point or implementation summaries.
6. If a query only finds anchors and no code results, `results` stays empty while `evidence_anchors` explains what matched. This is deliberate: anchors are always supporting evidence, never promoted into primary code results.
7. Anchor count grows with the requested result count but remains bounded: show up to `max(1, min(5, final_top_k // 3))` anchors, with at least one anchor when `final_top_k` is 1 or 2. This gives small result sets a concise explanation and larger result sets more support without letting anchors dominate the response.

## 4. Files And Responsibilities

- `src/context_search_tool/models.py`
  - Add `EvidenceAnchor`, a small dataclass for supporting evidence payloads.
- `src/context_search_tool/retrieval.py`
  - Add `QueryBundle.evidence_anchors`.
  - Add helpers to identify README/RISKS/pom anchors and split expanded ranked results.
  - Build `results` from code results and `evidence_anchors` from anchor results.
- `src/context_search_tool/formatters.py`
  - Add top-level `evidence_anchors` to JSON output.
  - Add a Markdown `## Evidence Anchors` section after `## Results`, and omit it when there are no anchors.
- `src/context_search_tool/mcp_tools.py`
  - Add top-level `evidence_anchors` to `context_search_query` payloads.
- `tests/test_retrieval_pipeline.py`
  - Add pipeline-level tests for README/RISKS/pom separation and summary isolation.
- `tests/test_mcp_tools.py`
  - Add payload-shape coverage for the new MCP field.
- `tests/test_formatters.py`
  - Add JSON/Markdown formatting coverage for the new evidence-anchor section.

## 5. Data Contract

Add this dataclass in `src/context_search_tool/models.py`:

```python
@dataclass(frozen=True)
class EvidenceAnchor:
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    anchor_kind: str
```

`EvidenceAnchor.score` is the final rerank score, matching the score used to order anchors. The original combined score remains available as `score_parts["combined_score"]`, and the final ranking signal remains duplicated as `score_parts["rerank_score"]` for diagnostics parity with `RetrievalResult`.

Update `QueryBundle` in `src/context_search_tool/retrieval.py`:

```python
@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
```

JSON/MCP payload shape:

```json
{
  "results": [
    {
      "file_path": "src/main/java/com/example/ApprovalController.java",
      "score_parts": {
        "direct_text": 0.7,
        "rerank_score": 1.12
      }
    }
  ],
  "evidence_anchors": [
    {
      "file_path": "README.md",
      "start_line": 1,
      "end_line": 3,
      "content": "当前审批人查询接口由 ApprovalController 负责。",
      "score": 1.25,
      "score_parts": {
        "direct_text": 1.0,
        "rerank_score": 1.25
      },
      "reasons": [
        "rerank_score=1.25 (original_direct)",
        "direct text match"
      ],
      "anchor_kind": "readme"
    }
  ]
}
```

## 6. Implementation Tasks

### Task 1: Add Anchor Model And Bundle Field

**Files:**
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/retrieval.py`

- [ ] **Step 1: Add the model**

Add `EvidenceAnchor` next to `RetrievalResult` in `models.py`.

- [ ] **Step 2: Import it**

Update the import block in `retrieval.py`:

```python
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    EvidenceAnchor,
    QueryPlan,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSummary,
)
```

- [ ] **Step 3: Extend `QueryBundle`**

Add `evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)` as the last field to keep existing positional construction safe.

- [ ] **Step 4: Verify focused import health**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_non_readme_markdown_display_priority_is_lower_than_code -q
```

Expected: the existing test still imports and runs. It may fail later only if Task 2 changes semantics before its assertions are updated.

### Task 2: Classify Evidence Anchor Paths

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing path-classification tests**

Add tests for the helper:

```python
def test_evidence_anchor_kind_classifies_supported_paths() -> None:
    assert retrieval._evidence_anchor_kind(Path("README.md")) == "readme"
    assert retrieval._evidence_anchor_kind(Path("docs/README-api.md")) == "readme"
    assert retrieval._evidence_anchor_kind(Path("RISKS.md")) == "risks"
    assert retrieval._evidence_anchor_kind(Path("docs/RISKS-auth.md")) == "risks"
    assert retrieval._evidence_anchor_kind(Path("pom.xml")) == "pom"
    assert retrieval._evidence_anchor_kind(Path("service/pom.xml")) == "pom"
    assert retrieval._evidence_anchor_kind(Path("src/main/java/AuthController.java")) == ""
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchor_kind_classifies_supported_paths -q
```

Expected: FAIL because `_evidence_anchor_kind` does not exist.

- [ ] **Step 3: Add the helper**

Add near `_is_document_or_config_anchor`:

```python
def _evidence_anchor_kind(path: Path) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() == ".md" and stem.startswith("readme"):
        return "readme"
    if path.suffix.lower() == ".md" and stem.startswith("risks"):
        return "risks"
    if name == "pom.xml":
        return "pom"
    return ""
```

- [ ] **Step 4: Run the test again**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchor_kind_classifies_supported_paths -q
```

Expected: PASS.

### Task 3: Split Ranked Output Into Code Results And Evidence Anchors

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing separation test**

Add a test that reproduces the problem directly at `query_repository` assembly level by calling a new helper, not by requiring embeddings:

```python
def test_evidence_anchors_do_not_consume_code_result_slots(tmp_path: Path) -> None:
    readme = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口由 ApprovalController 负责。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.2},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.2,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    risks = retrieval._ExpandedResult(
        chunk_ids=["risks"],
        file_path=Path("RISKS.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口风险说明。",
        score=0.95,
        score_parts={"direct_text": 0.95, "rerank_score": 1.1},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.1,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    pom = retrieval._ExpandedResult(
        chunk_ids=["pom"],
        file_path=Path("pom.xml"),
        start_line=1,
        end_line=20,
        content="<artifactId>approval-service</artifactId>",
        score=0.9,
        score_parts={"direct_text": 0.9, "rerank_score": 1.0},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    controller = retrieval._ExpandedResult(
        chunk_ids=["controller"],
        file_path=Path("src/main/java/com/example/ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        score=0.7,
        score_parts={"direct_text": 0.7, "rerank_score": 0.8},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [readme, risks, pom, controller],
        final_top_k=1,
        anchor_top_k=3,
    )

    assert [item.file_path for item in code_results] == [
        Path("src/main/java/com/example/ApprovalController.java")
    ]
    assert [anchor.anchor_kind for anchor in anchors] == ["readme", "risks", "pom"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_consume_code_result_slots -q
```

Expected: FAIL because `_split_code_results_and_evidence_anchors` does not exist.

- [ ] **Step 3: Implement the split helper**

Add:

```python
def _split_code_results_and_evidence_anchors(
    expanded: list[_ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
) -> tuple[list[_ExpandedResult], list[EvidenceAnchor]]:
    code_results: list[_ExpandedResult] = []
    anchors: list[EvidenceAnchor] = []
    seen_anchor_keys: set[tuple[str, Path]] = set()
    for item in expanded:
        anchor_kind = _evidence_anchor_kind(item.file_path)
        if anchor_kind:
            anchor_key = (anchor_kind, item.file_path)
            if anchor_key in seen_anchor_keys:
                continue
            seen_anchor_keys.add(anchor_key)
            if len(anchors) < anchor_top_k:
                anchors.append(_evidence_anchor_from_expanded(item, anchor_kind))
            continue
        if len(code_results) < final_top_k:
            code_results.append(item)
    return code_results, anchors


def _evidence_anchor_from_expanded(
    item: _ExpandedResult,
    anchor_kind: str,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=item.file_path,
        start_line=item.start_line,
        end_line=item.end_line,
        content=item.content,
        score=item.rerank_score,
        score_parts={
            **item.score_parts,
            "combined_score": item.score,
            "rerank_score": item.rerank_score,
            "evidence_priority": float(item.evidence_priority),
        },
        reasons=item.reasons,
        anchor_kind=anchor_kind,
    )
```

- [ ] **Step 4: Add split edge-case tests**

Add:

```python
def test_evidence_anchors_do_not_steal_when_many_code_results_exist() -> None:
    anchor = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="接口说明。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.3},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.3,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    code_items = [
        retrieval._ExpandedResult(
            chunk_ids=[f"code-{index}"],
            file_path=Path(f"src/main/java/com/example/Service{index}.java"),
            start_line=1,
            end_line=5,
            content=f"class Service{index} {{}}",
            score=0.8 - (index * 0.01),
            score_parts={"direct_text": 0.5, "rerank_score": 0.9 - (index * 0.01)},
            reasons=["direct text match"],
            followup_keywords=[],
            rank_tier=0,
            rerank_score=0.9 - (index * 0.01),
            evidence_class="original_direct",
            evidence_priority=0,
        )
        for index in range(3)
    ]

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [anchor, *code_items],
        final_top_k=2,
        anchor_top_k=1,
    )

    assert [item.file_path.name for item in code_results] == [
        "Service0.java",
        "Service1.java",
    ]
    assert [anchor.anchor_kind for anchor in anchors] == ["readme"]


def test_only_evidence_anchors_leave_code_results_empty() -> None:
    readme = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="接口说明。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.1},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.1,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    risks = retrieval._ExpandedResult(
        chunk_ids=["risks"],
        file_path=Path("RISKS.md"),
        start_line=1,
        end_line=2,
        content="风险说明。",
        score=0.9,
        score_parts={"direct_text": 0.9, "rerank_score": 1.0},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [readme, risks],
        final_top_k=5,
        anchor_top_k=5,
    )

    assert code_results == []
    assert [anchor.anchor_kind for anchor in anchors] == ["readme", "risks"]
```

- [ ] **Step 5: Run the tests again**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_consume_code_result_slots tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_steal_when_many_code_results_exist tests/test_retrieval_pipeline.py::test_only_evidence_anchors_leave_code_results_empty -q
```

Expected: PASS.

### Task 4: Wire The Split Into `query_repository`

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Replace direct slicing**

Change:

```python
visible_results = expanded[: config.retrieval.final_top_k]
```

to:

```python
visible_results, evidence_anchors = _split_code_results_and_evidence_anchors(
    expanded,
    final_top_k=config.retrieval.final_top_k,
    anchor_top_k=_evidence_anchor_top_k(config.retrieval.final_top_k),
)
```

- [ ] **Step 2: Add the anchor-count helper**

Add near `_split_code_results_and_evidence_anchors`:

```python
def _evidence_anchor_top_k(final_top_k: int) -> int:
    if final_top_k <= 0:
        return 0
    return max(1, min(5, final_top_k // 3))
```

This keeps `final_top_k=1` and `final_top_k=2` useful by returning one anchor, returns three anchors for the common `final_top_k=10` case, and caps large responses at five anchors.
It returns zero anchors for non-positive `final_top_k` direct API usage.

- [ ] **Step 3: Return anchors**

Update the returned `QueryBundle`:

```python
return QueryBundle(
    query=query,
    expanded_tokens=tokens,
    results=results,
    followup_keywords=_followup_keywords(results),
    summary=summary,
    planner=plan,
    evidence_anchors=evidence_anchors,
)
```

- [ ] **Step 4: Preserve empty-result anchor explanations**

Do not move anchors into `results` when `visible_results` is empty. This keeps the contract simple: code results and evidence anchors stay separate.

- [ ] **Step 5: Update the existing markdown-priority test**

Update `tests/test_retrieval_pipeline.py::test_non_readme_markdown_display_priority_is_lower_than_code` so it no longer expects document demotion inside one shared result list. The updated assertion should verify:

```python
expanded_for_split = [
    retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口由 ApprovalController 负责。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.2},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.2,
        evidence_class="original_direct",
        evidence_priority=0,
    ),
    retrieval._ExpandedResult(
        chunk_ids=["risks"],
        file_path=Path("RISKS.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口的风险说明。",
        score=0.95,
        score_parts={"direct_text": 0.95, "rerank_score": 1.1},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.1,
        evidence_class="original_direct",
        evidence_priority=0,
    ),
    retrieval._ExpandedResult(
        chunk_ids=["controller"],
        file_path=Path("src/main/java/com/example/ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        score=0.7,
        score_parts={"direct_text": 0.7, "rerank_score": 0.8},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    ),
]
code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
    expanded_for_split,
    final_top_k=1,
    anchor_top_k=2,
)
assert [item.file_path for item in code_results] == [
    Path("src/main/java/com/example/ApprovalController.java")
]
assert [anchor.file_path for anchor in anchors] == [
    Path("README.md"),
    Path("RISKS.md"),
]
```

Do not keep the old assertion that only checks `RISKS.md` is below code in a single ranked list.

- [ ] **Step 6: Run the focused pipeline tests**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_consume_code_result_slots tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_steal_when_many_code_results_exist tests/test_retrieval_pipeline.py::test_only_evidence_anchors_leave_code_results_empty tests/test_retrieval_pipeline.py::test_non_readme_markdown_display_priority_is_lower_than_code -q
```

Expected: PASS.

### Task 5: Expose Anchors In JSON, Markdown, And MCP

**Files:**
- Modify: `src/context_search_tool/formatters.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Test: formatter/MCP tests

- [ ] **Step 1: Add formatter payload helper**

In `formatters.py`, add:

```python
def _anchor_payload(anchor: EvidenceAnchor) -> dict[str, Any]:
    return {
        "file_path": anchor.file_path.as_posix(),
        "start_line": anchor.start_line,
        "end_line": anchor.end_line,
        "content": anchor.content,
        "score": anchor.score,
        "score_parts": anchor.score_parts,
        "reasons": anchor.reasons,
        "anchor_kind": anchor.anchor_kind,
    }
```

Import `EvidenceAnchor` from `models.py`.

- [ ] **Step 2: Add JSON field**

Add to the `format_json()` payload:

```python
"evidence_anchors": [_anchor_payload(anchor) for anchor in bundle.evidence_anchors],
```

- [ ] **Step 3: Add Markdown section after results**

After rendering the `## Results` block, append anchors only when anchors exist:

```python
if bundle.evidence_anchors:
    lines.extend(
        [
            "",
            "## Evidence Anchors",
            *_format_anchor_markdown(bundle.evidence_anchors),
        ]
    )
```

Placing anchors after results keeps code first for readers while still preserving explanatory context. Use a compact formatter:

```python
def _format_anchor_markdown(anchors: list[EvidenceAnchor]) -> list[str]:
    lines: list[str] = []
    for index, anchor in enumerate(anchors, start=1):
        lines.append(
            f"- {index}. {anchor.file_path.as_posix()}:{anchor.start_line}-{anchor.end_line} "
            f"({anchor.anchor_kind}, score={anchor.score})"
        )
        for reason in anchor.reasons:
            lines.append(f"  - {reason}")
    return lines
```

- [ ] **Step 4: Add MCP payload helper**

In `mcp_tools.py`, add:

```python
def _anchor_payload(anchor: EvidenceAnchor) -> dict[str, Any]:
    return {
        "file_path": anchor.file_path.as_posix(),
        "start_line": anchor.start_line,
        "end_line": anchor.end_line,
        "content": anchor.content,
        "score": anchor.score,
        "score_parts": anchor.score_parts,
        "reasons": anchor.reasons,
        "anchor_kind": anchor.anchor_kind,
    }
```

Import `EvidenceAnchor` from `models.py`.

Then add to `_query_payload()`:

```python
"evidence_anchors": [_anchor_payload(anchor) for anchor in bundle.evidence_anchors],
```

- [ ] **Step 5: Run formatter/MCP tests**

Run:

```bash
python -m pytest tests/test_formatters.py tests/test_mcp_tools.py -q
```

Expected: PASS after updating expected query payloads to include `evidence_anchors`.

### Task 6: Add Regression Coverage For Anchors, Summary Isolation, And Expansion

**Files:**
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add a synthetic summary-isolation test**

Create a temp repo with `README.md`, `RISKS.md`, `pom.xml`, and `src/main/java/com/example/ApprovalController.java`; store chunks manually in a temp index; call the ranking/assembly path that avoids network embeddings. The assertion must verify that anchors score higher than code but do not enter `results` or `summary`:

```python
assert all(
    result.file_path.suffix == ".java"
    for result in bundle.results
)
assert [anchor.anchor_kind for anchor in bundle.evidence_anchors] == [
    "readme",
    "risks",
    "pom",
]
summary_items = {
    *bundle.summary.entry_points,
    *bundle.summary.implementation,
    *bundle.summary.related_types,
    *bundle.summary.possibly_legacy,
}
assert "README.md" not in summary_items
assert "RISKS.md" not in summary_items
assert "pom.xml" not in summary_items
assert any("ApprovalController" in item for item in bundle.summary.entry_points)
```

- [ ] **Step 2: Add an anchor-expansion regression test**

Add:

```python
def test_evidence_anchors_still_seed_directory_expansion(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    readme = DocumentChunk(
        chunk_id="readme",
        file_path=Path("README.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口由 ApprovalController 负责。",
        chunk_type="file",
        lexical_tokens=["当前", "审批人", "查询", "接口"],
        metadata={"language": "markdown"},
    )
    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        chunk_type="symbol",
        lexical_tokens=["approval", "controller"],
        metadata={"language": "java"},
    )
    for chunk in (readme, controller):
        store.replace_chunks(chunk.file_path, [chunk])

    direct = RetrievalCandidate(
        chunk_id="readme",
        score=1.0,
        source="direct_text",
        score_parts={"direct_text": 1.0},
    )

    expanded = retrieval._anchor_expansion_candidates(
        store,
        [direct],
        ToolConfig(retrieval=RetrievalConfig(final_top_k=5)),
    )

    assert Path("ApprovalController.java") in {
        store.chunk_for_id(candidate.chunk_id).file_path
        for candidate in expanded
}
```

`ToolConfig` and `RetrievalConfig` are already imported in `tests/test_retrieval_pipeline.py`.

- [ ] **Step 3: Keep the tests deterministic**

Use synthetic chunks and direct candidate score parts like the existing `_rank_chunks` tests.

- [ ] **Step 4: Run the targeted regression tests**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_evidence_anchor_kind_classifies_supported_paths tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_consume_code_result_slots tests/test_retrieval_pipeline.py::test_evidence_anchors_do_not_steal_when_many_code_results_exist tests/test_retrieval_pipeline.py::test_only_evidence_anchors_leave_code_results_empty tests/test_retrieval_pipeline.py::test_evidence_anchors_still_seed_directory_expansion -q
```

Expected: PASS.

### Task 7: Full Verification

**Files:**
- No new edits unless tests expose a real defect.

- [ ] **Step 1: Run ranking and pipeline tests**

Run:

```bash
python -m pytest tests/test_rerank_soft_sorting.py tests/test_direct_text_evidence.py tests/test_retrieval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 2: Run MCP and formatter tests**

Run:

```bash
python -m pytest tests/test_mcp_tools.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS, allowing only pre-existing explicit skips.

## 7. Acceptance Criteria

- `README.md`, `RISKS.md`, and `pom.xml` no longer consume `results` slots when code results exist.
- `evidence_anchors` contains the separated README/RISKS/pom matches with snippets and reasons.
- `results` remains backward-compatible for existing consumers: same list shape, same result fields, numeric `score_parts`.
- `summary` is based on primary code results only.
- Markdown shows code results before evidence anchors and omits the anchor section when no anchors exist.
- Existing relation and anchor expansion behavior remains available before the final split.
- Existing rerank invariants still pass.

## 8. Review Notes

- Prefer splitting the output stream over adding larger document penalties. Penalties are brittle because README/RISKS/pom can still win when their literal match is much stronger than code.
- Keep `anchor_kind` outside `score_parts`; this follows the repo's existing numeric score-parts contract.
- Do not remove `_anchor_expansion_candidates`; it is the mechanism that lets explanatory docs point retrieval toward nearby code.
- Keep the initial anchor set narrow: README/RISKS/pom. Broader document splitting can be a later change with fresh evidence.
- Keep anchor-only queries split: an empty `results` list plus populated `evidence_anchors` is clearer than promoting documentation to primary code results.
