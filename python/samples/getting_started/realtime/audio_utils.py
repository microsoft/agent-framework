# Copyright (c) Microsoft. All rights reserved.

"""Audio utilities for realtime voice samples.

Provides microphone capture and speaker playback for use with RealtimeAgent.

Requirements:
- pyaudio package: pip install pyaudio
- On macOS: brew install portaudio (before pip install pyaudio)
"""

import asyncio
import queue
import threading
from collections.abc import AsyncIterator

# Audio configuration matching OpenAI Realtime API requirements
SAMPLE_RATE = 24000  # 24kHz
CHANNELS = 1  # Mono
CHUNK_SIZE = 2400  # 100ms at 24kHz (24000 * 0.1)
FORMAT_BYTES = 2  # 16-bit = 2 bytes per sample


class AudioPlayer:
    """Plays audio chunks through the default speaker."""

    def __init__(self):
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._pyaudio = None
        self._stream = None

    def start(self) -> None:
        """Start the audio playback thread."""
        import pyaudio

        self._pyaudio = pyaudio.PyAudio()
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        self._running = True
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the audio playback."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pyaudio:
            self._pyaudio.terminate()

    def play(self, audio: bytes) -> None:
        """Queue audio for playback."""
        self._queue.put(audio)

    def clear(self) -> None:
        """Clear queued audio (for interruptions)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _play_loop(self) -> None:
        """Background thread that plays queued audio."""
        while self._running:
            try:
                audio = self._queue.get(timeout=0.1)
                if self._stream and audio:
                    self._stream.write(audio)
            except queue.Empty:
                continue


class MicrophoneCapture:
    """Captures audio from the default microphone."""

    def __init__(self):
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._running = False
        self._pyaudio = None
        self._stream = None

    def start(self) -> None:
        """Start capturing from the microphone."""
        import pyaudio

        self._pyaudio = pyaudio.PyAudio()
        self._running = True
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def stop(self) -> None:
        """Stop capturing."""
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pyaudio:
            self._pyaudio.terminate()

    def _callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback - called when audio is available."""
        import pyaudio

        if self._running and in_data:
            self._queue.put(in_data)
        return (None, pyaudio.paContinue)

    async def audio_generator(self) -> AsyncIterator[bytes]:
        """Async generator that yields audio chunks."""
        while self._running:
            try:
                # Non-blocking get with short timeout
                audio = self._queue.get(timeout=0.05)
                yield audio
            except queue.Empty:
                await asyncio.sleep(0.01)


def check_pyaudio() -> bool:
    """Check if pyaudio is available, print help if not.

    Returns:
        True if pyaudio is available, False otherwise.
    """
    try:
        import pyaudio  # noqa: F401

        return True
    except ImportError:
        print("Error: pyaudio not installed")
        print("Install with: pip install pyaudio")
        print("On macOS, first run: brew install portaudio")
        return False
