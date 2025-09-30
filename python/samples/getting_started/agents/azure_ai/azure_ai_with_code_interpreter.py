# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentRunResponse, ChatResponseUpdate, HostedCodeInterpreterTool
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agents.models import (
    RunStepDeltaCodeInterpreterDetailItemObject,
)
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Code Interpreter Example

This sample demonstrates how to use the HostedCodeInterpreterTool with Azure AI Agents
for code generation and execution. The example includes:

- Creating agents with HostedCodeInterpreterTool for Python code execution
- Mathematical problem solving using code generation and execution
- Accessing and displaying the generated code from response data
- Working with structured response data to extract code interpreter outputs
- Helper functions for processing code interpreter inputs and outputs
- Integration of Azure AI Agents with computational capabilities

The HostedCodeInterpreterTool enables agents to write, execute, and iterate on Python code,
making it ideal for mathematical calculations, data analysis, and computational problem-solving tasks
with the reliability and scalability of Azure AI's managed infrastructure.
"""


def print_code_interpreter_inputs(response: AgentRunResponse) -> None:
    """Helper method to access code interpreter data."""

    print("\nCode Interpreter Inputs during the run:")
    if response.raw_representation is None:
        return
    for chunk in response.raw_representation:
        if isinstance(chunk, ChatResponseUpdate) and isinstance(
            chunk.raw_representation, RunStepDeltaCodeInterpreterDetailItemObject
        ):
            print(chunk.raw_representation.input, end="")
    print("\n")


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Azure AI."""
    print("=== Azure AI Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential) as chat_client,
    ):
        agent = chat_client.create_agent(
            name="CodingAgent",
            instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
            tools=HostedCodeInterpreterTool(),
        )
        query = "Generate the factorial of 100 using python code, show the code and execute it."
        print(f"User: {query}")
        response = await AgentRunResponse.from_agent_response_generator(agent.run_stream(query))
        print(f"Agent: {response}")
        # To review the code interpreter outputs, you can access
        # them from the response raw_representations, just uncomment the next line:
        # print_code_interpreter_inputs(response)


if __name__ == "__main__":
    asyncio.run(main())
