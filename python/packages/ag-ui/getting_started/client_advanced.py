# Copyright (c) Microsoft. All rights reserved.

"""Advanced AG-UI client example with tools and features.

This example demonstrates advanced AGUIChatClient features including:
- Tool/function calling
- Non-streaming responses
- Multiple conversation turns
- Error handling
"""

import asyncio
import os

from agent_framework import ai_function

from agent_framework_ag_ui import AGUIChatClient


@ai_function
def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city or location name
    """
    # Simulate weather lookup
    weather_data = {
        "seattle": "Rainy, 55°F",
        "san francisco": "Foggy, 62°F",
        "new york": "Sunny, 68°F",
        "london": "Cloudy, 52°F",
    }
    return weather_data.get(location.lower(), f"Weather data not available for {location}")


@ai_function
def calculate(a: float, b: float, operation: str) -> str:
    """Perform basic arithmetic operations.

    Args:
        a: First number
        b: Second number
        operation: Operation to perform (add, subtract, multiply, divide)
    """
    try:
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            result = a / b
        else:
            return f"Unsupported operation: {operation}"
        return f"The result is: {result}"
    except Exception as e:
        return f"Error calculating: {e}"


async def streaming_example(client: AGUIChatClient, thread_id: str | None = None):
    """Demonstrate streaming responses."""
    print("\n" + "=" * 60)
    print("STREAMING EXAMPLE")
    print("=" * 60)

    metadata = {"thread_id": thread_id} if thread_id else None

    print("\nUser: Tell me a short joke\n")
    print("Assistant: ", end="", flush=True)

    async for update in client.get_streaming_response("Tell me a short joke", metadata=metadata):
        if not thread_id and update.additional_properties:
            thread_id = update.additional_properties.get("thread_id")

        from agent_framework import TextContent

        for content in update.contents:
            if isinstance(content, TextContent) and content.text:
                print(content.text, end="", flush=True)

    print("\n")
    return thread_id


async def non_streaming_example(client: AGUIChatClient, thread_id: str | None = None):
    """Demonstrate non-streaming responses."""
    print("\n" + "=" * 60)
    print("NON-STREAMING EXAMPLE")
    print("=" * 60)

    metadata = {"thread_id": thread_id} if thread_id else None

    print("\nUser: What is 2 + 2?\n")

    response = await client.get_response("What is 2 + 2?", metadata=metadata)

    print(f"Assistant: {response.text}")

    if response.additional_properties:
        thread_id = response.additional_properties.get("thread_id")
        print(f"\n[Thread: {thread_id}]")

    return thread_id


async def tool_example(client: AGUIChatClient, thread_id: str | None = None):
    """Demonstrate sending tool definitions to the server.

    IMPORTANT: When using AGUIChatClient directly (without ChatAgent wrapper):
    - Tools are sent as DEFINITIONS only
    - No automatic client-side execution (no function invocation middleware)
    - Server must have matching tool implementations to execute them

    For CLIENT-SIDE tool execution (like .NET AGUIClient sample):
    - Use ChatAgent wrapper with tools
    - See client_with_agent.py for the hybrid pattern
    - ChatAgent middleware intercepts and executes client tools locally
    - Server can have its own tools that execute server-side
    - Both client and server tools work together in same conversation

    This example sends tool definitions and assumes server-side execution.
    """
    print("\n" + "=" * 60)
    print("TOOL DEFINITION EXAMPLE")
    print("=" * 60)

    metadata = {"thread_id": thread_id} if thread_id else None

    print("\nUser: What's the weather in Seattle?\n")
    print("Sending tool definitions to server...")
    print("(Server must be configured with matching tools to execute them)\n")

    response = await client.get_response(
        "What's the weather in Seattle?", tools=[get_weather, calculate], metadata=metadata
    )

    print(f"Assistant: {response.text}")

    # Show tool calls if any
    from agent_framework import FunctionCallContent

    tool_called = False
    for message in response.messages:
        for content in message.contents:
            if isinstance(content, FunctionCallContent):
                print(f"\n[Tool Called: {content.name}]")
                tool_called = True

    if not tool_called:
        print("\n[Note: No tools were called - server may not be configured for tool execution]")

    if response.additional_properties:
        thread_id = response.additional_properties.get("thread_id")

    return thread_id


async def conversation_example(client: AGUIChatClient):
    """Demonstrate multi-turn conversation.

    Note: Conversation continuity depends on the server maintaining thread state.
    Some servers may require explicit message history to be sent with each request.
    """
    print("\n" + "=" * 60)
    print("MULTI-TURN CONVERSATION EXAMPLE")
    print("=" * 60)
    print("\nNote: This example uses thread_id for context. Server must support thread-based state.\n")

    # First turn
    print("User: My name is Alice\n")
    response1 = await client.get_response("My name is Alice")
    print(f"Assistant: {response1.text}")
    thread_id = response1.additional_properties.get("thread_id")
    print(f"\n[Thread: {thread_id}]")

    # Second turn - using same thread
    print("\nUser: What's my name?\n")
    response2 = await client.get_response("What's my name?", metadata={"thread_id": thread_id})
    print(f"Assistant: {response2.text}")

    # Check if context was maintained
    if "alice" not in response2.text.lower():
        print("\n[Note: Server may not maintain thread context - consider using ChatAgent for history management]")

    # Third turn
    print("\nUser: Can you also tell me what 10 * 5 is?\n")
    response3 = await client.get_response(
        "Can you also tell me what 10 * 5 is?", metadata={"thread_id": thread_id}, tools=[calculate]
    )
    print(f"Assistant: {response3.text}")


async def main():
    """Run all examples."""
    # Get server URL from environment or use default
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")

    print("=" * 60)
    print("AG-UI Chat Client Advanced Examples")
    print("=" * 60)
    print(f"\nServer: {server_url}")
    print("\nThese examples demonstrate various AGUIChatClient features:")
    print("  1. Streaming responses")
    print("  2. Non-streaming responses")
    print("  3. Tool/function calling")
    print("  4. Multi-turn conversations")

    try:
        async with AGUIChatClient(endpoint=server_url) as client:
            # Run examples in sequence
            thread_id = await streaming_example(client)
            thread_id = await non_streaming_example(client, thread_id)
            await tool_example(client, thread_id)

            # Separate conversation with new thread
            await conversation_example(client)

            print("\n" + "=" * 60)
            print("All examples completed successfully!")
            print("=" * 60)

    except ConnectionError as e:
        print(f"\n\033[91mConnection Error: {e}\033[0m")
        print("\nMake sure an AG-UI server is running at the specified endpoint.")
    except Exception as e:
        print(f"\n\033[91mError: {e}\033[0m")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
