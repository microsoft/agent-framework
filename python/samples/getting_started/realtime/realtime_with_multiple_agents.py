# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from random import randint
from typing import Annotated

from agent_framework import BaseRealtimeClient, FunctionTool, RealtimeSessionConfig, execute_tool, tool, tool_to_schema
from agent_framework.azure import AzureOpenAIRealtimeClient, AzureVoiceLiveClient
from agent_framework.openai import OpenAIRealtimeClient
from audio_utils import AudioPlayer, MicrophoneCapture, check_pyaudio
from azure.identity import DefaultAzureCredential
from pydantic import Field

logger = logging.getLogger(__name__)

"""
Realtime Voice Agent with Multiple Agents Example

This sample demonstrates switching between multiple realtime voice agents during
a conversation. Each agent has its own instructions, tools, and personality.
A transfer tool triggers the switch between agents.

Supported client types (set via --client-type or REALTIME_CLIENT_TYPE env var):
- openai: OpenAI Realtime API (requires OPENAI_API_KEY)
- azure_openai: Azure OpenAI Realtime API (requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY)
- azure_voice_live: Azure Voice Live API (requires AZURE_VOICELIVE_ENDPOINT, AZURE_VOICELIVE_MODEL, AZURE_VOICELIVE_API_KEY)

Requirements:
- Environment variables set for the chosen client type
- pyaudio package: pip install pyaudio
- On macOS: brew install portaudio (before pip install pyaudio)

The sample shows:
1. Defining multiple agents with different capabilities
2. Switching between agents mid-conversation using a transfer tool
3. Each agent maintaining its own instructions and tools
4. Reusing a single connection via update_session() — conversation context preserved server-side
"""

# ============================================================================
# Shared tools
# ============================================================================


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
    current_time = datetime.now(timezone.utc)
    return f"The current time in {timezone_name} is {current_time.strftime('%I:%M %p')}."


@tool
def lookup_order(
    order_id: Annotated[str, Field(description="The order ID to look up, e.g. 'ORD-1234'")],
) -> str:
    """Look up an order by its ID."""
    # Mock order data
    orders = {
        "ORD-1001": "Laptop - Shipped, arriving tomorrow",
        "ORD-1002": "Headphones - Delivered on Jan 15",
        "ORD-1003": "Keyboard - Processing, ships in 2 days",
    }
    return orders.get(order_id, f"No order found with ID {order_id}")


@tool
def check_return_eligibility(
    order_id: Annotated[str, Field(description="The order ID to check return eligibility for")],
) -> str:
    """Check if an order is eligible for return."""
    return f"Order {order_id} is eligible for return within the next 14 days. Would you like to start a return?"


# ============================================================================
# Agent definitions
# ============================================================================

@dataclass
class AgentDefinition:
    """Defines a named agent configuration."""

    name: str
    display_name: str
    instructions: str
    tools: list
    voice: str


# The transfer tool is created per-agent-set since it needs the agent registry.
# We define a placeholder here and build it in main().
AGENT_DEFINITIONS = {
    "greeter": AgentDefinition(
        name="greeter",
        display_name="Greeter",
        instructions=(
            "You are a friendly receptionist named Alex. Your job is to greet users warmly "
            "and help direct them to the right agent. Keep your responses brief and welcoming.\n\n"
            "If the user needs help with an order, return, or support issue, transfer to 'support'.\n"
            "If the user asks about the weather, time, math, or general knowledge, transfer to 'assistant'.\n"
            "For general chat, you can handle it yourself."
        ),
        tools=[],
        voice="ash",
    ),
    "support": AgentDefinition(
        name="support",
        display_name="Support Agent",
        instructions=(
            "You are a customer support agent named Sam. You help users with orders, returns, "
            "and other support questions. Be professional, empathetic, and solution-oriented.\n\n"
            "You can look up orders and check return eligibility using your tools.\n"
            "If the user wants to go back to general conversation, transfer to 'greeter'.\n"
            "If they ask about weather, time, or math, transfer to 'assistant'."
        ),
        tools=[lookup_order, check_return_eligibility],
        voice="alloy",
    ),
    "assistant": AgentDefinition(
        name="assistant",
        display_name="Assistant",
        instructions=(
            "You are a helpful assistant named Robin. You can check the weather "
            "and tell the time. Be conversational and concise.\n\n"
            "If the user needs help with an order or support issue, transfer to 'support'.\n"
            "If they want general conversation, transfer to 'greeter'."
        ),
        tools=[get_weather, get_time],
        voice="echo",
    ),
}


# ============================================================================
# Client factory
# ============================================================================


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
    parser = argparse.ArgumentParser(description="Realtime Voice Agent — Multiple Agents")
    parser.add_argument(
        "--client-type",
        type=str,
        default=os.environ.get("REALTIME_CLIENT_TYPE", "openai"),
        choices=["openai", "azure_openai", "azure_voice_live"],
        help="The realtime client type to use (default: openai, env: REALTIME_CLIENT_TYPE)",
    )
    return parser.parse_args()


# ============================================================================
# Multi-agent conversation loop
# ============================================================================


async def run_agent_session(
    agent_def: AgentDefinition,
    client: BaseRealtimeClient,
    microphone: MicrophoneCapture,
    player: AudioPlayer,
    is_first: bool,
) -> str | None:
    """Run a single agent session on an existing connection.

    On the first call, connects the client. On subsequent calls, updates the
    session configuration so that the server-side conversation state is preserved.

    Returns the agent name to transfer to, or None to exit.
    """
    transfer_target: str | None = None

    @tool
    def transfer(
        agent_name: Annotated[str, Field(description="Name of the agent to transfer to: 'greeter', 'support', or 'assistant'")],
    ) -> str:
        """Transfer the conversation to another agent when the user's request is better handled elsewhere.

        Available agents:
        - 'greeter': General conversation and routing
        - 'support': Order lookups, returns, and support issues
        - 'assistant': Weather, time, calculations, and general knowledge

        Always tell the user you're transferring them before calling this tool.
        """
        nonlocal transfer_target
        if agent_name not in AGENT_DEFINITIONS:
            return f"Unknown agent '{agent_name}'. Available: greeter, support, assistant"
        transfer_target = agent_name
        return f"Transferring to {AGENT_DEFINITIONS[agent_name].display_name}..."

    tools: list[FunctionTool] = list(agent_def.tools) + [transfer]
    tool_registry = {tool.name: tool for tool in tools}

    # OpenAI and Azure OpenAI reject voice changes once assistant audio
    # exists in the conversation. Voice Live supports it, so only include
    # the voice when connecting for the first time or when using Voice Live.
    supports_voice_change = isinstance(client, AzureVoiceLiveClient)
    voice = agent_def.voice if (is_first or supports_voice_change) else None

    config = RealtimeSessionConfig(
        instructions=agent_def.instructions,
        voice=voice,
        tools=[tool_to_schema(tool) for tool in tools],
    )

    if is_first:
        await client.connect(config)
    else:
        await client.update_session(config)
        await client.send_text(
            "The user has just been transferred to you. Greet them briefly and help "
            "with whatever they were asking about."
        )

    async def send_audio() -> None:
        try:
            async for chunk in microphone.audio_generator():
                await client.send_audio(chunk)
        except asyncio.CancelledError:
            logger.debug("Audio send loop cancelled.")

    send_task = asyncio.create_task(send_audio())

    ai_speaking = False
    current_ai_text = ""
    try:
        async for event in client.events():
            if event.type == "session_update":
                if "created" in event.data.get("raw_type", ""):
                    print(f"[Connected — speaking with {agent_def.display_name}]")
                elif not is_first:
                    print(f"[Session updated — speaking with {agent_def.display_name}]")

            elif event.type == "tool_call":
                tool_name = event.data.get("name", "unknown")
                result = await execute_tool(tool_registry, event.data)

                if tool_name == "transfer" and transfer_target:
                    # Return immediately — don't send the tool result so the
                    # greeter won't generate a redundant farewell response.
                    # The greeter already spoke its farewell before calling the
                    # tool. update_session() will change the persona and
                    # send_text() will prompt the new agent to greet the user.
                    print(f"    >> Transferring to: {transfer_target}")
                    return transfer_target

                await client.send_tool_result(event.data["id"], result)
                tool_args = event.data.get("arguments", "{}")
                print(f"\n>>> Tool called: {tool_name}")
                print(f"    Arguments: {tool_args}")
                print(f"    Result: {result}")

            elif event.type == "listening":
                print("\n[You are speaking...]")
                ai_speaking = False
                current_ai_text = ""
                player.clear()

            elif event.type == "audio":
                audio = event.data.get("audio", b"")
                if audio:
                    player.play(audio)

            elif event.type == "transcript":
                text = event.data.get("text", "")
                if text:
                    if not ai_speaking:
                        print(f"{agent_def.display_name}: ", end="", flush=True)
                        ai_speaking = True
                    print(text, end="", flush=True)
                    current_ai_text += text

            elif event.type == "speaking_done":
                print()
                ai_speaking = False
                current_ai_text = ""

            elif event.type == "interrupted":
                print("\n[Interrupted — listening...]")
                ai_speaking = False
                current_ai_text = ""
                player.clear()

            elif event.type == "input_transcript":
                text = event.data.get("text", "")
                if text:
                    print(f"You: {text}")

            elif event.type == "error":
                error = event.data.get("error", {})
                print(f"\n[Error: {error}]")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"\n[Agent error: {e}]")
    finally:
        send_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await send_task

    return transfer_target


async def main(client_type: str) -> None:
    """Run a multi-agent voice conversation."""
    print("=== Realtime Voice Chat — Multiple Agents ===\n")

    if not check_pyaudio():
        return

    print(f"Using client type: {client_type}\n")
    print("Agents available:")
    for defn in AGENT_DEFINITIONS.values():
        print(f"  - {defn.display_name} ({defn.name})")

    microphone = MicrophoneCapture()
    player = AudioPlayer()

    print("\nStarting audio devices...")
    microphone.start()
    player.start()

    print("\n" + "=" * 50)
    print("Multi-agent voice chat is now active!")
    print("You'll start with the Greeter.")
    print("Agents can transfer you to each other.")
    print("Press Ctrl+C to end the conversation.")
    print("=" * 50 + "\n")

    client = create_realtime_client(client_type)
    current_agent = "greeter"
    is_first = True

    try:
        while current_agent:
            agent_def = AGENT_DEFINITIONS[current_agent]
            print(f"\n--- Now speaking with: {agent_def.display_name} ---\n")

            next_agent = await run_agent_session(
                agent_def, client, microphone, player, is_first,
            )
            is_first = False

            if next_agent and next_agent in AGENT_DEFINITIONS:
                print(f"\n[Transferred to {AGENT_DEFINITIONS[next_agent].display_name}]")
                current_agent = next_agent
            else:
                break

    except KeyboardInterrupt:
        print("\n\n[Ending conversation...]")
    except Exception as e:
        print(f"\n[Error: {e}]")
    finally:
        await client.disconnect()
        microphone.stop()
        player.stop()
        print("[Audio devices stopped]")
        print("\nGoodbye!")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.client_type))


"""
Sample Output:
=== Realtime Voice Chat — Multiple Agents ===

Using client type: azure_openai

Agents available:
  - Greeter (greeter)
  - Support Agent (support)
  - Assistant (assistant)

Starting audio devices...

==================================================
Multi-agent voice chat is now active!
You'll start with the Greeter.
Agents can transfer you to each other.
Press Ctrl+C to end the conversation.
==================================================


--- Now speaking with: Greeter ---

[Connected — speaking with Greeter]
Greeter: Hi there! Welcome! I'm Alex, how can I help you today?

[You are speaking...]
You: I need to check on my order.
Greeter: Sure, let me transfer you to our support team right away!
    >> Transferring to: support

[Transferred to Support Agent]

--- Now speaking with: Support Agent ---

[Session updated — speaking with Support Agent]
Support Agent: Hi! I'm Sam from support. What's your order number?

[You are speaking...]
You: It's ORD-1001.

>>> Tool called: lookup_order
    Arguments: {"order_id": "ORD-1001"}
    Result: Laptop - Shipped, arriving tomorrow

Support Agent: Your laptop has shipped and should arrive tomorrow!

[You are speaking...]
You: Great! What's the weather like in London?
Support Agent: Let me transfer you to our assistant for that!
    >> Transferring to: assistant

[Transferred to Assistant]

--- Now speaking with: Assistant ---

[Session updated — speaking with Assistant]

>>> Tool called: get_weather
    Arguments: {"location": "London"}
    Result: The weather in London is cloudy with a temperature of 18°C.
"""
