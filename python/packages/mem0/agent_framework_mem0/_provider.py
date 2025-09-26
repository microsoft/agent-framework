# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import MutableSequence, Sequence
from typing import Any

from agent_framework import ChatMessage, Context, ContextProvider, TextContent
from agent_framework.exceptions import ServiceInitializationError
from mem0 import AsyncMemoryClient
from pydantic import PrivateAttr

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


class Mem0Provider(ContextProvider):
    mem0_client: AsyncMemoryClient
    api_key: str | None = None
    application_id: str | None = None
    agent_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    scope_to_per_operation_thread_id: bool = False
    context_prompt: str = ContextProvider.DEFAULT_CONTEXT_PROMPT

    _should_close_client: bool = PrivateAttr(default=False)  # Track whether we should close client connection

    def __init__(
        self,
        api_key: str | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        scope_to_per_operation_thread_id: bool = False,
        context_prompt: str = ContextProvider.DEFAULT_CONTEXT_PROMPT,
        mem0_client: AsyncMemoryClient | None = None,
    ) -> None:
        """Initializes a new instance of the Mem0Provider class.

        Args:
            api_key: The API key for authenticating with the Mem0 API. If not
                provided, it will attempt to use the MEM0_API_KEY environment variable.
            application_id: The application ID for scoping memories or None.
            agent_id: The agent ID for scoping memories or None.
            thread_id: The thread ID for scoping memories or None.
            user_id: The user ID for scoping memories or None.
            scope_to_per_operation_thread_id: Whether to scope memories to per-operation thread ID.
            context_prompt: The prompt to prepend to retrieved memories.
            mem0_client: A pre-created Mem0 MemoryClient or None to create a default client.
        """
        should_close_client = False
        if mem0_client is None:
            mem0_client = AsyncMemoryClient(api_key=api_key)
            should_close_client = True

        super().__init__(
            api_key=api_key,  # type: ignore[reportCallIssue]
            application_id=application_id,  # type: ignore[reportCallIssue]
            agent_id=agent_id,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            user_id=user_id,  # type: ignore[reportCallIssue]
            scope_to_per_operation_thread_id=scope_to_per_operation_thread_id,  # type: ignore[reportCallIssue]
            context_prompt=context_prompt,  # type: ignore[reportCallIssue]
            mem0_client=mem0_client,  # type: ignore[reportCallIssue]
        )

        self._per_operation_thread_id: str | None = None
        self._should_close_client = should_close_client

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        if self.mem0_client:
            await self.mem0_client.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._should_close_client and self.mem0_client:
            await self.mem0_client.__aexit__(exc_type, exc_val, exc_tb)  # type: ignore

    async def thread_created(self, thread_id: str | None = None) -> None:
        """Called when a new thread is created.

        Args:
            thread_id: The ID of the thread or None.
        """
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called when a new message is being added to the thread.

        Args:
            thread_id: The ID of the thread or None.
            new_messages: New messages to add.
        """
        self._validate_filters()
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

        messages_list = [new_messages] if isinstance(new_messages, ChatMessage) else list(new_messages)

        messages: list[dict[str, str]] = [
            {"role": message.role.value, "content": message.text}
            for message in messages_list
            if message.role.value in {"user", "assistant", "system"} and message.text and message.text.strip()
        ]

        if messages:
            await self.mem0_client.add(  # type: ignore[misc]
                messages=messages,
                user_id=self.user_id,
                agent_id=self.agent_id,
                run_id=self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id,
                metadata={"application_id": self.application_id},
            )

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Called before invoking the AI model to provide context.

        Args:
            messages: List of new messages in the thread.

        Returns:
            Context: Context object containing instructions with memories.
        """
        self._validate_filters()
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        input_text = "\n".join(msg.text for msg in messages_list if msg and msg.text and msg.text.strip())

        memories = await self.mem0_client.search(  # type: ignore[misc]
            query=input_text,
            user_id=self.user_id,
            agent_id=self.agent_id,
            run_id=self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id,
        )

        line_separated_memories = "\n".join(memory.get("memory", "") for memory in memories)

        content = TextContent(f"{self.context_prompt}\n{line_separated_memories}") if line_separated_memories else None

        return Context(contents=[content] if content else None)

    def _validate_filters(self) -> None:
        """Validates that at least one filter is provided.

        Raises:
            ServiceInitializationError: If no filters are provided.
        """
        if not self.agent_id and not self.user_id and not self.application_id and not self.thread_id:
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, application_id, or thread_id is required."
            )

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        """Validates that a new thread ID doesn't conflict with an existing one when scoped.

        Args:
            thread_id: The new thread ID or None.

        Raises:
            ValueError: If a new thread ID is provided when one already exists.
        """
        if (
            self.scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "Mem0Provider can only be used with one thread at a time when scope_to_per_operation_thread_id is True."
            )
