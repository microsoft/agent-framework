# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Mem0 context provider using ContextProvider.

This module provides ``Mem0ContextProvider``, built on the new
:class:`ContextProvider` hooks pattern.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias, TypedDict

from agent_framework import Message
from agent_framework._sessions import AgentSession, ContextProvider, SessionContext
from agent_framework._telemetry import mark_feature_used
from mem0 import AsyncMemory, AsyncMemoryClient

from ._feature_usage import FeatureIndex

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

logger = logging.getLogger(__name__)
MemoryRecord: TypeAlias = dict[str, object]


class SearchResults(TypedDict):
    results: list[MemoryRecord]


SearchResponse: TypeAlias = list[MemoryRecord] | SearchResults


class Mem0ContextProvider(ContextProvider):
    """Mem0 context provider using the new ContextProvider hooks pattern.

    Integrates Mem0 for persistent semantic memory, searching and storing
    memories via the Mem0 API.

    The provider keeps the storage scope and the retrieval scope separate:

    * ``application_id`` / ``agent_id`` / ``user_id`` are the **storage scope**. They are
      stamped onto every memory written by :meth:`after_run` and are never used to
      retrieve memories.
    * ``search_application_id`` / ``search_agent_id`` / ``search_user_id`` are the
      **retrieval scope** used by :meth:`before_run`.

    Retrieval scope values never inherit from the storage scope. If no ``search_*``
    value is configured, no memories are retrieved. This prevents a memory written
    under a shared ``agent_id`` from being read back by an unrelated user, since
    agent-wide retrieval must be requested explicitly via ``search_agent_id``.
    """

    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "mem0"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        mem0_client: AsyncMemory | AsyncMemoryClient | None = None,
        api_key: str | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        search_application_id: str | None = None,
        search_agent_id: str | None = None,
        search_user_id: str | None = None,
        *,
        context_prompt: str | None = None,
    ) -> None:
        """Initialize the Mem0 context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            mem0_client: A pre-created Mem0 MemoryClient or None to create a default client.
            api_key: The API key for authenticating with the Mem0 API.
            application_id: The application ID that stored memories are stamped with. Platform-only:
                the OSS ``AsyncMemory`` client does not recognize an application
                scope (it scopes only by user_id/agent_id in this provider), so
                application_id cannot be used with an OSS client.
            agent_id: The agent ID that stored memories are stamped with.
            user_id: The user ID that stored memories are stamped with.
            search_application_id: The application ID to retrieve memories for. Platform-only,
                like ``application_id``.
            search_agent_id: The agent ID to retrieve memories for. Setting this retrieves
                memories stored by **any** user under that agent, so only set it for
                agent-wide knowledge that is safe to share across users.
            search_user_id: The user ID to retrieve memories for.
            context_prompt: The prompt to prepend to retrieved memories.

        Remarks:
            The ``search_*`` parameters do not default to their storage-scope counterparts.
            When none of them are set, :meth:`before_run` retrieves nothing and logs a warning.
        """
        super().__init__(source_id)
        should_close_client = False
        if mem0_client is None:
            mem0_client = AsyncMemoryClient(api_key=api_key)
            should_close_client = True

        self.api_key = api_key
        self.application_id = application_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.search_application_id = search_application_id
        self.search_agent_id = search_agent_id
        self.search_user_id = search_user_id
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.mem0_client = mem0_client
        self._should_close_client = should_close_client
        self._warned_no_search_scope = False

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.mem0_client and isinstance(self.mem0_client, AbstractAsyncContextManager):
            await self.mem0_client.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._should_close_client and self.mem0_client and isinstance(self.mem0_client, AbstractAsyncContextManager):
            await self.mem0_client.__aexit__(exc_type, exc_val, exc_tb)  # pyright: ignore[reportUnknownMemberType]

    # -- Hooks pattern ---------------------------------------------------------

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Search Mem0 for relevant memories and add to the session context."""
        mark_feature_used(FeatureIndex.MEM0)
        self._validate_filters()
        if not (self.search_user_id or self.search_agent_id or self.search_application_id):
            if not self._warned_no_search_scope:
                self._warned_no_search_scope = True
                logger.warning(
                    "Mem0ContextProvider has no retrieval scope configured, so no memories will be retrieved. "
                    "Set search_user_id, search_agent_id and/or search_application_id."
                )
            return

        input_text = "\n".join(msg.text for msg in context.input_messages if msg and msg.text and msg.text.strip())
        if not input_text.strip():
            return

        # Query entity partitions independently to bypass strict logical AND limitations
        # Mem0 OSS and Platform SDKs expose inconsistent search typings.
        search_tasks: list[Awaitable[Any]] = []

        # 1. Query User partition independently
        if self.search_user_id:
            user_kwargs = self._build_search_kwargs(input_text, "user_id", self.search_user_id)
            search_tasks.append(self.mem0_client.search(**user_kwargs))  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]

        # 2. Query Agent partition independently
        if self.search_agent_id:
            agent_kwargs = self._build_search_kwargs(input_text, "agent_id", self.search_agent_id)
            search_tasks.append(self.mem0_client.search(**agent_kwargs))  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]

        # Fall back to an app-scoped search when only search_application_id is configured.
        if not search_tasks and self.search_application_id:
            app_kwargs: dict[str, Any] = {"query": input_text, "filters": {"app_id": self.search_application_id}}
            search_tasks.append(self.mem0_client.search(**app_kwargs))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        if not search_tasks:
            return

        results: list[SearchResponse | BaseException] = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Merge and deduplicate results
        memories: list[MemoryRecord] = []
        seen_memory_ids: set[str] = set()
        failed_tasks_count: int = 0

        for search_response in results:
            if isinstance(search_response, asyncio.CancelledError):
                raise search_response

            if isinstance(search_response, BaseException):
                failed_tasks_count += 1
                logger.error(
                    "Mem0 partition search task failed: %s",
                    search_response,
                    exc_info=(type(search_response), search_response, search_response.__traceback__),
                )
                continue

            current_memories: list[MemoryRecord] = []
            if isinstance(search_response, list):
                current_memories = [mem for mem in search_response if isinstance(mem, dict)]
            elif isinstance(search_response, dict):
                results_field = search_response.get("results")
                if isinstance(results_field, list):
                    current_memories = [item for item in results_field if isinstance(item, dict)]
                else:
                    logger.warning(
                        "Unexpected Mem0 search response format: %s",
                        type(results_field).__name__,
                    )

            for mem in current_memories:
                mem_id = mem.get("id")
                if mem_id is not None and not isinstance(mem_id, str):
                    mem_id = str(mem_id)

                if mem_id is not None and mem_id in seen_memory_ids:
                    continue

                if mem_id is not None:
                    seen_memory_ids.add(mem_id)

                memories.append(mem)

        if failed_tasks_count == len(search_tasks):
            logger.error("All Mem0 retrieval tasks failed. Context provider is unable to verify memory state.")

        line_separated_memories = "\n".join(str(memory.get("memory", "")) for memory in memories)
        if line_separated_memories:
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=[f"{self.context_prompt}\n{line_separated_memories}"])],
            )

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store request/response messages to Mem0 for future retrieval."""
        mark_feature_used(FeatureIndex.MEM0)
        self._validate_filters()

        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        def get_role_value(role: Any) -> str:
            return role.value if hasattr(role, "value") else str(role)

        messages: list[dict[str, str]] = [
            {"role": get_role_value(message.role), "content": message.text}
            for message in messages_to_store
            if get_role_value(message.role) in {"user", "assistant", "system"} and message.text and message.text.strip()
        ]

        if messages:
            add_kwargs: dict[str, Any] = {
                "messages": messages,
            }

            if isinstance(self.mem0_client, AsyncMemory):
                add_kwargs["user_id"] = self.user_id
                add_kwargs["agent_id"] = self.agent_id
            else:
                add_kwargs["filters"] = self._build_filters()

            await self.mem0_client.add(**add_kwargs)  # type: ignore[misc, call-arg]

    # -- Internal methods ------------------------------------------------------

    def _validate_filters(self) -> None:
        """Validates that at least one usable filter is provided for the configured client."""
        if not self.agent_id and not self.user_id and not self.application_id:
            raise ValueError("At least one of the filters: agent_id, user_id, or application_id is required.")
        if isinstance(self.mem0_client, AsyncMemory) and (self.application_id or self.search_application_id):
            raise ValueError(
                "application_id is not supported by the OSS AsyncMemory client, which scopes "
                "memories only by user_id/agent_id. Remove application_id or use AsyncMemoryClient."
            )

    def _build_search_kwargs(self, input_text: str, entity_key: str, entity_value: str) -> dict[str, Any]:
        """Build search keyword arguments formatted for OSS vs Platform clients."""
        kwargs: dict[str, Any] = {"query": input_text}

        if self.search_application_id and isinstance(self.mem0_client, AsyncMemory):
            raise ValueError(
                "application_id is not supported by the OSS AsyncMemory client, which scopes "
                "memories only by user_id/agent_id. Remove application_id or use AsyncMemoryClient."
            )

        filters: dict[str, Any] = {entity_key: entity_value}
        if self.search_application_id and not isinstance(self.mem0_client, AsyncMemory):
            filters["app_id"] = self.search_application_id
        kwargs["filters"] = filters

        return kwargs

    def _build_filters(self) -> dict[str, Any]:
        """Build storage identity filters from initialization parameters."""
        filters: dict[str, Any] = {}
        if self.user_id:
            filters["user_id"] = self.user_id
        if self.agent_id:
            filters["agent_id"] = self.agent_id
        if self.application_id:
            filters["app_id"] = self.application_id
        return filters


__all__ = ["Mem0ContextProvider"]
