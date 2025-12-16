# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    CitationAnnotation,
    HostedCodeInterpreterTool,
    HostedFileContent,
    TextContent,
)
from agent_framework._agents import AgentRunResponseUpdate
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI V2 Code Interpreter File Generation Sample

This sample demonstrates how the V2 AzureAIClient handles file annotations
when code interpreter generates text files. It shows both non-streaming
and streaming approaches to verify file ID extraction.
"""

QUERY = (
    "Write a simple Python script that creates a text file called 'sample.txt' containing "
    "'Hello from the code interpreter!' and save it to disk."
)


async def test_non_streaming() -> None:
    """Test non-streaming response - should have annotations on TextContent."""
    print("=== Testing Non-Streaming Response ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="V2CodeInterpreterFileAgent",
            instructions="You are a helpful assistant that can write and execute Python code to create files.",
            tools=HostedCodeInterpreterTool(),
        ) as agent,
    ):
        print(f"User: {QUERY}\n")

        result = await agent.run(QUERY)
        print(f"Agent: {result.text}\n")

        # Check for annotations in the response
        annotations_found: list[str] = []
        # AgentRunResponse has messages property, which contains ChatMessage objects
        for message in result.messages:
            for content in message.contents:
                if isinstance(content, TextContent) and content.annotations:
                    for annotation in content.annotations:
                        if isinstance(annotation, CitationAnnotation) and annotation.file_id:
                            annotations_found.append(annotation.file_id)
                            print(f"Found file annotation: file_id={annotation.file_id}")

        if annotations_found:
            print(f"SUCCESS: Found {len(annotations_found)} file annotation(s)")
        else:
            print("WARNING: No file annotations found in non-streaming response")


async def test_streaming() -> None:
    """Test streaming response - check if file content is captured via HostedFileContent."""
    print("\n=== Testing Streaming Response ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="V2CodeInterpreterFileAgentStreaming",
            instructions="You are a helpful assistant that can write and execute Python code to create files.",
            tools=HostedCodeInterpreterTool(),
        ) as agent,
    ):
        print(f"User: {QUERY}\n")
        annotations_found: list[str] = []
        text_chunks: list[str] = []
        file_ids_found: list[str] = []

        async for update in agent.run_stream(QUERY):
            if isinstance(update, AgentRunResponseUpdate):
                for content in update.contents:
                    if isinstance(content, TextContent):
                        if content.text:
                            text_chunks.append(content.text)
                        if content.annotations:
                            for annotation in content.annotations:
                                if isinstance(annotation, CitationAnnotation) and annotation.file_id:
                                    annotations_found.append(annotation.file_id)
                                    print(f"Found streaming annotation: file_id={annotation.file_id}")
                    elif isinstance(content, HostedFileContent):
                        file_ids_found.append(content.file_id)
                        print(f"Found streaming HostedFileContent: file_id={content.file_id}")

        print(f"\nAgent response: {''.join(text_chunks)[:200]}...")

        if annotations_found or file_ids_found:
            total = len(annotations_found) + len(file_ids_found)
            print(f"SUCCESS: Found {total} file reference(s) in streaming")
        else:
            print("WARNING: No file annotations found in streaming response")


async def main() -> None:
    print("AzureAIClient Code Interpreter File Generation Test\n")
    await test_non_streaming()
    await test_streaming()


if __name__ == "__main__":
    asyncio.run(main())
