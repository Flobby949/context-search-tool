# Core Retrieval Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calibrate the core retrieval baseline so business-chain files outrank merely related files in BGE-M3 Java smoke scenarios.

**Architecture:** Keep Java as the first signal producer and validation target, but put ranking policy in core retrieval. Add repeatable calibration fixtures, expose compact diagnostics, split strong and weak direct evidence, add role-aware rerank signals from existing chunk/symbol/signal metadata, and tune relation expansion ranking without removing relation recall.

**Tech Stack:** Python 3.11+, pytest, SQLite FTS, local Ollama BGE-M3 (`provider=bge`, `model=bge-m3`, `dimensions=1024`), existing `context_search_tool.retrieval` pipeline, existing Java plugin signals, existing MCP/CLI wrappers.

---

## 1. Problem Statement

The previous rerank soft-sorting batch fixed the hard `rank_tier` bug: high-score direct matches such as `SmsUtils` no longer lose to low-score relation expansion. The next issue is subtler: CST now finds useful code, but still often ranks "related implementation detail" above "business core chain".

Observed BGE-M3 smoke results:

| Repo | Query | CST BGE-M3 behavior | Fast Context behavior | Gap |
|------|-------|---------------------|-----------------------|-----|
| `operation-client-api` | `发布意见反馈 发送短信` | `SmsUtils` Top1, but `FeedbackServiceImpl` can sit below Top5 | Returns feedback controller/service/dto plus SMS utility | Core chain completion still weak |
| `console-iot-api` | `开门控制` | Vendor handlers such as `BeehiveCodeHandler` can outrank `AccessControlServiceImpl` | Returns `AccessControlServiceImpl`, `AccessControlService`, controller entrypoints | Handler/detail role over-ranked |
| `console-iot-api` | `设备告警` | MQTT constants/listeners and param builders outrank alarm services | Returns `AlarmService`, `AlarmServiceImpl`, `AlarmPushServiceImpl`, `AlarmDto` | Business service role under-ranked |
| `console-iot-api` | `IOT设备状态` | Factory/handler and `DeviceControlServiceImpl` both appear | Returns `DeviceControlService`, `DeviceControlServiceImpl`, `EquipmentServiceImpl`, MQTT callback | Interface/service chain needs better ordering |

Current likely root causes:

- `_evidence_class()` treats any positive `semantic`, `lexical`, `path_symbol`, `signal`, or `token_coverage` as `original_direct`, so many weak candidates become `evidence_priority=0`.
- `_rerank_score()` has endpoint/controller and relation boosts, but no explicit business role model for service/interface/dto/entity/handler/constant/config.
- Relation expansion can surface useful service/impl files, but it also gives detail files enough support to stay high.
- Summary grouping already knows entry points and implementation names, but that grouping is post-ranking and does not yet feed back into rerank.

## 2. Scope

### In Scope

- Add calibration fixtures and a local integration smoke test path for BGE-M3.
- Add compact diagnostic fields in `score_parts` and `reasons` using numeric values only.
- Split direct evidence into strong and weak classes.
- Add core-level chunk role classification from existing path/symbol/signal metadata.
- Tune rerank scores so service/interface/business implementation files beat handler/constant/config files for broad business queries.
- Preserve existing MCP and CLI payload contracts.

### Out of Scope

- Do not replace BGE-M3 or add a new embedding provider.
- Do not build a full Java AST or full call graph.
- Do not make Fast Context API calls part of CI.
- Do not rewrite Java plugin extraction wholesale.
- Do not remove relation expansion.

## 3. Target Retrieval Semantics

Default BGE-M3 behavior should be:

1. Strong direct evidence still wins over relation-only or planner-only evidence.
2. Weak direct evidence is not automatically the highest class.
3. For broad business queries, business chain roles are preferred:
   - entrypoint/controller endpoint
   - service interface
   - service implementation
   - DTO/entity/query/mapper when adjacent to a matched chain
4. Detail roles are demoted unless the query explicitly names their domain:
   - vendor protocol handler
   - MQTT callback/listener/constant
   - generic param builder
   - generated/config/test utility
5. Relation expansion still keeps chain files visible, but relation support should not let detail roles steal Top1/Top3 from business chain files.

## 4. Files And Responsibilities

- `tests/fixtures/retrieval_calibration/queries.json`
  - New fixture with operation-client and console-iot smoke queries, expected core files, expected optional chain files, and known noise files.
- `tests/test_retrieval_calibration.py`
  - New slow/integration tests that run only when explicit repo paths are provided.
- `tests/conftest.py`
  - Add `--calibration-operation-client-repo` and `--calibration-console-iot-repo` options.
- `tests/test_rerank_soft_sorting.py`
  - Add synthetic unit tests for strong/weak evidence split and role-aware rerank.
- `tests/test_retrieval_pipeline.py`
  - Add focused pipeline tests for role classification and relation chain ordering.
- `src/context_search_tool/retrieval.py`
  - Modify evidence classification, role classification, rerank scoring, reasons, and numeric `score_parts`.
- `src/context_search_tool/models.py`
  - No planned dataclass changes. Keep the public payload shape stable.
- `src/context_search_tool/mcp_tools.py`
  - No planned schema change. Verify numeric `score_parts` fields flow through unchanged.
- `src/context_search_tool/formatters.py`
  - Only update text reason rendering if new reason strings require clearer display.
- `docs/superpowers/plans/2026-06-15-core-retrieval-calibration.md`
  - This implementation plan.

## 5. Calibration Fixture Contract

Create `tests/fixtures/retrieval_calibration/queries.json` with this exact shape:

```json
[
  {
    "repo_key": "operation_client",
    "query": "账号密码登录注册",
    "expected_core": [
      "src/main/java/com/njbandou/controller/AuthController.java",
      "src/main/java/com/njbandou/service/impl/AuthServiceImpl.java",
      "src/main/java/com/njbandou/service/AuthService.java",
      "src/main/java/com/njbandou/dto/AccountLoginDto.java",
      "src/main/java/com/njbandou/entity/User.java"
    ],
    "expected_top5_min": 4,
    "forbidden_top3": []
  },
  {
    "repo_key": "operation_client",
    "query": "驿站设备列表",
    "expected_core": [
      "src/main/java/com/njbandou/controller/StationController.java",
      "src/main/java/com/njbandou/service/StationService.java",
      "src/main/java/com/njbandou/service/impl/StationServiceImpl.java",
      "src/main/java/com/njbandou/service/StationEquipmentService.java",
      "src/main/java/com/njbandou/service/impl/StationEquipmentServiceImpl.java"
    ],
    "expected_top5_min": 4,
    "forbidden_top3": []
  },
  {
    "repo_key": "operation_client",
    "query": "发布意见反馈 发送短信",
    "expected_core": [
      "src/main/java/com/njbandou/controller/FeedbackController.java",
      "src/main/java/com/njbandou/service/FeedbackService.java",
      "src/main/java/com/njbandou/service/impl/FeedbackServiceImpl.java",
      "src/main/java/com/njbandou/dto/FeedbackDto.java",
      "src/main/java/com/njbandou/utils/SmsUtils.java"
    ],
    "expected_top5_min": 4,
    "forbidden_top3": [
      "src/main/java/com/njbandou/utils/client/WxMiniLoginClient.java",
      "src/main/java/com/njbandou/service/impl/AuthServiceImpl.java",
      "src/main/java/com/njbandou/common/cache/RedisCache.java"
    ]
  },
  {
    "repo_key": "console_iot",
    "query": "设备列表",
    "expected_core": [
      "src/main/java/com/njbandou/controller/EquipmentController.java",
      "src/main/java/com/njbandou/service/EquipmentService.java",
      "src/main/java/com/njbandou/service/impl/EquipmentServiceImpl.java",
      "src/main/java/com/njbandou/entity/Equipment.java",
      "src/main/java/com/njbandou/controller/open/OpenApiController.java"
    ],
    "expected_top5_min": 3,
    "forbidden_top3": []
  },
  {
    "repo_key": "console_iot",
    "query": "开门控制",
    "expected_core": [
      "src/main/java/com/njbandou/service/AccessControlService.java",
      "src/main/java/com/njbandou/service/impl/AccessControlServiceImpl.java",
      "src/main/java/com/njbandou/controller/EquipmentController.java",
      "src/main/java/com/njbandou/controller/open/OpenApiController.java"
    ],
    "expected_top5_min": 3,
    "required_top3": [
      "src/main/java/com/njbandou/service/impl/AccessControlServiceImpl.java"
    ],
    "forbidden_top3": [
      "src/main/java/com/njbandou/iot/code/beehive/BeehiveCodeHandler.java",
      "src/main/java/com/njbandou/iot/frs/weiguang/WeiGuangFrsHandler.java"
    ]
  },
  {
    "repo_key": "console_iot",
    "query": "IOT设备状态",
    "expected_core": [
      "src/main/java/com/njbandou/service/DeviceControlService.java",
      "src/main/java/com/njbandou/service/impl/DeviceControlServiceImpl.java",
      "src/main/java/com/njbandou/iot/DeviceControlFactoryManager.java",
      "src/main/java/com/njbandou/iot/DeviceControlHandler.java"
    ],
    "expected_top5_min": 3,
    "forbidden_top3": []
  },
  {
    "repo_key": "console_iot",
    "query": "设备告警",
    "expected_core": [
      "src/main/java/com/njbandou/service/AlarmService.java",
      "src/main/java/com/njbandou/service/impl/AlarmServiceImpl.java",
      "src/main/java/com/njbandou/service/AlarmPushService.java",
      "src/main/java/com/njbandou/service/impl/AlarmPushServiceImpl.java",
      "src/main/java/com/njbandou/dto/AlarmDto.java"
    ],
    "expected_top5_min": 3,
    "required_top3": [
      "src/main/java/com/njbandou/service/impl/AlarmServiceImpl.java"
    ],
    "forbidden_top3": [
      "src/main/java/com/njbandou/mqtt/peach/PeachMqttConstant.java",
      "src/main/java/com/njbandou/iot/param/DeviceParamBuilderManager.java"
    ]
  },
  {
    "repo_key": "console_iot",
    "query": "用户登录认证",
    "expected_core": [
      "src/main/java/com/njbandou/controller/AuthController.java",
      "src/main/java/com/njbandou/service/AuthService.java",
      "src/main/java/com/njbandou/service/impl/AuthServiceImpl.java",
      "src/main/java/com/njbandou/security/utils/TokenUtils.java",
      "src/main/java/com/njbandou/security/filter/AuthenticationTokenFilter.java"
    ],
    "expected_top5_min": 3,
    "forbidden_top3": []
  }
]
```

## 6. Implementation Tasks

### Task 1: Add Calibration Fixtures And Metrics

**Files:**
- Create: `tests/fixtures/retrieval_calibration/queries.json`
- Create: `tests/test_retrieval_calibration.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add pytest options**

Add these options to `tests/conftest.py`:

```python
    parser.addoption(
        "--calibration-operation-client-repo",
        action="store",
        default=None,
        help="Path to operation-client-api for retrieval calibration tests",
    )
    parser.addoption(
        "--calibration-console-iot-repo",
        action="store",
        default=None,
        help="Path to console-iot-api for retrieval calibration tests",
    )
```

- [ ] **Step 2: Add the fixture JSON**

Create `tests/fixtures/retrieval_calibration/queries.json` with the JSON from section 5.

- [ ] **Step 3: Add fixture load test**

Create `tests/test_retrieval_calibration.py`:

```python
import json
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieval_calibration" / "queries.json"


def _load_queries() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_retrieval_calibration_queries_load() -> None:
    queries = _load_queries()
    assert len(queries) == 8
    for query in queries:
        assert query["repo_key"] in {"operation_client", "console_iot"}
        assert query["query"]
        assert query["expected_core"]
        assert query["expected_top5_min"] >= 3
        assert isinstance(query.get("forbidden_top3", []), list)
```

- [ ] **Step 4: Add slow BGE-M3 smoke test**

Append to `tests/test_retrieval_calibration.py`:

```python
def _repo_for_query(request: pytest.FixtureRequest, repo_key: str) -> Path | None:
    option_name = {
        "operation_client": "--calibration-operation-client-repo",
        "console_iot": "--calibration-console-iot-repo",
    }[repo_key]
    raw_path = request.config.getoption(option_name, None)
    return Path(raw_path) if raw_path else None


def _top_paths(results, limit: int) -> list[str]:
    return [result.file_path.as_posix() for result in results[:limit]]


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("query_spec", _load_queries(), ids=lambda item: item["query"])
def test_bge_m3_retrieval_calibration(query_spec: dict, request: pytest.FixtureRequest) -> None:
    repo = _repo_for_query(request, query_spec["repo_key"])
    if repo is None:
        pytest.skip(f"{query_spec['repo_key']} repo option not provided")
    if not repo.exists():
        pytest.skip(f"repo not found: {repo}")

    config = ToolConfig(
        embedding=EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024)
    )
    index_repository(repo, config)
    bundle = query_repository(repo, query_spec["query"], config)

    top5 = _top_paths(bundle.results, 5)
    top3 = set(_top_paths(bundle.results, 3))
    expected = set(query_spec["expected_core"])
    coverage = len(expected.intersection(top5))

    assert coverage >= query_spec["expected_top5_min"], {
        "query": query_spec["query"],
        "top5": top5,
        "expected_core": sorted(expected),
        "coverage": coverage,
    }

    for required_path in query_spec.get("required_top3", []):
        assert required_path in top3, {
            "query": query_spec["query"],
            "top3": sorted(top3),
            "required": required_path,
        }

    for forbidden_path in query_spec.get("forbidden_top3", []):
        assert forbidden_path not in top3, {
            "query": query_spec["query"],
            "top3": sorted(top3),
            "forbidden": forbidden_path,
        }
```

- [ ] **Step 5: Run fixture-only test**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_calibration.py::test_retrieval_calibration_queries_load -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run local BGE-M3 calibration smoke**

Run when both repos are present:

```bash
conda run -n base python -m pytest tests/test_retrieval_calibration.py -q \
  --calibration-operation-client-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/operation-client-api \
  --calibration-console-iot-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/console-iot-api
```

Expected at this point:

```text
At least one calibration assertion fails for current ranking behavior.
```

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/fixtures/retrieval_calibration/queries.json tests/test_retrieval_calibration.py
git commit -m "test: add retrieval calibration smoke fixtures"
```

### Task 2: Add Compact Ranking Diagnostics

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`
- Test: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write a failing unit test for diagnostic score parts**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_rank_chunks_exposes_numeric_diagnostic_score_parts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="auth-service",
        file_path=Path("src/main/java/com/example/service/AuthService.java"),
        start_line=1,
        end_line=10,
        content="public interface AuthService { void login(); }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "login"],
        metadata={"language": "java"},
    )
    store.replace_chunks(chunk.file_path, [chunk])
    candidates = {
        "auth-service": RetrievalCandidate(
            chunk_id="auth-service",
            score=1.0,
            source="test",
            score_parts={"lexical": 0.8, "path_symbol": 2.0},
        )
    }

    ranked = retrieval._rank_chunks(store, candidates, ["auth", "login"], "auth login")

    parts = ranked[0].score_parts
    assert isinstance(parts["combined_score"], float)
    assert isinstance(parts["rerank_score"], float)
    assert isinstance(parts["evidence_priority"], float)
    assert isinstance(parts["role_priority"], float)
    assert isinstance(parts["role_boost"], float)
```

Expected failure:

```text
KeyError: 'combined_score'
```

- [ ] **Step 2: Store diagnostic score parts inside `_rank_chunks`**

In `src/context_search_tool/retrieval.py`, after computing `score`, `rerank_score`, `evidence_priority`, and role fields in `_rank_chunks`, set numeric diagnostic fields:

```python
score_parts["combined_score"] = float(score)
score_parts["rerank_score"] = float(item["rerank_score"])
score_parts["evidence_priority"] = float(item["evidence_priority"])
score_parts["role_priority"] = float(item["role_priority"])
score_parts["role_boost"] = float(item["role_boost"])
```

Keep `evidence_class` and role labels out of `score_parts` because the score-parts contract is `dict[str, float]`.

- [ ] **Step 3: Add reasons for diagnostics without changing payload schema**

Extend `_reasons(score_parts, query)` to include:

```python
if score_parts.get("role_boost", 0.0) > 0:
    reasons.append("business role boost")
if score_parts.get("role_penalty", 0.0) < 0:
    reasons.append("detail role penalty")
```

Use `role_penalty` as a negative numeric score part when detail roles are demoted.

- [ ] **Step 4: Verify MCP still returns numeric score parts**

Add to `tests/test_mcp_tools.py` or update the existing query payload test:

```python
def test_mcp_query_payload_keeps_rerank_diagnostics_numeric(tmp_path: Path) -> None:
    repo = _build_indexed_repo(tmp_path)
    payload = context_search_query_tool(str(repo), "AuthService login", final_top_k=1)

    assert payload["ok"] is True
    parts = payload["results"][0]["score_parts"]
    assert isinstance(parts["rerank_score"], float)
    assert isinstance(parts["evidence_priority"], float)
    assert "evidence_class" not in parts
```

If `_build_indexed_repo` is not available in that test file, use the existing helper already used by nearby MCP query tests.

- [ ] **Step 5: Run diagnostics tests**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_rank_chunks_exposes_numeric_diagnostic_score_parts tests/test_mcp_tools.py -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py tests/test_mcp_tools.py
git commit -m "feat: expose retrieval ranking diagnostics"
```

### Task 3: Split Strong And Weak Direct Evidence

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_rerank_soft_sorting.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add failing tests for weak direct classification**

In `tests/test_rerank_soft_sorting.py`, add this import next to the existing retrieval import:

```python
from context_search_tool import retrieval
```

Then add:

```python
def test_evidence_class_splits_weak_original_direct() -> None:
    assert retrieval._evidence_class({"lexical": 0.05}) == "weak_original_direct"
    assert retrieval._evidence_class({"token_coverage": 0.1}) == "weak_original_direct"
    assert retrieval._evidence_priority("weak_original_direct") == 1


def test_evidence_class_keeps_strong_original_direct() -> None:
    assert retrieval._evidence_class({"lexical": 0.25}) == "original_direct"
    assert retrieval._evidence_class({"semantic": 0.35}) == "original_direct"
    assert retrieval._evidence_class({"path_symbol": 1.0}) == "original_direct"
    assert retrieval._evidence_class({"signal": 0.5}) == "original_direct"
    assert retrieval._evidence_class({"token_coverage": 0.5}) == "original_direct"
```

Expected failure:

```text
AssertionError: assert 'original_direct' == 'weak_original_direct'
```

- [ ] **Step 2: Add weak direct helper**

In `src/context_search_tool/retrieval.py`, add:

```python
def _has_weak_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    return _has_original_direct_evidence(score_parts) and not _has_strong_original_direct_evidence(score_parts)
```

- [ ] **Step 3: Update `_evidence_class` priority order**

Change `_evidence_class` to:

```python
def _evidence_class(score_parts: dict[str, float]) -> str:
    if _has_strong_original_direct_evidence(score_parts):
        return "original_direct"
    if _has_weak_original_direct_evidence(score_parts):
        return "weak_original_direct"
    if score_parts.get("original_relation", 0.0) > 0:
        return "original_relation"
    if _has_planner_direct_evidence(score_parts):
        return "planner_direct"
    if score_parts.get("planner_relation", 0.0) > 0:
        return "planner_relation"
    return "weak_or_generic"
```

- [ ] **Step 4: Update `_evidence_priority`**

Use explicit numeric ordering:

```python
priority_map = {
    "original_direct": 0,
    "weak_original_direct": 1,
    "original_relation": 2,
    "planner_direct": 3,
    "planner_relation": 4,
    "weak_or_generic": 5,
}
```

- [ ] **Step 5: Update ceiling clamp classes**

In `_rank_chunks` and `_rerank_score`, clamp all non-strong classes:

```python
_CLAMPED_EVIDENCE_CLASSES = {
    "weak_original_direct",
    "original_relation",
    "planner_direct",
    "planner_relation",
    "weak_or_generic",
}
```

Use the constant at both clamp sites to avoid drift.

- [ ] **Step 6: Adjust original direct boost**

In `_rerank_score`, change:

```python
if _has_original_direct_evidence(score_parts):
    rerank_score += 0.2
```

to:

```python
if _has_strong_original_direct_evidence(score_parts):
    rerank_score += 0.2
elif _has_weak_original_direct_evidence(score_parts):
    rerank_score += 0.05
```

- [ ] **Step 7: Run rerank tests**

Run:

```bash
conda run -n base python -m pytest tests/test_rerank_soft_sorting.py tests/test_retrieval_pipeline.py -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 8: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_rerank_soft_sorting.py tests/test_retrieval_pipeline.py
git commit -m "feat: split weak and strong direct evidence"
```

### Task 4: Add Core Chunk Role Classification

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add failing role classification tests**

Add to `tests/test_retrieval_pipeline.py`:

```python
@pytest.mark.parametrize(
    ("path", "content", "expected_role", "expected_priority"),
    [
        ("src/main/java/com/example/controller/AuthController.java", "class AuthController {}", "entrypoint", 0),
        ("src/main/java/com/example/service/AuthService.java", "interface AuthService {}", "service_interface", 1),
        ("src/main/java/com/example/service/impl/AuthServiceImpl.java", "class AuthServiceImpl {}", "service_impl", 2),
        ("src/main/java/com/example/dto/AuthLoginDto.java", "class AuthLoginDto {}", "data_type", 3),
        ("src/main/java/com/example/entity/User.java", "class User {}", "data_type", 3),
        ("src/main/java/com/example/mapper/UserMapper.java", "interface UserMapper {}", "mapper", 4),
        ("src/main/java/com/example/iot/code/beehive/BeehiveCodeHandler.java", "class BeehiveCodeHandler {}", "handler", 5),
        ("src/main/java/com/example/mqtt/PeachMqttConstant.java", "class PeachMqttConstant {}", "constant_or_config", 6),
    ],
)
def test_chunk_role_classification(path: str, content: str, expected_role: str, expected_priority: int) -> None:
    chunk = DocumentChunk(
        chunk_id="chunk",
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content=content,
        chunk_type="symbol",
        lexical_tokens=[],
        metadata={"language": "java"},
    )

    role = retrieval._chunk_role(chunk)

    assert role.name == expected_role
    assert role.priority == expected_priority
```

Expected failure:

```text
AttributeError: module 'context_search_tool.retrieval' has no attribute '_chunk_role'
```

- [ ] **Step 2: Add role dataclass**

In `src/context_search_tool/retrieval.py`, near internal ranked dataclasses, add:

```python
@dataclass(frozen=True)
class _ChunkRole:
    name: str
    priority: int
    boost: float
    penalty: float = 0.0
```

- [ ] **Step 3: Implement `_chunk_role`**

Add:

```python
def _chunk_role(chunk: DocumentChunk) -> _ChunkRole:
    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    haystack = f"{path} {names} {content}"

    if "controller" in path or "controller" in names:
        return _ChunkRole("entrypoint", 0, 0.12)
    if "/service/" in path and "impl" not in path and "interface " in content:
        return _ChunkRole("service_interface", 1, 0.10)
    if "/service/impl/" in path or "serviceimpl" in haystack:
        return _ChunkRole("service_impl", 2, 0.10)
    if any(token in path for token in ("/dto/", "/vo/", "/query/", "/entity/")):
        return _ChunkRole("data_type", 3, 0.04)
    if "/mapper/" in path or "mapper" in names:
        return _ChunkRole("mapper", 4, 0.03)
    if any(token in haystack for token in ("handler", "listener", "callback", "connector")):
        return _ChunkRole("handler", 5, 0.0, 0.10)
    if any(token in haystack for token in ("constant", "config", "buildermanager", "parambuilder")):
        return _ChunkRole("constant_or_config", 6, 0.0, 0.12)
    return _ChunkRole("generic", 7, 0.0, 0.02)
```

This is intentionally heuristic and core-owned. It uses Java naming conventions only as signal inputs; it does not add Java-only ranking outside core.

- [ ] **Step 4: Run role tests**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_chunk_role_classification -q
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: classify retrieval chunk roles"
```

### Task 5: Apply Role-Aware Rerank

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`
- Test: `tests/test_rerank_soft_sorting.py`

- [ ] **Step 1: Add failing role-aware ordering tests**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_role_rerank_prefers_service_impl_over_handler_for_business_query(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service_impl = DocumentChunk(
        chunk_id="access-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AccessControlServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AccessControlServiceImpl { void keyOpenDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["access", "control", "service", "open", "door"],
        metadata={"language": "java"},
    )
    handler = DocumentChunk(
        chunk_id="beehive-handler",
        file_path=Path("src/main/java/com/example/iot/code/beehive/BeehiveCodeHandler.java"),
        start_line=1,
        end_line=20,
        content="class BeehiveCodeHandler { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["beehive", "handler", "open", "door"],
        metadata={"language": "java"},
    )
    store.replace_chunks(service_impl.file_path, [service_impl])
    store.replace_chunks(handler.file_path, [handler])
    candidates = {
        "access-service-impl": RetrievalCandidate(
            chunk_id="access-service-impl",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.3, "path_symbol": 1.0},
        ),
        "beehive-handler": RetrievalCandidate(
            chunk_id="beehive-handler",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.35, "path_symbol": 1.0},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["开门", "控制"], "开门控制")

    assert ranked[0].chunk.chunk_id == "access-service-impl"
    assert ranked[0].score_parts["role_priority"] < ranked[1].score_parts["role_priority"]
```

Add a second test:

```python
def test_role_rerank_prefers_alarm_service_over_mqtt_constant(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    alarm_service = DocumentChunk(
        chunk_id="alarm-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AlarmServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AlarmServiceImpl { void saveAlarm() {} }",
        chunk_type="symbol",
        lexical_tokens=["alarm", "service", "device"],
        metadata={"language": "java"},
    )
    mqtt_constant = DocumentChunk(
        chunk_id="mqtt-constant",
        file_path=Path("src/main/java/com/example/mqtt/peach/PeachMqttConstant.java"),
        start_line=1,
        end_line=20,
        content="class PeachMqttConstant { static final String ALARM = \"alarm\"; }",
        chunk_type="symbol",
        lexical_tokens=["alarm", "mqtt", "constant", "device"],
        metadata={"language": "java"},
    )
    store.replace_chunks(alarm_service.file_path, [alarm_service])
    store.replace_chunks(mqtt_constant.file_path, [mqtt_constant])
    candidates = {
        "alarm-service-impl": RetrievalCandidate(
            chunk_id="alarm-service-impl",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.3, "path_symbol": 1.0},
        ),
        "mqtt-constant": RetrievalCandidate(
            chunk_id="mqtt-constant",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.35, "path_symbol": 1.0},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["设备", "告警"], "设备告警")

    assert ranked[0].chunk.chunk_id == "alarm-service-impl"
```

Expected failure:

```text
AssertionError: handler or constant still ranks first
```

- [ ] **Step 2: Compute role in `_rank_chunks` first pass**

Inside the candidate loop in `_rank_chunks`:

```python
role = _chunk_role(chunk)
```

Store it in the temporary ranked item:

```python
"role": role,
```

- [ ] **Step 3: Include role in flags**

Extend flags:

```python
"role_name": role.name,
"role_priority": role.priority,
```

- [ ] **Step 4: Apply role boost and penalty in `_rerank_score`**

Change `_rerank_score` signature to accept `role: _ChunkRole`.

Apply:

```python
rerank_score += role.boost
if role.penalty:
    rerank_score -= role.penalty
    score_parts["role_penalty"] = -role.penalty
if role.boost:
    score_parts["role_boost"] = role.boost
```

Use these initial values:

| role | boost | penalty |
|------|-------|---------|
| `entrypoint` | `0.12` | `0.0` |
| `service_interface` | `0.10` | `0.0` |
| `service_impl` | `0.10` | `0.0` |
| `data_type` | `0.04` | `0.0` |
| `mapper` | `0.03` | `0.0` |
| `handler` | `0.0` | `0.10` |
| `constant_or_config` | `0.0` | `0.12` |
| `generic` | `0.0` | `0.02` |

- [ ] **Step 5: Add role priority to sort key**

Update final sort key:

```python
key=lambda item: (
    -item.rerank_score,
    item.evidence_priority,
    item.score_parts.get("role_priority", 99.0),
    -item.score,
    item.chunk.file_path.as_posix(),
    item.chunk.start_line,
    item.chunk.chunk_id,
)
```

- [ ] **Step 6: Keep fields numeric**

Before building `_RankedChunk`, write:

```python
item["score_parts"]["role_priority"] = float(item["role"].priority)
item["score_parts"]["role_boost"] = float(item["role"].boost)
```

Do not write `role.name` into `score_parts`.

- [ ] **Step 7: Run role-aware tests**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_role_rerank_prefers_service_impl_over_handler_for_business_query tests/test_retrieval_pipeline.py::test_role_rerank_prefers_alarm_service_over_mqtt_constant tests/test_rerank_soft_sorting.py -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 8: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py tests/test_rerank_soft_sorting.py
git commit -m "feat: apply role-aware retrieval rerank"
```

### Task 6: Tune Relation Chain Completion

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add failing chain-completion test**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_relation_chain_service_interface_stays_near_impl(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    controller = DocumentChunk(
        chunk_id="equipment-controller",
        file_path=Path("src/main/java/com/example/controller/EquipmentController.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentController { EquipmentService equipmentService; }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "controller", "service"],
        metadata={"language": "java"},
    )
    service = DocumentChunk(
        chunk_id="equipment-service",
        file_path=Path("src/main/java/com/example/service/EquipmentService.java"),
        start_line=1,
        end_line=20,
        content="interface EquipmentService { void page(); }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "service", "page"],
        metadata={"language": "java"},
    )
    impl = DocumentChunk(
        chunk_id="equipment-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/EquipmentServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentServiceImpl implements EquipmentService { void page() {} }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    handler = DocumentChunk(
        chunk_id="equipment-handler",
        file_path=Path("src/main/java/com/example/iot/EquipmentHandler.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentHandler { void page() {} }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "handler", "page"],
        metadata={"language": "java"},
    )
    for chunk in (controller, service, impl, handler):
        store.replace_chunks(chunk.file_path, [chunk])
    candidates = {
        "equipment-controller": RetrievalCandidate(
            chunk_id="equipment-controller",
            score=1.0,
            source="direct",
            score_parts={"lexical": 0.5, "path_symbol": 1.0},
        ),
        "equipment-service": RetrievalCandidate(
            chunk_id="equipment-service",
            score=1.0,
            source="relation",
            score_parts={"original_relation": 0.8, "relation": 0.8},
        ),
        "equipment-service-impl": RetrievalCandidate(
            chunk_id="equipment-service-impl",
            score=1.0,
            source="relation",
            score_parts={"original_relation": 0.8, "relation": 0.8},
        ),
        "equipment-handler": RetrievalCandidate(
            chunk_id="equipment-handler",
            score=1.0,
            source="semantic",
            score_parts={"semantic": 0.45, "lexical": 0.2},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["设备", "列表"], "设备列表")
    top3 = [item.chunk.chunk_id for item in ranked[:3]]

    assert "equipment-service" in top3
    assert "equipment-service-impl" in top3
    assert "equipment-handler" not in top3
```

- [ ] **Step 2: Add relation role boost**

In `_rerank_score`, after role boost:

```python
if flags.get("has_relation_support", False) and role.name in {"service_interface", "service_impl", "data_type", "mapper"}:
    rerank_score += 0.08
    score_parts["relation_role_boost"] = 0.08
```

For detail roles:

```python
if flags.get("has_relation_support", False) and role.name in {"handler", "constant_or_config"}:
    rerank_score -= 0.06
    score_parts["relation_detail_penalty"] = -0.06
```

- [ ] **Step 3: Add reasons**

In `_reasons`:

```python
if score_parts.get("relation_role_boost", 0.0) > 0:
    reasons.append("relation chain role boost")
if score_parts.get("relation_detail_penalty", 0.0) < 0:
    reasons.append("relation detail penalty")
```

- [ ] **Step 4: Run chain test**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_relation_chain_service_interface_stays_near_impl -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: boost relation-backed business chain roles"
```

### Task 7: Validate Against Local BGE-M3 Calibration Repos

**Files:**
- No source file changes expected.
- Read: `tests/fixtures/retrieval_calibration/queries.json`
- Read: local repos under `/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/`

- [ ] **Step 1: Confirm local repo paths exist**

Run:

```bash
test -d /Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/operation-client-api
test -d /Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/console-iot-api
```

Expected:

```text
Both commands exit 0.
```

- [ ] **Step 2: Confirm BGE-M3 is available**

Run:

```bash
ollama show bge-m3
```

Expected includes:

```text
Capabilities
  embedding
embedding length    1024
```

- [ ] **Step 3: Run full test suite**

Run:

```bash
conda run -n base python -m pytest -q
```

Expected:

```text
All non-integration tests pass.
```

- [ ] **Step 4: Run calibration smoke**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_calibration.py -q \
  --calibration-operation-client-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/operation-client-api \
  --calibration-console-iot-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/console-iot-api
```

Expected:

```text
All calibration queries pass their top5/top3 assertions.
```

- [ ] **Step 5: Run MCP smoke against console-iot**

Run:

```bash
conda run -n base python -c 'import asyncio,json
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
repo="/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/console-iot-api"
async def call_tool(session,name,args):
    result=await session.call_tool(name,args)
    return json.loads(result.content[0].text)
async def main():
    params=StdioServerParameters(command="/opt/homebrew/Caskroom/miniforge/base/bin/cst-mcp", args=[])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            payload=await call_tool(session,"context_search_query",{"repo":repo,"query":"设备告警","final_top_k":5})
            print(json.dumps([r["file_path"] for r in payload["results"]], ensure_ascii=False, indent=2))
asyncio.run(main())'
```

Expected top5 includes:

```text
src/main/java/com/njbandou/service/impl/AlarmServiceImpl.java
```

- [ ] **Step 6: Commit any final test expectation adjustments**

Only adjust calibration thresholds if the observed result is a legitimate improvement that still meets the target retrieval semantics in section 3. If thresholds change, update `tests/fixtures/retrieval_calibration/queries.json` and include the exact observed Top5 in the commit message body.

```bash
git add tests/fixtures/retrieval_calibration/queries.json
git commit -m "test: calibrate retrieval smoke thresholds"
```

Skip this commit if thresholds did not change.

## 7. Verification Matrix

Required before merging:

```bash
conda run -n base python -m pytest tests/test_rerank_soft_sorting.py -q
conda run -n base python -m pytest tests/test_retrieval_pipeline.py -q
conda run -n base python -m pytest tests/test_mcp_tools.py tests/test_formatters.py -q
conda run -n base python -m pytest -q
conda run -n base python -m pytest tests/test_retrieval_calibration.py -q \
  --calibration-operation-client-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/operation-client-api \
  --calibration-console-iot-repo=/Users/flobby/projects/Archive-Project/zhihuizhongkong/refactor/console-iot-api
```

Expected final result:

- Unit and non-integration tests pass.
- Calibration smoke passes all 8 query specs.
- MCP query payload still contains numeric `rerank_score`, `combined_score`, `evidence_priority`, `role_priority`, and no string `evidence_class` in `score_parts`.

## 8. Risks And Rollback

| Risk | Mitigation |
|------|------------|
| Role heuristic overfits Java naming | Keep role classification in core but use broad role categories; validate on two Java repos and synthetic tests |
| Handler demotion hurts protocol-specific queries | Demote handlers only by `0.10`; add future tests for explicit vendor/protocol queries before tuning harder |
| Weak direct split lowers useful recall | Keep weak direct visible with small boost and clamp only when strong direct exists |
| Calibration tests are local-path dependent | Mark as slow/integration and skip unless repo options are provided |
| Score changes break MCP consumers | Keep `score` as rerank score and `score_parts` numeric-only; add MCP payload test |

Rollback plan:

1. Revert role-aware commits in reverse order:

```bash
git revert <chain-role-commit> <role-rerank-commit> <role-classification-commit> --no-commit
```

2. Keep Task 1 fixtures and Task 2 diagnostics if they do not cause regressions.
3. Run:

```bash
conda run -n base python -m pytest -q
```

4. If diagnostics are implicated, revert those commits too and rerun the full test suite.

## 9. Self-Review

- Spec coverage: the plan covers fixtures, diagnostics, strong/weak evidence, role-aware rerank, relation chain sorting, MCP compatibility, and BGE-M3 validation.
- Placeholder scan: no placeholder tokens, empty requirements, or unspecified implementation steps remain.
- Type consistency: `score_parts` stays `dict[str, float]`; string labels such as evidence class and role name are not stored in payload score parts.
- Scope check: this is one focused core calibration milestone; Java plugin rewrite and embedding-provider work remain outside this plan.
