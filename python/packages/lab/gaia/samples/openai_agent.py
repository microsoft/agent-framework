# Copyright (c) Microsoft. All rights reserved.

"""OpenAI Agent factory for GAIA benchmark.

This module provides a factory function to create an OpenAI agent
configured for GAIA benchmark tasks using the OpenAI Responses API.

Required Environment Variables:
    OPENAI_API_KEY: Your OpenAI API key
    OPENAI_RESPONSES_MODEL_ID: Model to use with Responses API (e.g., gpt-4o, gpt-4o-mini)

Optional Environment Variables:
    OPENAI_BASE_URL: Custom API base URL if using a proxy or compatible service
    OPENAI_ORG_ID: Organization ID for OpenAI API (if applicable)

Authentication:
    Uses OPENAI_API_KEY environment variable.
    Get your API key from: https://platform.openai.com/api-keys

Example:
    export OPENAI_API_KEY="sk-..."
    export OPENAI_RESPONSES_MODEL_ID="gpt-4o"
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agent_framework import Agent
from agent_framework.openai import OpenAIResponsesClient


@asynccontextmanager
async def create_gaia_agent() -> AsyncIterator[Agent]:
    """Create an OpenAI agent configured for GAIA benchmark tasks.

    Uses OpenAI Responses API for enhanced capabilities.

    The agent is configured with:
    - Web Search tool for information retrieval
    - Code Interpreter tool for calculations and data analysis

    Yields:
        Agent: A configured agent ready to run GAIA tasks.

    Example:
        async with create_gaia_agent() as agent:
            result = await agent.run("What is the capital of France?")
            print(result.text)
    """
    client = OpenAIResponsesClient()

    async with client.as_agent(
        name="GaiaAgent",
        instructions="Solve tasks to your best ability. Use Web Search to find "
        "information and Code Interpreter to perform calculations and data analysis.",
        tools=[
            OpenAIResponsesClient.get_web_search_tool(),
            OpenAIResponsesClient.get_code_interpreter_tool(),
        ],
    ) as agent:
        yield agent
