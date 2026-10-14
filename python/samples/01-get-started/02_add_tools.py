# Copyright (c) Microsoft. All rights reserved.

"""Give an agent a function tool.

The weather function is registered with @tool and passed to the agent.
Safety guidance: https://learn.microsoft.com/agent-framework/concepts/agents/safety
"""

import asyncio

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


# This read-only sample tool can run without approval.
@tool(approval_mode="never_require")
def get_weather(location: str) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny."


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint="https://your-account.services.ai.azure.com/api/projects/your-project",
            model="gpt-6-luna",
            credential=AzureCliCredential(),
        ),
        instructions="Use the weather tool to answer questions.",
        tools=[get_weather],
    )
    print(await agent.run("What's the weather like in Seattle?"))


if __name__ == "__main__":
    asyncio.run(main())
