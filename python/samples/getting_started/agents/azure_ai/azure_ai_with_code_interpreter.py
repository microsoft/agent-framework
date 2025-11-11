# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatResponse, HostedCodeInterpreterTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall

"""
Azure AI Agent Code Interpreter Example

This sample demonstrates using HostedCodeInterpreterTool with AzureAIClient
for Python code execution and mathematical problem solving.
"""


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with AzureAIClient."""

    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
            tools=HostedCodeInterpreterTool(),
        ) as agent,
    ):
        query = "Use code to get the factorial of 100?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")

        if (
            isinstance(result.raw_representation, ChatResponse)
            and isinstance(result.raw_representation.raw_representation, OpenAIResponse)
            and len(result.raw_representation.raw_representation.output) > 0
        ):
            # Find the first ResponseCodeInterpreterToolCall item
            code_interpreter_item = next(
                (
                    item
                    for item in result.raw_representation.raw_representation.output
                    if isinstance(item, ResponseCodeInterpreterToolCall)
                ),
                None,
            )

            if code_interpreter_item is not None:
                generated_code = code_interpreter_item.code
                print(f"Generated code:\n{generated_code}")


if __name__ == "__main__":
    asyncio.run(main())
