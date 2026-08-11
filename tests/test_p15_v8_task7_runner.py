from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import p15_v8_task7_runner as runner

from context_search_tool.config import DEFAULT_CONFIG


def _write_package(repo: Path) -> None:
    package = repo / "src/pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text(
        "from .b import Bee\n"
        "from .c import Sea\n\n"
        "class Owner:\n"
        "    def run(self):\n"
        "        return Bee(), Sea()\n",
        encoding="utf-8",
    )
    (package / "b.py").write_text("class Bee: pass\n", encoding="utf-8")
    (package / "c.py").write_text("class Sea: pass\n", encoding="utf-8")


def test_candidate_blind_pool_emits_one_query_per_source_owner(
    tmp_path: Path,
) -> None:
    _write_package(tmp_path)

    cases = runner.derive_eligible_cases(tmp_path)

    assert [(case.source_symbol, case.target_path) for case in cases] == [
        ("Owner", "src/pkg/b.py"),
    ]
    payload = runner._case_payload("fresh-r01", 1, cases[0])
    assert "Bee" not in payload["query"]
    assert payload["required_paths"] == ["src/pkg/a.py"]
    assert payload["relevant_paths"] == [
        "src/pkg/a.py",
        "src/pkg/b.py",
        "src/pkg/c.py",
    ]


def test_candidate_blind_pool_counts_conditional_and_owner_local_imports_as_relevant(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src/pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "from .b import Bee\n"
        "if TYPE_CHECKING:\n"
        "    from .c import Sea\n\n"
        "class Owner:\n"
        "    def run(self):\n"
        "        from .d import Dee\n"
        "        return Bee(), Sea(), Dee()\n",
        encoding="utf-8",
    )
    (package / "b.py").write_text("class Bee: pass\n", encoding="utf-8")
    (package / "c.py").write_text("class Sea: pass\n", encoding="utf-8")
    (package / "d.py").write_text("class Dee: pass\n", encoding="utf-8")

    cases = runner.derive_eligible_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].relevant_paths == (
        "src/pkg/a.py",
        "src/pkg/b.py",
        "src/pkg/c.py",
        "src/pkg/d.py",
    )


def test_candidate_blind_pool_excludes_reexport_without_target_declaration(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src/pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text(
        "from .b import Bee\n"
        "from .c import Sea\n\n"
        "class Owner:\n"
        "    def run(self):\n"
        "        return Bee(), Sea()\n",
        encoding="utf-8",
    )
    (package / "b.py").write_text("from .d import Bee\n", encoding="utf-8")
    (package / "c.py").write_text("class Sea: pass\n", encoding="utf-8")
    (package / "d.py").write_text("class Bee: pass\n", encoding="utf-8")

    cases = runner.derive_eligible_cases(tmp_path)

    assert [(case.source_symbol, case.target_path) for case in cases] == [
        ("Owner", "src/pkg/c.py"),
    ]
    assert cases[0].relevant_paths == (
        "src/pkg/a.py",
        "src/pkg/b.py",
        "src/pkg/c.py",
    )


def test_task7_config_freezes_online_identity_without_repo_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "read_config", lambda _repo: DEFAULT_CONFIG)

    config = runner.task7_config(tmp_path)

    assert config.query_planner.enabled is True
    assert config.query_planner.send_repo_profile is False
    assert config.query_planner.timeout_seconds == 60
    assert config.query_planner.model == "Qwen/Qwen2.5-14B-Instruct"
    assert config.embedding.model == "Pro/BAAI/bge-m3"
    assert config.embedding.dimensions == 1024
    assert config.retrieval.consume_dependency_hints is False
    assert config.retrieval.final_top_k == 12


def test_replay_projects_existing_witness_and_observation() -> None:
    witness = {field: f"value-{field}" for field in runner.closure.WITNESS_FIELDS}
    witness.update(
        {
            "source_file_path": "src/source.py",
            "target_file_path": "src/target.py",
            "relation_kind": "imports",
            "resolution": "resolved_exact",
            "producer": "python_ast",
            "resolution_basis": "exact_python_imported_symbol",
        }
    )

    def fake_replay(_state, *, consume_dependency_hints, promotion_observer):
        promotion_observer(
            {
                "status": "promoted" if consume_dependency_hints else "disabled",
                "exact_source_hint_promoted": int(consume_dependency_hints),
                "exact_target_hint_promoted": 0,
                "semantic_pair_fallback_promoted": 0,
                "promoted_path_count": int(consume_dependency_hints),
            }
        )
        rows = [{"path": f"src/{index}.py"} for index in range(12)]
        if consume_dependency_hints:
            rows[-1] = {
                "path": "src/target.py",
                "planner_dependency_hint_promotion": 0.5,
                "closed_exact_witness": witness,
            }
        return {"top12": rows}

    replay = runner._replay(
        {}, enabled=True, replay_id="fresh-r01-c01-s1-treatment-r1", replay_fn=fake_replay
    )

    assert replay["top12"][-1]["closed_exact_witness"] == witness
    assert replay["promotion_report"]["mode_counts"]["exact_source_hint"] == 1
    assert replay["promotion_report"]["promoted_path_count"] == 1


def test_collect_case_uses_one_shared_capture_for_both_arms() -> None:
    state = {
        "plan": {"status": "ok"},
        "query_embedding_sha256": "e" * 64,
        "base_roster": [{"position": 1}],
        "canonical_sha256": "s" * 64,
    }
    captures = []

    def fake_capture(*_args):
        captures.append(object())
        return SimpleNamespace(
            replay_state=state,
            provider_observations=({"kind": "planner"}, {"kind": "embedding"}),
        )

    def fake_replay(_state, *, consume_dependency_hints, promotion_observer):
        promotion_observer(
            {
                "status": "no_eligible_closed_candidate"
                if consume_dependency_hints
                else "disabled",
                "exact_source_hint_promoted": 0,
                "exact_target_hint_promoted": 0,
                "semantic_pair_fallback_promoted": 0,
                "promoted_path_count": 0,
            }
        )
        return {"top12": [{"path": f"src/{index}.py"} for index in range(12)]}

    case = {
        "case_id": "fresh-r01-case-1",
        "repository_slot": "fresh-r01",
        "case_ordinal": 1,
        "query": "query",
        "cohort": "guard",
        "gold_target_path": "src/target.py",
        "required_paths": ["src/source.py"],
        "relevant_paths": ["src/source.py", "src/target.py"],
        "candidate_blind_target_missing": False,
        "replacement": False,
        "selection_proof": {},
    }

    observed = runner.collect_case(
        Path("repo"),
        case,
        DEFAULT_CONFIG,
        capture_fn=fake_capture,
        replay_fn=fake_replay,
    )

    assert len(captures) == 2
    assert len(observed["samples"]) == 2
    for sample in observed["samples"]:
        assert sample["control"]["capture"] == sample["treatment"]["capture"]
        assert len(sample["control"]["replays"]) == 2
        assert len(sample["treatment"]["replays"]) == 2
        assert sample["control"]["additional_planner_requests"] == 0
        assert sample["treatment"]["additional_embedding_requests"] == 0


def test_relative_import_resolution_uses_package_not_src_prefix() -> None:
    node = ast.parse("from .typing import Context\n").body[0]
    assert isinstance(node, ast.ImportFrom)

    assert runner._resolved_import_module(
        "structlog._base", "src/structlog/_base.py", node
    ) == "structlog.typing"
