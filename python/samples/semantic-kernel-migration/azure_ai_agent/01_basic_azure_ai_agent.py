# Copyright (c) Microsoft. All rights reserved.
"""Create an Azure AI agent using both Semantic Kernel and Agent Framework.

Prerequisites:
- Azure AI agent resource with a deployed model.
- Logged-in Azure CLI or other credential supported by AzureCliCredential.
"""

import asyncio


async def run_semantic_kernel() -> None:
    from azure.identity.aio import AzureCliCredential
    from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings

    async with AzureCliCredential() as credential, AzureAIAgent.create_client(credential=credential) as client:
        settings = AzureAIAgentSettings()  # Reads env vars for region/deployment.
        # SK builds the remote agent definition then wraps it with AzureAIAgent.
        definition = await client.agents.create_agent(
            model=settings.model_deployment_name,
            name="Support",
            instructions="Answer customer questions in one paragraph.",
        )
        agent = AzureAIAgent(client=client, definition=definition)
        response = await agent.get_response("How do I upgrade my plan?")
        print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework.azure import AzureAIAgentClient
    from azure.identity.aio import AzureCliCredential

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).create_agent(
            name="Support",
            instructions="Answer customer questions in one paragraph.",
        ) as agent,
    ):
        # AF client returns an asynchronous context manager for remote agents.
        reply = await agent.run("How do I upgrade my plan?")
        print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
