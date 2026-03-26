# Copyright (c) Microsoft. All rights reserved.

"""
Chat Agent Service

Provides an Agent instance configured with CosmosHistoryProvider for
automatic conversation history persistence, local tools for weather,
calculation, and knowledge base search, plus MCP integration for
Microsoft Learn documentation search.
"""

import logging
import os
from pathlib import Path

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.identity import DefaultAzureCredential
from tools import (
    calculate,
    get_weather,
    search_knowledge_base,
)

_history_provider: CosmosHistoryProvider | None = None
_agent: Agent | None = None
_credential: DefaultAzureCredential | None = None

# Prompts directory
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = _PROMPTS_DIR / f"{name}.txt"
    return prompt_path.read_text(encoding="utf-8")


# Microsoft Learn MCP server URL
MICROSOFT_LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"


def get_history_provider() -> CosmosHistoryProvider:
    """
    Get or create the singleton CosmosHistoryProvider instance.

    The provider automatically:
    - Loads conversation history before each agent run
    - Stores user inputs and agent responses
    - Uses session_id as the Cosmos DB partition key

    Returns:
        Configured CosmosHistoryProvider instance.
    """
    global _history_provider, _credential

    if _history_provider is None:
        endpoint = os.environ.get("AZURE_COSMOS_ENDPOINT")
        database_name = os.environ.get("AZURE_COSMOS_DATABASE_NAME", "chat_db")
        container_name = os.environ.get("AZURE_COSMOS_CONTAINER_NAME", "messages")

        if not endpoint:
            raise ValueError("AZURE_COSMOS_ENDPOINT environment variable is required")

        if _credential is None:
            _credential = DefaultAzureCredential()

        _history_provider = CosmosHistoryProvider(
            source_id="enterprise_chat_agent",
            endpoint=endpoint,
            database_name=database_name,
            container_name=container_name,
            credential=_credential,
            load_messages=True,  # Load history before each run
            store_inputs=True,  # Store user messages
            store_outputs=True,  # Store assistant responses
        )

        logging.info(
            f"Initialized CosmosHistoryProvider with database={database_name}, "
            f"container={container_name}"
        )

    return _history_provider


def get_agent() -> Agent:
    """
    Get or create the singleton Agent instance.

    The agent is configured with:
    - Azure OpenAI chat client
    - CosmosHistoryProvider for automatic conversation persistence
    - Weather, calculator, and knowledge base tools
    - System instructions for enterprise chat support

    Returns:
        Configured Agent instance.
    """
    global _agent

    if _agent is None:
        # Get Azure OpenAI configuration from environment
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")

        # Create Azure OpenAI chat client with credential
        global _credential
        if _credential is None:
            _credential = DefaultAzureCredential()

        chat_client = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=deployment_name,
            api_version=api_version,
            credential=_credential,
        )

        # Get the history provider
        history_provider = get_history_provider()

        # Load system instructions from prompts folder
        instructions = _load_prompt("system_prompt")

        # Create Agent with local tools and history provider
        # MCP tools are added at runtime via run() method
        _agent = Agent(
            client=chat_client,
            instructions=instructions,
            tools=[
                get_weather,
                calculate,
                search_knowledge_base,
            ],
            context_providers=[history_provider],  # Auto-persist history
            name="EnterpriseAssistant",
        )

        logging.info(
            f"Initialized Agent with deployment {deployment_name}, CosmosHistoryProvider, "
            "and local tools: get_weather, calculate, search_knowledge_base"
        )

    return _agent


def get_mcp_tool() -> MCPStreamableHTTPTool:
    """
    Create an MCPStreamableHTTPTool for Microsoft Learn documentation.

    This connects to the Microsoft Learn MCP server which provides:
    - microsoft_docs_search: Search Microsoft documentation
    - microsoft_code_sample_search: Search code samples

    The tool should be used as an async context manager:
        async with get_mcp_tool() as mcp:
            response = await agent.run(content, session_id=thread_id, tools=mcp)

    Returns:
        Configured MCPStreamableHTTPTool instance.
    """
    return MCPStreamableHTTPTool(
        name="Microsoft Learn",
        url=MICROSOFT_LEARN_MCP_URL,
        description="Search Microsoft and Azure documentation and code samples",
        approval_mode="never_require",  # Auto-approve tool calls for docs search
    )


async def close_providers() -> None:
    """Close the history provider and conversation store, and release resources."""
    global _history_provider
    if _history_provider is not None:
        await _history_provider.close()
        _history_provider = None
        logging.info("Closed CosmosHistoryProvider")

    # Close the conversation store (imported here to avoid circular imports)
    from routes.threads import close_store

    await close_store()
