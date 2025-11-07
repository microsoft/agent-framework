# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedMCPTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Hosted MCP Example

This sample demonstrates integrating hosted Model Context Protocol (MCP) tools with Azure AI Agent.
"""


async def run_hosted_mcp() -> None:
    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="MyDocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
            tools=HostedMCPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
                # "always_require" mode is not supported yet
                approval_mode="never_require",
            ),
        ) as agent,
    ):
        query = "How to create an Azure storage account using az cli?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"{agent.name}: {result}\n")


async def main() -> None:
    print("=== Azure AI Agent with Hosted Mcp Tools Example ===\n")

    await run_hosted_mcp()


if __name__ == "__main__":
    asyncio.run(main())
