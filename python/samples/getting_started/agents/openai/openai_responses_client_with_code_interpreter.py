# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, ChatResponse, HostedCodeInterpreterTool
from agent_framework.openai import OpenAIResponsesClient
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall

"""
OpenAI Responses Client with Code Interpreter Example

This sample demonstrates using HostedCodeInterpreterTool with OpenAI Responses Client
for Python code execution and mathematical problem solving.
"""


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with OpenAI Responses."""
    print("=== OpenAI Responses Agent with Code Interpreter Example ===")

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    )

    query = "Use code to get the factorial of 100?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")

    if (
        isinstance(result.raw_representation, ChatResponse)
        and isinstance(result.raw_representation.raw_representation, OpenAIResponse)
        and len(result.raw_representation.raw_representation.output) > 0
        and isinstance(result.raw_representation.raw_representation.output[0], ResponseCodeInterpreterToolCall)
    ):
        generated_code = result.raw_representation.raw_representation.output[0].code

        print(f"Generated code:\n{generated_code}")


if __name__ == "__main__":
    asyncio.run(main())
