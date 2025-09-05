# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
)
from agent_framework_workflow import AgentRunEvent
from azure.identity import AzureCliCredential

"""
Sample: Agents in a Workflow (Seamless AgentExecutor Chaining)

Purpose:
This sample demonstrates how to connect multiple AgentExecutors together
so that the output of one agent flows directly into the next agent in the workflow.
Specifically, it chains a "writer" agent (which generates content) to a "reviewer"
agent (which evaluates and provides feedback on that content).
The key concept is that an AgentExecutor can accept either raw string inputs
or prior AgentExecutorResponse objects, which enables automatic chaining.

Prerequisites:
- Azure AI or Azure OpenAI resource configured and accessible for AzureChatClient.
- Authentication configured via azure-identity. Run `az login` locally to enable AzureCliCredential.
- Familiarity with WorkflowBuilder and AgentExecutor from the agent_framework library.
- (Optional) Understanding of WorkflowCompletedEvent and AgentRunEvent for interpreting workflow outputs.
"""


async def main():
    """Build and run the agent-to-agent workflow with direct chaining."""
    # Create a chat client that authenticates using Azure CLI credentials.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Define the "writer" agent, responsible for generating and editing content.
    writer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        ),
        id="writer",
    )

    # Define the "reviewer" agent, responsible for providing structured feedback.
    reviewer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content reviewer. You must review the content and provide feedback to the writer."
            ),
        ),
        id="reviewer",
    )

    # Construct a workflow:
    # - Start execution with the writer
    # - Add an edge so that writer's output automatically feeds into reviewer
    workflow = WorkflowBuilder().set_start_executor(writer).add_edge(writer, reviewer).build()

    # Run the workflow in streaming mode.
    # Streaming yields intermediate AgentRunEvent objects as agents generate output,
    # followed by a WorkflowCompletedEvent once the workflow finishes.
    async for event in workflow.run_stream(
        "Create a slogan for a new electric SUV that is affordable and fun to drive."
    ):
        if isinstance(event, AgentRunEvent):
            # Print each intermediate run event for visibility into the agent execution process.
            print(f"AgentRunEvent: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            # Print the final result when the workflow has completed.
            print(f"{'*' * 60}\nCompletion Event:\n\n{event}")


if __name__ == "__main__":
    # Run the async main function when the script is executed directly.
    asyncio.run(main())
