# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import struct
from pathlib import Path

from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.openai import OpenAIChatClient

ASSETS_DIR = Path(__file__).resolve().parent.parent / "sample_assets"


def load_sample_pdf() -> bytes:
    """Read the bundled sample PDF for tests."""
    pdf_path = ASSETS_DIR / "sample.pdf"
    return pdf_path.read_bytes()


def create_sample_image() -> str:
    """Create a simple 1x1 pixel PNG image for testing."""
    # This is a tiny red pixel in PNG format
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    return f"data:image/png;base64,{png_data}"


def create_sample_audio() -> str:
    """Create a minimal WAV file for testing (0.1 seconds of silence)."""
    wav_header = (
        b"RIFF"
        + struct.pack("<I", 44)  # file size
        + b"WAVEfmt "
        + struct.pack("<I", 16)  # fmt chunk
        + struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)  # PCM, mono, 8kHz
        + b"data"
        + struct.pack("<I", 1600)  # data chunk
        + b"\x00" * 1600  # 0.1 sec silence
    )
    audio_b64 = base64.b64encode(wav_header).decode()
    return f"data:audio/wav;base64,{audio_b64}"


async def test_image() -> None:
    """Test image analysis with OpenAI."""
    client = OpenAIChatClient(model_id="gpt-4o")

    image_uri = create_sample_image()
    message = ChatMessage(
        role=Role.USER,
        contents=[TextContent(text="What's in this image?"), DataContent(uri=image_uri, media_type="image/png")],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def test_audio() -> None:
    """Test audio analysis with OpenAI."""
    client = OpenAIChatClient(model_id="gpt-4o-audio-preview")

    audio_uri = create_sample_audio()
    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What do you hear in this audio?"),
            DataContent(uri=audio_uri, media_type="audio/wav"),
        ],
    )

    response = await client.get_response(message)
    print(f"Audio Response: {response}")


async def test_pdf() -> None:
    """Test PDF document analysis with OpenAI."""
    client = OpenAIChatClient(model_id="gpt-4o")

    pdf_bytes = load_sample_pdf()
    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What information can you extract from this document?"),
            DataContent(
                data=pdf_bytes, media_type="application/pdf", additional_properties={"filename": "employee_report.pdf"}
            ),
        ],
    )

    response = await client.get_response(message)
    print(f"PDF Response: {response}")


async def main() -> None:
    print("=== Testing OpenAI Multimodal ===")
    await test_image()
    await test_audio()
    await test_pdf()


if __name__ == "__main__":
    asyncio.run(main())
