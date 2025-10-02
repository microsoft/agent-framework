# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64

from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential


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
        contents=[TextContent(text="What's in this image?"), DataContent(uri=image_uri, media_type="image/png")],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def test_pdf() -> None:
    """Test PDF document analysis with Azure OpenAI Responses API."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

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
    print("=== Testing Azure OpenAI Responses API Multimodal ===")
    print("The Responses API supports both images AND PDFs, unlike Chat Completions API.")
    await test_image()
    await test_pdf()


def create_sample_image() -> str:
    """Create a simple 1x1 pixel PNG image for testing."""
    # This is a tiny red pixel in PNG format
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    return f"data:image/png;base64,{png_data}"


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
