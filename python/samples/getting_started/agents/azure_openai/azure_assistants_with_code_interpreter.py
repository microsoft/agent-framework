# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentResponseUpdate, ChatAgent, ChatResponseUpdate, HostedCodeInterpreterTool
from agent_framework.azure import AzureOpenAIAssistantsClient
from azure.identity import AzureCliCredential
from openai.types.beta.threads.runs import (
    CodeInterpreterToolCallDelta,
    RunStepDelta,
    RunStepDeltaEvent,
    ToolCallDeltaObject,
)
from openai.types.beta.threads.runs.code_interpreter_tool_call_delta import CodeInterpreter

"""
Azure OpenAI Assistants with Code Interpreter Example

This sample demonstrates using HostedCodeInterpreterTool with Azure OpenAI Assistants
for Python code execution and mathematical problem solving.
"""


def get_code_interpreter_chunk(chunk: AgentResponseUpdate) -> str | None:
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
    """Example showing how to use the HostedCodeInterpreterTool with Azure OpenAI Assistants."""
    print("=== Azure OpenAI Assistants Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with ChatAgent(
        chat_client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    ) as agent:
        query = "What is current datetime?"
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
