"""Real-time streaming voice chat with interruption support.

This example demonstrates:
- Continuous microphone streaming (not buffered)
- Real-time audio playback
- Interruption support (user can interrupt agent)
- Server-side Voice Activity Detection (VAD)
- Persistent session across conversation
"""

import asyncio
import os
import queue
import sys
import threading
from datetime import datetime

import pyaudio
from dotenv import load_dotenv

from agent_framework import ai_function, ChatAgent
from agent_framework.openai import OpenAIResponsesClient
from agent_framework_azure_voice_live import VoiceLiveAgent
from azure.core.credentials import AzureKeyCredential

# Load environment variables
load_dotenv()

# Fix console encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Audio settings for Azure Voice Live (PCM16, 24kHz, mono)
SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 4800  # 200ms chunks (24000 * 0.2)
FORMAT = pyaudio.paInt16


# Initialize text agent for complex queries
text_agent = None

def init_text_agent():
    """Initialize the GPT-4.1 text agent for expert queries."""
    global text_agent

    openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    openai_base_url = os.getenv("AZURE_OPENAI_BASE_URL")
    model_id = os.getenv("AZURE_OPENAI_MODEL_ID", "gpt-4o")


    if not openai_api_key or not openai_base_url:
        print("⚠️  AZURE_OPENAI_API_KEY or AZURE_OPENAI_BASE_URL not found - expert agent disabled")
        return None

    # Create OpenAI Responses client (works with Azure when base_url is set)
    client = OpenAIResponsesClient(
        model_id=model_id,
        base_url=openai_base_url,
        api_key=openai_api_key,
    )

    # Wrap in ChatAgent for proper agent functionality
    text_agent = ChatAgent(
        chat_client=client,
        name="expert-analyst",
        instructions=(
            "You are an expert analyst with deep knowledge across many domains. "
            "Provide detailed, accurate, and well-reasoned responses. "
            "Be concise but thorough. Focus on facts and clarity."
        ),
        temperature=0.7,
    )
    print(f"✅ Expert text agent initialized ({model_id})")
    return text_agent


# Define AI functions
@ai_function
async def get_weather(location: str) -> str:
    """Get current weather for a location.

    Args:
        location: City name or location

    Returns:
        Weather description
    """
    weather_data = {
        "seattle": "Rainy, 55°F",
        "san francisco": "Foggy, 62°F",
        "new york": "Sunny, 68°F",
        "london": "Cloudy, 59°F",
        "tokyo": "Clear, 72°F",
    }
    weather = weather_data.get(location.lower(), "Sunny, 70°F")
    print(f"\n  🔧 [Function Call] get_weather('{location}') -> {weather}")
    return f"The weather in {location} is {weather}."


@ai_function
async def get_current_time(timezone: str = "UTC") -> str:
    """Get current time.

    Args:
        timezone: Timezone name

    Returns:
        Current time string
    """
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    print(f"\n  🔧 [Function Call] get_current_time('{timezone}') -> {time_str}")
    return f"The current time is {time_str} {timezone}"


@ai_function
async def ask_expert(query: str) -> str:
    """Ask the expert text agent for detailed analysis or complex questions.

    Use this function when the user asks:
    - Complex questions requiring deep reasoning
    - Technical queries needing detailed explanations
    - Research or analytical questions
    - Questions outside your immediate knowledge

    Args:
        query: The question to ask the expert agent

    Returns:
        Detailed expert response
    """
    if text_agent is None:
        return "Expert agent is not available. Please check AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT configuration."

    print(f"\n  🧠 [Expert Agent] Processing query: {query[:100]}...")

    try:
        # Send query to expert agent using run()
        response = await text_agent.run(query)

        # Extract text from response messages
        if response.messages:
            expert_answer = ""
            for message in response.messages:
                if message.contents:
                    for content in message.contents:
                        if hasattr(content, 'text'):
                            expert_answer += content.text

            print(f"  ✅ [Expert Agent] Response received ({len(expert_answer)} chars)")
            return expert_answer if expert_answer else "Expert agent returned an empty response."
        else:
            return "Expert agent returned an empty response."

    except Exception as e:
        error_msg = f"Expert agent error: {str(e)}"
        print(f"  ❌ [Expert Agent] {error_msg}")
        import traceback
        traceback.print_exc()
        return error_msg


class ConversationState:
    """Track conversation state for interruption handling."""

    def __init__(self):
        self.running = True
        self.user_is_speaking = False
        self.agent_is_speaking = False
        self.interrupted = False


class AudioPlayer:
    """Handles real-time audio playback with interruption support."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.queue = queue.Queue()
        self.playing = False
        self.chunks_played = 0

    def start(self):
        """Start the audio playback stream."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        self.playing = True
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        print("🔊 Audio player started")

    def _playback_worker(self):
        """Worker thread for playing audio chunks."""
        while self.playing:
            try:
                chunk = self.queue.get(timeout=0.1)
                if chunk is not None:
                    self.stream.write(chunk)
                    self.chunks_played += 1
            except queue.Empty:
                continue
            except Exception as e:
                print(f"\n⚠️ Error playing audio: {e}")

    def play(self, audio_chunk: bytes):
        """Queue audio chunk for playback."""
        if self.playing:
            self.queue.put(audio_chunk)

    def clear_buffer(self):
        """Clear playback buffer (for interruption)."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        print("\n🛑 Playback buffer cleared (interrupted)")

    def stop(self):
        """Stop playback and clean up."""
        self.playing = False
        if hasattr(self, 'playback_thread'):
            self.playback_thread.join(timeout=2.0)
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        print(f"\n🛑 Audio player stopped. Played {self.chunks_played} chunks.")


class MicrophoneStreamer:
    """Handles continuous microphone streaming."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.streaming = False

    def start(self):
        """Start the microphone streaming."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        self.streaming = True
        print("🎤 Microphone streaming started")

    def read_chunk(self) -> bytes:
        """Read a chunk of audio from the microphone."""
        if self.streaming and self.stream:
            try:
                return self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except Exception as e:
                print(f"\n⚠️ Error reading microphone: {e}")
                return b""
        return b""

    def stop(self):
        """Stop streaming and clean up."""
        self.streaming = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        print("🛑 Microphone streaming stopped")


async def audio_capture_loop(agent: VoiceLiveAgent, mic: MicrophoneStreamer, state: ConversationState):
    """Continuously stream microphone audio to agent."""
    print("📡 Audio capture loop started")

    while state.running:
        # Read chunk from microphone
        chunk = await asyncio.to_thread(mic.read_chunk)

        if chunk and len(chunk) > 0:
            # Stream to agent immediately
            await agent.stream_audio_chunk(chunk)

        await asyncio.sleep(0.01)  # Prevent tight loop

    print("📡 Audio capture loop stopped")


async def audio_playback_loop(agent: VoiceLiveAgent, player: AudioPlayer, state: ConversationState):
    """Play agent audio responses in real-time."""
    print("🔊 Audio playback loop started")

    try:
        async for update in agent.listen_to_responses():
            if not state.running:
                break

            props = update.additional_properties or {}
            update_type = props.get("type")

            if update_type == "response_started":
                state.agent_is_speaking = True
                state.interrupted = False
                print("\n🤖 [Agent speaking...]", end="", flush=True)

            elif update_type == "audio_delta":
                # Stream audio to speaker immediately
                if not state.interrupted:
                    audio_data = props.get("audio_data")
                    if audio_data:
                        player.play(audio_data)
                        print("▶️", end="", flush=True)

            elif update_type == "transcript_delta":
                # Display transcript
                text = props.get("text")
                if text:
                    print(text, end="", flush=True)

            elif update_type == "response_done":
                state.agent_is_speaking = False
                print("\n✅ [Agent finished]")

            elif update_type == "input_transcription_complete":
                # Show what the user said
                user_transcript = props.get("transcript")
                if user_transcript:
                    print(f"\n👤 [You]: {user_transcript}")

            elif update_type == "speech_started":
                # User started speaking
                if state.agent_is_speaking:
                    # User interrupted the agent
                    print("\n\n⚠️ [User interrupted agent]")
                    state.interrupted = True
                    await agent.cancel_response()
                    player.clear_buffer()

            elif update_type == "error":
                error_msg = props.get("error")
                # Suppress harmless errors
                if isinstance(error_msg, dict) and error_msg.get("code") == "conversation_already_has_active_response":
                    continue
                print(f"\n❌ Error: {error_msg}")

    except Exception as e:
        print(f"\n❌ Playback loop error: {e}")
        import traceback
        traceback.print_exc()

    print("🔊 Audio playback loop stopped")


async def streaming_conversation(agent: VoiceLiveAgent):
    """Run a streaming conversation with interruption support.

    Args:
        agent: The VoiceLiveAgent instance (must be connected)
    """
    print("\n" + "=" * 70)
    print("🎤 Starting streaming voice conversation...")
    print("💡 You can interrupt the agent anytime by speaking!")
    print("🛑 Press Ctrl+C to stop the conversation")
    print("=" * 70)

    # Initialize components
    mic = MicrophoneStreamer()
    player = AudioPlayer()
    state = ConversationState()

    try:
        # Start audio I/O
        mic.start()
        player.start()

        print("\n🎤 Listening... Start speaking anytime!")
        print("🤖 Agent will respond automatically when you stop speaking.\n")

        # Run concurrent loops indefinitely (until Ctrl+C)
        await asyncio.gather(
            audio_capture_loop(agent, mic, state),
            audio_playback_loop(agent, player, state),
        )

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user (Ctrl+C)")
    finally:
        # Stop everything
        state.running = False
        await asyncio.sleep(0.5)  # Let loops finish
        mic.stop()
        player.stop()

    print("=" * 70)
    print("✅ Streaming conversation complete!")
    print("=" * 70)


async def main():
    """Run the streaming voice chat demo."""
    # Get required environment variables
    api_key = os.getenv("AZURE_VOICELIVE_API_KEY")
    endpoint = os.getenv("AZURE_VOICELIVE_ENDPOINT")

    if not api_key or not endpoint:
        raise ValueError(
            "AZURE_VOICELIVE_API_KEY and AZURE_VOICELIVE_ENDPOINT "
            "environment variables are required."
        )

    # Initialize text agent for expert queries
    print("🔧 Initializing expert text agent...")
    init_text_agent()
    print(await ask_expert("Test initialization"))

    # Prepare tools list
    tools = [get_weather, get_current_time]
    if text_agent is not None:
        tools.append(ask_expert)
        print("✅ Expert agent added to tools")

    # Create agent with VAD enabled (required for streaming)
    agent = VoiceLiveAgent(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
        model=os.getenv("AZURE_VOICELIVE_MODEL", "gpt-4o-realtime-preview"),
        voice=os.getenv("AZURE_VOICELIVE_VOICE", "en-US-AvaNeural"),
        instructions=(
            "You are a helpful and friendly voice assistant. "
            "You can check the weather, tell the time, and answer complex questions. "
            "\n\n"
            "For simple queries (weather, time, greetings), answer directly. "
            "For complex questions requiring deep analysis, technical explanations, "
            "or research, use the ask_expert function to get detailed answers. "
            "\n\n"
            "Keep your responses concise and conversational. "
            "If interrupted, acknowledge and adapt naturally."
        ),
        tools=tools,
        temperature=0.8,
        enable_vad=True,  # REQUIRED for streaming and interruption
        vad_threshold=0.5,
        vad_silence_duration_ms=500,
        input_audio_transcription=True,
    )

    print("=" * 70)
    print("🎙️  Streaming Voice Chat Demo (with Expert Agent)")
    print("=" * 70)
    print("\nThis demo streams audio in real-time with:")
    print("  • Continuous microphone input")
    print("  • Real-time agent responses")
    print("  • Interruption support (speak over the agent)")
    print("  • Server-side Voice Activity Detection")
    if text_agent:
        print("  • Expert GPT-4 agent for complex queries")
    print("=" * 70)

    # Connect to persistent session
    print("\n🔌 Connecting to Azure Voice Live...")
    await agent.connect()
    print("✅ Connected! Session is ready.")

    try:
        # Run streaming conversation (runs until Ctrl+C)
        await streaming_conversation(agent)
    finally:
        # Disconnect session
        print("\n🔌 Disconnecting from Azure Voice Live...")
        await agent.disconnect()
        print("✅ Disconnected!")

    print("\n✨ Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
