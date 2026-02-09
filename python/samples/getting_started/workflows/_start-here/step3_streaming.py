# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentResponseUpdate, ChatMessage, WorkflowBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Step 3: Agents in a workflow with streaming

This sample creates two agents: a Writer agent creates or edits content, and a Reviewer agent which
evaluates and provides feedback.

Purpose:
Show how to create agents from AzureOpenAIChatClient and use them directly in a workflow. Demonstrate
how agents can be used in a workflow.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""


async def main():
    """Build the two node workflow and run it with streaming to observe events."""
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

    # Track the last author to format streaming output.
    last_author: str | None = None

    # Run the workflow with the user's initial message and stream events as they occur.
    async for event in workflow.run(
        ChatMessage("user", ["Create a slogan for a new electric SUV that is affordable and fun to drive."]),
        stream=True,
    ):
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

    """
    writer: "Electrify Your Journey: Affordable Fun Awaits!"
    reviewer: Feedback:

    1. **Clarity**: Consider simplifying the message. "Affordable Fun" could be more direct.
    2. **Emotional Appeal**: Emphasize the thrill of driving more. Try using words that evoke excitement.
    3. **Unique Selling Proposition**: Highlight the electric aspect more boldly.

    Example revision: "Charge Your Adventure: Affordable SUVs for Fun-Loving Drivers!"
    """


if __name__ == "__main__":
    asyncio.run(main())
