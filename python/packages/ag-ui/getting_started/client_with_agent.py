# Copyright (c) Microsoft. All rights reserved.

"""Example showing Agent with AGUIChatClient for hybrid tool execution.

This demonstrates the HYBRID pattern matching .NET AGUIClient implementation:

1. AgentSession Pattern (like .NET):
   - Create session with agent.create_session()
   - Pass session to agent.run(stream=True) on each turn
   - Session maintains conversation context via context providers

2. Hybrid Tool Execution:
   - AGUIChatClient uses function invocation mixin
   - Client-side tools (get_weather) can execute locally when server requests them
   - Server may also have its own tools that execute server-side
   - Both work together: server LLM decides which tool to call, decorator handles client execution

This matches .NET pattern: session maintains state, tools execute on appropriate side.
"""

from __future__ import annotations

import asyncio
import logging
import os

from agent_framework import Agent, tool
from agent_framework.ag_ui import AGUIChatClient

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@tool(description="Get the current weather for a location.")
def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city or location name
    """
    print(f"[CLIENT] get_weather tool called with location: {location}")
    weather_data = {
        "seattle": "Rainy, 55°F",
        "san francisco": "Foggy, 62°F",
        "new york": "Sunny, 68°F",
        "london": "Cloudy, 52°F",
    }
    result = weather_data.get(location.lower(), f"Weather data not available for {location}")
    print(f"[CLIENT] get_weather returning: {result}")
    return result


async def main():
    """Demonstrate Agent + AGUIChatClient hybrid tool execution.

    This matches the .NET pattern from Program.cs where:
    - AIAgent agent = chatClient.CreateAIAgent(tools: [...])
    - AgentSession session = agent.CreateSession()
    - RunStreamingAsync(messages, session)

    Python equivalent:
    - agent = Agent(client=AGUIChatClient(...), tools=[...])
    - session = agent.create_session()  # Creates session
    - agent.run(message, stream=True, session=session)  # Session tracks context
    """
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")

    print("=" * 70)
    print("Agent + AGUIChatClient: Hybrid Tool Execution")
    print("=" * 70)
    print(f"\nServer: {server_url}")
    print("\nThis example demonstrates:")
    print("  1. AgentSession maintains conversation state (like .NET)")
    print("  2. Client-side tools execute locally via function invocation mixin")
    print("  3. Server may have additional tools that execute server-side")
    print("  4. HYBRID: Client and server tools work together simultaneously\n")

    try:
        # Create remote client in async context manager
        async with AGUIChatClient(endpoint=server_url) as remote_client:
            # Wrap in Agent for conversation history management
            agent = Agent(
                name="remote_assistant",
                instructions="You are a helpful assistant. Remember user information across the conversation.",
                client=remote_client,
                tools=[get_weather],
            )

            # Create a session to maintain conversation state (like .NET AgentSession)
            session = agent.create_session()

            print("=" * 70)
            print("CONVERSATION WITH HISTORY")
            print("=" * 70)

            # Turn 1: Introduce
            print("\nUser: My name is Alice and I live in Seattle\n")
            async for chunk in agent.run("My name is Alice and I live in Seattle", stream=True, session=session):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 2: Ask about name (tests history)
            print("User: What's my name?\n")
            async for chunk in agent.run("What's my name?", stream=True, session=session):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 3: Ask about location (tests history)
            print("User: Where do I live?\n")
            async for chunk in agent.run("Where do I live?", stream=True, session=session):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 4: Test client-side tool (get_weather is client-side)
            print("User: What's the weather forecast for today in Seattle?\n")
            async for chunk in agent.run(
                "What's the weather forecast for today in Seattle?",
                stream=True,
                session=session,
            ):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 5: Test server-side tool (get_time_zone is server-side only)
            print("User: What time zone is Seattle in?\n")
            async for chunk in agent.run("What time zone is Seattle in?", stream=True, session=session):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

    except ConnectionError as e:
        print(f"\n\033[91mConnection Error: {e}\033[0m")
        print("\nMake sure an AG-UI server is running at the specified endpoint.")
    except Exception as e:
        print(f"\n\033[91mError: {e}\033[0m")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
