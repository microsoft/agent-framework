# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import AgentProtocol, AgentThread, HostedMCPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential


async def handle_approvals_with_thread(query: str, agent: "AgentProtocol", thread: "AgentThread"):
    """Here we let the thread deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import ChatMessage

    result = await agent.run(query, thread=thread, store=True)
    while len(result.user_input_requests) > 0:
        new_input: list[Any] = []
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            user_approval = input("Approve function call? (y/n): ")
            new_input.append(
                ChatMessage(
                    role="user",
                    contents=[user_input_needed.create_response(user_approval.lower() == "y")],
                )
            )
        result = await agent.run(new_input, thread=thread, store=True)
    return result


async def main() -> None:
    """Example showing Hosted MCP tools for a Foundry Agent."""
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential) as chat_client,
    ):
        # enable foundry observability
        await chat_client.setup_foundry_observability()
        agent = chat_client.create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with microsoft documentation questions.",
            tools=HostedMCPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
        )
        thread = agent.get_new_thread()
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_with_thread(query1, agent, thread)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Semantic Kernel?"
        print(f"User: {query2}")
        result2 = await handle_approvals_with_thread(query2, agent, thread)
        print(f"{agent.name}: {result2}\n")


if __name__ == "__main__":
    asyncio.run(main())
