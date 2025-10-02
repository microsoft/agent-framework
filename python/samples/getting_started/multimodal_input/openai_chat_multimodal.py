# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import struct

from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.openai import OpenAIChatClient


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

    pdf_uri = create_sample_pdf()
    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What information can you extract from this document?"),
            DataContent(
                uri=pdf_uri, media_type="application/pdf", additional_properties={"filename": "employee_report.pdf"}
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


def create_sample_pdf() -> str:
    """Create a minimal PDF document for testing."""
    pdf_content = """%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Resources <<
/Font <<
/F1 4 0 R
>>
>>
/Contents 5 0 R
>>
endobj

4 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj

5 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Employee Review: John Smith) Tj
ET
endstream
endobj

xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000361 00000 n
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
456
%%EOF"""
    pdf_b64 = base64.b64encode(pdf_content.encode()).decode()
    return f"data:application/pdf;base64,{pdf_b64}"


if __name__ == "__main__":
    asyncio.run(main())
