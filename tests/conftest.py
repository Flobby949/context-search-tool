from collections.abc import Iterator
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_global_config(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    variable = "CST_GLOBAL_CONFIG_PATH"
    previous = os.environ.get(variable)
    isolated = tmp_path_factory.mktemp("global-config") / "missing-config.toml"
    os.environ[variable] = str(isolated)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous
