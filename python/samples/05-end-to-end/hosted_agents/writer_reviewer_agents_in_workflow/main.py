# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import WorkflowBuilder
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential  # pyright: ignore[reportUnknownVariableType]
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure these for your Foundry project
PROJECT_ENDPOINT = os.getenv(
    "PROJECT_ENDPOINT"
)  # e.g., "https://<project>.services.ai.azure.com/api/projects/<project-name>"
MODEL_DEPLOYMENT_NAME = os.getenv(
    "MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"
)  # Your model deployment name e.g., "gpt-4.1-mini"


def main():
    """
    The writer and reviewer multi-agent workflow.

    Environment variables required:
    - PROJECT_ENDPOINT: Your Microsoft Foundry project endpoint
    - MODEL_DEPLOYMENT_NAME: Your Microsoft Foundry model deployment name
    """
    client = AzureOpenAIResponsesClient(
        project_endpoint=PROJECT_ENDPOINT,
        deployment_name=MODEL_DEPLOYMENT_NAME,
        credential=DefaultAzureCredential(),
    )
    writer = client.as_agent(
        name="Writer",
        instructions="You are an excellent content writer. You create new content and edit contents based on the feedback.",
    )
    reviewer = client.as_agent(
        name="Reviewer",
        instructions="You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content in the most concise manner possible.",
    )

    # Build the workflow and convert to agent
    workflow = WorkflowBuilder(start_executor=writer).add_edge(writer, reviewer).build()
    workflow_agent = workflow.as_agent()

    # Run the agent as a hosted agent
    from_agent_framework(workflow_agent).run()


if __name__ == "__main__":
    main()
