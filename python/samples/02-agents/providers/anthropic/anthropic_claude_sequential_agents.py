# Copyright (c) Microsoft. All rights reserved.

"""
Anthropic Claude Sequential Agents Example

Demonstrate conversation history handover between two Claude agents.

SequentialBuilder passes the original user message and the grammar inspector's
response to the second agent. ClaudeAgent represents that history as JSON records
containing each message's original role and content inside a single SDK user
message, rather than resuming a shared Claude session.
"""

import asyncio

from agent_framework import AgentResponse
from agent_framework_claude import ClaudeAgent
from agent_framework_orchestrations import SequentialBuilder
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    agents = [
        ClaudeAgent(instructions="You are an agent that corrects English grammar mistakes.", name="grammar_inspector"),
        ClaudeAgent(
            instructions="You are an agent that lists the diff between the participants of this conversation",
            name="diff_highlighter",
        ),
    ]
    workflow = SequentialBuilder(participants=agents, output_from="all").build()

    prompt = "Yesterday she go to the store and buyed two apple."
    result = await workflow.run(prompt)

    print(f"[user]\n{prompt}")
    for response in result.get_outputs():
        if isinstance(response, AgentResponse):
            for message in response.messages:
                author = message.author_name or message.role
                print(f"\n[{author}]\n{message.text}")


if __name__ == "__main__":
    asyncio.run(main())
