# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for _resolve_toolbox_endpoint() in the foundry-hosted-agents response samples.

Covers both 04_foundry_toolbox/main.py and 06_files/main.py which share the same
implementation of _resolve_toolbox_endpoint().
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub out packages unavailable in the unit-test environment so that importing
# the sample modules does not fail.
# ---------------------------------------------------------------------------
_MISSING_MODULES = (
    "agent_framework_foundry_hosting",
    "azure.ai.agentserver",
    "azure.ai.agentserver.responses",
)
for _mod_name in _MISSING_MODULES:
    sys.modules.setdefault(_mod_name, MagicMock())

# ---------------------------------------------------------------------------
# Load the two sample modules by file path to avoid needing them on sys.path.
# ---------------------------------------------------------------------------
_RESPONSES_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "samples"
    / "04-hosting"
    / "foundry-hosted-agents"
    / "responses"
)


def _load_sample(subdir: str, module_alias: str):
    spec = importlib.util.spec_from_file_location(module_alias, _RESPONSES_DIR / subdir / "main.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_toolbox_mod = _load_sample("04_foundry_toolbox", "foundry_toolbox_main")
_files_mod = _load_sample("06_files", "files_main")


# ---------------------------------------------------------------------------
# Parameterise over both modules so the same test cases run for each.
# ---------------------------------------------------------------------------
@pytest.fixture(params=["04_foundry_toolbox", "06_files"])
def resolve_endpoint(request):
    """Return _resolve_toolbox_endpoint from the requested sample module."""
    mod = _toolbox_mod if request.param == "04_foundry_toolbox" else _files_mod
    return mod._resolve_toolbox_endpoint


class TestResolveToolboxEndpoint:
    def test_explicit_endpoint_returned_as_is(self, resolve_endpoint, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FOUNDRY_TOOLBOX_ENDPOINT", "https://example.com/mcp")
        monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
        monkeypatch.delenv("TOOLBOX_NAME", raising=False)

        assert resolve_endpoint() == "https://example.com/mcp"

    def test_empty_string_raises_value_error(self, resolve_endpoint, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FOUNDRY_TOOLBOX_ENDPOINT", "")

        with pytest.raises(ValueError, match="FOUNDRY_TOOLBOX_ENDPOINT is set but empty"):
            resolve_endpoint()

    def test_fallback_constructs_url_from_project_vars(self, resolve_endpoint, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FOUNDRY_TOOLBOX_ENDPOINT", raising=False)
        monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://project.azure.com/")
        monkeypatch.setenv("TOOLBOX_NAME", "my-toolbox")

        result = resolve_endpoint()

        assert result == "https://project.azure.com/toolsets/my-toolbox/mcp?api-version=v1"

    def test_fallback_strips_trailing_slash_from_project_endpoint(
        self, resolve_endpoint, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("FOUNDRY_TOOLBOX_ENDPOINT", raising=False)
        monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://project.azure.com///")
        monkeypatch.setenv("TOOLBOX_NAME", "my-toolbox")

        result = resolve_endpoint()

        assert result == "https://project.azure.com/toolsets/my-toolbox/mcp?api-version=v1"

    def test_neither_variable_group_set_raises_key_error(self, resolve_endpoint, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FOUNDRY_TOOLBOX_ENDPOINT", raising=False)
        monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
        monkeypatch.delenv("TOOLBOX_NAME", raising=False)

        with pytest.raises(KeyError):
            resolve_endpoint()
