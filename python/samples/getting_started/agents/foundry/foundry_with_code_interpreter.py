# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentRunResponseUpdate, ChatClientAgent, ChatResponseUpdate, HostedCodeInterpreterTool
from agent_framework.foundry import FoundryChatClient
from azure.ai.agents.models import (
    RunStepDelta,
    RunStepDeltaChunk,
    RunStepDeltaCodeInterpreterDetailItemObject,
    RunStepDeltaCodeInterpreterToolCall,
    RunStepDeltaToolCallObject,
)
from azure.identity.aio import DefaultAzureCredential


def get_code_interpreter_chunk(chunk: AgentRunResponseUpdate) -> str | None:
    """Helper method to access code interpreter data."""
    if (
        isinstance(chunk.raw_representation, ChatResponseUpdate)
        and isinstance(chunk.raw_representation.raw_representation, RunStepDeltaChunk)
        and isinstance(chunk.raw_representation.raw_representation.delta, RunStepDelta)
        and isinstance(chunk.raw_representation.raw_representation.delta.step_details, RunStepDeltaToolCallObject)
        and chunk.raw_representation.raw_representation.delta.step_details.tool_calls
    ):
        for tool_call in chunk.raw_representation.raw_representation.delta.step_details.tool_calls:
            if (
                isinstance(tool_call, RunStepDeltaCodeInterpreterToolCall)
                and isinstance(tool_call.code_interpreter, RunStepDeltaCodeInterpreterDetailItemObject)
                and tool_call.code_interpreter.input is not None
            ):
                return tool_call.code_interpreter.input
    return None


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Foundry."""
    print("=== Foundry Agent with Code Interpreter Example ===")

    async with ChatClientAgent(
        chat_client=FoundryChatClient(async_ad_credential=DefaultAzureCredential()),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    ) as agent:
        query = "Generate the factorial of 100 using python code."
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        generated_code = ""
        async for chunk in agent.run_streaming(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
            code_interpreter_chunk = get_code_interpreter_chunk(chunk)
            if code_interpreter_chunk is not None:
                generated_code += code_interpreter_chunk

        print(f"\nGenerated code:\n{generated_code}")


if __name__ == "__main__":
    asyncio.run(main())
