# Copyright (c) Microsoft. All rights reserved.

import asyncio
from pathlib import Path

import aiofiles
from agent_framework import DataContent
from agent_framework.azure import AzureAIClient
from azure.ai.projects.models import ImageGenTool
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent With Image Generation

This sample demonstrates basic usage of AzureAIClient to create an agent
that can generate images based on user requirements.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def main() -> None:
    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="ImageGenAgent",
            instructions="Generate images based on user requirements.",
            tools=[ImageGenTool(quality="low", size="1024x1024")],
        ) as agent,
    ):
        query = "Generate an image of Microsoft logo."
        print(f"User: {query}")
        result = await agent.run(
            query,
            # These additional options are required for image generation
            additional_chat_options={
                "extra_headers": {"x-ms-oai-image-generation-deployment": "gpt-image-1"},
            },
        )
        print(f"Agent: {result}\n")

        # Save the image to a file
        print("Downloading generated image...")
        image_data = [
            content
            for content in result.messages[0].contents
            if isinstance(content, DataContent) and content.media_type == "image/png"
        ]
        if image_data and image_data[0]:
            # Save to the same directory as this script
            filename = "microsoft.png"
            current_dir = Path(__file__).parent.resolve()
            file_path = current_dir / filename
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(image_data[0].get_data_bytes())

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
