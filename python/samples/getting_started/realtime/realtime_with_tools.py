# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyaudio",
# ]
# ///
# Run with: uv run samples/getting_started/realtime/realtime_with_tools.py

# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import os
from datetime import datetime, timezone
from random import randint
from typing import Annotated

from agent_framework import BaseRealtimeClient, RealtimeAgent, tool
from agent_framework.azure import AzureOpenAIRealtimeClient, AzureVoiceLiveClient
from agent_framework.openai import OpenAIRealtimeClient
from audio_utils import AudioPlayer, MicrophoneCapture, check_pyaudio
from azure.identity import DefaultAzureCredential
from pydantic import Field

"""
Realtime Voice Agent with Tools Example

This sample demonstrates how to use function tools with realtime voice agents.
When the model needs to call a function, it will pause speaking, execute the tool,
and then continue the conversation with the result.

Supported client types (set via --client-type or REALTIME_CLIENT_TYPE env var):
- openai: OpenAI Realtime API (requires OPENAI_API_KEY)
- azure_openai: Azure OpenAI Realtime API (requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY)
- azure_voice_live: Azure Voice Live API (requires AZURE_VOICELIVE_ENDPOINT, AZURE_VOICELIVE_API_KEY)

Requirements:
- Environment variables set for the chosen client type
- pyaudio package: pip install pyaudio
- On macOS: brew install portaudio (before pip install pyaudio)

The sample shows:
1. Defining tools using the @tool decorator
2. Registering tools with the RealtimeAgent
3. Using microphone input for natural voice conversations with tools
4. Handling tool_call events during voice conversations
5. Configuring the realtime client type via CLI or environment variable
"""


# Define tools using the @tool decorator
@tool
def get_weather(
    location: Annotated[str, Field(description="The city to get weather for")],
) -> str:
    """Get the current weather for a location."""
    conditions = ["sunny", "cloudy", "rainy", "partly cloudy"]
    temp = randint(15, 30)
    condition = conditions[randint(0, len(conditions) - 1)]
    return f"The weather in {location} is {condition} with a temperature of {temp}°C."


@tool
def get_time(
    timezone_name: Annotated[str, Field(description="Timezone like 'UTC' or 'America/New_York'")] = "UTC",
) -> str:
    """Get the current time in a specified timezone."""
    # Simplified - just return UTC for demo
    current_time = datetime.now(timezone.utc)
    return f"The current time in {timezone_name} is {current_time.strftime('%I:%M %p')}."


def create_realtime_client(client_type: str) -> BaseRealtimeClient:
    """Create a realtime client based on the specified type."""
    if client_type == "openai":
        return OpenAIRealtimeClient(model_id="gpt-realtime")
    if client_type == "azure_openai":
        return AzureOpenAIRealtimeClient(
            deployment_name="gpt-realtime",
            credential=DefaultAzureCredential(),
        )
    if client_type == "azure_voice_live":
        return AzureVoiceLiveClient(
            credential=DefaultAzureCredential(),
        )
    raise ValueError(f"Unknown client type: {client_type}. Valid values: openai, azure_openai, azure_voice_live")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Realtime Voice Agent with Tools")
    parser.add_argument(
        "--client-type",
        type=str,
        default=os.environ.get("REALTIME_CLIENT_TYPE", "openai"),
        choices=["openai", "azure_openai", "azure_voice_live"],
        help="The realtime client type to use (default: openai, env: REALTIME_CLIENT_TYPE)",
    )
    return parser.parse_args()


async def main(client_type: str) -> None:
    """Run a realtime voice session with tools."""
    print("=== Realtime Voice Agent with Tools ===\n")

    if not check_pyaudio():
        return

    print(f"Using client type: {client_type}\n")

    # 1. Create the realtime client
    client = create_realtime_client(client_type)

    # 2. Create the agent with tools
    agent = RealtimeAgent(
        realtime_client=client,
        name="ToolsAssistant",
        instructions="""You are a helpful voice assistant with access to tools.
        You can check the weather and tell the time.
        When asked about these topics, use your tools to provide accurate information.
        Keep your responses conversational and brief.""",
        voice="alloy",
        tools=[get_weather, get_time],
    )

    # 3. Set up audio I/O
    microphone = MicrophoneCapture()
    player = AudioPlayer()

    print("Available tools:")
    print("  - get_weather(location): Get weather for a city")
    print("  - get_time(timezone): Get current time")

    print("\nStarting audio devices...")
    microphone.start()
    player.start()

    print("\n" + "=" * 50)
    print("Voice chat with tools is now active!")
    print("Try asking about the weather, time, or math.")
    print("Press Ctrl+C to end the conversation.")
    print("=" * 50 + "\n")

    # 4. Run the agent and observe tool execution
    ai_speaking = False
    try:
        async for event in agent.run(audio_input=microphone.audio_generator()):
            if event.type == "session_update":
                if "created" in event.data.get("raw_type", ""):
                    print("[Connected to realtime API]")

            elif event.type == "tool_call":
                tool_name = event.data.get("name", "unknown")
                tool_args = event.data.get("arguments", "{}")
                print(f"\n>>> Tool called: {tool_name}")
                print(f"Arguments:\n{tool_args}")

            elif event.type == "tool_result":
                result = event.data.get("result", "")
                print(f"Result:\n{result}")

            elif event.type == "listening":
                print("\n[You are speaking...]")
                ai_speaking = False
                player.clear()

            elif event.type == "audio":
                audio = event.data.get("audio", b"")
                if audio:
                    player.play(audio)

            elif event.type == "transcript":
                text = event.data.get("text", "")
                if text:
                    if not ai_speaking:
                        print("AI: ", end="", flush=True)
                        ai_speaking = True
                    print(text, end="", flush=True)

            elif event.type == "speaking_done":
                print()
                ai_speaking = False

            elif event.type == "interrupted":
                print("\n[Interrupted - listening...]")
                ai_speaking = False
                player.clear()

            elif event.type == "input_transcript":
                text = event.data.get("text", "")
                if text:
                    print(f"You: {text}")

            elif event.type == "error":
                error = event.data.get("error", {})
                print(f"\n[Error: {error}]")

    except KeyboardInterrupt:
        print("\n\n[Ending conversation...]")
    except Exception as e:
        print(f"\n[Error: {e}]")
    finally:
        microphone.stop()
        player.stop()
        print("[Audio devices stopped]")
        print("\nGoodbye!")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.client_type))


"""
Sample Output:
=== Realtime Voice Agent with Tools ===

Using client type: openai

Available tools:
  - get_weather(location): Get weather for a city
  - get_time(timezone): Get current time

Starting audio devices...

==================================================
Voice chat with tools is now active!
Try asking about the weather, time, or math.
Press Ctrl+C to end the conversation.
==================================================

[Connected to realtime API]

[You are speaking...]
You: What's the weather like in Seattle?

>>> Tool called: get_weather
    Arguments: {"location": "Seattle"}

AI: The weather in Seattle is partly cloudy with a temperature of 18 degrees Celsius.

[You are speaking...]
You: What time is it?

>>> Tool called: get_time
    Arguments: {"timezone_name": "UTC"}

AI: The current time in UTC is 3:45 PM.

^C

[Ending conversation...]
[Audio devices stopped]

Goodbye!
"""
