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
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict

from agent_framework import AgentSession, ContextProvider, Message, SessionContext
from agent_framework._settings import load_settings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun
    from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient

try:
    from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient as _RuntimeCosmosMemoryClient

    _memory_toolkit_available = True
except ImportError:
    _memory_toolkit_available = False
    _RuntimeCosmosMemoryClient = None

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_ID = "cosmos_memory"
DEFAULT_DATABASE = "ai_memory"
DEFAULT_CONTEXT_PROMPT = "## Relevant Memories\nConsider these memories when responding:"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"

# The memory categories the toolkit's extraction pipeline classifies and can retrieve.
MemoryType = Literal["fact", "procedural", "episodic"]


class CosmosMemorySettings(TypedDict, total=False):
    """Connection settings for the Cosmos memory provider, resolvable from the environment."""

    cosmos_endpoint: str | None
    cosmos_database: str | None
    foundry_endpoint: str | None
    embedding_model: str | None
    chat_model: str | None


class ProcessorConfig(TypedDict, total=False):
    """Agent Memory Toolkit cadence thresholds (number of turns between each pipeline step).

    Each value is the number of turns between runs of that step; ``0`` disables it. See the
    toolkit's auto-trigger documentation for the full semantics and defaults.
    """

    FACT_EXTRACTION_EVERY_N: int
    DEDUP_EVERY_N: int
    DEDUP_POOL_SIZE: int
    THREAD_SUMMARY_EVERY_N: int
    USER_SUMMARY_EVERY_N: int


class CosmosMemoryContextProvider(ContextProvider):
    """Azure Cosmos DB Memory context provider using Agent Memory Toolkit.

    Provides long-term semantic memory with fact extraction, user profiles,
    and cross-thread memory consolidation.
    """

    # Agent Framework uses the "assistant" role, but the Agent Memory Toolkit's TurnRecord
    # only accepts {user, agent, tool, system}. Map AF roles to toolkit roles when storing.
    _ROLE_MAP: ClassVar[dict[str, str]] = {"assistant": "agent"}

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        cosmos_endpoint: str | None = None,
        cosmos_database: str | None = None,
        foundry_endpoint: str | None = None,
        embedding_model: str | None = None,
        chat_model: str | None = None,
        credential: Any = None,
        memory_client: AsyncCosmosMemoryClient | None = None,
        top_k: int = 5,
        min_confidence: float = 0.7,
        memory_types: Sequence[MemoryType] | None = None,
        context_prompt: str = DEFAULT_CONTEXT_PROMPT,
        auto_extract: bool = True,
        processor_config: ProcessorConfig | None = None,
        prompts_dir: str | None = None,
    ) -> None:
        """Initialize the Cosmos Memory context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            cosmos_endpoint: Cosmos DB account endpoint.
                Can be set via ``COSMOS_ENDPOINT``.
            cosmos_database: Cosmos DB database name.
                Can be set via ``COSMOS_DATABASE``.
            foundry_endpoint: Azure AI Foundry project endpoint for LLM and embeddings.
                Can be set via ``FOUNDRY_ENDPOINT``.
            embedding_model: Embedding model deployment name.
                Can be set via ``EMBEDDING_MODEL``.
            chat_model: Chat model deployment name.
                Can be set via ``CHAT_MODEL``.
            credential: Azure credential for authentication. When provided it is used for both
                Cosmos DB and AI Foundry; when ``None`` the toolkit builds (and owns) a
                ``DefaultAzureCredential``.
            memory_client: Pre-created AsyncCosmosMemoryClient.
            top_k: Number of memories to retrieve in search.
            min_confidence: Minimum confidence score (0.0-1.0) for retrieved memories.
            memory_types: Types of memories to retrieve. Default: ["fact", "procedural"].
            context_prompt: Prompt to prepend to retrieved memories.
            auto_extract: Enable automatic background memory extraction/summarization after
                turn writes. When ``False`` the cadence thresholds are zeroed so nothing runs
                automatically and callers drive processing via ``memory_client.process_now()``.
            processor_config: Optional processor cadence configuration.
            prompts_dir: Optional directory of Prompty templates for the memory pipeline. When
                set, the extraction and summarization steps read their templates (including
                ``extract_memories.prompty``) from this directory instead of the toolkit's
                bundled defaults, letting you customize what the extraction LLM produces. The
                directory must contain the full template set. Applies whether the client is built
                by the provider or supplied via ``memory_client``.

        Raises:
            ImportError: If azure-cosmos-agent-memory is not installed.
        """
        if not _memory_toolkit_available:
            raise ImportError(
                "azure-cosmos-agent-memory is required. Install with: pip install agent-framework-azure-cosmos-memory"
            )

        super().__init__(source_id)

        # Track whether we created the client (and thus should close it in __aexit__)
        # vs. received a pre-created client (which the caller owns and should close)
        self._should_close_client = False
        self.top_k = top_k
        self.min_confidence = min_confidence
        self.memory_types: list[MemoryType] = list(memory_types) if memory_types else ["fact", "procedural"]
        self.context_prompt = context_prompt
        self.auto_extract = auto_extract
        self._prompts_dir = prompts_dir

        # Apply the cadence configuration to the environment BEFORE creating the memory client.
        # The Agent Memory Toolkit reads these thresholds from ``os.environ`` (see the toolkit's
        # thresholds module), so the environment is currently the only supported way to configure
        # the InProcessProcessor. ``auto_extract=False`` zeroes the cadence thresholds so the
        # toolkit's background auto-trigger never runs extraction/summarization on turn writes;
        # callers then drive processing explicitly via ``memory_client.process_now(...)``.
        cadence: dict[str, str] = {str(k): str(v) for k, v in (processor_config or {}).items()}
        if not auto_extract:
            cadence["FACT_EXTRACTION_EVERY_N"] = "0"
            cadence["THREAD_SUMMARY_EVERY_N"] = "0"
            cadence["USER_SUMMARY_EVERY_N"] = "0"
        for key, value in cadence.items():
            os.environ[key] = value

        # Initialize memory client if not provided
        if memory_client is None:
            # Resolve connection settings from explicit args, then the environment. ``load_settings``
            # validates that the required endpoints are present (raising if not), replacing manual
            # ``os.getenv`` + ``if not ...: raise`` blocks.
            settings = load_settings(
                CosmosMemorySettings,
                cosmos_endpoint=cosmos_endpoint,
                cosmos_database=cosmos_database,
                foundry_endpoint=foundry_endpoint,
                embedding_model=embedding_model,
                chat_model=chat_model,
                required_fields=["cosmos_endpoint", "foundry_endpoint"],
            )
            cosmos_endpoint = settings.get("cosmos_endpoint")
            cosmos_database = settings.get("cosmos_database") or DEFAULT_DATABASE
            foundry_endpoint = settings.get("foundry_endpoint")
            embedding_model = settings.get("embedding_model") or DEFAULT_EMBEDDING_MODEL
            chat_model = settings.get("chat_model") or DEFAULT_CHAT_MODEL

            # Authentication: if the caller supplies a credential, wire it into both the Cosmos
            # and AI Foundry clients and disable the toolkit's default-credential creation.
            # Otherwise let the toolkit build a DefaultAzureCredential (EnvironmentCredential →
            # ManagedIdentityCredential → AzureCliCredential → …), which it also owns and closes.
            # This works in production (via ManagedIdentity) and local dev (via az login).
            if credential is not None:
                memory_client = _RuntimeCosmosMemoryClient(
                    cosmos_endpoint=cosmos_endpoint,
                    cosmos_database=cosmos_database,
                    ai_foundry_endpoint=foundry_endpoint,
                    embedding_deployment_name=embedding_model,
                    chat_deployment_name=chat_model,
                    cosmos_credential=credential,
                    ai_foundry_credential=credential,
                    use_default_credential=False,
                )
            else:
                memory_client = _RuntimeCosmosMemoryClient(
                    cosmos_endpoint=cosmos_endpoint,
                    cosmos_database=cosmos_database,
                    ai_foundry_endpoint=foundry_endpoint,
                    embedding_deployment_name=embedding_model,
                    chat_deployment_name=chat_model,
                    use_default_credential=True,
                )
            self._should_close_client = True

        self.memory_client = memory_client
        self._cosmos_endpoint = cosmos_endpoint
        self._foundry_endpoint = foundry_endpoint

    def _resolve_user_id(self, state: dict[str, Any], session: AgentSession) -> str:
        """Resolve the user id for memory scoping.

        Long-term, cross-session memory requires a *stable* user id. Callers set it in the
        provider-scoped ``state`` (``state["user_id"]``). When absent, memory scopes to the
        session id, which limits recall to the current session. ``state`` is the state for
        this provider; the session is only consulted for its id as the fallback scope.

        Args:
            state: Provider-scoped mutable state.
            session: The current session (used only for its id as a fallback).

        Returns:
            The resolved user id.
        """
        return state.get("user_id") or session.session_id or "default"

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
        # The toolkit client tracks in-flight extraction in a ``set`` of asyncio tasks. Guard
        # against clients that expose no usable registry (missing, None, or a non-iterable).
        if not isinstance(tasks, (set, frozenset, list, tuple)) or not tasks:
            return
        pending = [task for task in tasks if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    def _apply_custom_prompts_dir(self, prompts_dir: str) -> None:
        """Point the memory pipeline's Prompty loader at a custom templates directory.

        The toolkit client builds its pipeline internally without forwarding a prompts
        directory, so once the store is connected we build the pipeline and swap in a loader
        rooted at ``prompts_dir``. The extraction and summarization steps then read their
        templates (e.g. ``extract_memories.prompty``) from there instead of the bundled defaults.
        """
        from azure.cosmos.agent_memory.services._pipeline_helpers import PromptyLoader

        # The toolkit exposes no public prompts-directory seam, so reach into the pipeline it
        # builds internally and swap its template loader. Contained here so callers never touch
        # toolkit internals themselves.
        pipeline = self.memory_client._get_pipeline()  # pyright: ignore[reportPrivateUsage]
        pipeline._prompty = PromptyLoader(prompts_dir)  # pyright: ignore[reportPrivateUsage]

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.memory_client and isinstance(self.memory_client, AbstractAsyncContextManager):
            await self.memory_client.__aenter__()
        # The async client cannot create or connect Cosmos containers in __init__ (no running
        # event loop), so ensure the database and memory containers exist and the client is
        # connected here. create_memory_store() is idempotent (create-if-not-exists), so it is
        # safe to call for both provider-created and caller-provided clients.
        await self.memory_client.create_memory_store()
        # If a custom prompts directory was supplied, redirect the pipeline's template loader now
        # that the store (and thus the pipeline) can be built.
        if self._prompts_dir is not None:
            self._apply_custom_prompts_dir(self._prompts_dir)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit.

        Drains any in-flight background memory extraction before closing so it persists
        instead of being cancelled. This keeps extraction transparent: callers get
        non-blocking turn writes during the session and an automatic drain on exit, and never
        need to call ``flush()`` in their own control flow.

        Only close the memory client if this provider created it (_should_close_client=True).
        If a pre-created client was provided, the caller is responsible for closing it.
        """
        # Let pending fire-and-forget extraction tasks finish and persist; the client's
        # close() would otherwise cancel them.
        await self.flush()
        if (
            self._should_close_client
            and self.memory_client
            and isinstance(self.memory_client, AbstractAsyncContextManager)
        ):
            await self.memory_client.__aexit__(exc_type, exc_val, exc_tb)

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
                memory_types=[str(t) for t in self.memory_types],
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
        # Get user_id and thread_id from provider-scoped state (falling back to the session id)
        user_id = self._resolve_user_id(state, session)
        thread_id = state.get("thread_id") or session.session_id or "default"

        try:
            # Store input messages (skip empty/whitespace-only content to avoid junk turns)
            for msg in context.input_messages:
                if hasattr(msg, "role") and hasattr(msg, "text") and msg.text and msg.text.strip():
                    role_value = getattr(msg.role, "value", None) or str(msg.role)
                    if role_value in {"user", "assistant", "system"}:
                        await self.memory_client.add_cosmos(
                            user_id=user_id,
                            thread_id=thread_id,
                            role=self._ROLE_MAP.get(role_value, role_value),
                            content=msg.text.strip(),
                        )

            # Store response messages (skip empty/whitespace-only content)
            if context.response and context.response.messages:
                for msg in context.response.messages:
                    if hasattr(msg, "role") and hasattr(msg, "text") and msg.text and msg.text.strip():
                        role_value = getattr(msg.role, "value", None) or str(msg.role)
                        if role_value in {"user", "assistant", "system"}:
                            await self.memory_client.add_cosmos(
                                user_id=user_id,
                                thread_id=thread_id,
                                role=self._ROLE_MAP.get(role_value, role_value),
                                content=msg.text.strip(),
                            )

            # Auto-extraction and processing:
            # When auto_extract is True (default), add_cosmos() schedules cadence-aware background
            # processing (fact extraction, summaries, reconciliation) based on the configured
            # thresholds (FACT_EXTRACTION_EVERY_N, DEDUP_EVERY_N, etc.), so no explicit
            # process_now() call is needed. When auto_extract is False, those thresholds were
            # zeroed in __init__ so nothing runs automatically; call memory_client.process_now()
            # to drive extraction manually.

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
            confidence = memory.get("confidence")

            # Format: [Type] Content (confidence: X.XX). Use an explicit None check so a
            # confidence of 0.0 is still shown, and coerce to float in case the toolkit
            # returns it as a string.
            if memory_type and confidence is not None:
                formatted.append(f"[{memory_type}] {content} (confidence: {float(confidence):.2f})")
            else:
                formatted.append(content)

        return "\n".join(formatted)


__all__ = ["CosmosMemoryContextProvider"]
