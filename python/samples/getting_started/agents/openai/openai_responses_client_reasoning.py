# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client Reasoning Example

This sample demonstrates advanced reasoning capabilities using OpenAI's gpt-5 models,
showing step-by-step reasoning process visualization and complex problem-solving.

This uses the additional_chat_options parameter to enable reasoning with high effort and detailed summaries.
You can also set these options at the run level, since they are api and/or provider specific, you will need to lookup
the correct values for your provider, since these are passed through as-is.

In this case they are here: https://platform.openai.com/docs/api-reference/responses/create#responses-create-reasoning
"""


agent = OpenAIResponsesClient(model_id="gpt-5").create_agent(
    name="MathHelper",
    instructions="You are a personal math tutor. When asked a math question, "
    "reason over how best to approach the problem and share your thought process.",
    additional_chat_options={"reasoning": {"effort": "high", "summary": "detailed"}},
)


async def reasoning_example() -> None:
    """Example of reasoning response (get results as they are generated)."""
    print("\033[92m=== Reasoning Example ===\033[0m")

    query = "I need to solve the equation 3x + 11 = 14 and I need to prove the pythagorean theorem. Can you help me?"
    print(f"User: {query}")
    print(f"{agent.name}: ", end="", flush=True)
    response = await agent.run(query)
    for msg in response.messages:
        if msg.contents:
            for content in msg.contents:
                if content.type == "text_reasoning":
                    print(f"\033[94m{content.text}\033[0m", end="", flush=True)
                elif content.type == "text":
                    print(content.text, end="", flush=True)
    print("\n")
    if response.usage_details:
        print(f"Usage: {response.usage_details}")


async def streaming_reasoning_example() -> None:
    """Example of reasoning response (get results as they are generated)."""
    print("\033[92m=== Streaming Reasoning Example ===\033[0m")

    query = "I need to solve the equation 3x + 11 = 14 and I need to prove the pythagorean theorem. Can you help me?"
    print(f"User: {query}")
    print(f"{agent.name}: ", end="", flush=True)
    usage = None
    async for chunk in agent.run_stream(query):
        if chunk.contents:
            for content in chunk.contents:
                if content.type == "text_reasoning":
                    print(f"\033[94m{content.text}\033[0m", end="", flush=True)
                elif content.type == "text":
                    print(content.text, end="", flush=True)
                elif content.type == "usage":
                    usage = content
    print("\n")
    if usage:
        print(f"Usage: {usage.details}")


async def main() -> None:
    print("\033[92m=== Basic OpenAI Responses Reasoning Agent Example ===\033[0m")

    await reasoning_example()
    await streaming_reasoning_example()


if __name__ == "__main__":
    asyncio.run(main())
