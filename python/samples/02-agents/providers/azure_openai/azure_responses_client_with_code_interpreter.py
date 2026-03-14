# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, ChatResponse
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall

# Load environment variables from .env file
load_dotenv()

"""
Azure OpenAI Responses Client with Code Interpreter Example

This sample demonstrates using get_code_interpreter_tool() with Azure OpenAI Responses
for Python code execution and mathematical problem solving.
"""


async def main() -> None:
    """Example showing how to use the code interpreter tool with Azure OpenAI Responses."""
    print("=== Azure OpenAI Responses Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    # Create code interpreter tool using instance method
    code_interpreter_tool = client.get_code_interpreter_tool()

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=[code_interpreter_tool],
    )

    query = "Use code to calculate the factorial of 100?"
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
