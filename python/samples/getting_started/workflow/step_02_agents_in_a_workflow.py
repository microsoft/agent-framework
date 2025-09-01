# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentRunEvent,
    WorkflowBuilder,
    WorkflowCompletedEvent,
)
from azure.identity import AzureCliCredential

"""
Agents In A Workflow

What it does:
- Wraps two Azure agents in `AgentExecutor`s (writer -> reviewer) and streams their runs.
- Demonstrates building and running a simple agent-to-agent pipeline.

Prerequisites:
- Azure AI/ Azure OpenAI configured for `AzureChatClient`.
- Authentication via `azure-identity` — this sample uses `AzureCliCredential()` (run `az login`).
"""


async def main():
    """Main function to run the workflow."""
    # Step 1: Create the executors.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    writer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        ),
        id="writer",
    )
    reviewer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content reviewer. You review the content and provide feedback to the writer."
            ),
        ),
        id="reviewer",
    )

    # Step 2: Build the workflow with the defined edges.
    workflow = WorkflowBuilder().set_start_executor(writer).add_edge(writer, reviewer).build()

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    async for event in workflow.run_streaming(
        "Create a slogan for a new electric SUV that is affordable and fun to drive."
    ):
        if isinstance(event, AgentRunEvent):
            print(f"{event}")

        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
