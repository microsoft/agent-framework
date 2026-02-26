# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import AgentResponse, AgentSession, SupportsAgentRun
from agent_framework.azure import AzureAIAgentClient, AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent with Hosted MCP Example

This sample demonstrates integration of Azure AI Agents with hosted Model Context Protocol (MCP)
servers, including user approval workflows for function call security.
"""


async def handle_approvals_with_session(
    query: str, agent: "SupportsAgentRun", session: "AgentSession"
) -> AgentResponse:
    """Here we let the session deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import Message

    result = await agent.run(query, session=session, store=True)
    while len(result.user_input_requests) > 0:
        new_input: list[Any] = []
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            user_approval = input("Approve function call? (y/n): ")
            new_input.append(
                Message(
                    role="user",
                    contents=[user_input_needed.to_function_approval_response(user_approval.lower() == "y")],
                )
            )
        result = await agent.run(new_input, session=session, store=True)
    return result


async def main() -> None:
    """Example showing Hosted MCP tools for a Azure AI Agent."""

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIAgentClient(credential=credential)
        # Create MCP tool using instance method
        mcp_tool = client.get_mcp_tool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        )

        agent = await provider.create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with microsoft documentation questions.",
            tools=[mcp_tool],
        )
        session = agent.create_session()
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_with_session(query1, agent, session)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_with_session(query2, agent, session)
        print(f"{agent.name}: {result2}\n")


if __name__ == "__main__":
    asyncio.run(main())
