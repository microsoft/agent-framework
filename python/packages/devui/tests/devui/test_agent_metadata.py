# Copyright (c) Microsoft. All rights reserved.

"""Tests for agent metadata extraction used by DevUI discovery."""

from unittest.mock import Mock

from agent_framework import Agent, ContextProvider, InMemoryHistoryProvider

from agent_framework_devui._utils import extract_agent_metadata


class _ZebraProvider(ContextProvider):
    """Provider whose class name sorts after the other one used in the order test."""


class _AardvarkProvider(ContextProvider):
    """Provider whose class name sorts before the other one used in the order test."""


def test_extract_agent_metadata_reports_configured_context_providers() -> None:
    """A configured context provider must show up in the agent metadata."""
    agent = Agent(
        client=Mock(model=None),
        context_providers=[InMemoryHistoryProvider()],
    )

    metadata = extract_agent_metadata(agent)

    assert metadata["context_provider"] == ["InMemoryHistoryProvider"]


def test_extract_agent_metadata_preserves_provider_order() -> None:
    """Multiple providers are listed in their configured order."""
    agent = Agent(
        client=Mock(model=None),
        context_providers=[
            _ZebraProvider(source_id="zebra"),
            _AardvarkProvider(source_id="aardvark"),
        ],
    )

    metadata = extract_agent_metadata(agent)

    assert metadata["context_provider"] == ["_ZebraProvider", "_AardvarkProvider"]


def test_extract_agent_metadata_without_context_providers() -> None:
    """An agent without providers reports no context provider."""
    agent = Agent(client=Mock(model=None))

    metadata = extract_agent_metadata(agent)

    assert metadata["context_provider"] is None


def test_extract_agent_metadata_falls_back_to_single_context_provider() -> None:
    """Older agent objects exposing a single ``context_provider`` still work."""

    class LegacyAgent:
        context_provider = InMemoryHistoryProvider()

    metadata = extract_agent_metadata(LegacyAgent())

    assert metadata["context_provider"] == ["InMemoryHistoryProvider"]


def test_extract_agent_metadata_ignores_non_iterable_context_providers() -> None:
    """A truthy but non-iterable ``context_providers`` value must not break discovery."""

    class OddAgent:
        context_providers = Mock()

    metadata = extract_agent_metadata(OddAgent())

    assert metadata["context_provider"] is None
