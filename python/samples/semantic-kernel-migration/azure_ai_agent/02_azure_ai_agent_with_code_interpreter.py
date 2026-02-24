# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/azure_ai_agent/02_azure_ai_agent_with_code_interpreter.py

# Copyright (c) Microsoft. All rights reserved.
"""Enable the hosted code interpreter for Azure AI agents in SK and AF.

The Azure AI service natively executes the code interpreter tool. Provide the
resource details via AzureAIAgentSettings (SK) or environment variables consumed
by AzureAIAgentClient (AF).
"""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from azure.identity.aio import AzureCliCredential
    from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings

    async with AzureCliCredential() as credential, AzureAIAgent.create_client(credential=credential) as client:
        settings = AzureAIAgentSettings()
        # Register the hosted code interpreter tool with the remote agent.
        definition = await client.agents.create_agent(
            model=settings.model_deployment_name,
            name="Analyst",
            instructions="Use the code interpreter for numeric work.",
            tools=[{"type": "code_interpreter"}],
        )
        agent = AzureAIAgent(client=client, definition=definition)
        response = await agent.get_response(
            "Use Python to compute 42 ** 2 and explain the result.",
        )
        print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework.azure import AzureAIAgentClient, AzureAIAgentsProvider
    from azure.identity.aio import AzureCliCredential

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        code_interpreter_tool = AzureAIAgentClient.get_code_interpreter_tool()

        agent = await provider.create_agent(
            name="Analyst",
            instructions="Use the code interpreter for numeric work.",
            tools=[code_interpreter_tool],
        )

        # Code interpreter tool mirrors the built-in Azure AI capability.
        reply = await agent.run(
            "Use Python to compute 42 ** 2 and explain the result.",
            tool_choice="auto",
        )
        print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
