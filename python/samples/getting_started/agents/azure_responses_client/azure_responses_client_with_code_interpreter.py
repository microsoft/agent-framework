# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatClientAgent, ChatResponse, HostedCodeInterpreterTool
from agent_framework.azure import AzureResponsesClient
from azure.identity import AzureCliCredential
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Azure OpenAI Responses."""
    print("=== Azure OpenAI Responses Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
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
