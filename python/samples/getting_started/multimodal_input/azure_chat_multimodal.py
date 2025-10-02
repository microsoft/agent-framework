# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64

import requests
from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


async def test_image() -> None:
    """Test image analysis with Azure."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option. Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    # environment variables to be set.
    # Alternatively, you can pass deployment_name explicitly:
    # client = AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name="your-deployment-name")
    client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Fetch image from httpbin
    image_url = "https://httpbin.org/image/jpeg"
    response = requests.get(image_url)
    image_b64 = base64.b64encode(response.content).decode()
    image_uri = f"data:image/jpeg;base64,{image_b64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[TextContent(text="What's in this image?"), DataContent(uri=image_uri, media_type="image/jpeg")],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def main() -> None:
    print("=== Testing Azure Multimodal ===")
    await test_image()


if __name__ == "__main__":
    asyncio.run(main())
