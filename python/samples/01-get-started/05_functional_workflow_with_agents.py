# Copyright (c) Microsoft. All rights reserved.

"""
Functional Workflow with Agents — Call agents inside @workflow

This sample shows how to call agents inside a functional workflow.
Agent calls are just regular async function calls — no special wrappers needed.
"""

import asyncio

from agent_framework import Agent, workflow
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

# <create_agents>
client = FoundryChatClient(credential=AzureCliCredential())

writer = Agent(
    name="WriterAgent",
    instructions="Write a short poem (4 lines max) about the given topic.",
    client=client,
)

reviewer = Agent(
    name="ReviewerAgent",
    instructions="Review the given poem in one sentence. Is it good?",
    client=client,
)
# </create_agents>


# <create_workflow>
@workflow
async def poem_workflow(topic: str) -> str:
    """Write a poem, then review it."""
    poem = (await writer.run(f"Write a poem about: {topic}")).text
    review = (await reviewer.run(f"Review this poem: {poem}")).text
    return f"Poem:\n{poem}\n\nReview: {review}"


# </create_workflow>


async def main() -> None:
    result = await poem_workflow.run("a cat learning to code")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
