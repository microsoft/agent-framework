# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import (
    AgentRunResponse,
    ChatMessage,
    ChatResponseUpdate,
    HostedCodeInterpreterTool,
    HostedFileContent,
    Role,
    TextContent,
)
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agents.models import (
    FilePurpose,
    RunStepDeltaCodeInterpreterDetailItemObject,
)
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.identity.aio import AzureCliCredential


def print_code_interpreter_inputs(response: AgentRunResponse) -> None:
    """Helper method to access code interpreter data."""

    print("\nCode Interpreter Inputs during the run:")
    if response.raw_representation is None:
        return
    for chunk in response.raw_representation:
        if isinstance(chunk, ChatResponseUpdate) and isinstance(
            chunk.raw_representation, RunStepDeltaCodeInterpreterDetailItemObject
        ):
            print(chunk.raw_representation.input, end="")
    print("\n")


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with an uploaded file."""
    print("=== Azure AI Agent with Code Interpreter and File Upload Example ===")

    # Get the path to the sample CSV file
    asset_file_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "assets", "synthetic_500_quarterly_results.csv")
    )

    # First, upload the file using AIProjectClient
    project_client = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )

    with project_client:
        agents_client = project_client.agents

        # Upload a file and wait for it to be processed
        file = agents_client.files.upload_and_poll(file_path=asset_file_path, purpose=FilePurpose.AGENTS)
        print(f"Uploaded file, file ID: {file.id}")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential) as chat_client,
    ):
        # Create an agent with code interpreter tool
        agent = chat_client.create_agent(
            name="DataAnalysisAgent",
            instructions="You are a helpful assistant that can analyze data files and execute Python code to provide insights.",
            tools=HostedCodeInterpreterTool(),
        )

        # Create a chat message with the uploaded file as HostedFileContent
        message = ChatMessage(
            role=Role.USER,
            contents=[
                TextContent(text="Analyze the quarterly results data in the uploaded csv file. Calculate the total revenue per company across all quarters and create a simple visualization showing the revenue trends."),
                HostedFileContent(file_id=file.id),
            ],
        )

        print(f"User: Analyze the quarterly results data in the uploaded file...")
        response = await AgentRunResponse.from_agent_response_generator(agent.run_stream(message))
        print(f"Agent: {response}")

        # To review the code interpreter outputs, you can access them from the response raw_representations
        print_code_interpreter_inputs(response)


if __name__ == "__main__":
    asyncio.run(main())
