# Copyright (c) Microsoft. All rights reserved.

"""Azure AI Agent factory for GAIA benchmark.

This module provides a factory function to create an Azure AI agent
configured for GAIA benchmark tasks.

Required Environment Variables:
    AZURE_AI_PROJECT_ENDPOINT: Azure AI project endpoint URL
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Name of the model deployment to use

Optional Environment Variables:
    BING_CONNECTION_ID: ID of the Bing connection for web search

Authentication:
    Uses Azure CLI credentials via AzureCliCredential.
    Run `az login` before executing to authenticate.

Example:
    export AZURE_AI_PROJECT_ENDPOINT="https://your-project.azure.com"
    export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
    export BING_CONNECTION_ID="connection-id"
    az login
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agent_framework import ChatAgent, HostedCodeInterpreterTool, HostedWebSearchTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential


@asynccontextmanager
async def create_gaia_agent() -> AsyncIterator[ChatAgent]:
    """Create an Azure AI agent configured for GAIA benchmark tasks.

    The agent is configured with:
    - Bing Search tool for web information retrieval
    - Code Interpreter tool for calculations and data analysis

    Yields:
        ChatAgent: A configured agent ready to run GAIA tasks.

    Example:
        async with create_gaia_agent() as agent:
            result = await agent.run("What is the capital of France?")
            print(result.text)
    """
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="GaiaAgent",
            instructions="Solve tasks to your best ability. Use Bing Search to find "
            "information and Code Interpreter to perform calculations and data analysis.",
            tools=[
                HostedWebSearchTool(
                    name="Bing Grounding Search",
                    description="Search the web for current information using Bing",
                ),
                HostedCodeInterpreterTool(),
            ],
        ) as agent,
    ):
        yield agent
