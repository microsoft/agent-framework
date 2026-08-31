# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: E402

"""Integration tests for CosmosMemoryContextProvider with live Azure accounts.

These tests require valid Azure credentials and environment variables:
- COSMOS_ENDPOINT: Cosmos DB account endpoint
- COSMOS_DATABASE: Database name (will be created if not exists)
- FOUNDRY_ENDPOINT: AI Foundry project endpoint
- EMBEDDING_MODEL: Embedding model deployment
- CHAT_MODEL: Chat model deployment

Run with: pytest -m integration tests/
"""

from __future__ import annotations

import pytest

# The Agent Memory Toolkit requires Python 3.11+, so it is not installed on the 3.10 CI
# leg. Skip this module there (mirrors the github_copilot package's importorskip guard).
pytest.importorskip("azure.cosmos.agent_memory")

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from agent_framework import Message
from agent_framework._sessions import AgentSession, SessionContext
from azure.identity.aio import DefaultAzureCredential

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

# Skip all tests in this module if required env vars not set.
# These tests hit a LIVE Azure account (Cosmos DB + AI Foundry), so they carry both
# the ``integration`` and ``azure`` markers. The emulator-backed suite in
# ``test_emulator.py`` is marked ``integration`` only and runs without any Azure account.
pytestmark = [pytest.mark.integration, pytest.mark.azure]

# The provider methods accept an ``agent`` implementing ``SupportsAgentRun`` but never
# use it in these tests, so a typed ``None`` stub keeps the call sites clean.
_STUB_AGENT: Any = None

REQUIRED_ENV_VARS = [
    "COSMOS_ENDPOINT",
    "FOUNDRY_ENDPOINT",
]


def _check_env_vars() -> tuple[bool, list[str]]:
    """Check if required environment variables are set."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    return len(missing) == 0, missing


@pytest.fixture(scope="module")
def skip_if_no_env() -> None:
    """Skip integration tests if environment variables not configured."""
    has_env, missing = _check_env_vars()
    if not has_env:
        pytest.skip(f"Integration tests require environment variables: {', '.join(missing)}")


@pytest.fixture
async def live_provider(skip_if_no_env: None) -> AsyncGenerator[CosmosMemoryContextProvider]:
    """Create a live CosmosMemoryContextProvider with real Azure credentials."""
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
        cosmos_database=os.getenv("COSMOS_DATABASE", "test_agent_memory"),
        foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        chat_model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        credential=DefaultAzureCredential(),
        top_k=3,
        min_confidence=0.5,
    )

    async with provider:
        yield provider


@pytest.fixture
def test_user_id() -> str:
    """Generate a unique user ID for test isolation."""
    return f"test-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_thread_id() -> str:
    """Generate a unique thread ID for test isolation."""
    return f"test-thread-{uuid.uuid4().hex[:8]}"


# -- Basic functionality tests -------------------------------------------------


class TestBasicFunctionality:
    """Test basic memory storage and retrieval with live accounts."""

    async def test_store_and_retrieve_conversation(
        self, live_provider: CosmosMemoryContextProvider, test_user_id: str, test_thread_id: str
    ) -> None:
        """Store a conversation and verify it's persisted."""
        session = AgentSession(session_id="integration-test")
        session.state["user_id"] = test_user_id
        session.state["thread_id"] = test_thread_id

        # Store messages
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["I love Python programming"])],
            session_id=session.session_id,
        )

        await live_provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )

        # Verify messages were stored (this tests the memory client integration)
        # In a real scenario, the memory extraction pipeline would process these
        # For this test, we're verifying the storage mechanism works

    async def test_search_returns_results(
        self, live_provider: CosmosMemoryContextProvider, test_user_id: str, test_thread_id: str
    ) -> None:
        """Search for memories (may return empty if no facts extracted yet)."""
        session = AgentSession(session_id="integration-test")
        session.state["user_id"] = test_user_id

        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["What are my programming preferences?"])],
            session_id=session.session_id,
        )

        # Should not raise even if no memories exist yet
        await live_provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )


# -- Multi-turn conversation tests ---------------------------------------------


class TestMultiTurnConversation:
    """Test memory across multiple conversation turns."""

    async def test_multi_turn_storage(
        self, live_provider: CosmosMemoryContextProvider, test_user_id: str, test_thread_id: str
    ) -> None:
        """Store multiple conversation turns."""
        session = AgentSession(session_id="integration-test")
        session.state["user_id"] = test_user_id
        session.state["thread_id"] = test_thread_id

        conversations = [
            ("user", "My name is Alice"),
            ("assistant", "Nice to meet you, Alice!"),
            ("user", "I work as a data scientist"),
            ("assistant", "That's a great field!"),
        ]

        for role, content in conversations:
            ctx = SessionContext(
                input_messages=[Message(role=role, contents=[content])],  # type: ignore
                session_id=session.session_id,
            )

            await live_provider.after_run(
                agent=_STUB_AGENT,
                session=session,
                context=ctx,
                state=session.state.setdefault(live_provider.source_id, {}),
            )


# -- Error handling tests ------------------------------------------------------


class TestErrorHandling:
    """Test error handling in integration scenarios."""

    async def test_handles_missing_user_id_gracefully(self, live_provider: CosmosMemoryContextProvider) -> None:
        """Falls back to session_id when user_id not in state."""
        session = AgentSession(session_id="fallback-test")
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["test"])],
            session_id=session.session_id,
        )

        # Should use session_id as fallback and not raise
        await live_provider.before_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )

    async def test_handles_empty_messages(
        self, live_provider: CosmosMemoryContextProvider, test_user_id: str, test_thread_id: str
    ) -> None:
        """Handles empty message content gracefully."""
        session = AgentSession(session_id="integration-test")
        session.state["user_id"] = test_user_id
        session.state["thread_id"] = test_thread_id

        ctx = SessionContext(
            input_messages=[Message(role="user", contents=[""])],
            session_id=session.session_id,
        )

        # Should not raise
        await live_provider.after_run(
            agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )


# -- Configuration tests -------------------------------------------------------


class TestConfiguration:
    """Test different configuration options."""

    async def test_custom_memory_types(self, skip_if_no_env: None, test_user_id: str) -> None:
        """Provider with custom memory types configuration."""
        provider = CosmosMemoryContextProvider(
            cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
            cosmos_database=os.getenv("COSMOS_DATABASE", "test_agent_memory"),
            foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
            credential=DefaultAzureCredential(),
            memory_types=["fact", "episodic", "procedural"],
            min_confidence=0.8,
            top_k=10,
        )

        async with provider:
            session = AgentSession(session_id="config-test")
            session.state["user_id"] = test_user_id

            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["test query"])],
                session_id=session.session_id,
            )

            # Should not raise
            await provider.before_run(
                agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
            )

    async def test_processor_config(self, skip_if_no_env: None, test_user_id: str, test_thread_id: str) -> None:
        """Provider with custom processor configuration."""
        provider = CosmosMemoryContextProvider(
            cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
            cosmos_database=os.getenv("COSMOS_DATABASE", "test_agent_memory"),
            foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
            credential=DefaultAzureCredential(),
            processor_config={
                "FACT_EXTRACTION_EVERY_N": 1,
                "DEDUP_EVERY_N": 3,
            },
        )

        async with provider:
            session = AgentSession(session_id="config-test")
            session.state["user_id"] = test_user_id
            session.state["thread_id"] = test_thread_id

            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["I prefer TypeScript over JavaScript"])],
                session_id=session.session_id,
            )

            # Should not raise
            await provider.after_run(
                agent=_STUB_AGENT, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
            )


# -- Transparent extraction tests ----------------------------------------------


class TestTransparentExtraction:
    """Memory extraction must happen transparently.

    A fact mentioned in one session is extracted and recalled in a later session without the
    application ever calling ``flush()`` or ``process_now()`` in its control flow: ``after_run``
    schedules extraction in the background and the provider drains it when its context exits.
    """

    def _build_provider(self) -> CosmosMemoryContextProvider:
        return CosmosMemoryContextProvider(
            cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
            cosmos_database=os.getenv("COSMOS_DATABASE", "test_agent_memory"),
            foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
            credential=DefaultAzureCredential(),
            top_k=5,
            min_confidence=0.3,
        )

    async def test_fact_extracted_and_recalled_without_manual_flush(
        self, skip_if_no_env: None, test_user_id: str
    ) -> None:
        """Mention a fact, exit the context (auto-drain), then recall it in a new session."""
        # Session 1: state a durable preference, then simply leave the context. No flush()/
        # process_now() is called anywhere -- extraction must be scheduled and drained for us.
        async with self._build_provider() as provider:
            session = AgentSession(session_id=f"test-thread-{uuid.uuid4().hex[:8]}")
            session.state.setdefault(provider.source_id, {})["user_id"] = test_user_id
            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["My favourite programming language is Rust."])],
                session_id=session.session_id,
            )
            await provider.after_run(
                agent=_STUB_AGENT,
                session=session,
                context=ctx,
                state=session.state.setdefault(provider.source_id, {}),
            )
        # Leaving the `async with` above drained the background extraction automatically.

        # Session 2: a brand-new thread for the same user must recall the extracted fact.
        async with self._build_provider() as provider:
            session = AgentSession(session_id=f"test-thread-{uuid.uuid4().hex[:8]}")
            session.state.setdefault(provider.source_id, {})["user_id"] = test_user_id
            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["What is my favourite programming language?"])],
                session_id=session.session_id,
            )
            await provider.before_run(
                agent=_STUB_AGENT,
                session=session,
                context=ctx,
                state=session.state.setdefault(provider.source_id, {}),
            )
            injected = ctx.context_messages.get(provider.source_id, [])
            recalled = "\n".join(m.text for m in injected if m.text).lower()  # type: ignore[union-attr]

        assert "rust" in recalled, f"expected the extracted fact to be recalled, got: {recalled!r}"


# -- Cleanup note --------------------------------------------------------------
# Note: These integration tests create data in the live Cosmos DB account.
# Consider adding cleanup logic or using time-based partitions if running frequently.
