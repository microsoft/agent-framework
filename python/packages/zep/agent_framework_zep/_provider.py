# Copyright (c) Microsoft. All rights reserved.

import os
import sys
from collections.abc import MutableSequence, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from agent_framework import ChatMessage, Context, ContextProvider
from agent_framework.exceptions import ServiceInitializationError
from zep_cloud.client import AsyncZep
from zep_cloud.types import Message

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


class ZepProvider(ContextProvider):
    """Zep Context Provider for Microsoft Agent Framework.

    This provider integrates Zep's long-term memory capabilities with the Agent Framework,
    enabling persistent conversation context across sessions using Zep's knowledge graph.

    Zep requires threads to be associated with users. When the framework creates a thread
    (via service_thread_id), this provider automatically creates the corresponding Zep thread
    and associates it with the configured user_id.
    """

    def __init__(
        self,
        user_id: str,
        zep_client: AsyncZep | None = None,
        api_key: str | None = None,
        thread_id: str | None = None,
        scope_to_per_operation_thread_id: bool = False,
    ) -> None:
        """Initializes a new instance of the ZepProvider class.

        Args:
            user_id: The Zep user ID to associate threads with. Required.
            zep_client: A pre-created AsyncZep client or None to create a default client.
            api_key: The API key for authenticating with the Zep API. If not
                provided, it will attempt to use the ZEP_API_KEY environment variable.
            thread_id: The thread ID for scoping memories or None.
            scope_to_per_operation_thread_id: Whether to scope memories to per-operation thread ID.
                When True, the provider binds to a single dynamically-assigned thread ID from
                the framework's service_thread_id. When False, uses the static pre-created thread_id.

        Raises:
            ServiceInitializationError: If neither zep_client nor api_key is provided.
        """
        should_close_client = False
        if zep_client is None:
            api_key = api_key or os.getenv("ZEP_API_KEY")
            if not api_key:
                raise ServiceInitializationError(
                    "Either zep_client or api_key must be provided. "
                    "You can also set the ZEP_API_KEY environment variable."
                )
            zep_client = AsyncZep(api_key=api_key)
            should_close_client = True

        self.user_id = user_id
        self.api_key = api_key
        self.thread_id = thread_id
        self.scope_to_per_operation_thread_id = scope_to_per_operation_thread_id
        self.zep_client = zep_client
        self._per_operation_thread_id: str | None = None
        self._should_close_client = should_close_client
        self._created_threads: set[str] = set()  # Track which threads we've created

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        if self.zep_client and isinstance(self.zep_client, AbstractAsyncContextManager):
            await self.zep_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        if self._should_close_client and self.zep_client and isinstance(self.zep_client, AbstractAsyncContextManager):
            await self.zep_client.__aexit__(exc_type, exc_val, exc_tb)

    async def thread_created(self, thread_id: str | None = None) -> None:
        """Called when a new thread is created by the framework.

        This method receives the service_thread_id (conversation_id) from the chat service
        and creates a corresponding Zep thread associated with the configured user_id.

        Args:
            thread_id: The service_thread_id from the framework (e.g., Azure AI conversation_id).

        Raises:
            ValueError: If attempting to use multiple threads when scope_to_per_operation_thread_id is True.
        """
        if not thread_id:
            return

        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

        # Create the Zep thread if we haven't already
        if thread_id not in self._created_threads:
            try:
                await self.zep_client.thread.create(
                    thread_id=thread_id,
                    user_id=self.user_id,
                )
                self._created_threads.add(thread_id)
            except Exception:
                # Thread might already exist (e.g., from a previous session)
                # This is not an error - we can still use the thread
                self._created_threads.add(thread_id)

    @override
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after invoking the AI model to persist messages to Zep.

        Args:
            request_messages: The messages sent to the AI model.
            response_messages: The messages returned by the AI model.
            invoke_exception: Any exception that occurred during invocation.
            **kwargs: Additional keyword arguments (unused).
        """
        self._validate_thread_id()

        request_messages_list = (
            [request_messages] if isinstance(request_messages, ChatMessage) else list(request_messages)
        )
        response_messages_list = (
            [response_messages]
            if isinstance(response_messages, ChatMessage)
            else list(response_messages)
            if response_messages
            else []
        )
        messages_list = [*request_messages_list, *response_messages_list]

        # Convert to Zep message format
        zep_messages: list[Message] = []
        for message in messages_list:
            # Only include messages with valid roles and non-empty text
            if message.role.value in {"user", "assistant", "system"} and message.text and message.text.strip():
                zep_messages.append(
                    Message(
                        role=message.role.value,  # type: ignore[arg-type]
                        content=message.text,
                        name=message.author_name if message.author_name else None,
                    )
                )

        if zep_messages:
            thread_id = self._get_current_thread_id()
            await self.zep_client.thread.add_messages(
                thread_id=thread_id,
                messages=zep_messages,
            )

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before invoking the AI model to provide context from Zep.

        Args:
            messages: List of new messages in the thread.
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Context: Context object containing instructions with memory context from Zep.
        """
        self._validate_thread_id()

        thread_id = self._get_current_thread_id()

        # Retrieve context from Zep using basic mode
        try:
            user_context = await self.zep_client.thread.get_user_context(
                thread_id=thread_id,
                mode="basic",
            )

            # Extract the context string from the response
            context_text = user_context.context if hasattr(user_context, "context") and user_context.context else None

            if context_text and context_text.strip():
                return Context(messages=[ChatMessage(role="system", text=context_text)])

            return Context()

        except Exception:
            # If thread doesn't exist yet or other errors, return empty context
            # Thread will be created on first add_messages call or via thread_created()
            return Context()

    def _get_current_thread_id(self) -> str:
        """Gets the current thread ID based on scoping configuration.

        Returns:
            The current thread ID.

        Raises:
            ServiceInitializationError: If no thread ID is available.
        """
        thread_id = self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id
        if not thread_id:
            raise ServiceInitializationError(
                "Thread ID is required. Either provide thread_id at initialization or enable "
                "scope_to_per_operation_thread_id and ensure thread_created is called."
            )
        return thread_id

    def _validate_thread_id(self) -> None:
        """Validates that a thread ID is available.

        Raises:
            ServiceInitializationError: If no thread ID is provided.
        """
        if not self.thread_id and not self._per_operation_thread_id:
            raise ServiceInitializationError(
                "Thread ID is required. Either provide thread_id at initialization or enable "
                "scope_to_per_operation_thread_id and ensure thread_created is called."
            )

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        """Validates that a new thread ID doesn't conflict with an existing one when scoped.

        Args:
            thread_id: The new thread ID or None.

        Raises:
            ValueError: If a new thread ID is provided when one already exists and they don't match.
        """
        if (
            self.scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "ZepProvider can only be used with one thread at a time when scope_to_per_operation_thread_id is True."
            )
