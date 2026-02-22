# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import AgentResponseUpdate, WorkflowBuilder
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Azure AI Agents in a Workflow with Streaming

This sample shows how to create agents backed by Azure OpenAI Responses and use them in a workflow with streaming.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- AZURE_AI_MODEL_DEPLOYMENT_NAME must be set to your Azure OpenAI model deployment name.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


async def main() -> None:
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    # Create two agents: a Writer and a Reviewer.
    writer_agent = client.as_agent(
        name="Writer",
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
    )

    reviewer_agent = client.as_agent(
        name="Reviewer",
        instructions=(
            "You are an excellent content reviewer. "
            "Provide actionable feedback to the writer about the provided content. "
            "Provide the feedback in the most concise manner possible."
        ),
    )

    # Build the workflow by adding agents directly as edges.
    # Agents adapt to workflow mode: run(stream=True) for incremental updates, run() for complete responses.
    workflow = WorkflowBuilder(start_executor=writer_agent).add_edge(writer_agent, reviewer_agent).build()

    # Track the last author to format streaming output.
    last_author: str | None = None

    events = workflow.run("Create a slogan for a new electric SUV that is affordable and fun to drive.", stream=True)
    async for event in events:
        # The outputs of the workflow are whatever the agents produce. So the events are expected to
        # contain `AgentResponseUpdate` from the agents in the workflow.
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            update = event.data
            author = update.author_name
            if author != last_author:
                if last_author is not None:
                    print()  # Newline between different authors
                print(f"{author}: {update.text}", end="", flush=True)
                last_author = author
            else:
                print(update.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
