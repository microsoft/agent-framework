# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, ChatResponse, HostedCodeInterpreterTool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall

"""
Azure OpenAI Responses Client with Code Interpreter Example

This sample demonstrates how to use the HostedCodeInterpreterTool with Azure OpenAI Responses
for code generation and execution. The example includes:

- Creating agents with HostedCodeInterpreterTool for Python code execution
- Mathematical problem solving using code generation and execution
- Accessing and displaying the generated code from response data
- Working with structured response data to extract code interpreter outputs
- Integration of Azure OpenAI Responses with computational capabilities

The HostedCodeInterpreterTool enables agents to write, execute, and iterate on Python code,
making it ideal for mathematical calculations, data analysis, and computational problem-solving tasks.
"""


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Azure OpenAI Responses."""
    print("=== Azure OpenAI Responses Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
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
