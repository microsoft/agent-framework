# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentRunUpdateEvent, ChatAgent, WorkflowBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
Sample: Agents in a workflow with streaming

A Writer agent generates content, then a Reviewer agent critiques it.
The workflow uses streaming so you can observe incremental AgentRunUpdateEvent chunks as each agent produces tokens.

Purpose:
Show how to wire chat agents into a WorkflowBuilder pipeline by adding agents directly as edges.

Demonstrate:
- Automatic streaming of agent deltas via AgentRunUpdateEvent when using run_stream().
- Agents adapt to workflow mode: run_stream() emits incremental updates, run() emits complete responses.

Prerequisites:
- Azure AI Agent Service configured, along with the required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


def create_writer_agent(client: AzureAIAgentClient) -> ChatAgent:
    return client.as_agent(
        name="Writer",
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
    )


def create_reviewer_agent(client: AzureAIAgentClient) -> ChatAgent:
    return client.as_agent(
        name="Reviewer",
        instructions=(
            "You are an excellent content reviewer. "
            "Provide actionable feedback to the writer about the provided content. "
            "Provide the feedback in the most concise manner possible."
        ),
    )


async def main() -> None:
    async with AzureCliCredential() as cred, AzureAIAgentClient(async_credential=cred) as client:
        # Build the workflow by adding agents directly as edges.
        # Agents adapt to workflow mode: run_stream() for incremental updates, run() for complete responses.
        workflow = (
            WorkflowBuilder()
            .register_agent(lambda: create_writer_agent(client), name="writer")
            .register_agent(lambda: create_reviewer_agent(client), name="reviewer", output_response=True)
            .set_start_executor("writer")
            .add_edge("writer", "reviewer")
            .build()
        )

        last_executor_id: str | None = None

        events = workflow.run_stream("Create a slogan for a new electric SUV that is affordable and fun to drive.")
        async for event in events:
            if isinstance(event, AgentRunUpdateEvent):
                eid = event.executor_id
                if eid != last_executor_id:
                    if last_executor_id is not None:
                        print()
                    print(f"{eid}:", end=" ", flush=True)
                    last_executor_id = eid
                print(event.data, end="", flush=True)
            elif isinstance(event, WorkflowOutputEvent):
                print("\n===== Final output =====")
                print(event.data)


if __name__ == "__main__":
    asyncio.run(main())
