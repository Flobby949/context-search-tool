from pathlib import Path

from context_search_tool import exploration
from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.context_pack import build_context_pack
from context_search_tool.formatters import format_json
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository, trace_repository
from context_search_tool.retrieval_scope import RetrievalScope


def test_public_surfaces_share_path_diverse_final_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src"
    source.mkdir(parents=True)
    repeated_lines = [
        (
            f"# path diversity target block {block} line {line}"
            if block % 2 == 0
            else f"# unrelated filler block {block} line {line}"
        )
        for block in range(7)
        for line in range(80)
    ]
    (source / "a_dominant.py").write_text(
        "\n".join(repeated_lines) + "\n",
        encoding="utf-8",
    )
    (source / "b_support.py").write_text(
        "def path_diversity_target_support():\n"
        "    return 'path diversity target support'\n",
        encoding="utf-8",
    )
    (source / "c_boundary.py").write_text(
        "def path_diversity_target_boundary():\n"
        "    return 'path diversity target boundary'\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=40,
            final_top_k=3,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)

    first = query_repository(repo, "path diversity target", config)
    traced = trace_repository(repo, "path diversity target", config)
    repeated = query_repository(repo, "path diversity target", config)

    first_paths = [item.file_path for item in first.results]
    assert set(first_paths) == {
        Path("src/a_dominant.py"),
        Path("src/b_support.py"),
        Path("src/c_boundary.py"),
    }
    assert len(first_paths) == len(set(first_paths))
    assert (
        format_json(first).encode("utf-8")
        == format_json(traced.bundle).encode("utf-8")
        == format_json(repeated).encode("utf-8")
    )
    assert [
        (item.file_path, item.start_line, item.end_line, item.content)
        for item in first.results
    ] == [
        (item.file_path, item.start_line, item.end_line, item.content)
        for item in traced.bundle.results
    ] == [
        (item.file_path, item.start_line, item.end_line, item.content)
        for item in repeated.results
    ]
    final_stage = traced.trace.stages[-1]
    assert dict(final_stage.decision_counts)["duplicate_result_path"] > 0

    options = exploration.resolve_explore_pack_options(
        config,
        context_lines=None,
    )
    assert options.max_items >= len(first_paths)
    pack = build_context_pack(first, options)
    assert {Path(item.file_path) for item in pack.items} == set(first_paths)
    explored = exploration.explore_repository(
        repo,
        "path diversity target",
        config,
        options,
    )
    assert [item.file_path for item in explored.initial_bundle.results] == first_paths


def test_controlled_followup_keeps_hard_scope_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    allowed = repo / "allowed"
    excluded = repo / "excluded"
    allowed.mkdir(parents=True)
    excluded.mkdir(parents=True)
    (allowed / "OwnerController.java").write_text(
        "class OwnerController { void registerOwner() {} }\n",
        encoding="utf-8",
    )
    (excluded / "OwnerControllerTests.java").write_text(
        "class OwnerControllerTests { void ownerRegistrationTest() {} }\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    options = exploration.resolve_explore_pack_options(
        config,
        context_lines=None,
    )

    explored = exploration.explore_repository(
        repo,
        "OwnerController test",
        config,
        options,
        scope=RetrievalScope(include_paths=("allowed/",)),
    )

    assert explored.trace.retrieval_call_count == 2
    assert explored.trace.termination_reason == "no_marginal_gain"
    assert {
        result.file_path.as_posix()
        for result in explored.fused_bundle.results
    } == {"allowed/OwnerController.java"}
    assert all(
        item.file_path.startswith("allowed/")
        for item in explored.final_pack.items
    )
    assert all(
        seed_path.startswith("allowed/")
        for round_record in explored.trace.rounds
        for probe in round_record.probes
        for seed_path in probe.seed_paths
    )
