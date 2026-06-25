# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB Memory Context Provider using Agent Memory Toolkit.

This module provides ``CosmosMemoryContextProvider``, built on the
:class:`ContextProvider` pattern for long-term semantic memory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict

from agent_framework import AgentSession, ContextProvider, Message, SessionContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential
    from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient

try:
    from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient
    from azure.identity.aio import DefaultAzureCredential

    _memory_toolkit_available = True
except ImportError:
    _memory_toolkit_available = False
    AsyncCosmosMemoryClient = None  # type: ignore
    DefaultAzureCredential = None  # type: ignore

logger = logging.getLogger(__name__)

AzureCredentialTypes = "TokenCredential | AsyncTokenCredential"


class CosmosMemorySettings(TypedDict, total=False):
    """Settings for Cosmos Memory Context Provider with auto-loading from environment."""

    cosmos_endpoint: str | None
    cosmos_database: str | None
    ai_foundry_endpoint: str | None
    embedding_deployment_name: str | None
    chat_deployment_name: str | None


class CosmosMemoryContextProvider(ContextProvider):
    """Azure Cosmos DB Memory context provider using Agent Memory Toolkit.

    Provides long-term semantic memory with fact extraction, user profiles,
    and cross-thread memory consolidation.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "cosmos_memory"
    DEFAULT_CONTEXT_PROMPT: ClassVar[str] = "## Relevant Memories\nConsider these memories when responding:"
    DEFAULT_DATABASE: ClassVar[str] = "ai_memory"

    # Agent Framework uses the "assistant" role, but the Agent Memory Toolkit's TurnRecord
    # only accepts {user, agent, tool, system}. Map AF roles to toolkit roles when storing.
    _ROLE_MAP: ClassVar[dict[str, str]] = {"assistant": "agent"}

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        cosmos_endpoint: str | None = None,
        cosmos_database: str | None = None,
        ai_foundry_endpoint: str | None = None,
        embedding_deployment_name: str | None = None,
        chat_deployment_name: str | None = None,
        credential: Any = None,
        memory_client: AsyncCosmosMemoryClient | None = None,
        top_k: int = 5,
        min_confidence: float = 0.7,
        memory_types: Sequence[str] | None = None,
        context_prompt: str | None = None,
        auto_extract: bool = True,
        processor_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the Cosmos Memory context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            cosmos_endpoint: Cosmos DB account endpoint.
                Can be set via ``COSMOS_DB_ENDPOINT``.
            cosmos_database: Cosmos DB database name.
                Can be set via ``COSMOS_DB_DATABASE``.
            ai_foundry_endpoint: AI Foundry project endpoint for LLM and embeddings.
                Can be set via ``AI_FOUNDRY_ENDPOINT``.
            embedding_deployment_name: Embedding model deployment name.
                Can be set via ``AI_FOUNDRY_EMBEDDING_DEPLOYMENT_NAME``.
            chat_deployment_name: Chat model deployment name.
                Can be set via ``AI_FOUNDRY_CHAT_DEPLOYMENT_NAME``.
            credential: Azure credential for authentication. If None, uses DefaultAzureCredential.
            memory_client: Pre-created AsyncCosmosMemoryClient.
            top_k: Number of memories to retrieve in search.
            min_confidence: Minimum confidence score (0.0-1.0) for retrieved memories.
            memory_types: Types of memories to retrieve. Default: ["fact", "procedural"].
            context_prompt: Prompt to prepend to retrieved memories.
            auto_extract: Enable automatic memory extraction after runs.
            processor_config: Optional processor configuration dict (e.g., extraction frequency).

        Raises:
            ImportError: If azure-cosmos-agent-memory is not installed.
        """
        if not _memory_toolkit_available:
            raise ImportError(
                "azure-cosmos-agent-memory is required. "
                "Install with: pip install agent-framework-azure-cosmos-memory"
            )

        super().__init__(source_id)

        # Track whether we created the client (and thus should close it in __aexit__)
        # vs. received a pre-created client (which the caller owns and should close)
        self._should_close_client = False
        self.top_k = top_k
        self.min_confidence = min_confidence
        self.memory_types = list(memory_types) if memory_types else ["fact", "procedural"]
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.auto_extract = auto_extract

        # Apply processor config to environment BEFORE creating the memory client.
        # The AsyncCosmosMemoryClient reads these environment variables during initialization
        # to configure the InProcessProcessor (extraction frequency, deduplication, etc.)
        if processor_config:
            for key, value in processor_config.items():
                os.environ[key] = str(value)

        # Initialize memory client if not provided
        if memory_client is None:
            # Load settings from environment if not provided
            cosmos_endpoint = cosmos_endpoint or os.getenv("COSMOS_DB_ENDPOINT")
            cosmos_database = cosmos_database or os.getenv("COSMOS_DB_DATABASE", self.DEFAULT_DATABASE)
            ai_foundry_endpoint = ai_foundry_endpoint or os.getenv("AI_FOUNDRY_ENDPOINT")
            embedding_deployment_name = embedding_deployment_name or os.getenv(
                "AI_FOUNDRY_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large"
            )
            chat_deployment_name = chat_deployment_name or os.getenv("AI_FOUNDRY_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini")

            if not cosmos_endpoint:
                raise ValueError("cosmos_endpoint must be provided or set via COSMOS_DB_ENDPOINT")
            if not ai_foundry_endpoint:
                raise ValueError("ai_foundry_endpoint must be provided or set via AI_FOUNDRY_ENDPOINT")

            # Create Azure credential using the standard chain: EnvironmentCredential →
            # ManagedIdentityCredential → AzureCliCredential → InteractiveBrowserCredential.
            # This works seamlessly in production (via ManagedIdentity) and local dev (via az login).
            if credential is None:
                credential = DefaultAzureCredential()  # type: ignore

            memory_client = AsyncCosmosMemoryClient(
                cosmos_endpoint=cosmos_endpoint,
                cosmos_database=cosmos_database,
                ai_foundry_endpoint=ai_foundry_endpoint,
                embedding_deployment_name=embedding_deployment_name,
                chat_deployment_name=chat_deployment_name,
                use_default_credential=True,
            )
            self._should_close_client = True

        self.memory_client = memory_client
        self._cosmos_endpoint = cosmos_endpoint
        self._ai_foundry_endpoint = ai_foundry_endpoint
        # Emit the "no stable user_id" warning at most once per provider instance to avoid
        # log spam on every run when a caller forgets to set user_id.
        self._warned_user_fallback = False

    def _resolve_user_id(self, state: dict[str, Any], session: AgentSession) -> str:
        """Resolve the user id for memory scoping, warning once if none was provided.

        Long-term, cross-session memory requires a *stable* user id. If the caller does
        not set ``state["user_id"]`` or ``session.state["user_id"]``, memory silently
        scopes to the ephemeral ``session_id`` (or ``"default"``), so cross-session recall
        will not work as intended. Log a one-time warning so this misconfiguration is
        visible instead of failing silently.

        Args:
            state: Provider-scoped mutable state.
            session: The current session.

        Returns:
            The resolved user id.
        """
        explicit = state.get("user_id") or session.state.get("user_id")
        if explicit:
            return explicit
        if not self._warned_user_fallback:
            self._warned_user_fallback = True
            logger.warning(
                "No 'user_id' found in state or session; falling back to session id '%s'. "
                "Long-term cross-session memory requires a stable user_id set via "
                "state['user_id'] or session.state['user_id'].",
                session.session_id,
            )
        return session.session_id or "default"

    async def flush(self, timeout: float = 30.0) -> None:
        """Wait for any pending background memory-extraction tasks to complete.

        After each stored turn, the Agent Memory Toolkit schedules fact/summary
        extraction as background ``asyncio`` tasks that run out-of-band. The client's
        ``close()`` cancels any still-pending tasks, so call ``flush()`` before shutdown
        to let in-flight extraction finish and persist instead of being discarded.

        Args:
            timeout: Maximum seconds to wait for pending tasks to complete.
        """
        tasks = getattr(self.memory_client, "_background_tasks", None)
        if not tasks:
            return
        pending = [task for task in list(tasks) if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.memory_client and isinstance(self.memory_client, AbstractAsyncContextManager):
            await self.memory_client.__aenter__()  # type: ignore
        # The async client cannot create or connect Cosmos containers in __init__ (no running
        # event loop), so ensure the database and memory containers exist and the client is
        # connected here. create_memory_store() is idempotent (create-if-not-exists), so it is
        # safe to call for both provider-created and caller-provided clients.
        if self.memory_client is not None:
            await self.memory_client.create_memory_store()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Async context manager exit.

        Only close the memory client if this provider created it (_should_close_client=True).
        If a pre-created client was provided, the caller is responsible for closing it.
        """
        if self.memory_client and isinstance(self.memory_client, AbstractAsyncContextManager):
            if self._should_close_client:
                await self.memory_client.__aexit__(exc_type, exc_val, exc_tb)  # type: ignore

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Search for relevant memories and inject into context.

        Args:
            agent: The agent running this invocation.
            session: The current session.
            context: The invocation context to add memories to.
            state: Provider-scoped mutable state.
        """
        # Extract query from input messages
        query_text = "\n".join(msg.text for msg in context.input_messages if msg.text and msg.text.strip())

        if not query_text:
            return

        # Get user_id from state or session (warns once if no stable user_id was provided)
        user_id = self._resolve_user_id(state, session)

        # Memory search and user-summary retrieval are independent: the user summary
        # provides baseline context even when no memories match the query, so a failure
        # in one must not suppress the other. They get separate error handling.
        try:
            results = await self.memory_client.search_cosmos(
                search_terms=query_text,
                user_id=user_id,
                top_k=self.top_k,
                memory_types=self.memory_types,
                min_confidence=self.min_confidence,
            )

            if results:
                # Format and inject memories
                memory_content = self._format_memories(results)
                context.extend_messages(
                    self.source_id, [Message(role="user", contents=[f"{self.context_prompt}\n{memory_content}"])]
                )
        except Exception as e:
            logger.warning("Failed to retrieve memories: %s", e, exc_info=True)

        # Retrieve and inject user summary as agent instructions.
        # This is INDEPENDENT of search results - even if no memories match the query,
        # the user summary provides baseline context about the user's preferences and traits.
        try:
            user_summary = await self.memory_client.get_user_summary(user_id=user_id)
            if user_summary:
                # get_user_summary returns the Cosmos summary document (a dict) whose
                # roll-up text lives in the "content" field; fall back to str() defensively.
                summary_text = user_summary.get("content") if isinstance(user_summary, dict) else str(user_summary)
                if summary_text and summary_text.strip():
                    context.extend_instructions(self.source_id, [f"User Profile: {summary_text}"])
        except Exception as e:
            logger.warning("Failed to retrieve user summary: %s", e, exc_info=True)

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store conversation turns and optionally trigger memory extraction.

        Args:
            agent: The agent that ran this invocation.
            session: The current session.
            context: The invocation context with response populated.
            state: Provider-scoped mutable state.
        """
        # Get user_id and thread_id from state or session (warns once if no stable user_id)
        user_id = self._resolve_user_id(state, session)
        thread_id = state.get("thread_id") or session.state.get("thread_id") or session.session_id or "default"

        try:
            # Store input messages
            for msg in context.input_messages:
                if hasattr(msg, "role") and hasattr(msg, "text") and msg.text:
                    role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    if role_value in {"user", "assistant", "system"}:
                        await self.memory_client.add_cosmos(
                            user_id=user_id,
                            thread_id=thread_id,
                            role=self._ROLE_MAP.get(role_value, role_value),
                            content=msg.text,
                        )

            # Store response messages
            if context.response and context.response.messages:
                for msg in context.response.messages:
                    if hasattr(msg, "role") and hasattr(msg, "text") and msg.text:
                        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                        if role_value in {"user", "assistant", "system"}:
                            await self.memory_client.add_cosmos(
                                user_id=user_id,
                                thread_id=thread_id,
                                role=self._ROLE_MAP.get(role_value, role_value),
                                content=msg.text,
                            )

            # Auto-extraction and processing:
            # The AsyncCosmosMemoryClient uses an InProcessProcessor that runs in the background
            # and automatically extracts facts, generates summaries, and reconciles memories based on
            # configured thresholds (FACT_EXTRACTION_EVERY_N, DEDUP_EVERY_N, etc.).
            # This happens asynchronously after add_cosmos() completes, so no explicit process_now() call is needed.
            # To disable auto-extraction, set auto_extract=False and call memory_client.process_now() manually.

        except Exception as e:
            logger.warning("Failed to store conversation turns: %s", e, exc_info=True)

    def _format_memories(self, memories: Sequence[dict[str, Any]]) -> str:
        """Format memories for context injection.

        Each memory is formatted as: "[type] content (confidence: X.XX)"
        This provides the agent with both the memory content and metadata about
        its type (fact, procedural, episodic) and confidence score for better reasoning.

        Args:
            memories: List of memory records from search.

        Returns:
            Formatted string of memories.
        """
        formatted = []
        for memory in memories:
            content = memory.get("content", "")
            memory_type = memory.get("memory_type", "")
            confidence = memory.get("confidence", 0.0)

            # Format: [Type] Content (confidence: X.XX)
            if memory_type and confidence:
                formatted.append(f"[{memory_type}] {content} (confidence: {confidence:.2f})")
            else:
                formatted.append(content)

        return "\n".join(formatted)


__all__ = ["CosmosMemoryContextProvider"]
