# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import os
from pathlib import Path

from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        AzureAIProjectAgentProvider(project_client=project_client) as provider,
    ):
        openai_client = project_client.get_openai_client()

        try:
            # 1. Upload file and create vector store via OpenAI client
            pdf_file_path = Path(__file__).parents[3] / "shared" / "resources" / "employees.pdf"
            print(f"Uploading file from: {pdf_file_path}")

            vector_store = await openai_client.vector_stores.create(name="my_vectorstore")
            print(f"Created vector store, vector store ID: {vector_store.id}")

            with open(pdf_file_path, "rb") as f:
                file = await openai_client.vector_stores.files.upload_and_poll(
                    vector_store_id=vector_store.id,
                    file=f,
                )
            print(f"Uploaded file, file ID: {file.id}")

            # 2. Create a file search tool
            client = AzureAIClient(project_client=project_client)
            file_search_tool = client.get_file_search_tool(vector_store_ids=[vector_store.id])

            # 3. Create an agent with file search capabilities using the provider
            agent = await provider.create_agent(
                name="EmployeeSearchAgent",
                instructions=(
                    "You are a helpful assistant that can search through uploaded employee files "
                    "to answer questions about employees."
                ),
                tools=[file_search_tool],
            )

            # 4. Simulate conversation with the agent
            for user_input in USER_INPUTS:
                print(f"# User: '{user_input}'")
                response = await agent.run(user_input)
                print(f"# Agent: {response.text}")
        finally:
            # 5. Cleanup: Delete the vector store (also deletes associated files)
            with contextlib.suppress(Exception):
                await openai_client.vector_stores.delete(vector_store.id)


if __name__ == "__main__":
    asyncio.run(main())
