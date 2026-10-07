# Copyright (c) Microsoft. All rights reserved.

"""Persist a user's name with a context provider.

The provider stores the name in session state and injects it into later calls.
"""

import asyncio
from typing import Any

from agent_framework import Agent, AgentSession, ContextProvider, SessionContext
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


class UserMemoryProvider(ContextProvider):
    def __init__(self) -> None:
        super().__init__("user_memory")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        user_name = state.get("user_name")
        instructions = (
            f"The user's name is {user_name}. Address them by name." if user_name else "Ask for the user's name."
        )
        context.extend_instructions(self.source_id, instructions)

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        for message in context.input_messages:
            text = message.text
            if not isinstance(text, str):
                continue
            _, marker, name = text.lower().partition("my name is")
            if marker and name.strip():
                state["user_name"] = name.split()[0].capitalize()


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint="https://your-account.services.ai.azure.com/api/projects/your-project",
            model="gpt-6-luna",
            credential=AzureCliCredential(),
        ),
        instructions="You are a friendly assistant.",
        context_providers=[UserMemoryProvider()],
    )
    session = agent.create_session()

    print(await agent.run("My name is Alice", session=session))
    print(await agent.run("What is 2 + 2?", session=session))


if __name__ == "__main__":
    asyncio.run(main())
