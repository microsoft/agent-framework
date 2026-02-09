# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Collection
from typing import Any

from agent_framework import ChatMessage, ChatMessageStoreProtocol
from agent_framework._threads import ChatMessageStoreState
from agent_framework.openai import OpenAIChatClient

"""
Persistent Conversation with a Custom Message Store

Demonstrates implementing a custom ChatMessageStoreProtocol to persist conversation
history. In production, replace the in-memory store with a database, file system,
or other storage backend.

Also shows serialize/deserialize to save and restore thread state across sessions.

For more on threads and persistence:
- Redis storage: ./redis_storage.py
- Suspend/resume: ./suspend_resume.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/threads
"""


# <custom_store>
class CustomChatMessageStore(ChatMessageStoreProtocol):
    """In-memory chat message store. Replace with a database in production."""

    def __init__(self, messages: Collection[ChatMessage] | None = None) -> None:
        self._messages: list[ChatMessage] = []
        if messages:
            self._messages.extend(messages)

    async def add_messages(self, messages: Collection[ChatMessage]) -> None:
        self._messages.extend(messages)

    async def list_messages(self) -> list[ChatMessage]:
        return self._messages

    @classmethod
    async def deserialize(cls, serialized_store_state: Any, **kwargs: Any) -> "CustomChatMessageStore":
        """Create a new instance from serialized state."""
        store = cls()
        await store.update_from_state(serialized_store_state, **kwargs)
        return store

    async def update_from_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        """Update this instance from serialized state."""
        if serialized_store_state:
            state = ChatMessageStoreState.from_dict(serialized_store_state, **kwargs)
            if state.messages:
                self._messages.extend(state.messages)

    async def serialize(self, **kwargs: Any) -> Any:
        """Serialize this store's state."""
        state = ChatMessageStoreState(messages=self._messages)
        return state.to_dict(**kwargs)
# </custom_store>


async def main() -> None:
    print("=== Persistent Conversation with Custom Message Store ===\n")

    # <create_agent>
    agent = OpenAIChatClient().as_agent(
        name="MemoryBot",
        instructions="You are a helpful assistant that remembers our conversation.",
        chat_message_store_factory=CustomChatMessageStore,
    )
    # </create_agent>

    # <conversation>
    thread = agent.get_new_thread()

    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # Serialize the thread state for later restoration
    serialized_thread = await thread.serialize()
    print(f"Serialized thread: {serialized_thread}\n")

    # Deserialize and resume the conversation
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")
    # </conversation>


if __name__ == "__main__":
    asyncio.run(main())
