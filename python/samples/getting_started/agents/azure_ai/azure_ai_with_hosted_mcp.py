# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import AgentProtocol, AgentRunResponse, AgentThread, ChatMessage, HostedMCPTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Hosted MCP Example

This sample demonstrates integrating hosted Model Context Protocol (MCP) tools with Azure AI Agent.
"""


async def handle_approvals_without_thread(query: str, agent: "AgentProtocol") -> AgentRunResponse:
    """When we don't have a thread, we need to ensure we return with the input, approval request and approval."""

    result = await agent.run(query, store=False)
    while len(result.user_input_requests) > 0:
        new_inputs: list[Any] = [query]
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            new_inputs.append(ChatMessage(role="assistant", contents=[user_input_needed]))
            user_approval = input("Approve function call? (y/n): ")
            new_inputs.append(
                ChatMessage(role="user", contents=[user_input_needed.create_response(user_approval.lower() == "y")])
            )

        result = await agent.run(new_inputs, store=False)
    return result


async def handle_approvals_with_thread(query: str, agent: "AgentProtocol", thread: "AgentThread") -> AgentRunResponse:
    """Here we let the thread deal with the previous responses, and we just rerun with the approval."""

    result = await agent.run(query, thread=thread)
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
        result = await agent.run(new_input, thread=thread)
    return result


async def run_hosted_mcp_without_approval() -> None:
    """Example showing MCP Tools without approval."""
    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="MyLearnDocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
            tools=HostedMCPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
                approval_mode="never_require",
            ),
        ) as agent,
    ):
        query = "How to create an Azure storage account using az cli?"
        print(f"User: {query}")
        result = await handle_approvals_without_thread(query, agent)
        print(f"{agent.name}: {result}\n")


async def run_hosted_mcp_with_approval_and_thread() -> None:
    """Example showing MCP Tools with approvals using a thread."""
    print("=== MCP with approvals and with thread ===")

    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="MyApiSpecsAgent",
            instructions="You are a helpful agent that can use MCP tools to assist users.",
            tools=HostedMCPTool(
                name="api-specs",
                url="https://gitmcp.io/Azure/azure-rest-api-specs",
                approval_mode="always_require",
            ),
        ) as agent,
    ):
        thread = agent.get_new_thread()
        query = "Please summarize the Azure REST API specifications Readme"
        print(f"User: {query}")
        result = await handle_approvals_with_thread(query, agent, thread)
        print(f"{agent.name}: {result}\n")


async def main() -> None:
    print("=== Azure AI Agent with Hosted MCP Tools Example ===\n")

    await run_hosted_mcp_without_approval()
    await run_hosted_mcp_with_approval_and_thread()


if __name__ == "__main__":
    asyncio.run(main())
