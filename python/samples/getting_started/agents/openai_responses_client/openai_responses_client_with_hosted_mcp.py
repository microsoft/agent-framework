# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import TYPE_CHECKING, Any

from agent_framework import ChatClientAgent, HostedMcpTool
from agent_framework.openai import OpenAIResponsesClient

if TYPE_CHECKING:
    from agent_framework import AgentThread, AIAgent


async def handle_approvals_without_thread(query: str, agent: "AIAgent"):
    """When we don't have a thread, we need to ensure we return with the input, approval request and approval."""
    from agent_framework import ChatMessage, FunctionApprovalRequestContent

    result = await agent.run(query)
    while len(result.user_input_requests) > 0:
        approvals: list[Any] = [query]
        for approval in result.user_input_requests:
            assert isinstance(approval, FunctionApprovalRequestContent)
            print(
                f"User Input Request for function from {agent.name}: {approval.function_call.name}"
                f" with arguments: {approval.function_call.arguments}"
            )
            approvals.append(ChatMessage(role="assistant", contents=[approval]))
            approvals.append(approval.approve())
        result = await agent.run(approvals)
    return result


async def handle_approvals_with_thread(query: str, agent: "AIAgent", thread: "AgentThread"):
    """Here we let the thread deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import FunctionApprovalRequestContent

    result = await agent.run(query, thread=thread, store=True)
    while len(result.user_input_requests) > 0:
        approvals: list[Any] = []
        for approval in result.user_input_requests:
            assert isinstance(approval, FunctionApprovalRequestContent)
            print(
                f"User Input Request for function from {agent.name}: {approval.function_call.name}"
                f" with arguments: {approval.function_call.arguments}"
            )
            approvals.append(approval.approve())
        result = await agent.run(approvals, thread=thread, store=True)
    return result


async def run_hosted_mcp_wo_thread() -> None:
    """Example showing Mcp Tools with approvals without using a thread."""
    print("=== Mcp with approvals and without thread ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatClientAgent(
        chat_client=OpenAIResponsesClient(),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMcpTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we require approval for all function calls
            approval_mode="always_require",
        ),
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await handle_approvals_without_thread(query1, agent)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Semantic Kernel?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_thread(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_wo_approval() -> None:
    """Example showing Mcp Tools without approvals."""
    print("=== Mcp without approvals ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatClientAgent(
        chat_client=OpenAIResponsesClient(),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMcpTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            # we require approval for all function calls
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
        query2 = "What is Microsoft Semantic Kernel?"
        print(f"User: {query2}")
        result2 = await handle_approvals_without_thread(query2, agent)
        print(f"{agent.name}: {result2}\n")


async def run_hosted_mcp_with_thread() -> None:
    """Example showing Mcp Tools with approvals using a thread."""
    print("=== Mcp with approvals and with thread ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatClientAgent(
        chat_client=OpenAIResponsesClient(),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMcpTool(
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
        query2 = "What is Microsoft Semantic Kernel?"
        print(f"User: {query2}")
        result2 = await handle_approvals_with_thread(query2, agent, thread)
        print(f"{agent.name}: {result2}\n")


async def main() -> None:
    print("=== OpenAI Responses Client Agent with Hosted Mcp Tools Examples ===\n")

    await run_hosted_mcp_with_thread()
    await run_hosted_mcp_wo_thread()
    await run_hosted_mcp_wo_approval()


if __name__ == "__main__":
    asyncio.run(main())
