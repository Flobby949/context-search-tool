from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_BASELINE = "b827707325d0ee4e9c6b2bcb3dee39955c263822"
P3_BASELINE_BLOB = "a0011178b2671af25cb0853260c8fdcf586acee0"
P0_P3_CATALOG_BLOB = "8bbe4d560fec1499aa1f436af929b8a6bb6f3eac"
P0_P3_CATALOG_SHA256 = (
    "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5"
)
PETCLINIC_COMMIT = "51045d1648dad955df586150c1a1a6e22ef400c2"
BASELINE_PASSED = 1938

P4_CATALOG_PATH = ROOT / "tests/fixtures/retrieval_quality/p4_exploration.json"
P4_MANIFEST_PATH = ROOT / "tests/fixtures/p4_exploration/input_manifest.json"
P2_PROJECTION_PATH = ROOT / "tests/fixtures/p4_exploration/p0_p3_p2_quality.json"
CI_PROJECTION_PATH = ROOT / "tests/fixtures/p4_exploration/p0_p3_ci_quality.json"
P3_BASELINE_PATH = (
    ROOT / "tests/fixtures/retrieval_core_decomposition/baseline.json"
)
P0_P3_CATALOG_PATH = ROOT / "tests/fixtures/retrieval_quality/queries.json"

PROTECTED_INPUT_PATHS = (
    "tests/fixtures/retrieval_quality/queries.json",
    "tests/fixtures/real_projects/program_tool",
    "tests/fixtures/context-pack-java",
    "tests/fixtures/context-pack-docs",
    "tests/fixtures/java-spring-mini",
    "tests/fixtures/retrieval_core_decomposition",
)

FROZEN_P4_INPUT_PATHS = (
    "tests/fixtures/retrieval_quality/p4_exploration.json",
    "tests/fixtures/p4-exploration-java",
    "tests/fixtures/p4-exploration-duplicate",
    "tests/fixtures/real_projects/program_tool",
)

EXPECTED_CASES = {
    "p4_exploration": (
        ("p4_exploration_java", "owner-registration-form-test"),
        ("p4_exploration_java", "owner-controller-exact"),
        ("p4_exploration_frontend", "qrcode-route-service-type"),
        ("p4_exploration_duplicate", "solo-controller-no-gain"),
    ),
    "p4_real_exploration": (
        ("spring_petclinic", "owner-registration-form-validation"),
    ),
}

_COMMON_CASE_FIELDS = {
    "id",
    "query",
    "profiles",
    "mode",
    "tags",
    "gate",
    "expected_top_k",
    "expected_context_groups",
    "expected_pack_status",
    "minimum_context_confidence",
    "expected_need_matches",
    "maximum_pack_bytes",
    "maximum_truncated_items",
    "forbidden_next_query_patterns",
}
_EXPLORATION_CASE_FIELDS = {
    "initial_absent",
    "final_present",
    "final_at_least",
    "final_forbidden",
    "final_noise_matchers",
    "expected_termination_reason",
    "expected_retrieval_call_count",
    "maximum_retrieval_call_count",
    "minimum_goal_gain",
    "maximum_final_noise_items",
}


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _worktree_files(relative_path: str) -> list[Path]:
    output = subprocess.run(
        (
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            relative_path,
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def working_tree_content_hash(relative_path: str) -> str:
    target = ROOT / relative_path
    files = _worktree_files(relative_path)
    if target.is_file() and files == [target]:
        return sha256_file(target)

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(target).as_posix()):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"P4 input is not a regular file: {path}")
        relative = path.relative_to(target).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def assert_protected_inputs() -> None:
    _git("cat-file", "-e", f"{IMPLEMENTATION_BASELINE}^{{commit}}")
    if _git("hash-object", str(P3_BASELINE_PATH)).stdout.strip() != P3_BASELINE_BLOB:
        raise RuntimeError("P3.2 baseline blob changed")
    if _git("hash-object", str(P0_P3_CATALOG_PATH)).stdout.strip() != P0_P3_CATALOG_BLOB:
        raise RuntimeError("P0-P3 quality catalog blob changed")
    if sha256_file(P0_P3_CATALOG_PATH) != P0_P3_CATALOG_SHA256:
        raise RuntimeError("P0-P3 quality catalog content changed")

    diff = _git(
        "diff",
        "--exit-code",
        IMPLEMENTATION_BASELINE,
        "--",
        *PROTECTED_INPUT_PATHS,
        check=False,
    )
    if diff.returncode:
        raise RuntimeError("protected P0-P3 inputs differ from the baseline")
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *PROTECTED_INPUT_PATHS,
    ).stdout
    if status:
        raise RuntimeError("protected P0-P3 inputs have worktree drift")


def load_raw_p4_catalog(path: Path = P4_CATALOG_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"schema_version", "profile_configs", "repos"}:
        raise ValueError("P4 catalog has unknown top-level fields")
    if data["schema_version"] != 1:
        raise ValueError("P4 catalog schema_version must be 1")
    if set(data["profile_configs"]) != set(EXPECTED_CASES):
        raise ValueError("P4 catalog must define only the two P4 profiles")

    deterministic = data["profile_configs"]["p4_exploration"]
    if deterministic.get("embedding") != {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384,
    }:
        raise ValueError("deterministic P4 profile must use hash-v1")
    if deterministic.get("query_planner") != {"enabled": False}:
        raise ValueError("deterministic P4 profile must disable the planner")

    inventory: dict[str, list[tuple[str, str]]] = {
        profile: [] for profile in EXPECTED_CASES
    }
    for repo in data["repos"]:
        if not isinstance(repo, dict):
            raise ValueError("P4 repo entry must be an object")
        repo_key = repo.get("repo_key")
        for case in repo.get("queries", []):
            unknown = set(case) - _COMMON_CASE_FIELDS - _EXPLORATION_CASE_FIELDS
            if unknown:
                raise ValueError(f"unknown P4 case field: {sorted(unknown)[0]}")
            if case.get("mode") != "exploration":
                raise ValueError("every P4 case must use exploration mode")
            profiles = tuple(case.get("profiles", repo.get("profiles", ())))
            if len(profiles) != 1 or profiles[0] not in EXPECTED_CASES:
                raise ValueError("every P4 case must select exactly one P4 profile")
            inventory[profiles[0]].append((repo_key, case.get("id")))

        if "p4_exploration" in repo.get("profiles", ()):
            if not repo.get("snapshot_path"):
                raise ValueError("deterministic P4 repos must use snapshots")
            if repo.get("source_url") or repo.get("source_commit"):
                raise ValueError("deterministic P4 repos must not require network")
        if repo_key == "spring_petclinic":
            if repo.get("source_commit") != PETCLINIC_COMMIT:
                raise ValueError("PetClinic source commit changed")

    for profile, expected in EXPECTED_CASES.items():
        if tuple(inventory[profile]) != expected:
            raise ValueError(f"unexpected {profile} case inventory")
    return data


def load_input_manifest(path: Path = P4_MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("P4 input manifest schema_version must be 1")
    if manifest.get("implementation_baseline") != IMPLEMENTATION_BASELINE:
        raise ValueError("P4 input manifest baseline changed")
    if manifest.get("p3_baseline_blob") != P3_BASELINE_BLOB:
        raise ValueError("P4 input manifest P3.2 blob changed")
    if manifest.get("p0_p3_catalog_blob") != P0_P3_CATALOG_BLOB:
        raise ValueError("P4 input manifest catalog blob changed")
    if manifest.get("p0_p3_catalog_sha256") != P0_P3_CATALOG_SHA256:
        raise ValueError("P4 input manifest catalog SHA-256 changed")

    entries = manifest.get("inputs")
    if not isinstance(entries, list):
        raise ValueError("P4 input manifest requires inputs")
    expected_paths = (*FROZEN_P4_INPUT_PATHS,)
    if tuple(entry.get("path") for entry in entries) != expected_paths:
        raise ValueError("P4 input manifest path order changed")
    for entry in entries:
        relative = entry["path"]
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("P4 input manifest path must be repository-relative")
        if working_tree_content_hash(relative) != entry.get("sha256"):
            raise ValueError(f"P4 input hash changed: {relative}")

    projections = manifest.get("quality_projections")
    expected_projections = (
        "tests/fixtures/p4_exploration/p0_p3_p2_quality.json",
        "tests/fixtures/p4_exploration/p0_p3_ci_quality.json",
    )
    if tuple(entry.get("path") for entry in projections or ()) != expected_projections:
        raise ValueError("P4 quality projection inventory changed")
    for entry in projections:
        if sha256_file(ROOT / entry["path"]) != entry.get("sha256"):
            raise ValueError(f"P4 quality projection changed: {entry['path']}")
    return manifest


def _without_timing(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_timing(item)
            for key, item in value.items()
            if key not in {"latency_ms", "generated_at"}
        }
    if isinstance(value, list):
        return [_without_timing(item) for item in value]
    return value


def p0_p3_quality_projection(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("generated_at", None)
    payload.get("command_args", {}).pop("fixture_path", None)
    payload.get("tool", {}).pop("git_commit", None)
    payload.get("fixture", {}).pop("path", None)
    for repo in payload.get("repos", []):
        repo.pop("workspace", None)
    return _without_timing(payload)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def verify_final_junit(path: Path) -> dict[str, int]:
    baseline = json.loads(P3_BASELINE_PATH.read_text(encoding="utf-8"))[
        "test_evidence"
    ]
    root = ElementTree.parse(path).getroot()
    suite = next(root.iter("testsuite"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", "0"))
    tests = int(suite.attrib["tests"])
    skips: list[dict[str, str]] = []
    xfails: list[dict[str, str]] = []
    p4_tests = 0
    for testcase in root.iter("testcase"):
        class_name = testcase.attrib.get("classname", "")
        if class_name.startswith("tests.test_exploration_") or class_name == (
            "tests.test_quality_p4"
        ):
            p4_tests += 1
        skipped_node = testcase.find("skipped")
        if skipped_node is None:
            continue
        entry = {
            "node_id": f"{class_name}::{testcase.attrib['name']}",
            "reason": skipped_node.attrib.get("message", ""),
        }
        if skipped_node.attrib.get("type") == "pytest.xfail":
            xfails.append(entry)
        else:
            skips.append(entry)

    if failures or errors:
        raise RuntimeError("final JUnit contains failures or errors")
    if skipped != baseline["skipped"] or skips != baseline["skips"]:
        raise RuntimeError("final JUnit skip identity changed")
    if xfails != baseline["xfails"]:
        raise RuntimeError("final JUnit xfail identity changed")
    if tests - skipped != BASELINE_PASSED + p4_tests:
        raise RuntimeError("final JUnit passed count does not match P4 inventory")
    return {
        "passed": tests - skipped,
        "skipped": skipped,
        "xfails": len(xfails),
        "p4_tests": p4_tests,
    }
