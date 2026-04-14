# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client — Code Interpreter Graph Generation from CSV

This sample demonstrates using code interpreter with the Responses API to:
  1. Upload a local CSV file via the Files API
  2. Pass the file to code interpreter via get_code_interpreter_tool(file_ids=[...])
  3. Ask the model to generate matplotlib charts from the data
  4. Download generated chart images from container file citations
  5. Clean up the uploaded file

The generated images are saved to the current working directory.
"""


def extract_file_citations(result) -> list[dict[str, str]]:
    """Extract container file citation metadata from an AgentResponse.

    Returns a list of dicts with 'container_id', 'file_id', and 'filename' keys.
    """
    citations = []
    for message in result.messages:
        for content in message.contents:
            if not content.annotations:
                continue
            for ann in content.annotations:
                if ann.get("type") == "citation" and ann.get("file_id"):
                    props = ann.get("additional_properties", {})
                    citations.append({
                        "container_id": props.get("container_id", ""),
                        "file_id": ann["file_id"],
                        "filename": ann.get("url", ann["file_id"]),
                    })
    return citations


async def upload_csv(openai_client: AsyncOpenAI, csv_path: str) -> str:
    """Upload a local CSV file for code interpreter use.

    Args:
        openai_client: The underlying AsyncOpenAI client.
        csv_path: Local path to the CSV file.

    Returns:
        The uploaded file ID.
    """
    with open(csv_path, "rb") as f:
        uploaded = await openai_client.files.create(file=f, purpose="assistants")
    print(f"Uploaded {csv_path} → {uploaded.id}")
    return uploaded.id


async def cleanup_uploaded_file(openai_client: AsyncOpenAI, file_id: str) -> None:
    """Delete an uploaded file."""
    await openai_client.files.delete(file_id)
    print(f"Deleted uploaded file: {file_id}")


async def download_container_file(
    openai_client: AsyncOpenAI,
    container_id: str,
    file_id: str,
    output_path: str,
) -> str:
    """Download a file from an OpenAI container and save it locally.

    Args:
        openai_client: The underlying AsyncOpenAI client.
        container_id: The container ID from the citation metadata.
        file_id: The file ID from the citation metadata.
        output_path: Local path to save the downloaded file.

    Returns:
        The output path where the file was saved.
    """
    response = await openai_client.containers.files.content.retrieve(
        file_id=file_id,
        container_id=container_id,
    )
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"Downloaded {output_path} ({len(response.content)} bytes)")
    return output_path


async def main() -> None:
    model = os.environ["AZURE_OPENAI_MODEL"]
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]

    client = OpenAIChatClient(
        model=model,
        azure_endpoint=endpoint,
        api_key=api_key,
    )

    # Upload the CSV and configure code interpreter with the file
    csv_path = str(Path(__file__).parents[3] / "shared" / "sample_assets" / "sample_city_populations.csv")
    openai_client = client.client
    uploaded_file_id = await upload_csv(openai_client, csv_path)

    agent = Agent(
        client=client,
        instructions=(
            "You are a data visualization assistant. "
            "When asked to create charts or graphs, use matplotlib to generate them. "
            "Always save charts with plt.savefig before plt.show."
        ),
        tools=client.get_code_interpreter_tool(file_ids=[uploaded_file_id]),
    )

    query = (
        "Read the uploaded CSV file and create two charts: "
        "1) A horizontal bar chart of the top 10 cities by population, "
        "2) A pie chart showing population distribution by continent. "
        "Use a nice color palette, add titles and labels."
    )
    print(f"\nUser: {query}\n")

    result = await agent.run(query)

    # Print the text response
    print(f"Assistant: {result.text}\n")

    # Print any generated Python code
    for message in result.messages:
        for content in message.contents:
            if content.type == "code_interpreter_tool_call" and content.inputs:
                print("Generated code:")
                print(content.inputs[0].text)
                print()

    # Download generated chart images from container file citations
    citations = extract_file_citations(result)
    for i, cite in enumerate(citations):
        filename = cite["filename"] or f"output_{i}.png"
        await download_container_file(
            openai_client,
            container_id=cite["container_id"],
            file_id=cite["file_id"],
            output_path=filename,
        )

    # Clean up
    await cleanup_uploaded_file(openai_client, uploaded_file_id)


if __name__ == "__main__":
    asyncio.run(main())
