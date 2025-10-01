# Copyright (c) Microsoft. All rights reserved.
"""Maintain Azure AI agent conversation state across turns in SK and AF."""

import asyncio


async def run_semantic_kernel() -> None:
    from azure.identity.aio import AzureCliCredential
    from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings, AzureAIAgentThread

    async with AzureCliCredential() as credential:
        async with AzureAIAgent.create_client(credential=credential) as client:
            settings = AzureAIAgentSettings()
            definition = await client.agents.create_agent(
                model=settings.model_deployment_name,
                name="Planner",
                instructions="Track follow-up questions within the same thread.",
            )
            agent = AzureAIAgent(client=client, definition=definition)

            thread: AzureAIAgentThread | None = None
            # SK returns the updated AzureAIAgentThread on each response.
            first = await agent.get_response("Outline the onboarding checklist.", thread=thread)
            thread = first.thread
            print("[SK][turn1]", first.message.content)

            second = await agent.get_response(
                "Highlight the items that require legal review.",
                thread=thread,
            )
            print("[SK][turn2]", second.message.content)
            if thread is not None:
                print("[SK][thread-id]", thread.id)


async def run_agent_framework() -> None:
    from azure.identity.aio import AzureCliCredential
    from agent_framework.azure import AzureAIAgentClient

    async with AzureCliCredential() as credential:
        async with AzureAIAgentClient(async_credential=credential).create_agent(
            name="Planner",
            instructions="Track follow-up questions within the same thread.",
        ) as agent:
            thread = agent.get_new_thread()
            # AF threads are explicit and can be serialized for external storage.
            first = await agent.run("Outline the onboarding checklist.", thread=thread)
            print("[AF][turn1]", first.text)

            second = await agent.run(
                "Highlight the items that require legal review.",
                thread=thread,
            )
            print("[AF][turn2]", second.text)

            serialized = await thread.serialize()
            print("[AF][thread-json]", serialized)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
