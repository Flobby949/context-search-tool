"""P12 paired acceptance runner: capture / compare / check.

capture reindexes the pinned project copies (bge) under the
implementation selected by PYTHONPATH, injects the frozen sampling
options into whichever tree is loaded, runs the frozen gold twice
in-process with the planner on (or off for the reference), enforces
the determinism and planner-status STOPs, and records the evidence
schema — never source bodies or absolute paths. compare applies gates
G1-G4 and G6. check validates capture invariants.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_real_python_graphs_acceptance as p8

SCHEMA_VERSION = 1
PINNED_OPTIONS = {"temperature": 0, "seed": 0, "top_k": 1}
PROJECTS = ("Investment-Assistant", "backend-template", "git-course")


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=1
    ) + "\n"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_gold(override: Path | None = None) -> dict:
    path = override or (
        Path(__file__).resolve().parent / "fixtures/p12_planner/gold.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_sources(sources_root: Path, gold: dict) -> None:
    manifest = json.loads(
        (sources_root / "manifest.json").read_text(encoding="utf-8")
    )
    for name, proj in gold["projects"].items():
        root = sources_root / name
        if not root.is_dir():
            raise RuntimeError(f"BLOCKED: pinned copy missing: {name}")
        files = {
            str(p.relative_to(root)): _sha(p)
            for p in sorted(root.rglob("*"))
            if p.is_file() and ".context-search" not in p.parts
        }
        agg = hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest()
        if agg != proj["aggregate_sha256"] or agg != manifest[name][
            "aggregate_sha256"
        ]:
            raise RuntimeError(f"STOP: source drift in {name}")


def _install_options_pin() -> None:
    """Inject the frozen sampling options into WHICHEVER tree
    PYTHONPATH selected (baseline trees predate the product pin)."""
    from context_search_tool import query_planner as qp

    original = qp.OllamaQueryPlanner.plan

    def pinned(self, query, repo_profile=None, **kwargs):
        session_post = self.session.post

        def post(url, **request):
            body = request.get("json")
            if isinstance(body, dict):
                body["options"] = dict(PINNED_OPTIONS)
            return session_post(url, **request)

        self.session.post = post
        try:
            return original(self, query, repo_profile=repo_profile, **kwargs)
        finally:
            self.session.post = session_post

    qp.OllamaQueryPlanner.plan = pinned


def _query_config(planner_on: bool):
    import dataclasses

    base = p8._embedding_config("bge")
    return dataclasses.replace(
        base,
        query_planner=dataclasses.replace(
            base.query_planner, enabled=planner_on
        ),
    )


def capture(
    implementation_root: Path,
    sources_root: Path,
    output_path: Path,
    *,
    planner_on: bool = True,
    gold_override: Path | None = None,
) -> dict:
    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository

    gold = _load_gold(gold_override)
    _validate_sources(sources_root, gold)
    p8._install_bge_truncation()
    _install_options_pin()
    config = _query_config(planner_on)
    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "implementation": p8.implementation_identity(implementation_root),
        "planner_on": planner_on,
        "embedding_identity": {
            "provider": "bge",
            "model": "bge-m3",
            "dimensions": 1024,
            "digest": p8._ollama_model_digest("bge-m3"),
        },
        "planner_identity": {
            "provider": "ollama",
            "model": config.query_planner.model,
            "digest": p8._ollama_model_digest(config.query_planner.model),
            "injected_options": PINNED_OPTIONS,
        },
        "cases": {},
        "timing": {},
    }

    scratch = Path(tempfile.mkdtemp(prefix="cst-p12-capture-"))
    latencies: list[float] = []
    for name, proj in sorted(gold["projects"].items()):
        workspace = scratch / name
        shutil.copytree(
            sources_root / name,
            workspace,
            ignore=shutil.ignore_patterns(".context-search"),
        )
        index_repository(workspace, config)
        for case in proj["queries"]:
            passes = []
            for _ in range(2):
                started = time.perf_counter()
                bundle = query_repository(workspace, case["query"], config)
                elapsed = time.perf_counter() - started
                latencies.append(elapsed)
                selected = [str(r.file_path) for r in bundle.results]
                ranks = {
                    req: (
                        selected.index(req) + 1
                        if req in selected
                        else None
                    )
                    for req in case["required"]
                }
                plan = bundle.planner
                if planner_on and plan.status != "ok":
                    raise RuntimeError(
                        f"STOP: planner status {plan.status!r}"
                        f" on {case['id']}"
                    )
                passes.append(
                    {
                        "required_ranks": ranks,
                        "selected": selected,
                        "planner_status": plan.status,
                        "kept_hints": len(plan.grep_keywords)
                        + len(plan.symbol_hints),
                        "discarded_hints": len(plan.discarded_hints),
                        "surviving": {
                            "grep_keywords": plan.grep_keywords,
                            "symbol_hints": plan.symbol_hints,
                            "rewritten_queries": plan.rewritten_queries,
                        },
                        "latency_seconds": round(elapsed, 5),
                    }
                )
            if passes[0]["required_ranks"] != passes[1]["required_ranks"]:
                raise RuntimeError(
                    f"STOP: pass divergence on {case['id']}"
                )
            payload["cases"][case["id"]] = {
                "project": name,
                "hit": sum(
                    1
                    for v in passes[0]["required_ranks"].values()
                    if v is not None
                ),
                "of": len(case["required"]),
                "passes": passes,
            }
    payload["timing"]["mean_latency_seconds"] = round(
        sum(latencies) / len(latencies), 5
    )
    rendered = _canonical(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    shutil.rmtree(scratch, ignore_errors=True)
    return payload


def _hits(capture_payload: dict) -> int:
    return sum(case["hit"] for case in capture_payload["cases"].values())


def _project_hits(capture_payload: dict) -> dict[str, int]:
    totals: dict[str, int] = {}
    for case in capture_payload["cases"].values():
        totals[case["project"]] = totals.get(case["project"], 0) + case["hit"]
    return totals


def compare(
    baseline: dict,
    candidate: dict,
    reference: dict,
    output_path: Path | None = None,
) -> dict:
    if set(baseline["cases"]) != set(candidate["cases"]):
        raise ValueError("case sets differ")
    gates = {
        "g1_gain_at_least_5": _hits(candidate) >= _hits(baseline) + 5,
        "g2_no_project_regression": all(
            _project_hits(candidate).get(name, 0) >= hits
            for name, hits in _project_hits(baseline).items()
        ),
        "g3_no_query_zeroed": all(
            candidate["cases"][cid]["hit"] > 0
            for cid, case in baseline["cases"].items()
            if case["hit"] > 0
        ),
        "g4_latency_bounded": (
            candidate["timing"]["mean_latency_seconds"]
            <= 1.5 * baseline["timing"]["mean_latency_seconds"]
        ),
        "g6_beats_planner_off": _hits(candidate) >= _hits(reference) + 3,
    }
    report = {
        "hits": {
            "reference_planner_off": _hits(reference),
            "baseline": _hits(baseline),
            "candidate": _hits(candidate),
        },
        "per_project": {
            "baseline": _project_hits(baseline),
            "candidate": _project_hits(candidate),
        },
        "timing": {
            "baseline": baseline["timing"],
            "candidate": candidate["timing"],
        },
        "gates": gates,
        "disposition": "ship" if all(gates.values()) else "reject",
    }
    if output_path is not None:
        output_path.write_text(_canonical(report), encoding="utf-8")
    return report


def check(capture_path: Path) -> None:
    rendered = capture_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported capture schema")
    if _canonical(payload) != rendered:
        raise ValueError("capture is not canonically rendered")
    for marker in ("/Users/", "/private/", "/home/"):
        if marker in rendered:
            raise ValueError("capture contains an absolute path")
    for case in payload["cases"].values():
        for item in case["passes"]:
            if "content" in item or "snippet" in item:
                raise ValueError("capture contains source content")
    if len(payload["cases"]) not in (8, 21):
        raise ValueError("capture must contain all gold cases")


def main() -> int:
    command = sys.argv[1]
    if command == "capture":
        planner_on = "--planner" not in sys.argv or (
            sys.argv[sys.argv.index("--planner") + 1] != "off"
        )
        gold_override = (
            Path(sys.argv[sys.argv.index("--gold") + 1])
            if "--gold" in sys.argv
            else None
        )
        capture(
            Path(sys.argv[2]),
            Path(sys.argv[3]),
            Path(sys.argv[4]),
            planner_on=planner_on,
            gold_override=gold_override,
        )
        print(f"captured {sys.argv[4]}")
        return 0
    if command == "compare":
        report = compare(
            json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")),
            json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")),
            json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")),
            Path(sys.argv[5]),
        )
        print(json.dumps(report["gates"], indent=1, sort_keys=True))
        print("disposition:", report["disposition"])
        return 0
    if command == "check":
        check(Path(sys.argv[2]))
        print("capture verified")
        return 0
    print("usage: capture <impl> <sources> <out> [--planner off] | compare <base> <cand> <ref> <out> | check <capture>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
