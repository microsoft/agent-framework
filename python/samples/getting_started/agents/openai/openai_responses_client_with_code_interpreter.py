# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    ChatAgent,
    CodeInterpreterToolCallContent,
    CodeInterpreterToolResultContent,
    HostedCodeInterpreterTool,
    TextContent,
    tool,
)
from agent_framework.openai import OpenAIResponsesClient

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

    for message in result.messages:
        code_blocks = [c for c in message.contents if isinstance(c, CodeInterpreterToolCallContent)]
        outputs = [c for c in message.contents if isinstance(c, CodeInterpreterToolResultContent)]
        if code_blocks:
            code_inputs = code_blocks[0].inputs or []
            for content in code_inputs:
                if isinstance(content, TextContent):
                    print(f"Generated code:\n{content.text}")
                    break
        if outputs:
            print("Execution outputs:")
            for out in outputs[0].outputs or []:
                if isinstance(out, TextContent):
                    print(out.text)


if __name__ == "__main__":
    asyncio.run(main())
