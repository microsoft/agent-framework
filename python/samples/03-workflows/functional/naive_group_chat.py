# Copyright (c) Microsoft. All rights reserved.

"""Naive group chat using the functional workflow API.

A simple round-robin group chat where agents take turns responding.
Because it's just a function, you control the loop, the turn order,
and the termination condition with plain Python — no framework abstractions.

Compare this with the graph-based GroupChat orchestration to see how the
functional API lets you start simple and add complexity only when needed.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT              — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""

import asyncio
import os

from agent_framework import Agent, workflow
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Create agents
# ---------------------------------------------------------------------------

client = AzureOpenAIResponsesClient(
    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
    credential=AzureCliCredential(),
)

expert = Agent(
    name="PythonExpert",
    instructions=(
        "You are a Python expert in a group discussion. "
        "Answer questions about Python and refine your answer based on feedback. "
        "Keep responses concise (2-3 sentences)."
    ),
    client=client,
)

critic = Agent(
    name="Critic",
    instructions=(
        "You are a constructive critic in a group discussion. "
        "Point out edge cases, gotchas, or missing nuances in the previous answer. "
        "If the answer is solid, say so briefly."
    ),
    client=client,
)

summarizer = Agent(
    name="Summarizer",
    instructions=(
        "You are a summarizer in a group discussion. "
        "After the discussion, provide a final concise summary that incorporates "
        "the expert's answer and the critic's feedback. Keep it to 2-3 sentences."
    ),
    client=client,
)

# ---------------------------------------------------------------------------
# A naive group chat is just a loop — no special framework needed
# ---------------------------------------------------------------------------


@workflow
async def group_chat(question: str) -> str:
    """Round-robin group chat: expert answers, critic reviews, summarizer wraps up."""
    participants = [expert, critic, summarizer]
    conversation: list[str] = [f"User: {question}"]

    # Simple round-robin: each agent sees the full conversation so far
    for agent in participants:
        prompt = "\n\n".join(conversation)
        response = (await agent.run(prompt)).text
        conversation.append(f"{agent.name}: {response}")

    return "\n\n".join(conversation)


async def main():
    result = await group_chat.run("What's the difference between a list and a tuple in Python?")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
