# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import tempfile

from agent_framework import ChatAgent, HostedCodeInterpreterTool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from openai import AsyncAzureOpenAI

"""
Azure OpenAI Responses Client with Code Interpreter and Files Example

This sample demonstrates using HostedCodeInterpreterTool with Azure OpenAI Responses
for Python code execution and data analysis with uploaded files.
"""

# Helper functions


async def create_sample_file_and_upload(openai_client: AsyncAzureOpenAI) -> tuple[str, str]:
    """Create a sample CSV file and upload it to Azure OpenAI."""
    csv_data = """name,department,salary,years_experience
Alice Johnson,Engineering,95000,5
Bob Smith,Sales,75000,3
Carol Williams,Engineering,105000,8
David Brown,Marketing,68000,2
Emma Davis,Sales,82000,4
Frank Wilson,Engineering,88000,6
"""

    # Create temporary CSV file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_file:
        temp_file.write(csv_data)
        temp_file_path = temp_file.name

    # Upload file to Azure OpenAI
    print("Uploading file to Azure OpenAI...")
    with open(temp_file_path, "rb") as file:
        uploaded_file = await openai_client.files.create(
            file=file,
            purpose="assistants",  # Required for code interpreter
        )

    print(f"File uploaded with ID: {uploaded_file.id}")
    return temp_file_path, uploaded_file.id


async def cleanup_files(openai_client: AsyncAzureOpenAI, temp_file_path: str, file_id: str) -> None:
    """Clean up both local temporary file and uploaded file."""
    # Clean up: delete the uploaded file
    await openai_client.files.delete(file_id)
    print(f"Cleaned up uploaded file: {file_id}")

    # Clean up temporary local file
    os.unlink(temp_file_path)
    print(f"Cleaned up temporary file: {temp_file_path}")


async def main() -> None:
    print("=== Azure OpenAI Code Interpreter with File Upload ===")

    # Initialize Azure OpenAI client for file operations
    credential = AzureCliCredential()

    async def get_token():
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token

    openai_client = AsyncAzureOpenAI(
        azure_ad_token_provider=get_token,
        api_version="2024-05-01-preview",
    )

    temp_file_path, file_id = await create_sample_file_and_upload(openai_client)

    # Create agent using Azure OpenAI Responses client
    agent = ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=credential),
        instructions="You are a helpful assistant that can analyze data files using Python code.",
        tools=HostedCodeInterpreterTool(inputs=[{"file_id": file_id}]),
    )

    # Test the code interpreter with the uploaded file
    query = "Analyze the employee data in the uploaded CSV file. Calculate average salary by department."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")

    await cleanup_files(openai_client, temp_file_path, file_id)


if __name__ == "__main__":
    asyncio.run(main())
