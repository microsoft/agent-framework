# Copyright (c) Microsoft. All rights reserved.

import sys
from types import ModuleType

import pytest

import agent_framework.gemini as gemini


def test_gemini_namespace_dir_lists_lazy_exports() -> None:
    names = dir(gemini)
    for expected in (
        "GeminiChatClient",
        "GeminiChatOptions",
        "GeminiSettings",
        "GoogleGeminiSettings",
        "RawGeminiChatClient",
        "ThinkingConfig",
    ):
        assert expected in names


def test_gemini_namespace_lazy_loads_known_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_module = ModuleType("agent_framework_gemini")
    fake_module.GeminiChatClient = sentinel  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "agent_framework_gemini", fake_module)

    assert gemini.GeminiChatClient is sentinel


def test_gemini_namespace_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="Module `gemini` has no attribute DoesNotExist."):
        _ = gemini.DoesNotExist  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


def test_gemini_namespace_missing_package_raises_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agent_framework_gemini", None)

    with pytest.raises(ModuleNotFoundError, match="agent-framework-gemini"):
        _ = gemini.GeminiChatClient
