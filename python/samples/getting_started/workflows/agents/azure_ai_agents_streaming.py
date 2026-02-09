# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentResponseUpdate, WorkflowBuilder
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
Sample: Azure AI Agents in a Workflow with Streaming

This sample shows how to create Azure AI Agents and use them in a workflow with streaming.

Prerequisites:
- Azure AI Agent Service configured, along with the required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


async def main() -> None:
    async with AzureCliCredential() as cred, AzureAIAgentClient(credential=cred) as client:
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

        events = workflow.run(
            "Create a slogan for a new electric SUV that is affordable and fun to drive.", stream=True
        )
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
