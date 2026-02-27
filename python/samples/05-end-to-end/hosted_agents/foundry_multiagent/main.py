import asyncio
import os
import sys
from contextlib import asynccontextmanager

from agent_framework import WorkflowBuilder
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure these for your Foundry project
# Read the explicit variables present in the .env file
PROJECT_ENDPOINT = os.getenv(
    "PROJECT_ENDPOINT"
)  # e.g., "https://<project>.services.ai.azure.com"
MODEL_DEPLOYMENT_NAME = os.getenv(
    "MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"
)  # Your model deployment name e.g., "gpt-4.1-mini"


def get_credential():
    """Will use Managed Identity when running in Azure, otherwise falls back to DefaultAzureCredential."""
    return (
        ManagedIdentityCredential()
        if os.getenv("MSI_ENDPOINT")
        else DefaultAzureCredential()
    )


@asynccontextmanager
async def create_agents():
    async with (
        get_credential() as credential,
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT_NAME,
            credential=credential,
        ) as writer_client,
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT_NAME,
            credential=credential,
        ) as reviewer_client,
    ):
        writer = writer_client.create_agent(
            name="Writer",
            instructions="You are an excellent content writer. You create new content and edit contents based on the feedback.",
        )
        reviewer = reviewer_client.create_agent(
            name="Reviewer",
            instructions="You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content in the most concise manner possible.",
        )
        yield writer, reviewer


def create_workflow(writer, reviewer):
    workflow = (
        WorkflowBuilder(name="Writer-Reviewer")
        .register_agent(lambda: writer, name="Writer", output_response=True)
        .register_agent(lambda: reviewer, name="Reviewer", output_response=True)
        .set_start_executor("Writer")
        .add_edge("Writer", "Reviewer")
        .build()
    )
    return workflow.as_agent()


async def main() -> None:
    """
    The writer and reviewer multi-agent workflow.

    Usage:
        python main.py          # Run in server mode

    Environment variables required:
    - PROJECT_ENDPOINT: Your Microsoft Foundry project endpoint
    - MODEL_DEPLOYMENT_NAME: Your Microsoft Foundry model deployment name
    """

    async with create_agents() as (writer, reviewer):
        agent = create_workflow(writer, reviewer)

        # Check if running in CLI mode (default is server mode)
        if "--cli" in sys.argv:
            # CLI mode for testing
            print("Running workflow agent in CLI mode...")

            # Test with a sample query
            user_message = "Create a slogan for a new electric SUV that is affordable and fun to drive."
            print(f"\nUser: {user_message}\n")

            response = await agent.run(user_message)
            for msg in response.messages:
                if msg.text:
                    print(f"{msg.author_name}: {msg.text}\n")
        else:
            # Server mode (default)
            print("Starting workflow agent HTTP server...")
            from azure.ai.agentserver.agentframework import from_agent_framework

        await from_agent_framework(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
