# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import os

from agent_framework import BaseRealtimeClient, RealtimeAgent
from agent_framework.azure import AzureOpenAIRealtimeClient, AzureVoiceLiveClient
from agent_framework.openai import OpenAIRealtimeClient
from audio_utils import AudioPlayer, MicrophoneCapture, check_pyaudio
from azure.identity import DefaultAzureCredential

"""
Realtime Voice Agent with Microphone Example

This sample demonstrates a full voice conversation using your microphone and speakers.
It captures audio from your microphone, streams it to the realtime API, and plays
the response audio through your speakers.

Supported client types (set via --client-type or REALTIME_CLIENT_TYPE env var):
- openai: OpenAI Realtime API (requires OPENAI_API_KEY)
- azure_openai: Azure OpenAI Realtime API (requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY)
- azure_voice_live: Azure Voice Live API (requires AZURE_VOICELIVE_ENDPOINT, AZURE_VOICELIVE_MODEL, AZURE_VOICELIVE_API_KEY)

Requirements:
- Environment variables set for the chosen client type
- pyaudio package: pip install pyaudio
- On macOS: brew install portaudio (before pip install pyaudio)

The sample shows:
1. Capturing microphone audio in real-time
2. Streaming audio to the RealtimeAgent
3. Playing response audio through speakers
4. Handling interruptions (barge-in)
5. Configuring the realtime client type via CLI or environment variable
"""


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
    parser = argparse.ArgumentParser(description="Realtime Voice Agent with Microphone")
    parser.add_argument(
        "--client-type",
        type=str,
        default=os.environ.get("REALTIME_CLIENT_TYPE", "openai"),
        choices=["openai", "azure_openai", "azure_voice_live"],
        help="The realtime client type to use (default: openai, env: REALTIME_CLIENT_TYPE)",
    )
    return parser.parse_args()


async def main(client_type: str) -> None:
    """Run a voice conversation with microphone input."""
    print("=== Realtime Voice Chat with Microphone ===\n")

    if not check_pyaudio():
        return

    # 1. Create realtime client and agent
    print(f"Using client type: {client_type}")
    client = create_realtime_client(client_type)

    agent = RealtimeAgent(
        realtime_client=client,
        name="VoiceChat",
        instructions="""You are a friendly voice assistant having a natural conversation.
        Listen carefully and respond conversationally. Keep responses concise.
        If the user interrupts you, stop speaking and listen to them.""",
        voice="alloy",
    )

    # 2. Set up audio I/O
    microphone = MicrophoneCapture()
    player = AudioPlayer()

    print("Starting audio devices...")
    microphone.start()
    player.start()

    print("\n" + "=" * 50)
    print("Voice chat is now active!")
    print("Speak into your microphone to talk with the AI.")
    print("Press Ctrl+C to end the conversation.")
    print("=" * 50 + "\n")

    # 3. Run the conversation
    ai_speaking = False
    try:
        async for event in agent.run(audio_input=microphone.audio_generator()):
            if event.type == "session_update":
                if "created" in event.data.get("raw_type", ""):
                    print("[Connected to realtime API]")

            elif event.type == "listening":
                print("\n[You are speaking...]")
                ai_speaking = False
                # Clear any queued audio when user starts speaking (barge-in)
                player.clear()

            elif event.type == "audio":
                # Play the AI's audio response
                audio = event.data.get("audio", b"")
                if audio:
                    player.play(audio)

            elif event.type == "transcript":
                text = event.data.get("text", "")
                if text:
                    # Print "AI: " prefix only for the first delta of each response
                    if not ai_speaking:
                        print("AI: ", end="", flush=True)
                        ai_speaking = True
                    print(text, end="", flush=True)

            elif event.type == "speaking_done":
                print()  # New line after AI finishes
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
        # 4. Clean up
        microphone.stop()
        player.stop()
        print("[Audio devices stopped]")
        print("\nGoodbye!")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(client_type=args.client_type))


"""
Sample Output:
=== Realtime Voice Chat with Microphone ===

Using client type: openai
Starting audio devices...

==================================================
Voice chat is now active!
Speak into your microphone to talk with the AI.
Press Ctrl+C to end the conversation.
==================================================

[Connected to realtime API]

[You are speaking...]
You: Hello, how are you?
AI: Hello! I'm doing great, thank you for asking. How can I help you today?

[You are speaking...]
You: What's the weather like?
AI: I'd be happy to help you with that. What location would you like to know about?

^C

[Ending conversation...]
[Audio devices stopped]

Goodbye!
"""
