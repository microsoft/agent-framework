# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime, timezone
from typing import Any

from agent_framework import (
    AgentSession,
    SupportsAgentRun,
    tool,
)
from agent_framework.azure import AzureAIAgentClient, AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent with Multiple Tools Example

This sample demonstrates integrating multiple tools (MCP and Web Search) with Azure AI Agents,
including user approval workflows for function call security.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables
2. For Bing search functionality, set BING_CONNECTION_ID environment variable to your Bing connection ID
   Example: BING_CONNECTION_ID="/subscriptions/{subscription-id}/resourceGroups/{resource-group}/
            providers/Microsoft.CognitiveServices/accounts/{ai-service-name}/projects/{project-name}/
            connections/{connection-name}"

To set up Bing Grounding:
1. Go to Azure AI Foundry portal (https://ai.azure.com)
2. Navigate to your project's "Connected resources" section
3. Add a new connection for "Grounding with Bing Search"
4. Copy the connection ID and set it as the BING_CONNECTION_ID environment variable
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_time() -> str:
    """Get the current UTC time."""
    current_time = datetime.now(timezone.utc)
    return f"The current UTC time is {current_time.strftime('%Y-%m-%d %H:%M:%S')}."


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


async def main() -> None:
    """Example showing multiple tools for an Azure AI Agent."""

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIAgentClient(credential=credential)
        # Create tools using instance methods
        mcp_tool = client.get_mcp_tool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        )
        web_search_tool = client.get_web_search_tool()

        agent = await provider.create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with microsoft documentation questions.",
            tools=[
                mcp_tool,
                web_search_tool,
                get_time,
            ],
        )
        session = agent.create_session()
        # First query
        query1 = "How to create an Azure storage account using az cli and what time is it?"
        print(f"User: {query1}")
        result1 = await handle_approvals_with_session(query1, agent, session)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework and use a web search to see what is Reddit saying about it?"
        print(f"User: {query2}")
        result2 = await handle_approvals_with_session(query2, agent, session)
        print(f"{agent.name}: {result2}\n")


if __name__ == "__main__":
    asyncio.run(main())
