# Copyright (c) Microsoft. All rights reserved.


from collections.abc import MutableSequence, Sequence
from typing import TYPE_CHECKING

from agent_framework import AIContext, ChatMessage

if TYPE_CHECKING:
    from mem0 import AsyncMemoryClient  # type: ignore[import-untyped]


class Mem0Provider:
    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"

    _mem0_client: "AsyncMemoryClient"  # type: ignore[no-any-unimported]

    def __init__(  # type: ignore[no-any-unimported]
        self,
        mem0_client: "AsyncMemoryClient | None" = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        scope_to_per_operation_thread_id: bool = False,
        context_prompt: str = DEFAULT_CONTEXT_PROMPT,
    ) -> None:
        """Initializes a new instance of the Mem0Provider class.

        Args:
            mem0_client: A pre-created Mem0 MemoryClient or None to create a default client.
            application_id: The application ID for scoping memories or None.
            agent_id: The agent ID for scoping memories or None.
            thread_id: The thread ID for scoping memories or None.
            user_id: The user ID for scoping memories or None.
            scope_to_per_operation_thread_id: Whether to scope memories to per-operation thread ID.
            context_prompt: The prompt to prepend to retrieved memories.
        """
        if mem0_client is None:
            from mem0 import AsyncMemoryClient  # type: ignore[import-untyped]

            mem0_client = AsyncMemoryClient()
        self._mem0_client = mem0_client
        self._application_id = application_id
        self._agent_id = agent_id
        self._thread_id = thread_id
        self._user_id = user_id
        self._scope_to_per_operation_thread_id = scope_to_per_operation_thread_id
        self._context_prompt = context_prompt
        self._per_operation_thread_id: str | None = None

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
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

        messages_list = [new_messages] if isinstance(new_messages, ChatMessage) else list(new_messages)

        messages: list[dict[str, str]] = [
            {"role": message.role.value, "content": message.text}
            for message in messages_list
            if message and hasattr(message, "role") and hasattr(message, "text")
        ]

        await self._mem0_client.add(  # type: ignore[misc]
            messages=messages,
            user_id=self._user_id,
            agent_id=self._agent_id,
            run_id=self._per_operation_thread_id if self._scope_to_per_operation_thread_id else self._thread_id,
            metadata={"application_id": self._application_id},
        )

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> AIContext:
        """Called before invoking the AI model to provide context.

        Args:
            messages: List of new messages in the thread.

        Returns:
            AIContext: Context object containing instructions with memories.
        """
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        input_text = "\n".join(msg.text for msg in messages_list if msg and msg.text and msg.text.strip())
        memories = await self._mem0_client.search(  # type: ignore[misc]
            query=input_text,
            user_id=self._user_id,
            agent_id=self._agent_id,
            run_id=self._per_operation_thread_id if self._scope_to_per_operation_thread_id else self._thread_id,
        )

        line_separated_memories = "\n".join(memory.get("memory", "") for memory in memories)

        return AIContext(instructions=f"{self._context_prompt}\n{line_separated_memories}")

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        """Validates that a new thread ID doesn't conflict with an existing one when scoped.

        Args:
            thread_id: The new thread ID or None.

        Raises:
            ValueError: If a new thread ID is provided when one already exists.
        """
        if (
            self._scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "Mem0Provider can only be used with one thread at a time when scope_to_per_operation_thread_id is True."
            )
