# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Provider

Demonstrates setting up OpenAIResponsesClient and running a simple query.

Environment variables:
- OPENAI_API_KEY: Your OpenAI API key
- OPENAI_RESPONSES_MODEL_ID: Model to use (default: gpt-4.1-mini)

For more OpenAI examples:
- With tools: getting_started/agents/openai/openai_responses_client_with_function_tools.py
- With structured output: ../structured_output.py
- Docs: https://learn.microsoft.com/agent-framework/providers/openai
"""


async def main() -> None:
    print("=== OpenAI Provider ===\n")

    # <create_agent>
    agent = OpenAIResponsesClient().as_agent(
        name="OpenAIAgent",
        instructions="You are a helpful assistant.",
    )
    # </create_agent>

    # <run_query>
    query = "What is the capital of France?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Agent: {response}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
