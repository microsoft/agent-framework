# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureChatClient
from agent_framework.workflow import AgentRunUpdateEvent, WorkflowBuilder, WorkflowCompletedEvent
from azure.identity import AzureCliCredential

"""
Sample: Agents in a workflow with streaming

A Writer agent generates content, then a Reviewer agent critiques it.
The workflow uses streaming so you can observe incremental AgentRunUpdateEvent chunks as each agent produces tokens.

Purpose:
Show how to wire chat agents directly into a WorkflowBuilder pipeline where agents are auto wrapped as executors.

Demonstrate:
- Automatic streaming of agent deltas via AgentRunUpdateEvent.
- A simple console aggregator that groups updates by executor id and prints them as they arrive.
- A final WorkflowCompletedEvent that contains the reviewer outcome after both agents finish.

Prerequisites:
- Azure OpenAI configured for AzureChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


async def main():
    """Build and run a simple two node agent workflow: Writer then Reviewer."""
    # Create the Azure chat client. AzureCliCredential uses your current az login.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Define two domain specific chat agents. The builder will wrap these as executors.
    writer_agent = chat_client.create_agent(
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
        name="writer_agent",
    )

    reviewer_agent = chat_client.create_agent(
        instructions=(
            "You are an excellent content reviewer."
            "Provide actionable feedback to the writer about the provided content."
            "Provide the feedback in the most concise manner possible."
        ),
        name="reviewer_agent",
    )

    # Build the workflow using the fluent builder.
    # Set the start node and connect an edge from writer to reviewer.
    workflow = WorkflowBuilder().set_start_executor(writer_agent).add_edge(writer_agent, reviewer_agent).build()

    # Stream events from the workflow. We aggregate partial token updates per executor for readable output.
    completed_event: WorkflowCompletedEvent | None = None
    last_executor_id = None

    async for event in workflow.run_stream(
        "Create a slogan for a new electric SUV that is affordable and fun to drive."
    ):
        if isinstance(event, AgentRunUpdateEvent):
            # AgentRunUpdateEvent contains incremental text deltas from the underlying agent.
            # Print a prefix when the executor changes, then append updates on the same line.
            eid = event.executor_id
            if eid != last_executor_id:  # type: ignore[reportUnnecessaryComparison]
                if last_executor_id is not None:
                    print()
                print(f"{eid}:", end=" ", flush=True)
                last_executor_id = eid
            print(event.data, end="", flush=True)
        elif isinstance(event, WorkflowCompletedEvent):
            # Terminal event with the final reviewer output.
            completed_event = event

    # Print the final consolidated reviewer result.
    if completed_event:
        print("\n===== Final Output =====")
        print(completed_event.data)

    """
    Sample Output:

    writer_agent: Charge Up Your Journey. Fun, Affordable, Electric.
    reviewer_agent: Clear message, but consider highlighting SUV specific benefits (space, versatility) for stronger
        impact. Try more vivid language to evoke excitement. Example: "Big on Space. Big on Fun. Electric for Everyone."
    ===== Final Output =====
    Clear message, but consider highlighting SUV specific benefits (space, versatility) for stronger impact. Try more
        vivid language to evoke excitement. Example: "Big on Space. Big on Fun. Electric for Everyone."
    """


if __name__ == "__main__":
    asyncio.run(main())
