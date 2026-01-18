# Copyright (c) Microsoft. All rights reserved.

import asyncio
from pathlib import Path

from agent_framework import ChatMessage, Content, Role
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

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


async def test_image() -> None:
    """Test image analysis with Azure OpenAI Responses API."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option. Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME
    # environment variables to be set.
    # Alternatively, you can pass deployment_name explicitly:
    # client = AzureOpenAIResponsesClient(credential=AzureCliCredential(), deployment_name="your-deployment-name")
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    image_uri = create_sample_image()
    message = ChatMessage(
        role=Role.USER,
        contents=[
            Content.from_text(text="What's in this image?"),
            Content.from_uri(uri=image_uri, media_type="image/png"),
        ],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def test_pdf() -> None:
    """Test PDF document analysis with Azure OpenAI Responses API."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    pdf_bytes = load_sample_pdf()
    message = ChatMessage(
        role=Role.USER,
        contents=[
            Content.from_text(text="What information can you extract from this document?"),
            Content.from_data(
                data=pdf_bytes,
                media_type="application/pdf",
                additional_properties={"filename": "sample.pdf"},
            ),
        ],
    )

    response = await client.get_response(message)
    print(f"PDF Response: {response}")


async def main() -> None:
    print("=== Testing Azure OpenAI Responses API Multimodal ===")
    print("The Responses API supports both images AND PDFs")
    await test_image()
    await test_pdf()


if __name__ == "__main__":
    asyncio.run(main())
