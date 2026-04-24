# Copyright (c) Microsoft. All rights reserved.

"""Azure AI Agent factory for GAIA benchmark.

This module provides a factory function to create an Azure AI agent
configured for GAIA benchmark tasks.

Required Environment Variables:
    FOUNDRY_PROJECT_ENDPOINT: Azure AI project endpoint URL
    FOUNDRY_MODEL: Name of the model deployment to use

Optional Environment Variables:
    BING_CONNECTION_ID: ID of the Bing connection for web search

Authentication:
    Uses Azure CLI credentials via AzureCliCredential.
    Run `az login` before executing to authenticate.

Example:
    export FOUNDRY_PROJECT_ENDPOINT="https://your-project.azure.com"
    export FOUNDRY_MODEL="gpt-4o"
    export BING_CONNECTION_ID="connection-id"
    az login
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential


@asynccontextmanager
async def create_gaia_agent() -> AsyncIterator[Agent]:
    """Create an Azure AI agent configured for GAIA benchmark tasks.

    The agent is configured with:
    - Bing Search tool for web information retrieval
    - Code Interpreter tool for calculations and data analysis

    Yields:
        Agent: A configured agent ready to run GAIA tasks.

    Example:
        async with create_gaia_agent() as agent:
            result = await agent.run("What is the capital of France?")
            print(result.text)
    """
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        ).as_agent(
            name="GaiaAgent",
            instructions="Solve tasks to your best ability. Use Bing Search to find "
            "information and Code Interpreter to perform calculations and data analysis.",
            tools=[
                FoundryChatClient.get_web_search_tool(),
                FoundryChatClient.get_code_interpreter_tool(),
            ],
        ) as agent,
    ):
        yield agent
