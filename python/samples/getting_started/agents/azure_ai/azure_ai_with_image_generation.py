# Copyright (c) Microsoft. All rights reserved.
import asyncio
import base64
import tempfile
from pathlib import Path
from urllib import request as urllib_request

import aiofiles
from agent_framework import HostedImageGenerationTool
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Image Generation Example

This sample demonstrates basic usage of AzureAIProjectAgentProvider to create an agent
that can generate images based on user requirements.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="ImageGenAgent",
            instructions="Generate images based on user requirements.",
            tools=[
                HostedImageGenerationTool(
                    options={
                        "model_id": "gpt-image-1",
                        "image_size": "1024x1024",
                        "media_type": "png",
                    },
                    additional_properties={
                        "quality": "low",
                        "background": "opaque",
                    },
                )
            ],
        )

        query = "Generate an image of Microsoft logo."
        print(f"User: {query}")
        result = await agent.run(
            query,
            # These additional options are required for image generation
            options={
                "extra_headers": {"x-ms-oai-image-generation-deployment": "gpt-image-1-mini"},
            },
        )
        print(f"Agent: {result}\n")

        # Save the image to a file
        print("Downloading generated image...")
        image_data = [
            content.outputs
            for content in result.messages[0].contents
            if content.type == "image_generation_tool_result" and content.outputs is not None
        ]
        if image_data and image_data[0]:
            # Save to the OS temporary directory
            filename = "microsoft.png"
            file_path = Path(tempfile.gettempdir()) / filename
            # outputs can be a list of Content items (data/uri) or a single item
            out = image_data[0][0] if isinstance(image_data[0], list) else image_data[0]
            data_bytes: bytes | None = None
            uri = getattr(out, "uri", None)
            if isinstance(uri, str):
                if ";base64," in uri:
                    try:
                        b64 = uri.split(";base64,", 1)[1]
                        data_bytes = base64.b64decode(b64)
                    except Exception:
                        data_bytes = None
                else:
                    try:
                        data_bytes = await asyncio.to_thread(lambda: urllib_request.urlopen(uri).read())
                    except Exception:
                        data_bytes = None

            if data_bytes is None:
                raise RuntimeError("Image output present but could not retrieve bytes.")

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data_bytes)

            print(f"Image downloaded and saved to: {file_path}")
        else:
            print("No image data found in the agent response.")

    """
    Sample output:
    User: Generate an image of Microsoft logo.
    Agent: Here is the Microsoft logo image featuring its iconic four quadrants.

    Downloading generated image...
    Image downloaded and saved to: .../microsoft.png
    """


if __name__ == "__main__":
    asyncio.run(main())
