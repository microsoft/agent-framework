# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from contextlib import asynccontextmanager

from agent_framework import Agent, WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure these for your Foundry project
# Read the explicit variables present in the .env file
PROJECT_ENDPOINT = os.getenv(
    "PROJECT_ENDPOINT"
)  # e.g., "https://<project>.services.ai.azure.com/api/projects/<project-name>"
MODEL_DEPLOYMENT_NAME = os.getenv(
    "MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"
)  # Your model deployment name e.g., "gpt-4.1-mini"


def get_credential():
    """Will use Managed Identity when running in Azure, otherwise falls back to Azure CLI Credential."""
    return ManagedIdentityCredential() if os.getenv("MSI_ENDPOINT") else AzureCliCredential()


@asynccontextmanager
async def create_agents():
    async with get_credential() as credential:
        client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=MODEL_DEPLOYMENT_NAME,
            credential=credential,
        )
        writer = Agent(
            client=client,
            name="Writer",
            instructions="You are an excellent content writer. You create new content and edit contents based on the feedback.",
        )
        reviewer = Agent(
            client=client,
            name="Reviewer",
            instructions="You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content in the most concise manner possible.",
        )
        yield writer, reviewer


def create_workflow(writer, reviewer):
    workflow = WorkflowBuilder(start_executor=writer).add_edge(writer, reviewer).build()
    return Agent(
        client=workflow,
    )


async def main() -> None:
    """
    The writer and reviewer multi-agent workflow.

    Environment variables required:
    - PROJECT_ENDPOINT: Your Microsoft Foundry project endpoint
    - MODEL_DEPLOYMENT_NAME: Your Microsoft Foundry model deployment name
    """

    async with create_agents() as (writer, reviewer):
        agent = create_workflow(writer, reviewer)
        await from_agent_framework(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
