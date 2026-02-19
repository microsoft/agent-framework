# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Sequence
from typing import Any

from agent_framework import AgentSession, BaseHistoryProvider, Message
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Custom History Provider Example

This sample demonstrates how to implement and use a custom history provider
for session management, allowing you to persist conversation history in your
preferred storage solution (database, file system, etc.).
"""


class CustomHistoryProvider(BaseHistoryProvider):
    """Implementation of custom history provider.
    In real applications, this can be an implementation of relational database or vector store."""

    def __init__(self) -> None:
        super().__init__("custom-history")
        self._storage: dict[str, list[Message]] = {}

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        key = session_id or "default"
        return list(self._storage.get(key, []))

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        key = session_id or "default"
        if key not in self._storage:
            self._storage[key] = []
        self._storage[key].extend(messages)


async def main() -> None:
    """Demonstrates how to use 3rd party or custom history provider for sessions."""
    print("=== Session with 3rd party or custom history provider ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().as_agent(
        name="CustomBot",
        instructions="You are a helpful assistant that remembers our conversation.",
        # Use custom history provider.
        # If not provided, the default in-memory provider will be used.
        context_providers=[CustomHistoryProvider()],
    )

    # Start a new session for the agent conversation.
    session = agent.create_session()

    # Respond to user input.
    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, session=session)}\n")

    # Serialize the session state, so it can be stored for later use.
    serialized_session = session.to_dict()

    # The session can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized session: {serialized_session}\n")

    # Deserialize the session state after loading from storage.
    resumed_session = AgentSession.from_dict(serialized_session)

    # Respond to user input.
    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, session=resumed_session)}\n")


if __name__ == "__main__":
    asyncio.run(main())
