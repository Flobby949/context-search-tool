from __future__ import annotations

from pathlib import Path

import pytest

from context_search_tool.frontend_graph import (
    FrontendGraphProducer,
    extract_frontend_facts,
    lex_vue_script_ranges,
)
from context_search_tool.graph_contract import generate_core_module_signal_id
from context_search_tool.graph_plugins import PluginContext
from context_search_tool.models import CodeSignal, DocumentChunk


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "p5-language-graphs"


def _diagnostic_count(facts, code: str) -> int:
    return sum(item.count for item in facts.diagnostics if item.code == code)


def test_vue_lexer_returns_only_top_level_original_script_ranges() -> None:
    source = b'''<template data-text=">">
  <!-- <script>comment fake</script> -->
  <section><script>template fake</script></section>
</template>
<script data-value="a > b">
import value from "./value";
</script>
<script setup lang='ts' generic="T extends A > B">
const count: number = 1;
</script>
'''

    ranges = lex_vue_script_ranges(source)

    assert [(item.language, item.setup) for item in ranges] == [
        ("javascript", False),
        ("typescript", True),
    ]
    assert [
        source[item.content_range.start_byte : item.content_range.end_byte]
        for item in ranges
    ] == [
        b'\nimport value from "./value";\n',
        b"\nconst count: number = 1;\n",
    ]
    assert [item.content_range.start_line for item in ranges] == [5, 8]
    assert all(item.content_range.start_column > 0 for item in ranges)


@pytest.mark.parametrize(
    "source",
    [
        b"<script>const value = 1;",
        b"</script>",
        b"<script><script>nested</script></script>",
        b"<script lang='coffee'>value</script>",
        b"<!-- unclosed <script></script>",
    ],
)
def test_vue_lexer_rejects_unclosed_nested_or_unsupported_ranges(
    source: bytes,
) -> None:
    with pytest.raises(ValueError):
        lex_vue_script_ranges(source)


def test_vue_lexer_ignores_script_tags_nested_in_template() -> None:
    source = b"<template><script>fake</script><main /></template>"

    assert lex_vue_script_ranges(source) == ()


def test_static_import_and_reexport_forms_are_ast_only_and_source_ordered() -> None:
    source = b'''import Default from "./a.ts";
import { value as alias, type Model } from "../views/Page";
import * as helpers from "@/utils/helpers";
import "./side-effect";
export { exported } from "./reexport";
export * from "pkg";
const fake = "import nope from './string-fake'";
// import commentFake from "./comment-fake";
const standalone = import("./standalone");
const computed = import(`./${name}`);
'''
    facts = extract_frontend_facts("src/router/index.ts", source)

    assert facts.persistent_facts_allowed is True
    assert [(item.kind, item.specifier) for item in facts.imports] == [
        ("import", "./a.ts"),
        ("import", "../views/Page"),
        ("import", "@/utils/helpers"),
        ("import", "./side-effect"),
        ("reexport", "./reexport"),
        ("reexport", "pkg"),
    ]
    assert "./standalone" not in {item.specifier for item in facts.imports}
    first = facts.imports[0]
    assert first.selector.state == "exact"
    assert first.selector.candidates == ("src/router/a.ts",)
    page = facts.imports[1]
    assert page.selector.state == "candidates"
    assert page.selector.candidates == (
        "src/views/Page",
        "src/views/Page.ts",
        "src/views/Page.tsx",
        "src/views/Page.js",
        "src/views/Page.jsx",
        "src/views/Page.vue",
        "src/views/Page.d.ts",
        "src/views/Page/index.ts",
        "src/views/Page/index.tsx",
        "src/views/Page/index.js",
        "src/views/Page/index.vue",
    )
    assert [(binding.local_name, binding.imported_name, binding.kind, binding.is_type_only) for binding in page.bindings] == [
        ("alias", "value", "named", False),
        ("Model", "Model", "named", True),
    ]
    assert facts.imports[2].selector.candidates[0] == "src/utils/helpers"
    assert facts.imports[-1].selector.state == "external"


def test_selector_states_cover_escape_bare_and_absolute_inputs() -> None:
    source = b'''import escaped from "../../../outside";
import external from "react";
import absolute from "/src/absolute";
'''
    facts = extract_frontend_facts("src/router/index.ts", source)

    assert [item.selector.state for item in facts.imports] == [
        "escape",
        "external",
        "unresolved",
    ]
    assert all(not item.selector.candidates for item in facts.imports)


def test_vue_sfc_import_ranges_keep_original_lines_and_offsets() -> None:
    path = FIXTURES / "vue" / "src/views/OrdersView.vue"
    source = path.read_bytes()
    facts = extract_frontend_facts("src/views/OrdersView.vue", source)

    assert facts.persistent_facts_allowed is True
    assert [(item.language, item.setup) for item in facts.script_ranges] == [
        ("typescript", True)
    ]
    assert [item.specifier for item in facts.imports] == [
        "../services/orderService",
        "../stores/orderStore",
        "../types/order",
    ]
    assert [item.source_range.start_line for item in facts.imports] == [7, 8, 9]
    assert all(item.source_range.start_byte > facts.script_ranges[0].content_range.start_byte for item in facts.imports)


def test_relevant_parse_error_closes_all_frontend_edge_facts() -> None:
    source = b'''import Page from "./Page";
import { broken from "./broken";
const routes = [{ path: "/x", component: Page }];
'''
    facts = extract_frontend_facts("src/router.ts", source)

    assert facts.persistent_facts_allowed is False
    assert facts.imports == ()
    assert facts.routes == ()
    assert _diagnostic_count(facts, "relevant_parse_error") >= 1


def test_unrelated_parse_error_does_not_invent_or_remove_static_import() -> None:
    source = b'''import Page from "./Page";
function unrelated() { const value = ; }
'''
    facts = extract_frontend_facts("src/router.ts", source)

    assert facts.persistent_facts_allowed is True
    assert [item.specifier for item in facts.imports] == ["./Page"]
    assert facts.routes == ()
    assert _diagnostic_count(facts, "unrelated_parse_error") >= 1


def test_vue_router_accepts_literal_nested_routes_and_direct_dynamic_component() -> None:
    source = b'''import { createRouter as makeRouter } from "vue-router";
import Parent from "./Parent.vue";
import IndexPage from "./Index.vue";
const routes = [
  {
    path: "/parent",
    component: Parent,
    children: [
      { path: "child", component: () => import("./Child.vue") },
      { path: "", component: IndexPage },
      { path: "/absolute", component: Parent },
    ],
  },
];
export default makeRouter({ routes });
'''
    facts = extract_frontend_facts("src/router/index.ts", source)

    assert [(route.framework, route.path, route.component.specifier) for route in facts.routes] == [
        ("vue", "/parent", "./Parent.vue"),
        ("vue", "/parent/child", "./Child.vue"),
        ("vue", "/parent", "./Index.vue"),
        ("vue", "/absolute", "./Parent.vue"),
    ]
    assert facts.routes[1].component.source_kind == "route_dynamic_import"
    assert "./Child.vue" not in {item.specifier for item in facts.imports}


@pytest.mark.parametrize(
    "source",
    [
        b'''import Page from "./Page.vue"; const createRouter = x => x; createRouter({ routes: [{ path: "/x", component: Page }] });''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; { const createRouter = x => x; createRouter({ routes: [{ path: "/x", component: Page }] }); }''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; const extra=[]; createRouter({ routes: [...extra, { path: "/x", component: Page }] });''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; const routes=[]; routes.push({path:"/x",component:Page}); createRouter({routes});''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; const routes=build([{path:"/x",component:Page}]); createRouter({routes});''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; createRouter({routes:[{path:`/${name}`,component:Page}]});''',
        b'''import { createRouter } from "vue-router"; import Page from "./Page.vue"; createRouter({routes:[{path:"../x",component:Page}]});''',
        b'''import { createRouter } from "vue-router"; createRouter({routes:[{path:"/x",component:Missing}]});''',
    ],
)
def test_vue_router_rejects_custom_shadowed_mutated_or_computed_forms(
    source: bytes,
) -> None:
    facts = extract_frontend_facts("src/router/index.ts", source)

    assert facts.routes == ()


def test_react_object_routes_and_lazy_imports_compose_nested_paths() -> None:
    source = b'''import { createBrowserRouter as makeRouter } from "react-router-dom";
import Layout from "./Layout";
import { Page as ChildPage } from "./Page";
const routes = [{
  path: "/app",
  element: <Layout />,
  children: [
    { path: "child", Component: ChildPage },
    { path: "lazy", lazy: () => import("./LazyPage") },
  ],
}];
export const router = makeRouter(routes);
'''
    facts = extract_frontend_facts("src/routes.tsx", source)

    assert [(route.path, route.component.specifier) for route in facts.routes] == [
        ("/app", "./Layout"),
        ("/app/child", "./Page"),
        ("/app/lazy", "./LazyPage"),
    ]


def test_react_jsx_route_supports_nested_children_and_import_alias() -> None:
    source = b'''import { Route as R } from "react-router-dom";
import Layout from "./Layout";
import Page from "./Page";
const view = (
  <R path="/root" element={<Layout />}>
    <R path="child" Component={Page} />
  </R>
);
'''
    facts = extract_frontend_facts("src/routes.tsx", source)

    assert [(route.path, route.component.specifier) for route in facts.routes] == [
        ("/root", "./Layout"),
        ("/root/child", "./Page"),
    ]


@pytest.mark.parametrize(
    "source",
    [
        b'''import Page from "./Page"; const Route = p => <div/>; const x=<Route path="/x" Component={Page}/>;''',
        b'''import { Route } from "react-router-dom"; import Page from "./Page"; { const Route=p=><div/>; const x=<Route path="/x" Component={Page}/>; }''',
        b'''import { createBrowserRouter } from "react-router-dom"; import Page from "./Page"; const routes=[]; routes.push({path:"/x",Component:Page}); createBrowserRouter(routes);''',
        b'''import { useRoutes } from "react-router-dom"; import Page from "./Page"; useRoutes([{...base,path:"/x",Component:Page}]);''',
        b'''import { Route } from "react-router-dom"; import Page from "./Page"; const x=<Route path={computed} Component={Page}/>;''',
    ],
)
def test_react_router_rejects_custom_shadowed_mutated_spread_or_computed_forms(
    source: bytes,
) -> None:
    facts = extract_frontend_facts("src/routes.tsx", source)

    assert facts.routes == ()


def test_frontend_fact_caps_are_source_ordered_and_diagnostic() -> None:
    imports = "\n".join(
        f'import Item{index} from "./item{index}";' for index in range(65)
    )
    routes = ",\n".join(
        f'{{ path: "/r{index}", component: Item0 }}' for index in range(129)
    )
    source = f'''import {{ createRouter }} from "vue-router";
{imports}
createRouter({{ routes: [{routes}] }});
'''.encode("utf-8")
    facts = extract_frontend_facts("src/router.ts", source)

    assert len(facts.imports) == 64
    assert _diagnostic_count(facts, "imports_omitted") == 2
    assert len(facts.routes) == 128
    assert facts.routes[0].path == "/r0"
    assert facts.routes[-1].path == "/r127"
    assert _diagnostic_count(facts, "routes_omitted") == 1


def test_frozen_vue_and_react_routes_are_positive_while_shadowed_are_negative() -> None:
    cases = [
        ("vue/src/router/index.ts", "/orders"),
        ("react/src/routes.tsx", "/orders"),
    ]
    for relative, expected_path in cases:
        path = FIXTURES / relative
        facts = extract_frontend_facts(relative.split("/", 1)[1], path.read_bytes())
        assert [route.path for route in facts.routes] == [expected_path]

    for relative in (
        "vue/src/router/shadowed.ts",
        "react/src/shadowedRoutes.tsx",
    ):
        path = FIXTURES / relative
        facts = extract_frontend_facts(relative.split("/", 1)[1], path.read_bytes())
        assert facts.routes == ()


def _frontend_module(path: Path, chunk: DocumentChunk) -> CodeSignal:
    return CodeSignal(
        signal_id=generate_core_module_signal_id(
            file_path=path.as_posix(),
            start_line=chunk.start_line,
            start_column=0,
            end_line=chunk.end_line,
            end_column=0,
        ),
        chunk_id=chunk.chunk_id,
        file_path=path,
        kind="module",
        name=path.as_posix(),
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        language="typescript",
        qualified_name=path.as_posix(),
        project_unit_key="",
        producer="core_module",
        recallable=False,
    )


def test_frontend_graph_uses_the_complete_active_candidate_set() -> None:
    path = Path("src/routes.tsx")
    source = b'''import { createBrowserRouter } from "react-router-dom";
import View from "./View";
createBrowserRouter([{ path: "/view", Component: View }]);
'''
    chunk = DocumentChunk(
        "frontend-chunk",
        path,
        1,
        3,
        source.decode(),
        "code",
    )
    context = PluginContext(
        path,
        "typescript",
        "",
        {},
        (path, Path("src/View.ts"), Path("src/View.js")),
    )
    producer = FrontendGraphProducer()

    parsed = producer.parse(context, source)
    graph = producer.materialize(
        context,
        parsed,
        (chunk,),
        _frontend_module(path, chunk),
    )

    [route] = graph.signals
    assert route.kind == "route"
    assert route.name == "/view"
    assert route.recallable is False
    view_relations = [
        relation
        for relation in graph.relations
        if relation.target_name == "./View"
    ]
    assert {relation.kind for relation in view_relations} == {
        "imports",
        "routes_to",
    }
    assert all(
        relation.metadata["candidates"] == ("src/View.ts", "src/View.js")
        for relation in view_relations
    )
    assert all(relation.resolution == "unresolved" for relation in graph.relations)


def test_frontend_graph_missing_route_chunk_fails_the_producer_closed() -> None:
    path = Path("src/routes.tsx")
    source = b'''import { createBrowserRouter } from "react-router-dom";
import View from "./View.ts";
createBrowserRouter([{ path: "/view", Component: View }]);
'''
    chunk = DocumentChunk("first", path, 1, 1, source.decode(), "code")
    context = PluginContext(
        path,
        "typescript",
        "",
        {},
        (path, Path("src/View.ts")),
    )
    producer = FrontendGraphProducer()
    parsed = producer.parse(context, source)

    graph = producer.materialize(
        context,
        parsed,
        (chunk,),
        _frontend_module(path, chunk),
    )

    assert graph.signals == ()
    assert graph.relations == ()
    assert graph.metadata["graph_materialize_status"] == "missing_chunk"
