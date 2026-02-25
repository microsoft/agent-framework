# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import os
from pathlib import Path

from agent_framework import Content, Message
from agent_framework.azure import AzureAIAgentClient, AzureAIAgentsProvider
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import FilePurpose
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent Code Interpreter with Per-Message File Attachment

This sample demonstrates how to upload a CSV file and attach it to a specific
message using Content.from_hosted_file(), rather than to the agent/thread.

This uses the MessageAttachment pattern from the Azure AI Agents SDK, which
scopes the file to a single message — making it safe for multi-user scenarios
where the same agent definition is shared across users.

The flow:
1. Create an agent with code interpreter tool (no file_ids)
2. Upload a CSV file via the agents client
3. Attach the file per-message using Content.from_hosted_file()
4. The framework converts this to a MessageAttachment automatically
5. Clean up the uploaded file
"""

# Questions to ask the agent about the CSV data
USER_INPUTS = [
    "How many employees are in the dataset?",
    "What is the average salary by department?",
    "Who has the most years of experience?",
]


async def main() -> None:
    """Example showing per-message file attachment with code interpreter."""
    print("=== Azure AI Code Interpreter with Per-Message File Attachment ===\n")

    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        # 1. Upload the CSV file
        csv_file_path = Path(__file__).parents[3] / "shared" / "resources" / "employees.csv"
        print(f"Uploading file from: {csv_file_path}")

        uploaded = await agents_client.files.upload_and_poll(
            file_path=str(csv_file_path),
            purpose=FilePurpose.AGENTS,
        )
        print(f"Uploaded file, file ID: {uploaded.id}\n")

        try:
            # 2. Create a code interpreter tool (no file_ids — files attached per-message)
            client = AzureAIAgentClient(credential=credential)
            code_interpreter_tool = client.get_code_interpreter_tool()

            # 3. Create an agent with code interpreter
            agent = await provider.create_agent(
                name="DataAnalysisAgent",
                instructions=(
                    "You are a data analyst assistant. Use the code interpreter to read "
                    "and analyze the attached CSV file. Always show your work by writing "
                    "Python code to answer questions about the data."
                ),
                tools=[code_interpreter_tool],
            )

            # 4. Ask questions — file is attached per-message via Content.from_hosted_file()
            file_content = Content.from_hosted_file(file_id=uploaded.id)
            for user_input in USER_INPUTS:
                print(f"# User: '{user_input}'")
                message = Message(role="user", contents=[user_input, file_content])
                response = await agent.run(message)
                print(f"# Agent: {response.text}\n")

        finally:
            # 5. Cleanup: Delete the uploaded file
            with contextlib.suppress(Exception):
                await agents_client.files.delete(uploaded.id)
                print("Cleaned up uploaded file.")


if __name__ == "__main__":
    asyncio.run(main())
