# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentRunResponseUpdate, ChatAgent, ChatResponseUpdate, HostedCodeInterpreterTool
from agent_framework.openai import OpenAIAssistantsClient
from openai.types.beta.threads.runs import (
    CodeInterpreterToolCallDelta,
    RunStepDelta,
    RunStepDeltaEvent,
    ToolCallDeltaObject,
)
from openai.types.beta.threads.runs.code_interpreter_tool_call_delta import CodeInterpreter

"""
OpenAI Assistants with Code Interpreter Example

This sample demonstrates using HostedCodeInterpreterTool with OpenAI Assistants
for Python code execution and mathematical problem solving.
"""


def get_code_interpreter_chunk(chunk: AgentRunResponseUpdate) -> str | None:
    """Helper method to access code interpreter data."""
    if (
        isinstance(chunk.raw_representation, ChatResponseUpdate)
        and isinstance(chunk.raw_representation.raw_representation, RunStepDeltaEvent)
        and isinstance(chunk.raw_representation.raw_representation.delta, RunStepDelta)
        and isinstance(chunk.raw_representation.raw_representation.delta.step_details, ToolCallDeltaObject)
        and chunk.raw_representation.raw_representation.delta.step_details.tool_calls
    ):
        for tool_call in chunk.raw_representation.raw_representation.delta.step_details.tool_calls:
            if (
                isinstance(tool_call, CodeInterpreterToolCallDelta)
                and isinstance(tool_call.code_interpreter, CodeInterpreter)
                and tool_call.code_interpreter.input is not None
            ):
                return tool_call.code_interpreter.input
    return None


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with OpenAI Assistants."""
    print("=== OpenAI Assistants Agent with Code Interpreter Example ===")

    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    ) as agent:
        query = "Use code to get the factorial of 100?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        generated_code = ""
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
            code_interpreter_chunk = get_code_interpreter_chunk(chunk)
            if code_interpreter_chunk is not None:
                generated_code += code_interpreter_chunk

        print(f"\nGenerated code:\n{generated_code}")


if __name__ == "__main__":
    asyncio.run(main())
