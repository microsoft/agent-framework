# Copyright (c) Microsoft. All rights reserved.
"""Enable the hosted code interpreter for Azure AI agents in SK and AF.

The Azure AI service natively executes the code interpreter tool. Provide the
resource details via AzureAIAgentSettings (SK) or environment variables consumed
by AzureAIAgentClient (AF).
"""

import asyncio


async def run_semantic_kernel() -> None:
    from azure.identity.aio import AzureCliCredential
    from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings

    async with AzureCliCredential() as credential, AzureAIAgent.create_client(credential=credential) as client:
        settings = AzureAIAgentSettings()
        # Register the hosted code interpreter tool with the remote agent.
        definition = await client.agents.as_agent(
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
    from agent_framework.azure import AzureAIAgentClient, HostedCodeInterpreterTool
    from azure.identity.aio import AzureCliCredential

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="Analyst",
            instructions="Use the code interpreter for numeric work.",
            tools=[HostedCodeInterpreterTool()],
        ) as agent,
    ):
        # HostedCodeInterpreterTool mirrors the built-in Azure AI capability.
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
