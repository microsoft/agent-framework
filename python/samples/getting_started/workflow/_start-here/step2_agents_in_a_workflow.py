# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentRunEvent, WorkflowBuilder
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Step 2: Agents in a Workflow non-streaming

This sample uses two custom executors. A Writer agent creates or edits content,
then hands the conversation to a Reviewer agent which evaluates and finalizes the result.

Purpose:
Show how to wrap chat agents created by AzureChatClient inside workflow executors. Demonstrate how agents
automatically yield outputs when they complete, removing the need for explicit completion events.
The workflow completes when it becomes idle.

Prerequisites:
- Azure OpenAI configured for AzureChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming or non streaming runs.
"""


async def main():
    """Build and run a simple two node agent workflow: Writer then Reviewer."""
    # Create the Azure chat client. AzureCliCredential uses your current az login.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    writer_agent = chat_client.create_agent(
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
        name="writer",
    )

    reviewer_agent = chat_client.create_agent(
        instructions=(
            "You are an excellent content reviewer."
            "Provide actionable feedback to the writer about the provided content."
            "Provide the feedback in the most concise manner possible."
        ),
        name="reviewer",
    )

    # Build the workflow using the fluent builder.
    # Set the start node and connect an edge from writer to reviewer.
    workflow = WorkflowBuilder().set_start_executor(writer_agent).add_edge(writer_agent, reviewer_agent).build()

    # Run the workflow with the user's initial message.
    # For foundational clarity, use run (non streaming) and print the terminal event.
    events = await workflow.run("Create a slogan for a new electric SUV that is affordable and fun to drive.")
    # Print agent run events and final outputs
    for event in events:
        if isinstance(event, AgentRunEvent):
            print(f"{event.executor_id}: {event.data}")

    print(f"{'=' * 60}\nWorkflow Outputs: {events.get_outputs()}")
    # Summarize the final run state (e.g., COMPLETED)
    print("Final state:", events.get_final_state())

    """
    Sample Output:

    writer: "Charge Up Your Adventure—Affordable Fun, Electrified!"
    reviewer: Slogan: "Plug Into Fun—Affordable Adventure, Electrified."

    **Feedback:**
    - Clear focus on affordability and enjoyment.
    - "Plug into fun" connects emotionally and highlights electric nature.
    - Consider specifying "SUV" for clarity in some uses.
    - Strong, upbeat tone suitable for marketing.
    ============================================================
    Workflow Outputs: ['Slogan: "Plug Into Fun—Affordable Adventure, Electrified."

    **Feedback:**
    - Clear focus on affordability and enjoyment.
    - "Plug into fun" connects emotionally and highlights electric nature.
    - Consider specifying "SUV" for clarity in some uses.
    - Strong, upbeat tone suitable for marketing.']
    """


if __name__ == "__main__":
    asyncio.run(main())
