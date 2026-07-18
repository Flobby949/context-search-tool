from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_BASELINE = "319dfedc777b7479e9b542c1e65ddd15814100b1"
PETCLINIC_COMMIT = "51045d1648dad955df586150c1a1a6e22ef400c2"

P5_CATALOG_PATH = ROOT / "tests/fixtures/retrieval_quality/p5_language_graphs.json"
P5_REAL_CATALOG_PATH = (
    ROOT / "tests/fixtures/retrieval_quality/p5_real_language_graphs.json"
)
P5_MANIFEST_PATH = ROOT / "tests/fixtures/p5_language_graphs/input_manifest.json"
PRE_P5_NO_EDGE_PATH = (
    ROOT / "tests/fixtures/p5_language_graphs/pre_p5_no_edge_projection.json"
)

P5_REPOSITORIES = {
    "p5_java_spring": "tests/fixtures/p5-language-graphs/java-spring",
    "p5_vue": "tests/fixtures/p5-language-graphs/vue",
    "p5_react": "tests/fixtures/p5-language-graphs/react",
    "p5_generic_tests": "tests/fixtures/p5-language-graphs/generic-tests",
    "p5_malformed_compat": "tests/fixtures/p5-language-graphs/malformed-compat",
}

P5_SOURCE_INVENTORY = {
    "p5_java_spring": (
        "nested/pom.xml",
        "nested/src/main/java/com/example/nested/NestedOnly.java",
        "nested/src/test/java/com/example/check/NestedOwnerCheck.java",
        "pom.xml",
        "src/main/java/com/example/order/DefaultOrderService.java",
        "src/main/java/com/example/order/Order.java",
        "src/main/java/com/example/order/OrderController.java",
        "src/main/java/com/example/order/OrderDto.java",
        "src/main/java/com/example/order/OrderFactory.java",
        "src/main/java/com/example/order/OrderMapper.java",
        "src/main/java/com/example/order/OrderService.java",
        "src/main/java/com/example/order/OrderStatus.java",
        "src/main/java/com/example/order/OrderValidator.java",
        "src/main/java/com/example/order/OverloadCaller.java",
        "src/main/java/com/example/order/OverloadService.java",
        "src/main/resources/mappers/OrderMapper.xml",
        "src/test/java/com/example/order/OrderControllerTests.java",
        "src/test/java/com/example/order/UnrelatedWorkerTests.java",
    ),
    "p5_vue": (
        "package.json",
        "src/Ambiguous.js",
        "src/Ambiguous.ts",
        "src/AmbiguousImporter.ts",
        "src/EscapeImporter.ts",
        "src/IndexTieImporter.ts",
        "src/catalog/OrdersRoutePageAlpha.ts",
        "src/catalog/OrdersRoutePageBeta.ts",
        "src/catalog/OrdersRoutePageDelta.ts",
        "src/catalog/OrdersRoutePageEpsilon.ts",
        "src/catalog/OrdersRoutePageEta.ts",
        "src/catalog/OrdersRoutePageGamma.ts",
        "src/catalog/OrdersRoutePageIota.ts",
        "src/catalog/OrdersRoutePageTheta.ts",
        "src/catalog/OrdersRoutePageZeta.ts",
        "src/router/index.ts",
        "src/router/shadowed.ts",
        "src/services/orderService.ts",
        "src/stores/orderStore.ts",
        "src/tied/index.js",
        "src/tied/index.ts",
        "src/types/order.ts",
        "src/views/OrdersView.vue",
        "src/views/ShadowView.vue",
    ),
    "p5_react": (
        "package.json",
        "src/pages/OrdersPage.tsx",
        "src/pages/ShadowPage.tsx",
        "src/routes.tsx",
        "src/services/orderService.ts",
        "src/shadowedRoutes.tsx",
        "src/types/order.ts",
    ),
    "p5_generic_tests": (
        "go/go.mod",
        "go/payment.go",
        "go/payment_test.go",
        "go/testdata/archive.go",
        "go/testdata/archive_test.go",
        "java/pom.xml",
        "java/src/main/java/com/example/contest/Contest.java",
        "java/src/main/java/com/example/generated/ArchiveWorker.java",
        "java/src/main/java/com/example/payment/PaymentService.java",
        "java/src/test/java/com/example/generated/ArchiveWorkerITCase.java",
        "java/src/test/java/com/example/payment/PaymentServiceTests.java",
        "javascript/package.json",
        "javascript/src/generated/archive.js",
        "javascript/src/payment.js",
        "javascript/tests/generated/archive.test.js",
        "javascript/tests/payment.test.js",
        "python/pyproject.toml",
        "python/src/generated/archive.py",
        "python/src/payment.py",
        "python/tests/generated/test_archive.py",
        "python/tests/test_payment.py",
        "rust/Cargo.toml",
        "rust/src/generated/archive.rs",
        "rust/src/payment.rs",
        "rust/tests/generated/archive.rs",
        "rust/tests/payment.rs",
        "typescript/package.json",
        "typescript/src/__tests__/generated/archive.spec.ts",
        "typescript/src/__tests__/payment.spec.ts",
        "typescript/src/generated/archive.ts",
        "typescript/src/payment.ts",
    ),
    "p5_malformed_compat": (
        "package.json",
        "pom.xml",
        "src/frontend/FakeFrontendTarget.ts",
        "src/frontend/MalformedFrontend.ts",
        "src/main/java/com/example/broken/BrokenMapper.java",
        "src/main/java/com/example/broken/MalformedJava.java",
        "src/main/java/com/example/custom/LocalController.java",
        "src/main/java/com/example/custom/LocalMapper.java",
        "src/main/java/com/example/custom/LocalRepository.java",
        "src/main/java/com/example/custom/LocalService.java",
        "src/main/java/com/example/custom/Mapper.java",
        "src/main/java/com/example/custom/Repository.java",
        "src/main/java/com/example/custom/RestController.java",
        "src/main/java/com/example/custom/Service.java",
        "src/main/java/com/example/standalone/Standalone.java",
        "src/main/java/com/example/znegative/ParserNeighbour.java",
        "src/main/resources/mappers/FakeTagMapper.xml",
        "src/main/resources/mappers/InternalSubsetMapper.xml",
        "src/main/resources/mappers/MalformedMapper.xml",
        "src/main/resources/mappers/XIncludeMapper.xml",
        "src/main/resources/mappers/XxeMapper.xml",
    ),
}

EXPECTED_DETERMINISTIC_CASES = (
    (
        "p5_java_spring",
        "java-owner-flow-results",
        "OrderController create order business flow",
        "results",
    ),
    (
        "p5_java_spring",
        "java-owner-flow-context",
        "OrderController create order business flow",
        "context_pack",
    ),
    ("p5_java_spring", "java-owner-test", "OrderController tests", "results"),
    (
        "p5_java_spring",
        "java-overload-ambiguous",
        "OverloadCaller same arity dispatch",
        "results",
    ),
    (
        "p5_java_spring",
        "java-duplicate-unit",
        "OrderController service implementation",
        "results",
    ),
    (
        "p5_vue",
        "vue-route-flow",
        "orders route view service store type",
        "results",
    ),
    (
        "p5_vue",
        "vue-route-exploration",
        "orders page route type",
        "exploration",
    ),
    (
        "p5_vue",
        "frontend-ambiguous-import",
        "AmbiguousImporter exact dependency",
        "results",
    ),
    (
        "p5_react",
        "react-route-flow",
        "orders react route page service type",
        "results",
    ),
    (
        "p5_generic_tests",
        "generic-test-conventions",
        "tests for cross language payment modules",
        "results",
    ),
    (
        "p5_malformed_compat",
        "malformed-fallback",
        "MalformedUniqueLexicalToken",
        "results",
    ),
    (
        "p5_malformed_compat",
        "no-legal-edge-compat",
        "StandaloneUniqueToken",
        "results",
    ),
)

EXPECTED_REAL_CASES = (
    (
        "spring_petclinic",
        "petclinic-owner-graph",
        "OwnerController owner flow repository domain object representing owner tests",
        "exploration",
    ),
    (
        "program_tool",
        "program-tool-qrcode-graph",
        "QRCode page route service type",
        "exploration",
    ),
)

JAVA_FLOW_PATHS = (
    "src/main/java/com/example/order/OrderController.java",
    "src/main/java/com/example/order/OrderService.java",
    "src/main/java/com/example/order/DefaultOrderService.java",
    "src/main/java/com/example/order/OrderMapper.java",
    "src/main/java/com/example/order/Order.java",
    "src/main/java/com/example/order/OrderDto.java",
)
GENERIC_POSITIVE_PATHS = (
    "java/src/main/java/com/example/payment/PaymentService.java",
    "java/src/test/java/com/example/payment/PaymentServiceTests.java",
    "go/payment.go",
    "go/payment_test.go",
    "rust/src/payment.rs",
    "rust/tests/payment.rs",
    "python/src/payment.py",
    "python/tests/test_payment.py",
    "javascript/src/payment.js",
    "javascript/tests/payment.test.js",
    "typescript/src/payment.ts",
    "typescript/src/__tests__/payment.spec.ts",
)
GENERIC_FORBIDDEN_PATHS = (
    "java/src/main/java/com/example/contest/Contest.java",
    "java/src/main/java/com/example/generated/ArchiveWorker.java",
    "go/testdata/archive.go",
    "rust/src/generated/archive.rs",
    "python/src/generated/archive.py",
    "javascript/src/generated/archive.js",
    "typescript/src/generated/archive.ts",
)

EXPECTED_CASE_POSITIVES = {
    "java-owner-flow-results": JAVA_FLOW_PATHS,
    "java-owner-flow-context": JAVA_FLOW_PATHS,
    "java-owner-test": (
        "src/test/java/com/example/order/OrderControllerTests.java",
    ),
    "java-overload-ambiguous": (
        "src/main/java/com/example/order/OverloadCaller.java",
    ),
    "java-duplicate-unit": (
        "src/main/java/com/example/order/OrderService.java",
    ),
    "vue-route-flow": (
        "src/router/index.ts",
        "src/views/OrdersView.vue",
        "src/services/orderService.ts",
        "src/stores/orderStore.ts",
        "src/types/order.ts",
    ),
    "vue-route-exploration": ("src/router/index.ts", "src/types/order.ts"),
    "react-route-flow": (
        "src/routes.tsx",
        "src/pages/OrdersPage.tsx",
        "src/services/orderService.ts",
        "src/types/order.ts",
    ),
    "frontend-ambiguous-import": ("src/AmbiguousImporter.ts",),
    "generic-test-conventions": GENERIC_POSITIVE_PATHS,
    "malformed-fallback": (
        "src/main/java/com/example/broken/MalformedJava.java",
    ),
    "no-legal-edge-compat": (
        "src/main/java/com/example/standalone/Standalone.java",
    ),
}

EXPECTED_CASE_NEGATIVES = {
    "java-owner-test": (
        "src/test/java/com/example/order/UnrelatedWorkerTests.java",
        "nested/src/test/java/com/example/check/NestedOwnerCheck.java",
    ),
    "java-duplicate-unit": (
        "nested/src/main/java/com/example/nested/NestedOnly.java",
    ),
    "generic-test-conventions": GENERIC_FORBIDDEN_PATHS,
    "malformed-fallback": (
        "src/main/java/com/example/znegative/ParserNeighbour.java",
    ),
}

GRAPH_ONLY_NEGATIVE_PATHS = {
    "java-overload-ambiguous": (
        "src/main/java/com/example/order/OverloadService.java",
    ),
    "frontend-ambiguous-import": ("src/Ambiguous.ts", "src/Ambiguous.js"),
}

PROTECTED_IDENTITIES = (
    {
        "path": "tests/fixtures/retrieval_quality/queries.json",
        "git_blob": "8bbe4d560fec1499aa1f436af929b8a6bb6f3eac",
        "sha256": "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5",
    },
    {
        "path": "tests/fixtures/retrieval_quality/p4_exploration.json",
        "git_blob": "2dde23938277e3fec5d63c6037365eedfbce74e4",
        "sha256": "110e806dead64b4270d579a955abc8f56d7ec23d1b1f61a7951e5e4309a9c683",
    },
    {
        "path": "tests/fixtures/p4_exploration/input_manifest.json",
        "git_blob": "f89118ea8c5e3fa94b9fcac5c832adc4326dd138",
        "sha256": "78e81f1c08c8216dc3355519cb89f07577ed61706e8150c9575e8395141c0b40",
    },
    {
        "path": "tests/fixtures/retrieval_core_decomposition/baseline.json",
        "git_blob": "a0011178b2671af25cb0853260c8fdcf586acee0",
        "sha256": "4235ec5539c548005d75b98be4a0c347364d40ec28a79fc45b10d351bcf8bed7",
    },
)

PROTECTED_INPUT_PATHS = (
    "tests/fixtures/retrieval_quality/queries.json",
    "tests/fixtures/retrieval_quality/p4_exploration.json",
    "tests/fixtures/p4_exploration",
    "tests/fixtures/retrieval_core_decomposition",
    "tests/fixtures/real_projects/program_tool",
    "tests/fixtures/context-pack-java",
    "tests/fixtures/context-pack-docs",
    "tests/fixtures/java-spring-mini",
    "tests/fixtures/p4-exploration-java",
    "tests/fixtures/p4-exploration-duplicate",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def assert_protected_inputs() -> None:
    for expected in PROTECTED_IDENTITIES:
        path = ROOT / expected["path"]
        if _git("hash-object", str(path)).stdout.strip() != expected["git_blob"]:
            raise RuntimeError(f"protected Git blob changed: {expected['path']}")
        if sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"protected SHA-256 changed: {expected['path']}")

    diff = _git(
        "diff",
        "--exit-code",
        IMPLEMENTATION_BASELINE,
        "--",
        *PROTECTED_INPUT_PATHS,
        check=False,
    )
    if diff.returncode:
        raise RuntimeError("protected P0-P4 inputs differ from the baseline")
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *PROTECTED_INPUT_PATHS,
    ).stdout
    if status:
        raise RuntimeError("protected P0-P4 inputs have worktree drift")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def expected_profile_config() -> dict[str, Any]:
    return {
        "retrieval": {"final_top_k": 12},
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    }


def load_raw_p5_catalog(path: Path = P5_CATALOG_PATH) -> dict[str, Any]:
    data = _load_json(path, "P5 deterministic catalog")
    if set(data) != {"schema_version", "profile_configs", "repos"}:
        raise ValueError("P5 deterministic catalog has unknown top-level fields")
    if data["schema_version"] != 1:
        raise ValueError("P5 deterministic catalog schema_version must be 1")
    if data["profile_configs"] != {
        "p5_language_graphs": expected_profile_config()
    }:
        raise ValueError("P5 deterministic profile config changed")

    repos = data.get("repos")
    if not isinstance(repos, list):
        raise ValueError("P5 deterministic catalog repos must be a list")
    actual_repos = {
        repo.get("repo_key"): repo.get("snapshot_path") for repo in repos
    }
    if actual_repos != P5_REPOSITORIES:
        raise ValueError("P5 deterministic repository inventory changed")

    actual_cases: list[tuple[str, str, str, str]] = []
    for repo in repos:
        if repo.get("profiles") != ["p5_language_graphs"]:
            raise ValueError("every deterministic repo must select the P5 profile")
        for case in repo.get("queries", []):
            if case.get("profiles") != ["p5_language_graphs"]:
                raise ValueError("every deterministic case must select the P5 profile")
            if case.get("gate") != "required":
                raise ValueError("every deterministic case must be required")
            actual_cases.append(
                (
                    repo["repo_key"],
                    case.get("id"),
                    case.get("query"),
                    case.get("mode", "results"),
                )
            )
    if tuple(actual_cases) != EXPECTED_DETERMINISTIC_CASES:
        raise ValueError("P5 deterministic case inventory changed")
    return data


def load_raw_p5_real_catalog(path: Path = P5_REAL_CATALOG_PATH) -> dict[str, Any]:
    data = _load_json(path, "P5 real catalog")
    if set(data) != {"schema_version", "profile_configs", "repos"}:
        raise ValueError("P5 real catalog has unknown top-level fields")
    if data["schema_version"] != 1:
        raise ValueError("P5 real catalog schema_version must be 1")
    if data["profile_configs"] != {
        "p5_real_language_graphs": expected_profile_config()
    }:
        raise ValueError("P5 real profile config changed")

    actual_cases: list[tuple[str, str, str, str]] = []
    for repo in data.get("repos", []):
        if repo.get("profiles") != ["p5_real_language_graphs"]:
            raise ValueError("every real repo must select the P5 real profile")
        for case in repo.get("queries", []):
            if case.get("profiles") != ["p5_real_language_graphs"]:
                raise ValueError("every real case must select the P5 real profile")
            if case.get("gate") != "required":
                raise ValueError("every real case must be required")
            actual_cases.append(
                (
                    repo.get("repo_key"),
                    case.get("id"),
                    case.get("query"),
                    case.get("mode", "results"),
                )
            )
    if tuple(actual_cases) != EXPECTED_REAL_CASES:
        raise ValueError("P5 real case inventory changed")

    petclinic = next(
        repo for repo in data["repos"] if repo.get("repo_key") == "spring_petclinic"
    )
    if petclinic.get("source_commit") != PETCLINIC_COMMIT:
        raise ValueError("P5 PetClinic commit changed")
    program_tool = next(
        repo for repo in data["repos"] if repo.get("repo_key") == "program_tool"
    )
    if program_tool.get("snapshot_path") != "tests/fixtures/real_projects/program_tool":
        raise ValueError("P5 program-tool snapshot changed")
    return data


def source_inventory() -> dict[str, tuple[str, ...]]:
    actual: dict[str, tuple[str, ...]] = {}
    for repo_key, relative_root in P5_REPOSITORIES.items():
        root = ROOT / relative_root
        files = tuple(
            sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file() or path.is_symlink()
            )
        )
        actual[repo_key] = files
    return actual


def frozen_input_paths() -> tuple[str, ...]:
    paths = [
        f"{P5_REPOSITORIES[repo_key]}/{relative}"
        for repo_key, inventory in P5_SOURCE_INVENTORY.items()
        for relative in inventory
    ]
    paths.extend(
        (
            P5_CATALOG_PATH.relative_to(ROOT).as_posix(),
            P5_REAL_CATALOG_PATH.relative_to(ROOT).as_posix(),
            PRE_P5_NO_EDGE_PATH.relative_to(ROOT).as_posix(),
        )
    )
    return tuple(sorted(paths))


def load_input_manifest(path: Path = P5_MANIFEST_PATH) -> dict[str, Any]:
    manifest = _load_json(path, "P5 input manifest")
    if manifest.get("schema_version") != 1:
        raise ValueError("P5 input manifest schema_version must be 1")
    if manifest.get("implementation_baseline") != IMPLEMENTATION_BASELINE:
        raise ValueError("P5 input manifest baseline changed")
    if manifest.get("excluded_outputs") != [
        "tests/fixtures/p5-language-graphs/expected/**",
        "tests/fixtures/p5_language_graphs/real_acceptance.json",
    ]:
        raise ValueError("P5 generated-output exclusions changed")
    if manifest.get("inventory") != {
        key: list(value) for key, value in P5_SOURCE_INVENTORY.items()
    }:
        raise ValueError("P5 input manifest inventory changed")
    if manifest.get("protected_inputs") != list(PROTECTED_IDENTITIES):
        raise ValueError("P5 protected identities changed")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, list):
        raise ValueError("P5 input manifest requires inputs")
    if tuple(item.get("path") for item in inputs) != frozen_input_paths():
        raise ValueError("P5 input path inventory changed")
    for item in inputs:
        relative = item["path"]
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("P5 input path must be repository-relative")
        path_on_disk = ROOT / relative_path
        if path_on_disk.is_symlink() or not path_on_disk.is_file():
            raise ValueError(f"P5 input is not a regular file: {relative}")
        if sha256_file(path_on_disk) != item.get("sha256"):
            raise ValueError(f"P5 input hash changed: {relative}")
        if path_on_disk.stat().st_size != item.get("bytes"):
            raise ValueError(f"P5 input byte count changed: {relative}")

    assays = manifest.get("assays")
    if not isinstance(assays, list) or [item.get("case_id") for item in assays] != [
        item[1] for item in EXPECTED_DETERMINISTIC_CASES
    ]:
        raise ValueError("P5 baseline assay inventory changed")
    protected = manifest.get("evidence", {}).get("protected_direct")
    if not isinstance(protected, list) or [item.get("case_id") for item in protected] != [
        "apply-audit-endpoint",
        "workspace-service-symbol",
        "dashboard-controller-path",
        "order-service-symbol",
    ]:
        raise ValueError("P5 protected direct evidence inventory changed")
    return manifest
