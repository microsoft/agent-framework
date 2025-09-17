# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import requests
import struct
from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.openai import OpenAIChatClient

async def test_image():
    """Test image analysis with OpenAI."""
    client = OpenAIChatClient(ai_model_id="gpt-4o")

    # Fetch image from httpbin
    image_url = "https://httpbin.org/image/jpeg"
    response = requests.get(image_url)
    image_b64 = base64.b64encode(response.content).decode()
    image_uri = f"data:image/jpeg;base64,{image_b64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What's in this image?"),
            DataContent(uri=image_uri, media_type="image/jpeg")
        ]
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")

async def test_audio():
    """Test audio analysis with OpenAI."""
    client = OpenAIChatClient(ai_model_id="gpt-4o-audio-preview")

    # Create minimal WAV file (0.1 seconds of silence)
    wav_header = (
        b'RIFF' + struct.pack('<I', 44) +  # file size
        b'WAVEfmt ' + struct.pack('<I', 16) +  # fmt chunk
        struct.pack('<HHIIHH', 1, 1, 8000, 16000, 2, 16) +  # PCM, mono, 8kHz
        b'data' + struct.pack('<I', 1600) +  # data chunk
        b'\x00' * 1600  # 0.1 sec silence
    )
    audio_b64 = base64.b64encode(wav_header).decode()
    audio_uri = f"data:audio/wav;base64,{audio_b64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What do you hear in this audio?"),
            DataContent(uri=audio_uri, media_type="audio/wav")
        ]
    )

    response = await client.get_response(message)
    print(f"Audio Response: {response}")

async def main():
    print("=== Testing OpenAI Multimodal ===")
    await test_image()
    await test_audio()

if __name__ == "__main__":
    asyncio.run(main())
