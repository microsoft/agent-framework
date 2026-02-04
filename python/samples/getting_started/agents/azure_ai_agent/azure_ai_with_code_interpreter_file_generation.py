# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import (
    AgentResponseUpdate,
    HostedCodeInterpreterTool,
    HostedFileContent,
    tool,
)
from agent_framework.azure import AzureAIAgentsProvider
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent Code Interpreter File Generation Example

This sample demonstrates using HostedCodeInterpreterTool with AzureAIAgentsProvider
to generate a text file and then retrieve it.

The test flow:
1. Create an agent with code interpreter tool
2. Ask the agent to generate a txt file using Python code
3. Capture the file_id from HostedFileContent in the response
4. Retrieve the file using the agents_client.files API
"""


async def main() -> None:
    """Test file generation and retrieval with code interpreter."""

    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        agent = await provider.create_agent(
            name="CodeInterpreterAgent",
            instructions=(
                "You are a Python code execution assistant. "
                "ALWAYS use the code interpreter tool to execute Python code when asked to create files. "
                "Write actual Python code to create files, do not just describe what you would do."
            ),
            tools=[HostedCodeInterpreterTool()],
        )

        # Be very explicit about wanting code execution and a download link
        query = (
            "Use the code interpreter to execute this Python code and then provide me "
            "with a download link for the generated file:\n"
            "```python\n"
            "with open('/mnt/data/sample.txt', 'w') as f:\n"
            "    f.write('Hello, World! This is a test file.')\n"
            "'/mnt/data/sample.txt'\n"  # Return the path so it becomes downloadable
            "```"
        )
        print(f"User: {query}\n")
        print("=" * 60)

        # Collect file_ids from the response
        file_ids: list[str] = []

        async for chunk in agent.run_stream(query):
            if not isinstance(chunk, AgentResponseUpdate):
                continue

            for content in chunk.contents:
                if content.type == "text":
                    print(content.text, end="", flush=True)
                elif content.type == "hosted_file" and isinstance(content, HostedFileContent):
                    file_ids.append(content.file_id)
                    print(f"\n[File generated: {content.file_id}]")

        print("\n" + "=" * 60)

        # Attempt to retrieve discovered files
        if file_ids:
            print(f"\nAttempting to retrieve {len(file_ids)} file(s):")
            for file_id in file_ids:
                try:
                    file_info = await agents_client.files.get(file_id)
                    print(f"  File {file_id}: Retrieved successfully")
                    print(f"    Filename: {file_info.filename}")
                    print(f"    Purpose: {file_info.purpose}")
                    print(f"    Bytes: {file_info.bytes}")
                except Exception as e:
                    print(f"  File {file_id}: FAILED to retrieve - {e}")
        else:
            print("No file IDs were captured from the response.")

        # List all files to see if any exist
        print("\nListing all files in the agent service:")
        try:
            files_list = await agents_client.files.list()
            count = 0
            for file_info in files_list.data:
                count += 1
                print(f"  - {file_info.id}: {file_info.filename} ({file_info.purpose})")
            if count == 0:
                print("  No files found.")
        except Exception as e:
            print(f"  Failed to list files: {e}")


if __name__ == "__main__":
    asyncio.run(main())
