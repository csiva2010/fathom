import os

import pytest

from src.core.config import Settings
from src.core.tracing import configure_langsmith

LANGSMITH_VARS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv first so monkeypatch records the variable and removes it again afterwards;
    # otherwise later tests would trace to LangSmith.
    for name in LANGSMITH_VARS:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def test_off_unless_enabled_and_keyed() -> None:
    assert (
        configure_langsmith(
            Settings(_env_file=None, langsmith_tracing=False, langsmith_api_key="k")
        )
        is None
    )
    assert (
        configure_langsmith(Settings(_env_file=None, langsmith_tracing=True, langsmith_api_key=""))
        is None
    )
    assert "LANGSMITH_TRACING" not in os.environ


def test_exports_settings_for_langchain() -> None:
    settings = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key="lsv2-test",
        langsmith_project="fathom-dev",
        langsmith_endpoint="https://eu.api.smith.langchain.com",
    )
    assert configure_langsmith(settings, "-evals") == "fathom-dev-evals"
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2-test"
    assert os.environ["LANGSMITH_PROJECT"] == "fathom-dev-evals"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://eu.api.smith.langchain.com"
