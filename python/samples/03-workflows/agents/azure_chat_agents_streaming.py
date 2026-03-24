# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, AgentResponseUpdate, WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: AzureOpenAI Chat Agents in a Workflow with Streaming

This sample shows how to create AzureOpenAI Chat Agents and use them in a workflow with streaming.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI configured for FoundryChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


async def main():
    """Build and run a simple two node agent workflow: Writer then Reviewer."""
    # Create the agents
    _writer_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    writer_agent = Agent(
        client=_writer_client,
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
        name="writer",
    )

    _reviewer_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    reviewer_agent = Agent(
        client=_reviewer_client,
        instructions=(
            "You are an excellent content reviewer."
            "Provide actionable feedback to the writer about the provided content."
            "Provide the feedback in the most concise manner possible."
        ),
        name="reviewer",
    )

    # Build the workflow using the fluent builder.
    # Set the start node and connect an edge from writer to reviewer.
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
