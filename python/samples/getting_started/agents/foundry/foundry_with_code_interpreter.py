# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentRunResponse,
    HostedCodeInterpreterTool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential


def print_code_interpreter_inputs(response: AgentRunResponse) -> None:
    """Helper method to access code interpreter data."""
    from agent_framework import ChatResponseUpdate
    from azure.ai.agents.models import (
        RunStepDeltaCodeInterpreterDetailItemObject,
    )

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
    """Example showing how to use the HostedCodeInterpreterTool with Foundry."""
    print("=== Foundry Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential) as chat_client,
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
        # To review the code interpreter outputs, you can access them from the response raw_representations, just uncomment the next line:
        # print_code_interpreter_inputs(response)


if __name__ == "__main__":
    asyncio.run(main())
