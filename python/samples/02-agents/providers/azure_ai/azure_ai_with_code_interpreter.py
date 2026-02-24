# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatResponse
from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent Code Interpreter Example

This sample demonstrates using get_code_interpreter_tool() with AzureAIProjectAgentProvider
for Python code execution and mathematical problem solving.
"""


async def main() -> None:
    """Example showing how to use the code interpreter tool with AzureAIProjectAgentProvider."""

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIClient(credential=credential)
        code_interpreter_tool = client.get_code_interpreter_tool()

        agent = await provider.create_agent(
            name="MyCodeInterpreterAgent",
            instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
            tools=[code_interpreter_tool],
        )

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
