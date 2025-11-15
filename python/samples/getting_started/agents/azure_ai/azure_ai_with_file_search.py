# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import ChatAgent, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIClient
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import FileInfo, VectorStore
from azure.identity.aio import AzureCliCredential

"""
The following sample demonstrates how to create a simple, Azure AI agent that
uses a file search tool to answer user questions.
"""


# Simulate a conversation with the agent
USER_INPUTS = [
    "Who is the youngest employee?",
    "Who works in sales?",
    "I have a customer request, who can help me?",
]


async def main() -> None:
    """Main function demonstrating Azure AI agent with file search capabilities."""
    file: FileInfo | None = None
    vector_store: VectorStore | None = None

    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIClient(async_credential=credential) as client,
    ):
        try:
            # 1. Upload file and create vector store
            pdf_file_path = Path(__file__).parent.parent / "resources" / "employees.pdf"
            print(f"Uploading file from: {pdf_file_path}")

            file = await agents_client.files.upload_and_poll(file_path=str(pdf_file_path), purpose="assistants")
            print(f"Uploaded file, file ID: {file.id}")

            vector_store = await agents_client.vector_stores.create_and_poll(file_ids=[file.id], name="my_vectorstore")
            print(f"Created vector store, vector store ID: {vector_store.id}")

            # 2. Create file search tool with uploaded resources
            file_search_tool = HostedFileSearchTool(inputs=[HostedVectorStoreContent(vector_store_id=vector_store.id)])

            # 3. Create an agent with file search capabilities
            # The tool_resources are automatically extracted from HostedFileSearchTool
            async with ChatAgent(
                chat_client=client,
                name="EmployeeSearchAgent",
                instructions=(
                    "You are a helpful assistant that can search through uploaded employee files "
                    "to answer questions about employees."
                ),
                tools=file_search_tool,
            ) as agent:
                # 4. Simulate conversation with the agent
                for user_input in USER_INPUTS:
                    print(f"# User: '{user_input}'")
                    response = await agent.run(user_input)
                    print(f"# Agent: {response.text}")
        finally:
            # 5. Cleanup: Delete the vector store and file in case of earlier failure to prevent orphaned resources.
            if vector_store:
                await agents_client.vector_stores.delete(vector_store.id)
            if file:
                await agents_client.files.delete(file.id)


if __name__ == "__main__":
    asyncio.run(main())
