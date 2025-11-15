# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import TYPE_CHECKING, Any

from agent_framework import ChatAgent, HostedMCPTool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Responses Client with Hosted MCP Example

This sample demonstrates integrating hosted Model Context Protocol (MCP) tools with
Azure OpenAI Responses Client, including user approval workflows for function call security.
"""

if TYPE_CHECKING:
    from agent_framework import AgentProtocol, AgentThread


async def handle_approvals_without_thread(query: str, agent: "AgentProtocol"):
    """When we don't have a thread, we need to ensure we return with the input, approval request and approval."""
    from agent_framework import ChatMessage

    result = await agent.run(query)
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

        result = await agent.run(new_inputs)
    return result


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


async def handle_approvals_with_thread_streaming(query: str, agent: "AgentProtocol", thread: "AgentThread"):
    """Here we let the thread deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import ChatMessage

    new_input: list[ChatMessage] = []
    new_input_added = True
    while new_input_added:
        new_input_added = False
        new_input.append(ChatMessage(role="user", text=query))
        async for update in agent.run_stream(new_input, thread=thread, store=True):
            if update.user_input_requests:
                for user_input_needed in update.user_input_requests:
                    print(
                        f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                        f" with arguments: {user_input_needed.function_call.arguments}"
                    )
                    user_approval = input("Approve function call? (y/n): ")
                    new_input.append(
                        ChatMessage(
                            role="user", contents=[user_input_needed.create_response(user_approval.lower() == "y")]
                        )
                    )
                    new_input_added = True
            else:
                yield update


async def run_hosted_mcp_without_thread_and_specific_approval() -> None:
    """Example showing Mcp Tools with approvals without using a thread."""
    print("=== Mcp with approvals and without thread ===")
    credential = AzureCliCredential()
    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(
            credential=credential,
        ),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we don't require approval for microsoft_docs_search tool calls
            # but we do for any other tool
            approval_mode={"never_require_approval": ["microsoft_docs_search"]},
        ),
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_without_thread(query1, agent)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_thread(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_without_approval() -> None:
    """Example showing Mcp Tools without approvals."""
    print("=== Mcp without approvals ===")
    credential = AzureCliCredential()
    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(
            credential=credential,
        ),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we don't require approval for any function calls
            # this means we will not see the approval messages,
            # it is fully handled by the service and a final response is returned.
            approval_mode="never_require",
        ),
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_without_thread(query1, agent)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_thread(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_with_thread() -> None:
    """Example showing Mcp Tools with approvals using a thread."""
    print("=== Mcp with approvals and with thread ===")
    credential = AzureCliCredential()
    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(
            credential=credential,
        ),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we require approval for all function calls
            approval_mode="always_require",
        ),
    ) as agent:
        # First query
        thread = agent.get_new_thread()
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_with_thread(query1, agent, thread)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await handle_approvals_with_thread(query2, agent, thread)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_with_thread_streaming() -> None:
    """Example showing Mcp Tools with approvals using a thread."""
    print("=== Mcp with approvals and with thread ===")
    credential = AzureCliCredential()
    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(
            credential=credential,
        ),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we require approval for all function calls
            approval_mode="always_require",
        ),
    ) as agent:
        # First query
        thread = agent.get_new_thread()
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        print(f"{agent.name}: ", end="")
        async for update in handle_approvals_with_thread_streaming(query1, agent, thread):
            print(update, end="")
        print("\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        print(f"{agent.name}: ", end="")
        async for update in handle_approvals_with_thread_streaming(query2, agent, thread):
            print(update, end="")
        print("\n")


async def main() -> None:
    print("=== OpenAI Responses Client Agent with Hosted Mcp Tools Examples ===\n")

    await run_hosted_mcp_without_approval()
    await run_hosted_mcp_without_thread_and_specific_approval()
    await run_hosted_mcp_with_thread()
    await run_hosted_mcp_with_thread_streaming()


if __name__ == "__main__":
    asyncio.run(main())
