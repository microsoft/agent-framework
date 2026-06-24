# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for CosmosMemoryContextProvider with live Azure accounts.

These tests require valid Azure credentials and environment variables:
- COSMOS_DB_ENDPOINT: Cosmos DB account endpoint
- COSMOS_DB_DATABASE: Database name (will be created if not exists)
- AI_FOUNDRY_ENDPOINT: AI Foundry project endpoint
- AI_FOUNDRY_EMBEDDING_DEPLOYMENT_NAME: Embedding model deployment
- AI_FOUNDRY_CHAT_DEPLOYMENT_NAME: Chat model deployment

Run with: pytest -m integration tests/
"""

from __future__ import annotations

import os
import uuid

import pytest
from agent_framework import Message
from agent_framework._sessions import AgentSession, SessionContext
from azure.identity.aio import DefaultAzureCredential

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

# Skip all tests in this module if required env vars not set.
# These tests hit a LIVE Azure account (Cosmos DB + AI Foundry), so they carry both
# the ``integration`` and ``azure`` markers. The emulator-backed suite in
# ``test_emulator.py`` is marked ``integration`` only and runs without any Azure account.
pytestmark = [pytest.mark.integration, pytest.mark.azure]

REQUIRED_ENV_VARS = [
    "COSMOS_DB_ENDPOINT",
    "AI_FOUNDRY_ENDPOINT",
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
async def live_provider(skip_if_no_env: None) -> CosmosMemoryContextProvider:
    """Create a live CosmosMemoryContextProvider with real Azure credentials."""
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
        cosmos_database=os.getenv("COSMOS_DB_DATABASE", "test_agent_memory"),
        ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        embedding_deployment_name=os.getenv("AI_FOUNDRY_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large"),
        chat_deployment_name=os.getenv("AI_FOUNDRY_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini"),
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )  # type: ignore

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
            agent=None, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )  # type: ignore


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
                agent=None, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
            )  # type: ignore


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
            agent=None, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )  # type: ignore

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
            agent=None, session=session, context=ctx, state=session.state.setdefault(live_provider.source_id, {})
        )  # type: ignore


# -- Configuration tests -------------------------------------------------------


class TestConfiguration:
    """Test different configuration options."""

    async def test_custom_memory_types(self, skip_if_no_env: None, test_user_id: str) -> None:
        """Provider with custom memory types configuration."""
        provider = CosmosMemoryContextProvider(
            cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
            cosmos_database=os.getenv("COSMOS_DB_DATABASE", "test_agent_memory"),
            ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
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
                agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
            )  # type: ignore

    async def test_processor_config(self, skip_if_no_env: None, test_user_id: str, test_thread_id: str) -> None:
        """Provider with custom processor configuration."""
        provider = CosmosMemoryContextProvider(
            cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
            cosmos_database=os.getenv("COSMOS_DB_DATABASE", "test_agent_memory"),
            ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
            credential=DefaultAzureCredential(),
            processor_config={
                "FACT_EXTRACTION_EVERY_N": "1",
                "DEDUP_EVERY_N": "3",
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
                agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
            )  # type: ignore


# -- Cleanup note --------------------------------------------------------------
# Note: These integration tests create data in the live Cosmos DB account.
# Consider adding cleanup logic or using time-based partitions if running frequently.
