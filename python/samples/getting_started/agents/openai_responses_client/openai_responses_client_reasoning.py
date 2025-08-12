# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedCodeInterpreterTool, TextContent, TextReasoningContent, UsageContent
from agent_framework.openai import OpenAIResponsesClient


async def reasoning_example() -> None:
    """Example of reasoning response (get results as they are generated)."""
    print("=== Reasoning Example ===")

    agent = OpenAIResponsesClient(ai_model_id="o4-mini").create_agent(
        name="MathHelper",
        instructions="You are a personal math tutor. When asked a math question, "
        "write and run code using the python tool to answer the question.",
        tools=HostedCodeInterpreterTool(),
        reasoning={"effort": "medium"},
    )

    query = "I need to solve the equation 3x + 11 = 14. Can you help me?"
    print(f"User: {query}")
    print(f"{agent.name}: ", end="", flush=True)
    usage = None
    async for chunk in agent.run_streaming(query):
        if chunk.contents:
            for content in chunk.contents:
                if isinstance(content, TextReasoningContent):
                    print(f"\033[97m{content.text}\033[0m", end="", flush=True)
                if isinstance(content, TextContent):
                    print(content.text, end="", flush=True)
                if isinstance(content, UsageContent):
                    usage = content
    print("\n")
    if usage:
        print(f"Usage: {usage.details}")


async def main() -> None:
    print("=== Basic OpenAI Responses Reasoning Agent Example ===")

    await reasoning_example()


if __name__ == "__main__":
    asyncio.run(main())
