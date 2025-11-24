"""
Example showing how to configure AI agents with different trigger configurations.

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
- AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint
- AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: Your Azure OpenAI deployment name

Authentication uses AzureCliCredential (Azure Identity).
"""

from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient

# Create Azure OpenAI Chat Client
# This uses AzureCliCredential for authentication (requires 'az login')
chat_client = AzureOpenAIChatClient()

# Define three AI agents with different roles
# Agent 1: Joker - HTTP trigger only (default)
agent1 = chat_client.create_agent(
    name="Joker",
    instructions="You are good at telling jokes.",
)

# Agent 2: StockAdvisor - MCP tool trigger only
agent2 = chat_client.create_agent(
    name="StockAdvisor",
    instructions="Check stock prices.",
)

# Agent 3: PlantAdvisor - Both HTTP and MCP tool triggers
agent3 = chat_client.create_agent(
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
