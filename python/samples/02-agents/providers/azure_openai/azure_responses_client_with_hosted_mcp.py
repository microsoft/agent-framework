# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import TYPE_CHECKING, Any

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Responses Client with Hosted MCP Example

This sample demonstrates integrating hosted Model Context Protocol (MCP) tools with
Azure OpenAI Responses Client, including user approval workflows for function call security.
"""

if TYPE_CHECKING:
    from agent_framework import AgentSession, SupportsAgentRun


async def handle_approvals_without_session(query: str, agent: "SupportsAgentRun"):
    """When we don't have a session, we need to ensure we return with the input, approval request and approval."""
    from agent_framework import Message

    result = await agent.run(query)
    while len(result.user_input_requests) > 0:
        new_inputs: list[Any] = [query]
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            new_inputs.append(Message(role="assistant", contents=[user_input_needed]))
            user_approval = input("Approve function call? (y/n): ")
            new_inputs.append(
                Message(
                    role="user",
                    contents=[user_input_needed.to_function_approval_response(user_approval.lower() == "y")],
                )
            )

        result = await agent.run(new_inputs)
    return result


async def handle_approvals_with_session(query: str, agent: "SupportsAgentRun", session: "AgentSession"):
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


async def handle_approvals_with_session_streaming(query: str, agent: "SupportsAgentRun", session: "AgentSession"):
    """Here we let the session deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import Message

    new_input: list[Message | str] = [query]
    new_input_added = True
    while new_input_added:
        new_input_added = False
        async for update in agent.run(new_input, session=session, options={"store": True}, stream=True):
            if update.user_input_requests:
                # Reset input to only contain new approval responses for the next iteration
                new_input = []
                for user_input_needed in update.user_input_requests:
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
                    new_input_added = True
            else:
                yield update


async def run_hosted_mcp_without_session_and_specific_approval() -> None:
    """Example showing Mcp Tools with approvals without using a session."""
    print("=== Mcp with approvals and without session ===")
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(credential=credential)

    # Create MCP tool with specific approval settings
    mcp_tool = client.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        # we don't require approval for microsoft_docs_search tool calls
        # but we do for any other tool
        approval_mode={"never_require_approval": ["microsoft_docs_search"]},
    )

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with Agent(
        client=client,
        name="DocsAgent",
        instructions="You are a helpful assistant that uses your MCP tool "
        "to help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_without_session(query1, agent)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_session(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_without_approval() -> None:
    """Example showing Mcp Tools without approvals."""
    print("=== Mcp without approvals ===")
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(credential=credential)

    # Create MCP tool without approval requirements
    mcp_tool = client.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        # we don't require approval for any function calls
        # this means we will not see the approval messages,
        # it is fully handled by the service and a final response is returned.
        approval_mode="never_require",
    )

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with Agent(
        client=client,
        name="DocsAgent",
        instructions="You are a helpful assistant that uses your MCP tool "
        "to help with Microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_without_session(query1, agent)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_session(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_with_session() -> None:
    """Example showing Mcp Tools with approvals using a session."""
    print("=== Mcp with approvals and with session ===")
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(credential=credential)

    # Create MCP tool with always require approval
    mcp_tool = client.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        # we require approval for all function calls
        approval_mode="always_require",
    )

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with Agent(
        client=client,
        name="DocsAgent",
        instructions="You are a helpful assistant that uses your MCP tool "
        "to help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        # First query
        session = agent.create_session()
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


async def run_hosted_mcp_with_session_streaming() -> None:
    """Example showing Mcp Tools with approvals using a session."""
    print("=== Mcp with approvals and with session ===")
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(credential=credential)

    # Create MCP tool with always require approval
    mcp_tool = client.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        # we require approval for all function calls
        approval_mode="always_require",
    )

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with Agent(
        client=client,
        name="DocsAgent",
        instructions="You are a helpful assistant that uses your MCP tool "
        "to help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        # First query
        session = agent.create_session()
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        print(f"{agent.name}: ", end="")
        async for update in handle_approvals_with_session_streaming(query1, agent, session):
            print(update, end="")
        print("\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        print(f"{agent.name}: ", end="")
        async for update in handle_approvals_with_session_streaming(query2, agent, session):
            print(update, end="")
        print("\n")


async def main() -> None:
    print("=== OpenAI Responses Client Agent with Hosted Mcp Tools Examples ===\n")

    await run_hosted_mcp_without_approval()
    await run_hosted_mcp_without_session_and_specific_approval()
    await run_hosted_mcp_with_session()
    await run_hosted_mcp_with_session_streaming()


if __name__ == "__main__":
    asyncio.run(main())
