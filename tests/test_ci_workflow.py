from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
README = ROOT / "README.md"
PRODUCT_EXPRESSION = (
    "not slow and not archival_acceptance and not runtime_pinned"
)
OPTIONAL_V8_CONTRACT_TEST = "tests/test_p15_v8_contract.py"
README_INSTALL_BLOCK = "\n".join(
    (
        "python -m venv .venv",
        ".venv/bin/python -m pip install -e '.[dev]'",
    )
)


def test_ci_workflow_is_offline_python313_single_product_contract() -> None:
    assert WORKFLOW.is_file(), "ordinary CI workflow is absent"
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)

    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert list(workflow["jobs"]) == ["test"]
    job = workflow["jobs"]["test"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == "30"
    checkout = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"] == {"fetch-depth": "0"}
    setup = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert setup["with"]["python-version"] == "3.13"

    named_steps = {step["name"]: step for step in job["steps"] if "name" in step}
    install = named_steps["Install frozen dependencies"]["run"]
    assert install.splitlines() == [
        "python -m pip install uv==0.9.14",
        "uv sync --frozen --extra dev",
    ]

    product = named_steps["Run product gate"]["run"]
    assert "--strict-markers" in product
    assert "-rs" in product
    assert f'-m "{PRODUCT_EXPRESSION}"' in product
    assert "--junitxml=.quality/ci/product-junit.xml" in product
    assert text.count(".venv/bin/pytest") == 1
    assert "Run focused P15 gate" not in named_steps

    identity_step = named_steps["Write runtime identity"]
    assert identity_step["if"] == "${{ !cancelled() }}"
    assert "scripts/write_runtime_identity.py" in identity_step["run"]
    assert "--output .quality/ci/runtime-identity.json" in identity_step["run"]

    for name in ("Upload JUnit reports", "Upload runtime identity"):
        step = named_steps[name]
        assert step["if"] == "${{ always() }}"
        assert step["uses"] == "actions/upload-artifact@v6"
    assert "${{ secrets." not in text
    assert "http://" not in text and "https://" not in text


def test_product_gate_fails_if_introduced_v8_contract_is_deleted() -> None:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    named_steps = {
        step["name"]: step
        for step in workflow["jobs"]["test"]["steps"]
        if "name" in step
    }
    product = named_steps["Run product gate"]["run"]

    assert product.count(OPTIONAL_V8_CONTRACT_TEST) == 1
    assert (
        f"P15_V8_CONTRACT_TEST={OPTIONAL_V8_CONTRACT_TEST}" in product
    )
    assert (
        'P15_V8_CONTRACT_HISTORY="$(git log -1 --format=%H HEAD -- '
        '"$P15_V8_CONTRACT_TEST")"' in product
    )
    assert (
        'if [[ -n "$P15_V8_CONTRACT_HISTORY" ]] && '
        '[[ ! -f "$P15_V8_CONTRACT_TEST" ]]; then' in product
    )
    assert 'echo "P15 v8 contract test existed in history but is missing"' in product
    assert "exit 1" in product
    assert product.index("fi") < product.index(".venv/bin/pytest")

    junit_upload = named_steps["Upload JUnit reports"]
    assert junit_upload["if"] == "${{ always() }}"
    assert junit_upload["with"]["if-no-files-found"] == "error"
    assert junit_upload["with"]["path"] == ".quality/ci/product-junit.xml"


def test_readme_and_ci_share_the_exact_product_gate_expression() -> None:
    readme = README.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    product_marker = f'-m "{PRODUCT_EXPRESSION}"'
    assert product_marker in readme
    assert product_marker in workflow
    assert readme.count(README_INSTALL_BLOCK) == 2
    assert 'python -m pip install -e ".[dev]"' not in readme
    assert ".venv/bin/pytest" in readme
    assert '-m "runtime_pinned"' in readme
    assert '-m "archival_acceptance"' in readme
    assert '--archival-evidence-root "$PWD"' in readme
    assert "当前只支持仓库根目录" in readme
    normalized_readme = " ".join(readme.split())
    assert "runtime 身份不匹配会在执行前返回 `UsageError`" in normalized_readme
    assert "`--collect-only` 只绕过 evidence/runtime 环境绑定" in normalized_readme
    assert "不会绕过双 marker 冲突" in normalized_readme
