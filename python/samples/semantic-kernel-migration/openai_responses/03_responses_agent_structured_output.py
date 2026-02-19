# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/openai_responses/03_responses_agent_structured_output.py

# Copyright (c) Microsoft. All rights reserved.
"""Request structured JSON output from the Responses API in SK and AF."""

import asyncio

from pydantic import BaseModel


class ReleaseBrief(BaseModel):
    feature: str
    benefit: str
    launch_date: str


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import OpenAIResponsesAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAISettings

    client = OpenAIResponsesAgent.create_client()
    # response_format requests schema-constrained output from the model.
    agent = OpenAIResponsesAgent(
        ai_model_id=OpenAISettings().responses_model_id,
        client=client,
        instructions="Return launch briefs as structured JSON.",
        name="ProductMarketer",
        text=OpenAIResponsesAgent.configure_response_format(ReleaseBrief),
    )
    response = await agent.get_response(
        "Draft a launch brief for the Contoso Note app.",
    )
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework import Agent
    from agent_framework.openai import OpenAIResponsesClient

    chat_agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="Return launch briefs as structured JSON.",
        name="ProductMarketer",
    )
    # AF forwards the same response_format payload at invocation time.
    reply = await chat_agent.run(
        "Draft a launch brief for the Contoso Note app.",
        options={"response_format": ReleaseBrief},
    )
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
