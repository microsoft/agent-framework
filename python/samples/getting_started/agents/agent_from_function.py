# Copyright (c) Microsoft. All rights reserved.
import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, ChatMessage, TextContent, agent


async def streaming_agent_from_function() -> None:
    @agent(instructions="This is a custom agent that responds to user input.")  # type: ignore
    async def my_custom_streaming_agent(messages: str, **kwargs: Any) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        """This is a custom agent that responds to user input."""
        # Your custom agent logic here
        texts = ["Hello ", "from ", "my_custom_streaming_agent!"]
        for text in texts:
            yield AgentRunResponseUpdate(contents=[TextContent(text=text)])
            await asyncio.sleep(0)

    assert isinstance(my_custom_streaming_agent, AgentProtocol)

    async for update in my_custom_streaming_agent.run_streaming("Hello, agent!"):
        print(update, end=" . ")
    print()


async def agent_from_function() -> None:
    @agent(instructions="This is a custom agent that responds to user input.")  # type: ignore
    async def my_custom_agent(messages: str, **kwargs: Any) -> AgentRunResponse:
        """This is a custom agent that responds to user input."""
        # Your custom agent logic here
        return AgentRunResponse(messages=[ChatMessage(role="assistant", text="Hello from my_custom_agent!")])

    assert isinstance(my_custom_agent, AgentProtocol)

    response = await my_custom_agent.run("Hello, agent!")
    print(response)


async def main() -> None:
    await streaming_agent_from_function()
    await agent_from_function()


if __name__ == "__main__":
    asyncio.run(main())
