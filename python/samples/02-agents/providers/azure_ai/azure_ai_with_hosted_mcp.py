# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import AgentResponse, AgentSession, Message, SupportsAgentRun
from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent with Hosted MCP Example

This sample demonstrates integrating hosted Model Context Protocol (MCP) tools with Azure AI Agent.
"""


async def handle_approvals_without_session(query: str, agent: "SupportsAgentRun") -> AgentResponse:
    """When we don't have a session, we need to ensure we return with the input, approval request and approval."""

    result = await agent.run(query, store=False)
    while len(result.user_input_requests) > 0:
        new_inputs: list[Any] = [query]
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            new_inputs.append(Message("assistant", [user_input_needed]))
            user_approval = input("Approve function call? (y/n): ")
            new_inputs.append(
                Message("user", [user_input_needed.to_function_approval_response(user_approval.lower() == "y")])
            )

        result = await agent.run(new_inputs, store=False)
    return result


async def handle_approvals_with_session(
    query: str, agent: "SupportsAgentRun", session: "AgentSession"
) -> AgentResponse:
    """Here we let the session deal with the previous responses, and we just rerun with the approval."""

    result = await agent.run(query, session=session)
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
        result = await agent.run(new_input, session=session)
    return result


async def run_hosted_mcp_without_approval() -> None:
    """Example showing MCP Tools without approval."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIClient(credential=credential)
        # Create MCP tool using instance method
        mcp_tool = client.get_mcp_tool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            approval_mode="never_require",
        )

        agent = await provider.create_agent(
            name="MyLearnDocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
            tools=[mcp_tool],
        )

        query = "How to create an Azure storage account using az cli?"
        print(f"User: {query}")
        result = await handle_approvals_without_session(query, agent)
        print(f"{agent.name}: {result}\n")


async def run_hosted_mcp_with_approval_and_session() -> None:
    """Example showing MCP Tools with approvals using a session."""
    print("=== MCP with approvals and with session ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIClient(credential=credential)
        # Create MCP tool using instance method
        mcp_tool = client.get_mcp_tool(
            name="api-specs",
            url="https://gitmcp.io/Azure/azure-rest-api-specs",
            approval_mode="always_require",
        )

        agent = await provider.create_agent(
            name="MyApiSpecsAgent",
            instructions="You are a helpful agent that can use MCP tools to assist users.",
            tools=[mcp_tool],
        )

        session = agent.create_session()
        query = "Please summarize the Azure REST API specifications Readme"
        print(f"User: {query}")
        result = await handle_approvals_with_session(query, agent, session)
        print(f"{agent.name}: {result}\n")


async def main() -> None:
    print("=== Azure AI Agent with Hosted MCP Tools Example ===\n")

    await run_hosted_mcp_without_approval()
    await run_hosted_mcp_with_approval_and_session()


if __name__ == "__main__":
    asyncio.run(main())
