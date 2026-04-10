# Copyright (c) Microsoft. All rights reserved.

"""Example showing how to configure AI agents with different trigger configurations.

This sample demonstrates how to configure agents to be accessible as both HTTP endpoints
and Model Context Protocol (MCP) tools, enabling flexible integration patterns for AI agent
consumption.

Key concepts demonstrated:
- Multi-trigger Agent Configuration: Configure agents to support HTTP triggers, MCP tool triggers, or both
- Microsoft Agent Framework Integration: Use the framework to define AI agents with specific roles
- Flexible Agent Registration: Register agents with customizable trigger configurations

This sample creates three agents with different trigger configurations:
- Joker: HTTP trigger only (default)
- StockAdvisor: MCP tool trigger only (HTTP disabled)
- PlantAdvisor: Both HTTP and MCP tool triggers enabled

Required environment variables:
- FOUNDRY_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
- FOUNDRY_MODEL: Your Azure AI Foundry deployment name

Authentication uses AzureCliCredential (Azure Identity).
"""

import os

from agent_framework import Agent
from agent_framework.azure import AgentFunctionApp
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

# Create Foundry chat client
# This uses AzureCliCredential for authentication (requires 'az login')
client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=AzureCliCredential(),
)

# Define three AI agents with different roles
# Agent 1: Joker - HTTP trigger only (default)
agent1 = Agent(
    client=client,
    name="Joker",
    instructions="You are good at telling jokes.",
)

# Agent 2: StockAdvisor - MCP tool trigger only
agent2 = Agent(
    client=client,
    name="StockAdvisor",
    instructions="Check stock prices.",
)

# Agent 3: PlantAdvisor - Both HTTP and MCP tool triggers
agent3 = Agent(
    client=client,
    name="PlantAdvisor",
    instructions="Recommend plants.",
    description="Get plant recommendations.",
)

# Create the AgentFunctionApp with selective trigger configuration
app = AgentFunctionApp(
    enable_health_check=True,
)

# Agent 1: HTTP trigger only (default)
app.add_agent(agent1)

# Agent 2: Disable HTTP trigger, enable MCP tool trigger only
app.add_agent(agent2, enable_http_endpoint=False, enable_mcp_tool_trigger=True)

# Agent 3: Enable both HTTP and MCP tool triggers
app.add_agent(agent3, enable_http_endpoint=True, enable_mcp_tool_trigger=True)
