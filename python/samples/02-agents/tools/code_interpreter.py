# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedCodeInterpreterTool
from agent_framework.openai import OpenAIResponsesClient

"""
Code Interpreter Tool

Demonstrates using HostedCodeInterpreterTool to let the agent write and execute
Python code for calculations, data analysis, and problem solving.

The code interpreter runs in a sandboxed environment managed by the provider.

For more on code interpreter:
- File downloads: getting_started/agents/openai/openai_responses_client_with_code_interpreter_files.py
- Azure AI: getting_started/agents/azure_ai/azure_ai_with_code_interpreter.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/code-interpreter
"""


async def main() -> None:
    print("=== Code Interpreter Tool ===\n")

    # <create_agent>
    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    )
    # </create_agent>

    # <run_query>
    query = "Calculate the factorial of 100"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")
    # </run_query>

    # <inspect_code>
    # Inspect the generated code and outputs
    for message in result.messages:
        code_blocks = [c for c in message.contents if c.type == "code_interpreter_tool_call"]
        outputs = [c for c in message.contents if c.type == "code_interpreter_tool_result"]
        if code_blocks:
            code_inputs = code_blocks[0].inputs or []
            for content in code_inputs:
                if content.type == "text":
                    print(f"Generated code:\n{content.text}")
                    break
        if outputs:
            print("Execution outputs:")
            for out in outputs[0].outputs or []:
                if out.type == "text":
                    print(out.text)
    # </inspect_code>


if __name__ == "__main__":
    asyncio.run(main())
