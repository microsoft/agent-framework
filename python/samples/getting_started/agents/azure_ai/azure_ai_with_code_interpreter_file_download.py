# Copyright (c) Microsoft. All rights reserved.

import asyncio
import tempfile
from pathlib import Path

from agent_framework import (
    AgentResponseUpdate,
    ChatAgent,
    CitationAnnotation,
    HostedCodeInterpreterTool,
    HostedFileContent,
    TextContent,
    tool,
)
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI V2 Code Interpreter File Download Sample

This sample demonstrates how the AzureAIProjectAgentProvider handles file annotations
when code interpreter generates text files. It shows:
1. How to extract file IDs and container IDs from annotations
2. How to download container files using the OpenAI containers API
3. How to save downloaded files locally

Note: Code interpreter generates files in containers, which require both
file_id and container_id to download via client.containers.files.content.retrieve().
"""

QUERY = (
    "Write a simple Python script that creates a text file called 'sample.txt' containing "
    "'Hello from the code interpreter!' and save it to disk."
)


async def download_container_files(
    file_contents: list[CitationAnnotation | HostedFileContent], agent: ChatAgent
) -> list[Path]:
    """Download container files using the OpenAI containers API.

    Code interpreter generates files in containers, which require both file_id
    and container_id to download. The container_id is stored in additional_properties.

    This function works for both streaming (HostedFileContent) and non-streaming
    (CitationAnnotation) responses.

    Args:
        file_contents: List of CitationAnnotation or HostedFileContent objects
                      containing file_id and container_id.
        agent: The ChatAgent instance with access to the AzureAIClient.

    Returns:
        List of Path objects for successfully downloaded files.
    """
    if not file_contents:
        return []

    # Create output directory in system temp folder
    temp_dir = Path(tempfile.gettempdir())
    output_dir = temp_dir / "agent_framework_downloads"
    output_dir.mkdir(exist_ok=True)

    print(f"\nDownloading {len(file_contents)} container file(s) to {output_dir.absolute()}...")

    # Access the OpenAI client from AzureAIClient
    openai_client = agent.chat_client.client

    downloaded_files: list[Path] = []

    for content in file_contents:
        file_id = content.file_id

        # Extract container_id from additional_properties
        if not content.additional_properties or "container_id" not in content.additional_properties:
            print(f"  File {file_id}: ✗ Missing container_id")
            continue

        container_id = content.additional_properties["container_id"]

        # Extract filename based on content type
        if isinstance(content, CitationAnnotation):
            filename = content.url or f"{file_id}.txt"
            # Extract filename from sandbox URL if present (e.g., sandbox:/mnt/data/sample.txt)
            if filename.startswith("sandbox:"):
                filename = filename.split("/")[-1]
        else:  # HostedFileContent
            filename = content.additional_properties.get("filename") or f"{file_id}.txt"

        output_path = output_dir / filename

        try:
            # Download using containers API
            print(f"  Downloading {filename}...", end="", flush=True)
            file_content = await openai_client.containers.files.content.retrieve(
                file_id=file_id,
                container_id=container_id,
            )

            # file_content is HttpxBinaryResponseContent, read it
            content_bytes = file_content.read()

            # Save to disk
            output_path.write_bytes(content_bytes)
            file_size = output_path.stat().st_size
            print(f"({file_size} bytes)")

            downloaded_files.append(output_path)

        except Exception as e:
            print(f"Failed: {e}")

    return downloaded_files


async def non_streaming_example() -> None:
    """Example of downloading files from non-streaming response using CitationAnnotation."""
    print("=== Non-Streaming Response Example ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="V2CodeInterpreterFileAgent",
            instructions="You are a helpful assistant that can write and execute Python code to create files.",
            tools=HostedCodeInterpreterTool(),
        )

        print(f"User: {QUERY}\n")

        result = await agent.run(QUERY)
        print(f"Agent: {result.text}\n")

        # Check for annotations in the response
        annotations_found: list[CitationAnnotation] = []
        # AgentResponse has messages property, which contains ChatMessage objects
        for message in result.messages:
            for content in message.contents:
                if isinstance(content, TextContent) and content.annotations:
                    for annotation in content.annotations:
                        if isinstance(annotation, CitationAnnotation) and annotation.file_id:
                            annotations_found.append(annotation)
                            print(f"Found file annotation: file_id={annotation.file_id}")
                            if annotation.additional_properties and "container_id" in annotation.additional_properties:
                                print(f"  container_id={annotation.additional_properties['container_id']}")

        if annotations_found:
            print(f"SUCCESS: Found {len(annotations_found)} file annotation(s)")

            # Download the container files
            downloaded_paths = await download_container_files(annotations_found, agent)

            if downloaded_paths:
                print("\nDownloaded files available at:")
                for path in downloaded_paths:
                    print(f"  - {path.absolute()}")
        else:
            print("WARNING: No file annotations found in non-streaming response")


async def streaming_example() -> None:
    """Example of downloading files from streaming response using HostedFileContent."""
    print("\n=== Streaming Response Example ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="V2CodeInterpreterFileAgentStreaming",
            instructions="You are a helpful assistant that can write and execute Python code to create files.",
            tools=HostedCodeInterpreterTool(),
        )

        print(f"User: {QUERY}\n")
        file_contents_found: list[HostedFileContent] = []
        text_chunks: list[str] = []

        async for update in agent.run_stream(QUERY):
            if isinstance(update, AgentResponseUpdate):
                for content in update.contents:
                    if isinstance(content, TextContent):
                        if content.text:
                            text_chunks.append(content.text)
                        if content.annotations:
                            for annotation in content.annotations:
                                if isinstance(annotation, CitationAnnotation) and annotation.file_id:
                                    print(f"Found streaming CitationAnnotation: file_id={annotation.file_id}")
                    elif isinstance(content, HostedFileContent):
                        file_contents_found.append(content)
                        print(f"Found streaming HostedFileContent: file_id={content.file_id}")
                        if content.additional_properties and "container_id" in content.additional_properties:
                            print(f"  container_id={content.additional_properties['container_id']}")

        print(f"\nAgent response: {''.join(text_chunks)[:200]}...")

        if file_contents_found:
            print(f"SUCCESS: Found {len(file_contents_found)} file reference(s) in streaming")

            # Download the container files
            downloaded_paths = await download_container_files(file_contents_found, agent)

            if downloaded_paths:
                print("\n✓ Downloaded files available at:")
                for path in downloaded_paths:
                    print(f"  - {path.absolute()}")
        else:
            print("WARNING: No file annotations found in streaming response")


async def main() -> None:
    print("AzureAIClient Code Interpreter File Download Sample\n")
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
