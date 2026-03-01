# Copyright (c) Microsoft. All rights reserved.

"""Foundry Memory Context Provider using BaseContextProvider.

This module provides ``FoundryMemoryProvider``, built on
:class:`BaseContextProvider`.
"""

from __future__ import annotations

import logging
import sys
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework import AGENT_FRAMEWORK_USER_AGENT, Message
from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework._settings import load_settings
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import ItemParam, ResponsesAssistantMessageItemParam, ResponsesUserMessageItemParam

from ._shared import AzureAISettings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

logger = logging.getLogger(__name__)


class FoundryMemoryProvider(BaseContextProvider):
    """Foundry Memory context provider using the new BaseContextProvider hooks pattern.

    Integrates Azure AI Foundry Memory Store for persistent semantic memory,
    searching and storing memories via the Azure AI Projects SDK.

    Args:
        source_id: Unique identifier for this provider instance.
        project_client: Azure AI Project client for memory operations.
        memory_store_name: The name of the memory store to use.
        scope: The namespace that logically groups and isolates memories (e.g., user ID).
        context_prompt: The prompt to prepend to retrieved memories.
        update_delay: Timeout period before processing memory update in seconds.
            Defaults to 300 (5 minutes). Set to 0 to immediately trigger updates.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "foundry_memory"
    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        project_client: AIProjectClient | None = None,
        project_endpoint: str | None = None,
        credential: AzureCredentialTypes | None = None,
        memory_store_name: str,
        scope: str | None = None,
        context_prompt: str | None = None,
        update_delay: int = 300,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Foundry Memory context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            project_client: Azure AI Project client for memory operations.
            project_endpoint: Azure AI project endpoint URL. Used when project_client is not provided.
            credential: Azure credential for authentication. Accepts a TokenCredential,
                AsyncTokenCredential, or a callable token provider.
                Required when project_client is not provided.
            memory_store_name: The name of the memory store to use.
            scope: The namespace that logically groups and isolates memories (e.g., user ID).
                If None, `session_id` will be used.
            context_prompt: The prompt to prepend to retrieved memories.
            update_delay: Timeout period before processing memory update in seconds.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(source_id)
        azure_ai_settings = load_settings(
            AzureAISettings,
            env_prefix="AZURE_AI_",
            project_endpoint=project_endpoint,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if project_client is None:
            resolved_endpoint = azure_ai_settings.get("project_endpoint")
            if not resolved_endpoint:
                raise ValueError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )
            if not credential:
                raise ValueError("Azure credential is required when project_client is not provided.")
            project_client = AIProjectClient(
                endpoint=resolved_endpoint,
                credential=credential,  # type: ignore[arg-type]
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )

        if not memory_store_name:
            raise ValueError("memory_store_name is required")
        if not scope:
            raise ValueError("scope is required")

        self.project_client = project_client
        self.memory_store_name = memory_store_name
        self.scope = scope
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.update_delay = update_delay

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.project_client and isinstance(self.project_client, AbstractAsyncContextManager):
            await self.project_client.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self.project_client and isinstance(self.project_client, AbstractAsyncContextManager):
            await self.project_client.__aexit__(exc_type, exc_val, exc_tb)

    # -- Hooks pattern ---------------------------------------------------------

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Search Foundry Memory for relevant memories and add to the session context.

        This method:
        1. Retrieves static memories (user profile) on first call per session
        2. Searches for contextual memories based on input messages
        3. Combines and injects memories into the context
        """
        # On first run, retrieve static memories (user profile memories)
        if not state.get("initialized"):
            try:
                static_search_result = await self.project_client.memory_stores.search_memories(
                    name=self.memory_store_name,
                    scope=self.scope or context.session_id,  # type: ignore[arg-type]
                )
                static_memories = [{"content": memory.memory_item.content} for memory in static_search_result.memories]
                state["static_memories"] = static_memories
            except Exception as e:
                # Log but don't fail - memory retrieval is non-critical
                logger.warning(f"Failed to retrieve static memories: {e}")
                state["static_memories"] = []
            finally:
                # Mark as initialized regardless of success to avoid repeated attempts
                state["initialized"] = True

        # Search for contextual memories based on input messages
        # Check if there are any non-empty input messages
        has_input = any(msg and msg.text and msg.text.strip() for msg in context.input_messages)
        if not has_input:
            return

        # Convert input messages to ItemParam format for search
        items = [
            ItemParam({"type": "text", "text": msg.text})
            for msg in context.input_messages
            if msg and msg.text and msg.text.strip()
        ]

        try:
            search_result = await self.project_client.memory_stores.search_memories(
                name=self.memory_store_name,
                scope=self.scope or context.session_id,  # type: ignore[arg-type]
                items=items,
                previous_search_id=state.get("previous_search_id"),
            )

            # Extract search_id for next incremental search
            if search_result.memories:
                state["previous_search_id"] = search_result.search_id

            # Combine static and contextual memories
            contextual_memories = [{"content": memory.memory_item.content} for memory in search_result.memories]

            all_memories = state.get("static_memories", []) + contextual_memories

            # Inject memories into context
            if all_memories:
                line_separated_memories = "\n".join(
                    str(memory.get("content", "")) for memory in all_memories if memory.get("content")
                )
                if line_separated_memories:
                    context.extend_messages(
                        self.source_id,
                        [Message(role="user", text=f"{self.context_prompt}\n{line_separated_memories}")],
                    )
        except Exception as e:
            # Log but don't fail - memory retrieval is non-critical
            logger.warning(f"Failed to search contextual memories: {e}")

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store request/response messages to Foundry Memory for future retrieval.

        This method updates the memory store with conversation messages.
        The update is debounced by the configured update_delay.
        """
        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        # Filter and convert messages to ItemParam format
        items: list[ResponsesUserMessageItemParam | ResponsesAssistantMessageItemParam] = []
        for message in messages_to_store:
            if message.role in {"user", "assistant", "system"} and message.text and message.text.strip():
                if message.role == "user":
                    items.append(ResponsesUserMessageItemParam(content=message.text))
                elif message.role == "assistant":
                    items.append(ResponsesAssistantMessageItemParam(content=message.text))

        if not items:
            return

        try:
            # Fire and forget - don't wait for the update to complete
            update_poller = await self.project_client.memory_stores.begin_update_memories(
                name=self.memory_store_name,
                scope=self.scope or context.session_id,  # type: ignore[arg-type]
                items=items,  # type: ignore[arg-type]
                previous_update_id=state.get("previous_update_id"),
                update_delay=self.update_delay,
            )
            # Store the update_id for next incremental update
            state["previous_update_id"] = update_poller.update_id

        except Exception as e:
            # Log but don't fail - memory storage is non-critical
            logger.warning(f"Failed to update memories: {e}")


__all__ = ["FoundryMemoryProvider"]
