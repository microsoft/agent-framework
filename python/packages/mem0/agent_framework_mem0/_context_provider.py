# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Mem0 context provider using BaseContextProvider.

This module provides ``Mem0ContextProvider``, built on the new
:class:`BaseContextProvider` hooks pattern.
"""

from __future__ import annotations

import sys
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework import Message
from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework.exceptions import ServiceInitializationError
from mem0 import AsyncMemory, AsyncMemoryClient

if sys.version_info >= (3, 11):
    from typing import NotRequired, Self, TypedDict  # pragma: no cover
else:
    from typing_extensions import NotRequired, Self, TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun


class _MemorySearchResponse_v1_1(TypedDict):
    results: list[dict[str, Any]]
    relations: NotRequired[list[dict[str, Any]]]


_MemorySearchResponse_v2 = list[dict[str, Any]]


class Mem0ContextProvider(BaseContextProvider):
    """Mem0 context provider using the new BaseContextProvider hooks pattern.

    Integrates Mem0 for persistent semantic memory, searching and storing
    memories via the Mem0 API.
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
        *,
        context_prompt: str | None = None,
    ) -> None:
        """Initialize the Mem0 context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            mem0_client: A pre-created Mem0 MemoryClient or None to create a default client.
            api_key: The API key for authenticating with the Mem0 API.
            application_id: The application ID for scoping memories.
            agent_id: The agent ID for scoping memories.
            user_id: The user ID for scoping memories.
            context_prompt: The prompt to prepend to retrieved memories.
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
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.mem0_client = mem0_client
        self._should_close_client = should_close_client

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.mem0_client and isinstance(self.mem0_client, AbstractAsyncContextManager):
            await self.mem0_client.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._should_close_client and self.mem0_client and isinstance(self.mem0_client, AbstractAsyncContextManager):
            await self.mem0_client.__aexit__(exc_type, exc_val, exc_tb)

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
        self._validate_filters()
        input_text = "\n".join(msg.text for msg in context.input_messages if msg and msg.text and msg.text.strip())
        if not input_text.strip():
            return

        filters = self._build_filters()

        # AsyncMemory (OSS) expects user_id/agent_id/run_id as direct kwargs
        # AsyncMemoryClient (Platform) expects them in a filters dict
        search_kwargs: dict[str, Any] = {"query": input_text}
        if isinstance(self.mem0_client, AsyncMemory):
            search_kwargs.update(filters)
        else:
            search_kwargs["filters"] = filters

        search_response: _MemorySearchResponse_v1_1 | _MemorySearchResponse_v2 = await self.mem0_client.search(  # type: ignore[misc]
            **search_kwargs,
        )

        if isinstance(search_response, list):
            memories = search_response
        elif isinstance(search_response, dict) and "results" in search_response:
            memories = search_response["results"]
        else:
            memories = [search_response]

        line_separated_memories = "\n".join(memory.get("memory", "") for memory in memories)
        if line_separated_memories:
            context.extend_messages(
                self.source_id,
                [Message(role="user", text=f"{self.context_prompt}\n{line_separated_memories}")],
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
            await self.mem0_client.add(  # type: ignore[misc]
                messages=messages,
                user_id=self.user_id,
                agent_id=self.agent_id,
                metadata={"application_id": self.application_id},
            )

    # -- Internal methods ------------------------------------------------------

    def _validate_filters(self) -> None:
        """Validates that at least one filter is provided."""
        if not self.agent_id and not self.user_id and not self.application_id:
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, or application_id is required."
            )

    def _build_filters(self) -> dict[str, Any]:
        """Build search filters from initialization parameters."""
        filters: dict[str, Any] = {}
        if self.user_id:
            filters["user_id"] = self.user_id
        if self.agent_id:
            filters["agent_id"] = self.agent_id
        if self.application_id:
            filters["app_id"] = self.application_id
        return filters


__all__ = ["Mem0ContextProvider"]
