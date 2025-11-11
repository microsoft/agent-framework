# Copyright (c) Microsoft. All rights reserved.

"""Example showing ChatAgent with AGUIChatClient for hybrid tool execution.

This demonstrates the HYBRID pattern matching .NET AGUIClient implementation:

1. AgentThread Pattern (like .NET):
   - Create thread with agent.get_new_thread()
   - Pass thread to agent.run_stream() on each turn
   - Thread automatically maintains conversation history via message_store

2. Hybrid Tool Execution:
   - AGUIChatClient has @use_function_invocation decorator
   - Client-side tools (get_weather) can execute locally when server requests them
   - Server may also have its own tools that execute server-side
   - Both work together: server LLM decides which tool to call, decorator handles client execution

This matches .NET pattern: thread maintains state, tools execute on appropriate side.
"""

import asyncio
import logging
import os

from agent_framework import ChatAgent, FunctionCallContent, FunctionResultContent, TextContent, ai_function

from agent_framework_ag_ui import AGUIChatClient

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@ai_function(description="Get the current weather for a location.")
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
    """Demonstrate ChatAgent + AGUIChatClient hybrid tool execution.

    This matches the .NET pattern from Program.cs where:
    - AIAgent agent = chatClient.CreateAIAgent(tools: [...])
    - AgentThread thread = agent.GetNewThread()
    - RunStreamingAsync(messages, thread)

    Python equivalent:
    - agent = ChatAgent(chat_client=AGUIChatClient(...), tools=[...])
    - thread = agent.get_new_thread()  # Creates thread with message_store
    - agent.run_stream(message, thread=thread)  # Thread accumulates history
    """
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")

    print("=" * 70)
    print("ChatAgent + AGUIChatClient: Hybrid Tool Execution")
    print("=" * 70)
    print(f"\nServer: {server_url}")
    print("\nThis example demonstrates:")
    print("  1. AgentThread maintains conversation state (like .NET)")
    print("  2. Client-side tools execute locally via @use_function_invocation")
    print("  3. Server may have additional tools that execute server-side")
    print("  4. HYBRID: Client and server tools work together simultaneously\n")

    try:
        # Create remote client in async context manager
        async with AGUIChatClient(endpoint=server_url) as remote_client:
            # Wrap in ChatAgent for conversation history management
            agent = ChatAgent(
                name="remote_assistant",
                instructions="You are a helpful assistant. Remember user information across the conversation.",
                chat_client=remote_client,
                tools=[get_weather],
            )

            # Create a thread to maintain conversation state (like .NET AgentThread)
            thread = agent.get_new_thread()

            print("=" * 70)
            print("CONVERSATION WITH HISTORY")
            print("=" * 70)

            # Turn 1: Introduce
            print("\nUser: My name is Alice and I live in Seattle\n")
            async for chunk in agent.run_stream("My name is Alice and I live in Seattle", thread=thread):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 2: Ask about name (tests history)
            print("User: What's my name?\n")
            async for chunk in agent.run_stream("What's my name?", thread=thread):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 3: Ask about location (tests history)
            print("User: Where do I live?\n")
            async for chunk in agent.run_stream("Where do I live?", thread=thread):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 4: Test client-side tool (get_weather is client-side)
            print("User: What's the weather forecast for today in Seattle?\n")
            async for chunk in agent.run_stream("What's the weather forecast for today in Seattle?", thread=thread):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Turn 5: Test server-side tool (get_time_zone is server-side only)
            print("User: What time zone is Seattle in?\n")
            async for chunk in agent.run_stream("What time zone is Seattle in?", thread=thread):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")

            # Show thread state
            if thread.message_store:

                def _preview_for_message(m) -> str:
                    # Prefer plain text when present
                    if getattr(m, "text", ""):
                        t = m.text
                        return (t[:60] + "...") if len(t) > 60 else t
                    # Build from contents when no direct text
                    parts: list[str] = []
                    for c in getattr(m, "contents", []) or []:
                        if isinstance(c, FunctionCallContent):
                            args = c.arguments
                            if isinstance(args, dict):
                                try:
                                    import json as _json

                                    args_str = _json.dumps(args)
                                except Exception:
                                    args_str = str(args)
                            else:
                                args_str = str(args or "{}")
                            parts.append(f"tool_call {c.name} {args_str}")
                        elif isinstance(c, FunctionResultContent):
                            parts.append(f"tool_result[{c.call_id}]: {str(c.result)[:40]}")
                        elif isinstance(c, TextContent):
                            if c.text:
                                parts.append(c.text)
                        else:
                            typename = getattr(c, "type", c.__class__.__name__)
                            parts.append(f"<{typename}>")
                    preview = " | ".join(parts) if parts else ""
                    return (preview[:60] + "...") if len(preview) > 60 else preview

                messages = await thread.message_store.list_messages()
                print(f"\n[THREAD STATE] {len(messages)} messages in thread's message_store")
                for i, msg in enumerate(messages[-6:], 1):  # Show last 6
                    role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    text_preview = _preview_for_message(msg)
                    print(f"  {i}. [{role}]: {text_preview}")

    except ConnectionError as e:
        print(f"\n\033[91mConnection Error: {e}\033[0m")
        print("\nMake sure an AG-UI server is running at the specified endpoint.")
    except Exception as e:
        print(f"\n\033[91mError: {e}\033[0m")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
