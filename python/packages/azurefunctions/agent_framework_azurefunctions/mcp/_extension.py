# Copyright (c) Microsoft. All rights reserved.

"""MCP Server Extension for AgentFunctionApp.

This module provides the MCPServerExtension class that adds MCP protocol support
to durable agents, allowing them to be used as tools by MCP clients.
"""

from typing import TYPE_CHECKING, Any

from agent_framework import get_logger

if TYPE_CHECKING:
    from .._app import AgentFunctionApp

logger = get_logger("agent_framework.azurefunctions.mcp")


class MCPServerExtension:
    """Extension to expose durable agents as MCP tools.

    This creates HTTP endpoints that implement the MCP protocol,
    allowing any MCP client (Claude Desktop, Cursor, etc.) to invoke
    agents as tools while maintaining durable state.

    Example:
        ```python
        from agent_framework.azurefunctions import AgentFunctionApp
        from agent_framework.azurefunctions.mcp import MCPServerExtension

        app = AgentFunctionApp("MyApp")
        app.add_agent(weather_agent)

        # Enable MCP server - all agents become MCP tools
        mcp = MCPServerExtension(app)
        app.register_mcp_server(mcp)
        ```

    Advanced Usage:
        ```python
        # Selective agent exposure
        mcp = MCPServerExtension(
            app,
            expose_agents=["WeatherAgent", "MathAgent"],
            route_prefix="/mcp/v1"
        )

        # Customize tool appearance
        mcp.configure_tool(
            "WeatherAgent",
            description="Get detailed weather information",
            display_name="Weather Tool",
            examples=["What's the weather in Seattle?"]
        )

        app.register_mcp_server(mcp)
        ```
    """

    def __init__(
        self,
        app: "AgentFunctionApp",
        expose_agents: list[str] | None = None,
        route_prefix: str = "mcp/v1",
        enable_streaming: bool = False,
        enable_resources: bool = False,
        enable_prompts: bool = False,
        auth_level: str = "function",
    ) -> None:
        """Initialize MCP server extension.

        Args:
            app: AgentFunctionApp instance to extend
            expose_agents: List of agent names to expose. If None, all agents are exposed
            route_prefix: URL prefix for MCP endpoints (default: mcp/v1, becomes /api/mcp/v1)
            enable_streaming: Enable SSE streaming
            enable_resources: Enable resource endpoints for conversation history
            enable_prompts: Enable prompt template endpoints
            auth_level: Azure Functions authentication level (anonymous, function, admin)
        """
        self.app = app
        self.expose_agents = expose_agents
        self.route_prefix = route_prefix
        self.enable_streaming = enable_streaming
        self.enable_resources = enable_resources
        self.enable_prompts = enable_prompts
        self.auth_level = auth_level
        self._tool_configs: dict[str, dict[str, Any]] = {}

        logger.info(f"MCPServerExtension initialized with route_prefix={route_prefix}")

    def configure_tool(
        self,
        agent_name: str,
        description: str | None = None,
        display_name: str | None = None,
        category: str | None = None,
        examples: list[str] | None = None,
    ) -> None:
        """Configure how an agent appears as an MCP tool.

        Args:
            agent_name: Name of the agent to configure
            description: Custom description for the tool
            display_name: Display name shown to users
            category: Category for grouping tools
            examples: Example prompts for using the tool

        Example:
            ```python
            mcp.configure_tool(
                "WeatherAgent",
                description="Get weather information for any location",
                display_name="Weather Information",
                category="utilities",
                examples=[
                    "What's the weather in Seattle?",
                    "Will it rain tomorrow in Boston?"
                ]
            )
            ```
        """
        logger.info(f"Configuring MCP tool: {agent_name}")

        self._tool_configs[agent_name] = {
            "description": description,
            "display_name": display_name,
            "category": category,
            "examples": examples,
        }

    def get_exposed_agents(self) -> list[str]:
        """Get list of agents to expose via MCP.

        Returns:
            List of agent names that should be available as MCP tools
        """
        if self.expose_agents is not None:
            # Filter to only include registered agents
            exposed = [name for name in self.expose_agents if name in self.app.agents]
            if len(exposed) < len(self.expose_agents):
                missing = set(self.expose_agents) - set(exposed)
                logger.warning(f"Some agents in expose_agents not found: {missing}")
            return exposed

        # Expose all registered agents
        return list(self.app.agents.keys())

    def register(self) -> None:
        """Register MCP endpoints with the function app.

        This is called by AgentFunctionApp.register_mcp_server() and should not
        be called directly by users.

        Registers the following endpoints:
        - POST {route_prefix} - JSON-RPC 2.0 handler
        - GET/POST {route_prefix}/tools - List available tools
        - POST {route_prefix}/call - Invoke a tool
        - GET/POST {route_prefix}/resources - List resources (if enabled)
        - GET {route_prefix}/resources/{uri} - Read resource (if enabled)
        - GET/POST {route_prefix}/prompts - List prompts (if enabled)
        """
        from ._endpoints import (
            create_call_tool_endpoint,
            create_jsonrpc_handler,
            create_list_prompts_endpoint,
            create_list_resources_endpoint,
            create_list_tools_endpoint,
            create_read_resource_endpoint,
        )

        logger.info(f"Registering MCP endpoints with route_prefix={self.route_prefix}")
        logger.info(f"Exposing {len(self.get_exposed_agents())} agents as MCP tools")

        # JSON-RPC base endpoint for MCP protocol
        logger.info(f"Registering: {self.route_prefix} (JSON-RPC handler)")
        jsonrpc_func = create_jsonrpc_handler(self)
        jsonrpc_func = self.app.durable_client_input(client_name="client")(jsonrpc_func)
        jsonrpc_func = self.app.route(
            route=f"{self.route_prefix}", methods=["POST"], auth_level=self.auth_level
        )(jsonrpc_func)

        # List tools endpoint (backward compatibility)
        logger.info(f"Registering: {self.route_prefix}/tools")
        self.app.route(
            route=f"{self.route_prefix}/tools",
            methods=["GET", "POST"],
            auth_level=self.auth_level,
        )(create_list_tools_endpoint(self))

        # Call tool endpoint (needs durable client)
        logger.info(f"Registering: {self.route_prefix}/call")
        call_tool_func = create_call_tool_endpoint(self)
        # Apply decorators
        call_tool_func = self.app.durable_client_input(client_name="client")(call_tool_func)
        call_tool_func = self.app.route(
            route=f"{self.route_prefix}/call", methods=["POST"], auth_level=self.auth_level
        )(call_tool_func)

        # Resources endpoints
        if self.enable_resources:
            logger.info(f"Registering: {self.route_prefix}/resources")
            self.app.route(
                route=f"{self.route_prefix}/resources",
                methods=["GET", "POST"],
                auth_level=self.auth_level,
            )(create_list_resources_endpoint(self))

            logger.info(f"Registering: {self.route_prefix}/resources/{{resource_uri}}")
            read_resource_func = create_read_resource_endpoint(self)
            # Apply decorators (read_resource needs durable client)
            read_resource_func = self.app.durable_client_input(client_name="client")(
                read_resource_func
            )
            read_resource_func = self.app.route(
                route=f"{self.route_prefix}/resources/{{resource_uri}}",
                methods=["GET"],
                auth_level=self.auth_level,
            )(read_resource_func)

        # Prompts endpoints
        if self.enable_prompts:
            logger.info(f"Registering: {self.route_prefix}/prompts")
            self.app.route(
                route=f"{self.route_prefix}/prompts",
                methods=["GET", "POST"],
                auth_level=self.auth_level,
            )(create_list_prompts_endpoint(self))

        logger.info("MCP server endpoints registered successfully")

        # Log exposed agents
        for agent_name in self.get_exposed_agents():
            config = self._tool_configs.get(agent_name)
            if config:
                logger.info(f"  - {agent_name}: {config.get('description', 'No description')}")
            else:
                logger.info(f"  - {agent_name}")
