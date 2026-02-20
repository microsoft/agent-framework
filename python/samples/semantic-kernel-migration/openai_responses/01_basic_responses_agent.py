# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/openai_responses/01_basic_responses_agent.py

# Copyright (c) Microsoft. All rights reserved.
"""Issue a basic Responses API call using SK and Agent Framework."""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import OpenAIResponsesAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAISettings

    client = OpenAIResponsesAgent.create_client()
    # SK response agents wrap OpenAI's hosted Responses API.
    agent = OpenAIResponsesAgent(
        ai_model_id=OpenAISettings().responses_model_id,
        client=client,
        instructions="Answer in one concise sentence.",
        name="Expert",
    )
    response = await agent.get_response("Why is the sky blue?")
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework import Agent
    from agent_framework.openai import OpenAIResponsesClient

    # AF Agent can swap in an OpenAIResponsesClient directly.
    chat_agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="Answer in one concise sentence.",
        name="Expert",
    )
    reply = await chat_agent.run("Why is the sky blue?")
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
