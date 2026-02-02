# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Collection
from typing import Any

from agent_framework import ChatMessage, ChatMessageStoreProtocol
from agent_framework._threads import ChatMessageStoreState
from agent_framework.openai import OpenAIChatClient

"""
Custom Chat Message Store Thread Example

This sample demonstrates how to implement and use a custom chat message store
for thread management, allowing you to persist conversation history in your
preferred storage solution (database, file system, etc.).
"""


class CustomChatMessageStore(ChatMessageStoreProtocol):
    """Implementation of custom chat message store.
    In real applications, this can be an implementation of relational database or vector store."""

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


async def main() -> None:
    """Demonstrates how to use 3rd party or custom chat message store for threads."""
    print("=== Thread with 3rd party or custom chat message store ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().as_agent(
        name="CustomBot",
        instructions="You are a helpful assistant that remembers our conversation.",
        # Use custom chat message store.
        # If not provided, the default in-memory store will be used.
        chat_message_store_factory=CustomChatMessageStore,
    )

    # Start a new thread for the agent conversation.
    thread = agent.get_new_thread()

    # Respond to user input.
    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # Serialize the thread state, so it can be stored for later use.
    serialized_thread = await thread.serialize()

    # The thread can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized thread: {serialized_thread}\n")

    # Deserialize the thread state after loading from storage.
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    # Respond to user input.
    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")


if __name__ == "__main__":
    asyncio.run(main())
