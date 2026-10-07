# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

"""Reuse one agent session across multiple turns."""


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint="https://your-account.services.ai.azure.com/api/projects/your-project",
            model="gpt-4o",
            credential=AzureCliCredential(),
        ),
        instructions="You are a friendly assistant. Keep your answers brief.",
    )
    session = agent.create_session()

    print(await agent.run("My name is Alice and I love hiking.", session=session))
    print(await agent.run("What do you remember about me?", session=session))


if __name__ == "__main__":
    asyncio.run(main())
