# Copyright (c) Microsoft. All rights reserved.

"""Naive group chat using the functional workflow API.

A simple round-robin group chat where agents take turns responding.
Because it's just a function, you control the loop, the turn order,
and the termination condition with plain Python — no framework abstractions.

Compare this with the graph-based GroupChat orchestration to see how the
functional API lets you start simple and add complexity only when needed.
"""

import asyncio

from agent_framework import Agent, Message, workflow
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

# ---------------------------------------------------------------------------
# Create agents
# ---------------------------------------------------------------------------

client = FoundryChatClient(credential=AzureCliCredential())

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
    # Passing list[Message] keeps roles/authorship intact between turns,
    # instead of stringifying everything into a single prompt.
    conversation: list[Message] = [Message("user", [question])]

    # Simple round-robin: each agent sees the full conversation so far
    for agent in participants:
        response = await agent.run(conversation)
        conversation.extend(response.messages)

    return "\n\n".join(f"{m.author_name or m.role}: {m.text}" for m in conversation)


async def main():
    result = await group_chat.run("What's the difference between a list and a tuple in Python?")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
