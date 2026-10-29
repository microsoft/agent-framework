# Copyright (c) Microsoft. All rights reserved.

"""Call two agents from a functional workflow.

One agent writes a poem, and the other reviews it.
"""

import asyncio

from agent_framework import Agent, workflow
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint="https://your-account.services.ai.azure.com/api/projects/your-project",
    model="gpt-6-luna",
    credential=AzureCliCredential(),
)

writer = Agent(
    client=client,
    instructions="Write a four-line poem about the given topic.",
)

reviewer = Agent(
    client=client,
    instructions="Review the poem in one sentence.",
)


@workflow
async def poem_workflow(topic: str) -> str:
    poem = (await writer.run(f"Write a poem about: {topic}")).text
    review = (await reviewer.run(f"Review this poem: {poem}")).text
    return f"Poem:\n{poem}\n\nReview: {review}"


async def main() -> None:
    workflow_instance = poem_workflow.build()
    result = await workflow_instance.run("a cat learning to code")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
