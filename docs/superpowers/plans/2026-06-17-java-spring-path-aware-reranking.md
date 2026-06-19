# Java/Spring Path-Aware Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Java/Spring retrieval ranking so route-aware business paths, controller-to-implementation chains, DTO fields, and executor/filter methods rank ahead of sibling routes, tests, and incidental same-token matches.

**Architecture:** Keep Evidence Anchors as a separate result-surface feature and make this change a Java/Spring-specific signal and rerank enhancement. The Java plugin should emit richer framework/domain signals, while `retrieval.py` should consume those signals through small score parts that are easy to explain and test.

**Tech Stack:** Python 3.11+, pytest, existing Java plugin extraction, existing SQLite signal/relation store, existing `context_search_tool.retrieval` rerank pipeline.

---

## 1. Problem Statement

The current separation of README/RISKS/pom into `evidence_anchors` fixes documentation stealing primary result slots. It does not solve a different problem: Java/Spring business-path ranking still treats many framework-specific matches as generic token overlap.

Concrete failures to guard against:

- `@RequestMapping("/appCatalog")` plus `@PostMapping("/page")` should be treated as the exact endpoint `/appCatalog/page`.
- `/openApi/appCatalog/page` should not outrank `/appCatalog/page` merely because it contains the same route suffix.
- Controller, service implementation, and executor/filter methods should rank as a business path, with service interfaces allowed but not favored over implementations.
- Query DTO fields such as `canApply` should boost the DTO and the executor/filter method that uses that field.
- Test files, side statistics endpoints, and same-name non-target entrypoints should sink when the query names a route or field.

## 2. Scope

### In Scope

- Add focused Java/Spring acceptance fixtures for the two real cases.
- Improve Spring route exact-match scoring and sibling-route penalties.
- Improve Java plugin signals for DTO fields and method parameter context.
- Add executor/query-executor role classification and relation-aware boosts.
- Update ranking reasons and `score_parts` with numeric diagnostics only.
- Verify using focused pytest commands and a BGE-M3 smoke command when the local model/index is available.

### Out Of Scope

- Do not change `evidence_anchors`.
- Do not change `RetrievalResult` or MCP payload shape.
- Do not replace BGE-M3 or alter embedding manifests.
- Do not make the query planner responsible for Java/Spring path semantics.
- Do not add a config flag for this behavior.
- Do not introduce a general framework abstraction for non-Java languages.

## 3. Current Code Map

- `src/context_search_tool/java_plugin.py`
  - Already emits Spring endpoint signals with full joined paths via `_class_route_before`, `_mapping_before_current_symbol`, `_join_route`, and `_endpoint_signal`.
  - Already emits usage relations such as controller endpoint -> service method and service method -> executor method.
  - Does not emit field signals for DTO/query fields.
  - Does not attach method parameter type/name context to method signals.

- `src/context_search_tool/retrieval.py`
  - `_rank_chunks` computes `score_parts`, role, rerank score, evidence class, and sort order.
  - `_route_boost` currently checks only route-token overlap, so exact `/appCatalog/page` and sibling `/openApi/appCatalog/page` are not separated strongly enough.
  - `_chunk_role` recognizes controller, service interface, service implementation, data type, mapper, handler, and generic chunks, but not executor/query-executor chunks.
  - `_generated_or_test_penalty` already applies a test penalty; this plan tightens acceptance around it rather than creating a new test-filtering system.

- `tests/test_acceptance_java_fixture.py`
  - Already validates Java fixture retrieval broadly.
  - Needs ranking-specific assertions for the two real cases, not only presence assertions.

## 4. Target Semantics

For query `/appCatalog/page canApply`:

- `AppCatalogController.java` appears before `AppCatalogOpenController.java`.
- `AppCatalogOpenController.java` is not result 1.
- `AppInfoServiceImpl.java` and `PageAppCatalogQueryExe.java` are in the early result window.
- `AppCatalogPageQry.java` can appear as a related type, but should not displace the controller or executor path.

For query `/apply/audit/pageEs INVOLVED_BY_ME`:

- `ResourceApplyAuditController.java`, `ResourceAuditServiceImpl.java`, and `EsApplyAuditPageQryExe.java` appear in the early result window.
- Test files do not appear in the early result window.
- Non-ES executor files do not rank ahead of `EsApplyAuditPageQryExe.java`.

## 5. Files And Responsibilities

- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogController.java`
  - Exact `/appCatalog/page` route and `canApply` field flow entrypoint.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogOpenController.java`
  - Sibling `/openApi/appCatalog/page` route used to prove suffix-only route matches are downgraded.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppInfoService.java`
  - Interface that may appear but should not outrank the implementation path.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppInfoServiceImpl.java`
  - Service implementation that calls the executor.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/PageAppCatalogQueryExe.java`
  - Executor containing `fillCanApplyFilter`.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogPageQry.java`
  - DTO carrying `canApply`.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ResourceApplyAuditController.java`
  - Exact `/apply/audit/pageEs` route for the real audit case.
- `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditPageQryExe.java`
  - Non-ES executor used as a negative ranking control.
- `tests/fixtures/java-spring-mini/src/test/java/com/example/audit/ResourceApplyAuditControllerTest.java`
  - Test-file negative control.
- `tests/test_acceptance_java_fixture.py`
  - Ranking acceptance tests for the two cases.
- `tests/test_chunker_java_plugin.py`
  - Java plugin signal extraction unit tests.
- `tests/test_retrieval_pipeline.py`
  - Synthetic rerank unit tests for route exactness, sibling penalties, executor role boosts, and field-context boosts.
- `src/context_search_tool/java_plugin.py`
  - Field and method-context signal extraction.
- `src/context_search_tool/retrieval.py`
  - Route-aware and Java-context-aware score parts.

## 6. Implementation Tasks

### Task 1: Add Ranking Acceptance Fixtures

**Files:**
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogController.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogOpenController.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppInfoService.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppInfoServiceImpl.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/PageAppCatalogQueryExe.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/catalog/AppCatalogPageQry.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ResourceApplyAuditController.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditPageQryExe.java`
- Create: `tests/fixtures/java-spring-mini/src/test/java/com/example/audit/ResourceApplyAuditControllerTest.java`
- Modify: `tests/test_acceptance_java_fixture.py`

- [ ] **Step 0: Verify existing audit support fixture types**

Before editing audit fixtures, confirm these support types already exist:

```bash
rg -n "public enum AuditStatus|public interface ApplyAuditMapper|interface ResourceAuditService|class ApplyAuditEsSearchQry|class WorkbenchResourceAuditStatsDTO" tests/fixtures/java-spring-mini/src/main/java/com/example/audit
```

Expected output includes:

```text
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/AuditStatus.java:public enum AuditStatus
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditMapper.java:public interface ApplyAuditMapper
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java:interface ResourceAuditService
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java:class ApplyAuditEsSearchQry
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java:class WorkbenchResourceAuditStatsDTO
```

If this command does not find all five types, add the missing type to the existing audit fixture before continuing. In the current repository, `AuditStatus`, `ApplyAuditMapper`, `ApplyAuditEsSearchQry`, and `WorkbenchResourceAuditStatsDTO` already exist; this task only extends `ResourceAuditService` with `applyPageEs`.

- [ ] **Step 1: Add the exact app catalog route fixture**

Create `AppCatalogController.java`:

```java
package com.example.catalog;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/appCatalog")
public class AppCatalogController {
    private final AppInfoService appInfoService;

    public AppCatalogController(AppInfoService appInfoService) {
        this.appInfoService = appInfoService;
    }

    @PostMapping("/page")
    public String page(@RequestBody AppCatalogPageQry qry) {
        return appInfoService.page(qry);
    }
}
```

- [ ] **Step 2: Add the sibling open API route fixture**

Create `AppCatalogOpenController.java`:

```java
package com.example.catalog;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/openApi/appCatalog")
public class AppCatalogOpenController {
    @PostMapping("/page")
    public String page() {
        return "open";
    }
}
```

- [ ] **Step 3: Add service interface and implementation fixtures**

Create `AppInfoService.java`:

```java
package com.example.catalog;

public interface AppInfoService {
    String page(AppCatalogPageQry qry);
}
```

Create `AppInfoServiceImpl.java`:

```java
package com.example.catalog;

public class AppInfoServiceImpl implements AppInfoService {
    private final PageAppCatalogQueryExe pageAppCatalogQueryExe;

    public AppInfoServiceImpl(PageAppCatalogQueryExe pageAppCatalogQueryExe) {
        this.pageAppCatalogQueryExe = pageAppCatalogQueryExe;
    }

    @Override
    public String page(AppCatalogPageQry qry) {
        return pageAppCatalogQueryExe.execute(qry);
    }
}
```

- [ ] **Step 4: Add DTO and executor fixtures**

Create `AppCatalogPageQry.java`:

```java
package com.example.catalog;

public class AppCatalogPageQry {
    private Boolean canApply;

    public Boolean getCanApply() {
        return canApply;
    }
}
```

Create `PageAppCatalogQueryExe.java`:

```java
package com.example.catalog;

public class PageAppCatalogQueryExe {
    public String execute(AppCatalogPageQry qry) {
        return fillCanApplyFilter(qry);
    }

    private String fillCanApplyFilter(AppCatalogPageQry qry) {
        if (Boolean.TRUE.equals(qry.getCanApply())) {
            return "canApply";
        }
        return "all";
    }
}
```

- [ ] **Step 5: Add audit route, non-ES executor, and test-file controls**

Create `ResourceApplyAuditController.java`:

```java
package com.example.audit;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ResourceApplyAuditController {
    private final ResourceAuditService resourceAuditService;

    public ResourceApplyAuditController(ResourceAuditService resourceAuditService) {
        this.resourceAuditService = resourceAuditService;
    }

    @PostMapping("/pageEs")
    public String applyPageEs() {
        return resourceAuditService.applyPageEs(AuditStatus.INVOLVED_BY_ME);
    }
}
```

Create `ApplyAuditPageQryExe.java`:

```java
package com.example.audit;

public class ApplyAuditPageQryExe {
    public String applyPage(AuditStatus auditStatus) {
        return "non-es-" + auditStatus.name();
    }
}
```

Create `ResourceApplyAuditControllerTest.java`:

```java
package com.example.audit;

public class ResourceApplyAuditControllerTest {
    public void applyPageEsMentionsInvolvedByMe() {
        String value = "/apply/audit/pageEs INVOLVED_BY_ME";
    }
}
```

- [ ] **Step 6: Extend the audit fixture chain**

Modify `ResourceAuditServiceImpl.java` so it includes the real `applyPageEs` service implementation:

```java
package com.example.audit;

import java.util.Map;

public class ResourceAuditServiceImpl implements ResourceAuditService {
    private final EsApplyAuditPageQryExe esApplyAuditPageQryExe;

    public ResourceAuditServiceImpl(EsApplyAuditPageQryExe esApplyAuditPageQryExe) {
        this.esApplyAuditPageQryExe = esApplyAuditPageQryExe;
    }

    public String applyPageEs(AuditStatus auditStatus) {
        return esApplyAuditPageQryExe.involvedByMe(auditStatus);
    }

    public Map<String, Long> statsWait() {
        return esApplyAuditPageQryExe.statsWait();
    }

    public WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry) {
        return esApplyAuditPageQryExe.auditStats(qry);
    }
}
```

Modify the `ResourceAuditService` interface inside `ApplyAuditController.java` so the new implementation compiles as coherent fixture code:

```java
interface ResourceAuditService {
    String applyPageEs(AuditStatus auditStatus);

    Map<String, Long> statsWait();

    WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry);
}
```

Modify `EsApplyAuditPageQryExe.java` to expose the target executor method:

```java
package com.example.audit;

import java.util.Map;

public class EsApplyAuditPageQryExe {
    private final ApplyAuditMapper mapper = null;

    public String execute(AuditStatus auditStatus) {
        return mapper.findByStatus(auditStatus.name());
    }

    public String involvedByMe(AuditStatus auditStatus) {
        if (auditStatus == AuditStatus.INVOLVED_BY_ME) {
            return mapper.findByStatus(auditStatus.name());
        }
        return "other";
    }

    public Map<String, Long> statsWait() {
        return Map.of("wait", 1L);
    }

    public WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry) {
        return new WorkbenchResourceAuditStatsDTO();
    }
}
```

- [ ] **Step 7: Add failing acceptance tests**

Add this helper near the top of `tests/test_acceptance_java_fixture.py`:

```python
def _copy_java_fixture(tmp_path: Path) -> Path:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)
    return repo
```

Add the app catalog acceptance test:

```python
def test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain(
    tmp_path: Path,
) -> None:
    repo = _copy_java_fixture(tmp_path)
    config = DEFAULT_CONFIG

    index_repository(repo, config)
    bundle = query_repository(
        repo,
        "/appCatalog/page canApply",
        config,
        context_lines=20,
    )

    names = [result.file_path.name for result in bundle.results]
    top_five = names[:5]

    assert "AppCatalogController.java" in top_five
    assert "AppInfoServiceImpl.java" in top_five
    assert "PageAppCatalogQueryExe.java" in top_five
    assert names[0] != "AppCatalogOpenController.java"
    assert names.index("AppCatalogController.java") < names.index(
        "AppCatalogOpenController.java"
    )
```

Add the audit acceptance test:

```python
def test_java_spring_path_rerank_prefers_es_audit_business_chain(
    tmp_path: Path,
) -> None:
    repo = _copy_java_fixture(tmp_path)
    config = DEFAULT_CONFIG

    index_repository(repo, config)
    bundle = query_repository(
        repo,
        "/apply/audit/pageEs INVOLVED_BY_ME",
        config,
        context_lines=20,
    )

    names = [result.file_path.name for result in bundle.results]
    top_six = names[:6]

    assert "ResourceApplyAuditController.java" in top_six
    assert "ResourceAuditServiceImpl.java" in top_six
    assert "EsApplyAuditPageQryExe.java" in top_six
    assert "ResourceApplyAuditControllerTest.java" not in top_six
    if "ApplyAuditPageQryExe.java" in names:
        assert names.index("EsApplyAuditPageQryExe.java") < names.index(
            "ApplyAuditPageQryExe.java"
        )
```

- [ ] **Step 8: Run the focused acceptance tests and confirm they fail for ranking**

Run:

```bash
.venv/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_es_audit_business_chain -q
```

Expected: FAIL before implementation because the current scorer has only token-overlap route boosting and does not yet prefer exact Spring route chains strongly enough.

### Task 2: Emit Java Field And Method Context Signals

**Files:**
- Modify: `src/context_search_tool/java_plugin.py`
- Modify: `tests/test_chunker_java_plugin.py`

- [ ] **Step 0: Verify reusable Java parser helpers already exist**

Run:

```bash
rg -n "_FIELD_RE|def _split_java_parameters" src/context_search_tool/java_plugin.py
```

Expected output includes:

```text
src/context_search_tool/java_plugin.py:_FIELD_RE = re.compile(
src/context_search_tool/java_plugin.py:def _split_java_parameters(parameters: str) -> list[str]:
```

This task reuses both helpers. Do not add duplicate regexes or duplicate parameter-splitting functions.

- [ ] **Step 1: Write field-signal extraction tests**

Add to `tests/test_chunker_java_plugin.py`:

```python
def test_java_plugin_emits_field_signals_for_dto_fields() -> None:
    source = """
class AppCatalogPageQry {
    private Boolean canApply;

    public Boolean getCanApply() {
        return canApply;
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("AppCatalogPageQry.java"), source)
    signals = {signal.name: signal for signal in extraction.signals}

    field_signal = signals["AppCatalogPageQry.canApply"]
    assert field_signal.kind == "field"
    assert field_signal.metadata["owner_type"] == "AppCatalogPageQry"
    assert field_signal.metadata["field"] == "canApply"
    assert field_signal.metadata["field_type"] == "Boolean"
    assert "can" in field_signal.tokens
    assert "apply" in field_signal.tokens
```

Add method-context assertions:

```python
def test_java_plugin_method_signals_include_parameter_context() -> None:
    source = """
class PageAppCatalogQueryExe {
    public String execute(AppCatalogPageQry qry) {
        return fillCanApplyFilter(qry);
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("PageAppCatalogQueryExe.java"), source)
    signals = {signal.name: signal for signal in extraction.signals}

    method_signal = signals["PageAppCatalogQueryExe.execute"]
    assert method_signal.kind == "method"
    assert method_signal.metadata["parameter_types"] == ["AppCatalogPageQry"]
    assert method_signal.metadata["parameter_names"] == ["qry"]
    assert "app" in method_signal.tokens
    assert "catalog" in method_signal.tokens
    assert "qry" in method_signal.tokens
```

- [ ] **Step 2: Run the failing plugin tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_chunker_java_plugin.py::test_java_plugin_emits_field_signals_for_dto_fields tests/test_chunker_java_plugin.py::test_java_plugin_method_signals_include_parameter_context -q
```

Expected: FAIL because field signals and method parameter metadata do not exist yet.

- [ ] **Step 3: Add a field-signal helper**

Add near `_method_signal` in `src/context_search_tool/java_plugin.py`:

```python
def _field_signal(
    path: Path,
    owner_type: str,
    field_type: str,
    field_name: str,
    line_number: int,
) -> CodeSignal:
    signal_name = f"{owner_type}.{field_name}" if owner_type else field_name
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, owner_type)
    _add_identifier_tokens(signal_tokens, field_type)
    _add_identifier_tokens(signal_tokens, field_name)
    return CodeSignal(
        signal_id=generate_signal_id(path, "field", line_number, signal_name),
        chunk_id="",
        file_path=path,
        kind="field",
        name=signal_name,
        start_line=line_number,
        end_line=line_number,
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata={
            "owner_type": owner_type,
            "field": field_name,
            "field_type": _clean_java_type(field_type),
        },
    )
```

- [ ] **Step 4: Emit field signals during extraction**

Inside the main `for line_number, line in enumerate(lines, start=1):` loop in `extract`, after the constant block and before method handling, add:

```python
            field_match = _FIELD_RE.search(line)
            if field_match and line_number not in enum_constant_lines:
                field_type, field_name = field_match.groups()
                type_context = _type_context_for_line(type_contexts, line_number)
                owner_type = type_context["name"] if type_context else ""
                symbols.append(_symbol(field_name, "field", line_number, line_number))
                _add_identifier_tokens(tokens, field_name)
                _add_identifier_tokens(tokens, field_type)
                signals.append(
                    _field_signal(
                        path=path,
                        owner_type=owner_type,
                        field_type=field_type,
                        field_name=field_name,
                        line_number=line_number,
                    )
                )
```

- [ ] **Step 5: Capture method parameter context**

Add this helper near `_parameter_types`:

```python
def _method_parameter_context(line: str) -> dict[str, list[str]]:
    match = re.search(r"\(([^)]*)\)", line)
    if not match:
        return {"parameter_types": [], "parameter_names": []}

    parameter_types: list[str] = []
    parameter_names: list[str] = []
    for parameter in _split_java_parameters(match.group(1)):
        cleaned = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", parameter).strip()
        cleaned = re.sub(r"\bfinal\s+", "", cleaned).strip()
        if not cleaned:
            continue
        parts = cleaned.replace("...", " ").split()
        if len(parts) < 2:
            continue
        parameter_types.append(_clean_java_type(" ".join(parts[:-1])))
        parameter_names.append(parts[-1])
    return {
        "parameter_types": parameter_types,
        "parameter_names": parameter_names,
    }
```

Immediately before `method_contexts.append(...)`, compute the parameter context once:

```python
                parameter_context = _method_parameter_context(line)
```

When building `method_contexts.append(...)`, include:

```python
                        "parameter_types": parameter_context["parameter_types"],
                        "parameter_names": parameter_context["parameter_names"],
```

- [ ] **Step 6: Add method parameter metadata to method signals**

Modify `_method_signal` so it adds method parameter context to tokens and metadata:

```python
def _method_signal(path: Path, method_context: dict[str, Any]) -> CodeSignal:
    owner_type = method_context["owner_type"]
    method_name = method_context["method"]
    signal_name = f"{owner_type}.{method_name}" if owner_type else method_name
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, owner_type)
    _add_identifier_tokens(signal_tokens, method_name)
    for parameter_type in method_context.get("parameter_types", []):
        _add_identifier_tokens(signal_tokens, parameter_type)
    for parameter_name in method_context.get("parameter_names", []):
        _add_identifier_tokens(signal_tokens, parameter_name)
    metadata = {
        "owner_method": method_name,
        "parameter_types": method_context.get("parameter_types", []),
        "parameter_names": method_context.get("parameter_names", []),
    }
    if owner_type:
        metadata["owner_type"] = owner_type
    return CodeSignal(
        signal_id=generate_signal_id(path, "method", method_context["line"], signal_name),
        chunk_id="",
        file_path=path,
        kind="method",
        name=signal_name,
        start_line=method_context["line"],
        end_line=method_context["line"],
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata=metadata,
    )
```

- [ ] **Step 7: Emit method signals even when a method has no receiver usage**

Modify `_relation_signals_and_relations` so non-endpoint methods get a method signal before the usage-signal early exit. Replace the start of the method loop with:

```python
    for method_context in method_contexts:
        usage_signals = method_context["usage_signals"]
        source_signal_id = method_context["endpoint_signal_id"]
        relation_kind = "calls" if source_signal_id else "uses"
        if not source_signal_id:
            signal = _method_signal(path, method_context)
            signals.append(signal)
            source_signal_id = signal.signal_id
        if not usage_signals:
            continue
```

Keep the existing relation-building body after this block. This preserves endpoint signals as relation sources, emits method signals for executor/filter methods, and avoids duplicate method signals for controller endpoints.

- [ ] **Step 8: Run plugin tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_chunker_java_plugin.py -q
```

Expected: PASS.

### Task 3: Add Exact Spring Route Scoring

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write route scoring unit tests**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_route_score_parts_prefers_exact_route_over_sibling_route() -> None:
    exact_signal = CodeSignal(
        signal_id="sig-exact",
        chunk_id="exact",
        file_path=Path("AppCatalogController.java"),
        kind="endpoint",
        name="POST /appCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["app", "catalog", "page", "/appCatalog/page"],
        metadata={"path": "/appCatalog/page"},
    )
    sibling_signal = CodeSignal(
        signal_id="sig-sibling",
        chunk_id="sibling",
        file_path=Path("AppCatalogOpenController.java"),
        kind="endpoint",
        name="POST /openApi/appCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
        metadata={"path": "/openApi/appCatalog/page"},
    )
    false_sibling_signal = CodeSignal(
        signal_id="sig-false-sibling",
        chunk_id="false-sibling",
        file_path=Path("MegaCatalogController.java"),
        kind="endpoint",
        name="POST /megaCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["mega", "catalog", "page", "/megaCatalog/page"],
        metadata={"path": "/megaCatalog/page"},
    )

    exact_parts = retrieval._route_score_parts(
        [exact_signal],
        "/appCatalog/page canApply",
    )
    sibling_parts = retrieval._route_score_parts(
        [sibling_signal],
        "/appCatalog/page canApply",
    )
    false_sibling_parts = retrieval._route_score_parts(
        [false_sibling_signal],
        "/catalog/page canApply",
    )

    assert exact_parts["route_exact_match"] == 0.35
    assert sibling_parts["route_sibling_penalty"] == -0.18
    assert "route_sibling_penalty" not in false_sibling_parts
    assert exact_parts["route_exact_match"] > abs(
        sibling_parts["route_sibling_penalty"]
    )
```

- [ ] **Step 2: Run the failing route test**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_route_score_parts_prefers_exact_route_over_sibling_route -q
```

Expected: FAIL because `_route_score_parts` does not exist.

- [ ] **Step 3: Add route constants and helpers**

Add near the retrieval constants:

```python
_ROUTE_EXACT_MATCH_BOOST = 0.35
_ROUTE_PREFIX_MATCH_BOOST = 0.12
_ROUTE_SIBLING_PENALTY = 0.18
```

Add helper functions near `_route_boost`:

```python
def _query_route(query: str) -> str:
    for part in re.split(r"\s+", query.strip()):
        if "/" in part:
            return _normalize_route(part)
    return ""


def _normalize_route(value: str) -> str:
    cleaned = value.strip().strip("`'\".,;:()[]{}")
    if not cleaned:
        return ""
    cleaned = "/" + cleaned.strip("/")
    return re.sub(r"/+", "/", cleaned)


def _route_segments(route: str) -> list[str]:
    return [segment for segment in route.strip("/").split("/") if segment]


def _has_route_segment_suffix(endpoint_route: str, query_route: str) -> bool:
    endpoint_segments = _route_segments(endpoint_route)
    query_segments = _route_segments(query_route)
    if len(endpoint_segments) <= len(query_segments):
        return False
    return endpoint_segments[-len(query_segments) :] == query_segments


def _route_score_parts(signals: list[CodeSignal], query: str) -> dict[str, float]:
    query_route = _query_route(query)
    if not query_route:
        return {}

    parts: dict[str, float] = {}
    for signal in signals:
        if signal.kind != "endpoint":
            continue
        path = signal.metadata.get("path")
        if not isinstance(path, str):
            continue
        endpoint_route = _normalize_route(path)
        if endpoint_route == query_route:
            parts["route_exact_match"] = max(
                parts.get("route_exact_match", 0.0),
                _ROUTE_EXACT_MATCH_BOOST,
            )
            continue
        if _has_route_segment_suffix(endpoint_route, query_route):
            parts["route_sibling_penalty"] = min(
                parts.get("route_sibling_penalty", 0.0),
                -_ROUTE_SIBLING_PENALTY,
            )
            continue
        if query_route.startswith(endpoint_route + "/"):
            parts["route_prefix_match"] = max(
                parts.get("route_prefix_match", 0.0),
                _ROUTE_PREFIX_MATCH_BOOST,
            )
    return parts
```

- [ ] **Step 4: Safely load signals once per unique chunk in `_rank_chunks`**

Inside `_rank_chunks`, before the candidate loop, add a small local cache so duplicate merged candidates do not cause repeated signal queries:

```python
    signal_cache: dict[str, list[CodeSignal]] = {}

    def signals_for_ranked_chunk(chunk_id: str) -> list[CodeSignal]:
        if chunk_id not in signal_cache:
            try:
                signal_cache[chunk_id] = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signal_cache[chunk_id] = []
        return signal_cache[chunk_id]
```

Inside the candidate loop, after `chunk = store.chunk_for_id(candidate.chunk_id)`, add:

```python
        signals = signals_for_ranked_chunk(candidate.chunk_id)
```

Replace the `has_endpoint_signal` flag calculation with:

```python
            "has_endpoint_signal": any(
                signal.kind == "endpoint" for signal in signals
            ),
```

Add route score parts before `_combined_score(score_parts)`:

```python
        route_score_parts = _route_score_parts(signals, query)
        score_parts.update(route_score_parts)
```

Also replace any new `_chunk_has_signal_kind(store, chunk.chunk_id, "endpoint")` use in `_rank_chunks` with the already-loaded `signals` list. Keep the existing `_chunk_has_signal_kind` helper for other call sites.

- [ ] **Step 5: Include new route parts in `_combined_score`**

Modify `_combined_score`:

```python
        + score_parts.get("route_exact_match", 0.0)
        + score_parts.get("route_prefix_match", 0.0)
        + score_parts.get("route_sibling_penalty", 0.0)
```

- [ ] **Step 6: Add route reason text**

Modify `_reasons`:

```python
    if score_parts.get("route_exact_match", 0.0) > 0:
        reasons.append("exact Spring route match")
    if score_parts.get("route_prefix_match", 0.0) > 0:
        reasons.append("Spring route prefix match")
    if score_parts.get("route_sibling_penalty", 0.0) < 0:
        reasons.append("sibling Spring route penalty")
```

- [ ] **Step 7: Run route-focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_route_score_parts_prefers_exact_route_over_sibling_route tests/test_retrieval_pipeline.py::test_query_combines_route_tokens_and_ranking_reasons tests/test_retrieval_pipeline.py::test_route_reason_only_applies_to_chunks_with_route_tokens -q
```

Expected: PASS.

- [ ] **Step 8: Add a signal-loading performance guard**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_rank_chunks_uses_one_signal_lookup_per_unique_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    candidates: dict[str, RetrievalCandidate] = {}
    for index in range(1000):
        chunk_id = f"chunk-{index}"
        store.replace_chunks(
            Path(f"src/main/java/example/Service{index}.java"),
            [
                DocumentChunk(
                    chunk_id=chunk_id,
                    file_path=Path(f"src/main/java/example/Service{index}.java"),
                    start_line=1,
                    end_line=1,
                    content=f"class Service{index} {{ String targetToken; }}",
                    chunk_type="symbol",
                    symbols=[],
                    lexical_tokens=["target", "token"],
                    embedding_id=chunk_id,
                    deleted_at=None,
                    metadata={"language": "java"},
                )
            ],
        )
        candidates[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=1.0,
            source="lexical",
            score_parts={"lexical": 1.0},
        )

    call_count = 0
    original = store.signals_for_chunk

    def counting_signals_for_chunk(chunk_id: str) -> list[CodeSignal]:
        nonlocal call_count
        call_count += 1
        return original(chunk_id)

    monkeypatch.setattr(store, "signals_for_chunk", counting_signals_for_chunk)

    retrieval._rank_chunks(store, candidates, ["target", "token"], "targetToken")

    assert call_count == len(candidates)
```

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_rank_chunks_uses_one_signal_lookup_per_unique_candidate -q
```

Expected: PASS. This guards the main performance risk introduced by route/context scoring: ranking 1000 candidates should do no more than 1000 signal lookups, with no duplicate signal queries from endpoint flag calculation.

### Task 4: Add Executor Role And Java Context Boosts

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write executor role tests**

Add to `tests/test_retrieval_pipeline.py`:

```python
def test_chunk_role_classifies_query_executor_before_generic() -> None:
    chunk = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=5,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        symbols=[SymbolRef("PageAppCatalogQueryExe", "class", 1, 5, "java")],
        lexical_tokens=["page", "app", "catalog", "query", "exe", "can", "apply"],
        metadata={"language": "java"},
    )

    role = retrieval._chunk_role(chunk)

    assert role.name == "executor"
    assert role.priority == 2
    assert role.boost == 0.12
```

Update the existing parametrized `test_chunk_role_classification` expectations to make the role-order change explicit:

```python
("src/main/java/com/example/service/AuthService.java", "interface AuthService {}", "service_interface", 4, 0.06, 0.0),
("src/main/java/com/example/service/SimpleService.java", "interface SimpleService {}", "service_interface", 4, 0.06, 0.0),
("src/main/java/com/example/service/AuthService.java", "interface AuthService { // AuthServiceImpl handles this }", "service_interface", 4, 0.06, 0.0),
("src/main/java/com/example/service/impl/AuthServiceImpl.java", "class AuthServiceImpl {}", "service_impl", 1, 0.12, 0.0),
("src/main/java/com/example/dto/AuthLoginDto.java", "class AuthLoginDto {}", "data_type", 3, 0.04, 0.0),
```

This is an intentional behavior change: for business-path queries, concrete service implementations and executors should outrank service interfaces when relation support or route context is present. The interface can still appear as related code, but it should not be the preferred implementation result.

- [ ] **Step 2: Write Java context boost tests**

Add:

```python
def test_java_context_score_parts_boosts_field_related_executor_method() -> None:
    method_signal = CodeSignal(
        signal_id="sig-method",
        chunk_id="executor",
        file_path=Path("PageAppCatalogQueryExe.java"),
        kind="method",
        name="PageAppCatalogQueryExe.fillCanApplyFilter",
        start_line=3,
        end_line=3,
        language="java",
        tokens=["page", "app", "catalog", "fill", "can", "apply", "filter"],
        metadata={
            "owner_type": "PageAppCatalogQueryExe",
            "owner_method": "fillCanApplyFilter",
            "parameter_types": ["AppCatalogPageQry"],
            "parameter_names": ["qry"],
        },
    )

    parts = retrieval._java_context_score_parts(
        [method_signal],
        ["app", "catalog", "page", "can", "apply"],
        retrieval._ChunkRole("executor", 2, 0.12),
    )

    assert parts["java_method_context_match"] == 0.14
    assert parts["java_executor_context_boost"] == 0.10
```

Use this same test to validate the generic overlap threshold. Do not special-case `canApply`; the query and method tokens naturally overlap on `can` and `apply`.

- [ ] **Step 3: Run the failing context tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_chunk_role_classifies_query_executor_before_generic tests/test_retrieval_pipeline.py::test_java_context_score_parts_boosts_field_related_executor_method -q
```

Expected: FAIL because executor role and Java context score parts do not exist.

- [ ] **Step 4: Add executor role classification**

Modify `_chunk_role` so the service interface does not outrank service implementation and executor chunks:

```python
    if "controller" in path or "controller" in names:
        return _ChunkRole("entrypoint", 0, 0.12)
    if "/service/impl/" in path or "serviceimpl" in path_and_names:
        return _ChunkRole("service_impl", 1, 0.12)
    if any(
        token in path_and_names
        for token in ("queryexe", "qryexe", "executor", "queryexecutor")
    ):
        return _ChunkRole("executor", 2, 0.12)
    if "/service/" in path and "interface " in content:
        return _ChunkRole("service_interface", 4, 0.06)
    if any(token in path for token in ("/dto/", "/vo/", "/query/", "/entity/")):
        return _ChunkRole("data_type", 3, 0.04)
```

- [ ] **Step 5: Add Java context score helper**

Add near the route constants:

```python
_JAVA_CONTEXT_MIN_TOKEN_OVERLAP = 2
_JAVA_METHOD_CONTEXT_MATCH_BOOST = 0.14
_JAVA_FIELD_CONTEXT_MATCH_BOOST = 0.12
_JAVA_EXECUTOR_CONTEXT_BOOST = 0.10
```

Add near `_route_score_parts`:

```python
def _java_context_score_parts(
    signals: list[CodeSignal],
    query_tokens: list[str],
    role: _ChunkRole,
) -> dict[str, float]:
    normalized_query = {token.lower() for token in query_tokens if token}
    if not normalized_query:
        return {}

    parts: dict[str, float] = {}
    for signal in signals:
        if signal.kind not in {"method", "field"}:
            continue
        signal_tokens = {token.lower() for token in signal.tokens if token}
        overlap = normalized_query.intersection(signal_tokens)
        if len(overlap) >= _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
            if signal.kind == "method":
                parts["java_method_context_match"] = max(
                    parts.get("java_method_context_match", 0.0),
                    _JAVA_METHOD_CONTEXT_MATCH_BOOST,
                )
            if signal.kind == "field":
                parts["java_field_context_match"] = max(
                    parts.get("java_field_context_match", 0.0),
                    _JAVA_FIELD_CONTEXT_MATCH_BOOST,
                )
            if role.name == "executor":
                parts["java_executor_context_boost"] = max(
                    parts.get("java_executor_context_boost", 0.0),
                    _JAVA_EXECUTOR_CONTEXT_BOOST,
                )
    return parts
```

`_JAVA_CONTEXT_MIN_TOKEN_OVERLAP = 2` is deliberately conservative: one token is too noisy for Java identifiers (`page`, `list`, `query`), while two query-token overlaps are enough to connect `canApply`, `fillCanApplyFilter`, and `AppCatalogPageQry` without hard-coding a business field.

- [ ] **Step 6: Apply Java context score parts in `_rank_chunks`**

After route score parts are applied:

```python
        java_context_parts = _java_context_score_parts(signals, tokens, role)
        score_parts.update(java_context_parts)
```

Ensure this code runs after `role = _chunk_role(chunk)` is assigned.

- [ ] **Step 7: Include new Java context parts in `_combined_score`**

Modify `_combined_score`:

```python
        + score_parts.get("java_method_context_match", 0.0)
        + score_parts.get("java_field_context_match", 0.0)
        + score_parts.get("java_executor_context_boost", 0.0)
```

- [ ] **Step 8: Extend relation role boost to executors**

Modify the relation role boost set in `_rerank_score`:

```python
    if flags.get("has_relation_support", False) and role.name in {
        "service_impl",
        "executor",
        "data_type",
        "mapper",
    }:
        rerank_score += 0.08
        score_parts["relation_role_boost"] = 0.08
```

- [ ] **Step 9: Add context reason text**

Modify `_reasons`:

```python
    if score_parts.get("java_method_context_match", 0.0) > 0:
        reasons.append("Java method context match")
    if score_parts.get("java_field_context_match", 0.0) > 0:
        reasons.append("Java field context match")
    if score_parts.get("java_executor_context_boost", 0.0) > 0:
        reasons.append("Java executor context boost")
```

- [ ] **Step 10: Run context-focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_chunk_role_classifies_query_executor_before_generic tests/test_retrieval_pipeline.py::test_java_context_score_parts_boosts_field_related_executor_method tests/test_rerank_soft_sorting.py -q
```

Expected: PASS.

- [ ] **Step 11: Run role regression coverage**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_chunk_role_classification -q
```

Expected: PASS with the updated intentional role expectations: `service_impl` priority 1, `executor` priority 2, `data_type` priority 3, and `service_interface` priority 4.

### Task 5: Validate End-To-End Ranking

**Files:**
- Modify: `tests/test_acceptance_java_fixture.py`
- No production files beyond Tasks 2-4.

- [ ] **Step 1: Run the two ranking acceptance cases**

Run:

```bash
.venv/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_es_audit_business_chain -q
```

Expected: PASS.

- [ ] **Step 2: Run existing Java fixture acceptance coverage**

Run:

```bash
.venv/bin/python -m pytest tests/test_acceptance_java_fixture.py -q
```

Expected: PASS.

- [ ] **Step 3: Run focused retrieval and plugin suites**

Run:

```bash
.venv/bin/python -m pytest tests/test_chunker_java_plugin.py tests/test_retrieval_pipeline.py tests/test_rerank_soft_sorting.py -q
```

Expected: PASS.

- [ ] **Step 4: Verify existing acceptance behavior remains intact**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_query_expands_signal_relations_before_weak_lexical_matches tests/test_retrieval_pipeline.py::test_relation_expansion_scores_from_signal_strength tests/test_retrieval_pipeline.py::test_query_bundle_summary_groups_entrypoints_implementation_related_and_legacy -q
```

Expected: PASS. These tests protect the existing relation-expansion and summary behavior while allowing the intentional role-order change from Task 4.

- [ ] **Step 5: Run the full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 6: Run BGE-M3 smoke validation when local dependencies are present**

Use this after the pytest suite passes and only if the local BGE-M3 environment is available:

```bash
cst index tests/fixtures/java-spring-mini --config .context-search/config.toml
cst query tests/fixtures/java-spring-mini "/appCatalog/page canApply" --json
cst query tests/fixtures/java-spring-mini "/apply/audit/pageEs INVOLVED_BY_ME" --json
```

Expected:

- The first JSON result set has `AppCatalogController.java`, `AppInfoServiceImpl.java`, and `PageAppCatalogQueryExe.java` before `AppCatalogOpenController.java`.
- The second JSON result set has `ResourceApplyAuditController.java`, `ResourceAuditServiceImpl.java`, and `EsApplyAuditPageQryExe.java` before test files and before `ApplyAuditPageQryExe.java`.
- Result `score_parts` contain route/context diagnostics such as `route_exact_match`, `java_method_context_match`, or `relation_role_boost`.

## 7. Self-Review Checklist

- The plan is separate from Evidence Anchors and does not modify the anchor payload contract.
- Every production change is tied to Java/Spring route, chain, field, or executor ranking.
- The two real user cases are encoded as acceptance tests.
- The sibling route downgrade is tested by relative order, not only by score-part presence.
- The service implementation and executor path are explicitly preferred over service interface-only matches.
- Test-file sinking is validated through the audit fixture control.
- All new `score_parts` values are numeric floats, preserving the existing score-parts contract.
- Verification starts with failing focused tests and ends with full pytest plus BGE-M3 smoke when available.
