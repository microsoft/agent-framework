# Copyright (c) Microsoft. All rights reserved.

"""
Functional Workflow with Agents — Call agents inside @workflow

This sample shows how to call agents inside a functional workflow.
Agent calls are just regular async function calls — no special wrappers needed.

Use @step on expensive operations (like agent calls) so their results are
cached and won't re-execute on HITL resume or crash recovery.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT              — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""

import asyncio
import os

from agent_framework import Agent, step, workflow
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

# <create_agents>
client = AzureOpenAIResponsesClient(
    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
    credential=AzureCliCredential(),
)

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


# @step caches the result — the agent call won't re-execute on resume.
@step
async def write_poem(topic: str) -> str:
    return (await writer.run(f"Write a poem about: {topic}")).text


# <create_workflow>
@workflow
async def poem_workflow(topic: str) -> str:
    """Write a poem, then review it."""
    poem = await write_poem(topic)
    review = (await reviewer.run(f"Review this poem: {poem}")).text
    return f"Poem:\n{poem}\n\nReview: {review}"
# </create_workflow>


async def main() -> None:
    result = await poem_workflow.run("a cat learning to code")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
