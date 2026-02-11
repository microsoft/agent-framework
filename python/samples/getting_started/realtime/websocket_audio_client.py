# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import base64
import json
import logging
import sys

from audio_utils import AudioPlayer, MicrophoneCapture, check_pyaudio

logger = logging.getLogger(__name__)

"""
WebSocket Audio Client

A command-line utility that connects to the FastAPI WebSocket voice endpoint
(realtime_fastapi_websocket.py), captures microphone audio, sends it over the
WebSocket, and plays back AI audio responses through the speaker.

Prerequisites:
    pip install websockets pyaudio

    On macOS, install PortAudio first:
        brew install portaudio

Quick start:
    1. Set environment variables for your chosen client type:

        # Azure OpenAI
        export REALTIME_CLIENT_TYPE=azure_openai
        export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
        export AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME=gpt-4o-realtime-preview

        # OpenAI
        export REALTIME_CLIENT_TYPE=openai
        export OPENAI_API_KEY=sk-...

        # Azure Voice Live
        export REALTIME_CLIENT_TYPE=azure_voice_live
        export AZURE_VOICELIVE_ENDPOINT=https://...

    2. Start the FastAPI server (in the samples/getting_started/realtime/ dir):
        uvicorn realtime_fastapi_websocket:app

    3. In a separate terminal, run this client:
        python websocket_audio_client.py

Options:
    --url <ws-url>   WebSocket URL (default: ws://localhost:8000/ws/voice)

WebSocket Protocol:
    The client exchanges JSON messages with the server:

    Send (client -> server):
        {"type": "audio", "audio": "<base64-pcm16-24khz-mono>"}

    Receive (server -> client):
        {"type": "audio", "audio": "<base64-pcm16-24khz-mono>"}
        {"type": "transcript", "text": "..."}
        {"type": "input_transcript", "text": "..."}
        {"type": "listening"}
        {"type": "speaking_done"}
        {"type": "tool_call", "name": "...", "arguments": "..."}
        {"type": "tool_result", "name": "...", "result": "..."}
        {"type": "error", "message": "..."}
        {"type": "session_update", "status": "..."}
"""

try:
    import websockets
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    print("Error: websockets not installed")
    print("Install with: pip install websockets")
    sys.exit(1)


DEFAULT_URL = "ws://localhost:8000/ws/voice"


async def main(url: str) -> None:
    """Connect to the WebSocket endpoint and stream audio bidirectionally."""
    if not check_pyaudio():
        return

    print("=== WebSocket Audio Client ===")
    print(f"Connecting to {url} ...")

    microphone = MicrophoneCapture()
    player = AudioPlayer()

    try:
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            print("[Connected]\n")

            microphone.start()
            player.start()

            print("Speak into your microphone. Press Ctrl+C to quit.\n")

            # Run send and receive loops concurrently
            send_task = asyncio.create_task(_send_audio(ws, microphone))
            receive_task = asyncio.create_task(
                _receive_events(ws, player),
            )

            done, pending = await asyncio.wait(
                [send_task, receive_task],
                return_when=asyncio.FIRST_EXCEPTION,
            )

            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, (ConnectionClosedOK, ConnectionClosedError)):
                    raise exc

    except ConnectionRefusedError:
        print(f"\n[Error: Could not connect to {url}]")
        print("Make sure the FastAPI server is running:")
        print("  uvicorn realtime_fastapi_websocket:app")
    except (ConnectionClosedError, ConnectionClosedOK):
        print("\n[Server closed the connection]")
        print("Check the server terminal for errors.")
    except KeyboardInterrupt:
        print("\n\n[Disconnected]")
    except Exception as e:
        print(f"\n[Error: {e}]")
    finally:
        microphone.stop()
        player.stop()
        print("Goodbye!")


async def _send_audio(ws, microphone: MicrophoneCapture) -> None:
    """Stream microphone audio to the WebSocket as base64 JSON messages."""
    try:
        async for chunk in microphone.audio_generator():
            message = json.dumps({
                "type": "audio",
                "audio": base64.b64encode(chunk).decode("utf-8"),
            })
            await ws.send(message)
    except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
        logger.debug("Audio send loop stopped.")


async def _receive_events(ws, player: AudioPlayer) -> None:
    """Receive events from the WebSocket and handle audio/text."""
    ai_speaking = False
    try:
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "audio":
                audio_b64 = msg.get("audio", "")
                if audio_b64:
                    player.play(base64.b64decode(audio_b64))

            elif msg_type == "transcript":
                text = msg.get("text", "")
                if text:
                    if not ai_speaking:
                        print("AI: ", end="", flush=True)
                        ai_speaking = True
                    print(text, end="", flush=True)

            elif msg_type == "listening":
                print("\n[You are speaking...]")
                ai_speaking = False
                player.clear()

            elif msg_type == "speaking_done":
                print()
                ai_speaking = False

            elif msg_type == "tool_call":
                tool_name = msg.get("name", "unknown")
                args = msg.get("arguments", "{}")
                print(f"\n>>> Tool called: {tool_name}")
                print(f"    Arguments: {args}")

            elif msg_type == "tool_result":
                result = msg.get("result", "")
                print(f"    Result: {result}")

            elif msg_type == "input_transcript":
                text = msg.get("text", "")
                if text:
                    print(f"You: {text}")

            elif msg_type == "error":
                detail = msg.get("message", msg.get("details", ""))
                print(f"\n[Error: {detail}]")

            elif msg_type == "session_update":
                status = msg.get("status", "")
                if "created" in status:
                    print("[Session ready]")

    except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
        logger.debug("Event receive loop stopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocket Audio Client for realtime voice endpoint")
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"WebSocket URL to connect to (default: {DEFAULT_URL})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.url))


"""
Sample Output:
=== WebSocket Audio Client ===
Connecting to ws://localhost:8000/ws/voice ...
[Connected]

Speak into your microphone. Press Ctrl+C to quit.

[Session ready]

[You are speaking...]
You: Hello, what can you do?
AI: Hi there! I can check the weather and tell you the current time. What would you like to know?

[You are speaking...]
You: What's the weather in Paris?

>>> Tool called: get_weather
    Arguments: {"location": "Paris"}
AI: The weather in Paris is sunny with a temperature of 22 degrees Celsius.

^C

[Disconnected]
Goodbye!
"""
