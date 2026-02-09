# Copyright (c) Microsoft. All rights reserved.

"""
Agents in Workflows Sample

Demonstrates using AI agents directly as workflow steps. A Writer agent creates
content, and a Reviewer agent evaluates and provides feedback.

What you'll learn:
- Creating agents from AzureOpenAIChatClient
- Using agents as workflow executors
- Building a two-agent sequential workflow

Related samples:
- ../sequential/ — Basic sequential workflows without agents
- ../concurrent/ — Fan-out/fan-in with multiple agents

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
from typing import cast

from agent_framework import AgentResponse, WorkflowBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


# <workflow_definition>
async def main():
    """Build and run a simple two-node agent workflow: Writer then Reviewer."""
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

    workflow = WorkflowBuilder(start_executor=writer_agent).add_edge(writer_agent, reviewer_agent).build()
# </workflow_definition>

    # <running>
    events = await workflow.run("Create a slogan for a new electric SUV that is affordable and fun to drive.")

    outputs = cast(list[AgentResponse], events.get_outputs())
    for output in outputs:
        print(f"{output.messages[0].author_name}: {output.text}\n")

    print("Final state:", events.get_final_state())
    # </running>

    """
    Sample Output:

    writer: "Charge Ahead: Affordable Adventure Awaits!"

    reviewer: - Consider emphasizing both affordability and fun in a more dynamic way.
    - Try using a catchy phrase that includes a play on words.
    - Ensure the slogan is succinct while capturing the essence of the car's unique selling proposition.

    Final state: WorkflowRunState.IDLE
    """


if __name__ == "__main__":
    asyncio.run(main())
