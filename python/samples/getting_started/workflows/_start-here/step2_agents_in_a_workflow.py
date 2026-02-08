# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import cast

from agent_framework import AgentResponse, WorkflowBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Step 2: Agents in a Workflow non-streaming

This sample creates two agents: a Writer agent creates or edits content, and a Reviewer agent which
evaluates and provides feedback.

Purpose:
Show how to create agents from AzureOpenAIChatClient and use them directly in a workflow. Demonstrate
how agents can be used in a workflow.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming or non-streaming runs.
"""


async def main():
    """Build and run a simple two node agent workflow: Writer then Reviewer."""
    # Create the Azure chat client. AzureCliCredential uses your current az login.
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    writer_agent = chat_client.as_agent(
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
        name="writer",
    )

    reviewer_agent = chat_client.as_agent(
        instructions=(
            "You are an excellent content reviewer."
            "Provide actionable feedback to the writer about the provided content."
            "Provide the feedback in the most concise manner possible."
        ),
        name="reviewer",
    )

    # Build the workflow using the fluent builder.
    # Set the start node via constructor and connect an edge from writer to reviewer.
    workflow = WorkflowBuilder(start_executor=writer_agent).add_edge(writer_agent, reviewer_agent).build()

    # Run the workflow with the user's initial message.
    # For foundational clarity, use run (non streaming) and print the terminal event.
    events = await workflow.run("Create a slogan for a new electric SUV that is affordable and fun to drive.")

    outputs = events.get_outputs()
    # The outputs of the workflow are whatever the agents produce. So the outputs are expected to be a list
    # of `AgentResponse` from the agents in the workflow.
    outputs = cast(list[AgentResponse], outputs)
    for output in outputs:
        print(f"{output.messages[0].author_name}: {output.text}\n")

    # Summarize the final run state (e.g., COMPLETED)
    print("Final state:", events.get_final_state())

    """
    writer: "Charge Ahead: Affordable Adventure Awaits!"

    reviewer: - Consider emphasizing both affordability and fun in a more dynamic way.
    - Try using a catchy phrase that includes a play on words, like “Electrify Your Drive: Fun Meets Affordability!”
    - Ensure the slogan is succinct while capturing the essence of the car's unique selling proposition.

    Final state: WorkflowRunState.IDLE
    """


if __name__ == "__main__":
    asyncio.run(main())
