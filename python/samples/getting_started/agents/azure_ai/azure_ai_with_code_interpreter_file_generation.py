# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentResponseUpdate,
    HostedCodeInterpreterTool,
    tool,
)
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI V2 Code Interpreter File Generation Sample

This sample demonstrates how the AzureAIProjectAgentProvider handles file annotations
when code interpreter generates text files. It shows both non-streaming
and streaming approaches to verify file ID extraction.
"""

QUERY = (
    "Write a simple Python script that creates a text file called 'sample.txt' containing "
    "'Hello from the code interpreter!' and save it to disk."
)


async def non_streaming_example() -> None:
    """Example of extracting file annotations from non-streaming response."""
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
        annotations_found: list[str] = []
        # AgentResponse has messages property, which contains ChatMessage objects
        for message in result.messages:
            for content in message.contents:
                if content.type == "text" and content.annotations:
                    for annotation in content.annotations:
                        if annotation.file_id:
                            annotations_found.append(annotation.file_id)
                            print(f"Found file annotation: file_id={annotation.file_id}")

        if annotations_found:
            print(f"SUCCESS: Found {len(annotations_found)} file annotation(s)")
        else:
            print("WARNING: No file annotations found in non-streaming response")


async def streaming_example() -> None:
    """Example of extracting file annotations from streaming response."""
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
        annotations_found: list[str] = []
        text_chunks: list[str] = []
        file_ids_found: list[str] = []

        async for update in agent.run_stream(QUERY):
            if isinstance(update, AgentResponseUpdate):
                for content in update.contents:
                    if content.type == "text":
                        if content.text:
                            text_chunks.append(content.text)
                        if content.annotations:
                            for annotation in content.annotations:
                                if annotation.file_id:
                                    annotations_found.append(annotation.file_id)
                                    print(f"Found streaming annotation: file_id={annotation.file_id}")
                    elif content.type == "hosted_file":
                        file_ids_found.append(content.file_id)
                        print(f"Found streaming HostedFileContent: file_id={content.file_id}")

        print(f"\nAgent response: {''.join(text_chunks)[:200]}...")

        if annotations_found or file_ids_found:
            total = len(annotations_found) + len(file_ids_found)
            print(f"SUCCESS: Found {total} file reference(s) in streaming")
        else:
            print("WARNING: No file annotations found in streaming response")


async def main() -> None:
    print("AzureAIClient Code Interpreter File Generation Sample\n")
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
