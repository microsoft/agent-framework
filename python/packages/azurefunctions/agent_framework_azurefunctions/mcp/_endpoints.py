# Copyright (c) Microsoft. All rights reserved.

"""MCP Protocol HTTP Endpoints.

This module implements the HTTP handlers for MCP protocol operations.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import azure.durable_functions as df
import azure.functions as func
from agent_framework import get_logger

if TYPE_CHECKING:
    from ._extension import MCPServerExtension

logger = get_logger("agent_framework.azurefunctions.mcp")


def create_list_tools_endpoint(
    extension: "MCPServerExtension",
) -> Callable[[func.HttpRequest], Awaitable[func.HttpResponse]]:
    """Create endpoint to list available tools (agents).

    Returns:
        Async function that handles GET/POST requests to list MCP tools
    """

    async def list_tools(req: func.HttpRequest) -> func.HttpResponse:
        """MCP endpoint: List available tools.

        Returns JSON response with tool definitions for all exposed agents.

        Example response:
        {
            "tools": [
                {
                    "name": "WeatherAgent",
                    "description": "Get weather information",
                    "inputSchema": {...}
                }
            ]
        }
        """
        logger.info("MCP: Listing available tools")

        tools = []

        for agent_name in extension.get_exposed_agents():
            agent = extension.app.agents.get(agent_name)
            if not agent:
                logger.warning(f"Agent '{agent_name}' not found in app registry")
                continue

            # Get custom configuration or use defaults
            config = extension._tool_configs.get(agent_name, {})

            tool = {
                "name": agent_name,
                "description": config.get("description") or f"Invoke {agent_name} agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to send to the agent",
                        },
                        "sessionId": {
                            "type": "string",
                            "description": "Optional session ID for conversation continuity",
                        },
                        "enable_tool_calls": {
                            "type": "boolean",
                            "description": "Whether to allow the agent to use tools (default: true)",
                        },
                    },
                    "required": ["message"],
                },
            }

            # Add custom fields if configured
            if config.get("display_name"):
                tool["displayName"] = config["display_name"]
            if config.get("category"):
                tool["category"] = config["category"]
            if config.get("examples"):
                tool["examples"] = config["examples"]

            tools.append(tool)

        logger.info(f"MCP: Returning {len(tools)} tools")

        return func.HttpResponse(
            json.dumps({"tools": tools}), mimetype="application/json", status_code=200
        )

    return list_tools


def create_call_tool_endpoint(
    extension: "MCPServerExtension",
) -> Callable[[func.HttpRequest, df.DurableOrchestrationClient], Awaitable[func.HttpResponse]]:
    """Create endpoint to invoke a tool (agent).

    Returns:
        Async function that handles POST requests to call MCP tools
    """

    async def call_tool(
        req: func.HttpRequest, client: df.DurableOrchestrationClient
    ) -> func.HttpResponse:
        """MCP endpoint: Call a tool (invoke an agent).

        Expects JSON request body with:
        {
            "name": "WeatherAgent",
            "arguments": {
                "message": "What's the weather?",
                "sessionId": "optional-session-id",
                "enable_tool_calls": true
            }
        }

        Returns:
        {
            "content": [{"type": "text", "text": "Response text"}],
            "metadata": {
                "sessionId": "session-id",
                "messageCount": 1,
                "timestamp": "..."
            }
        }
        """
        try:
            body = req.get_json()
        except ValueError:
            logger.error("MCP: Invalid JSON in request body")
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON"}),
                mimetype="application/json",
                status_code=400,
            )

        # Extract tool name and arguments
        tool_name = body.get("name")
        arguments = body.get("arguments", {})

        logger.info(f"MCP: Call tool request - name={tool_name}")

        if not tool_name:
            logger.error("MCP: Missing tool name in request")
            return func.HttpResponse(
                json.dumps({"error": "Missing tool name"}),
                mimetype="application/json",
                status_code=400,
            )

        # Check if agent exists and is exposed
        if tool_name not in extension.get_exposed_agents():
            logger.error(f"MCP: Tool '{tool_name}' not found or not exposed")
            return func.HttpResponse(
                json.dumps({"error": f"Tool '{tool_name}' not found"}),
                mimetype="application/json",
                status_code=404,
            )

        # Get agent
        agent = extension.app.agents.get(tool_name)
        if not agent:
            logger.error(f"MCP: Agent '{tool_name}' not found in registry")
            return func.HttpResponse(
                json.dumps({"error": f"Agent '{tool_name}' not found"}),
                mimetype="application/json",
                status_code=404,
            )

        # Extract parameters
        message = arguments.get("message")
        session_id = arguments.get("sessionId")
        enable_tool_calls = arguments.get("enable_tool_calls", True)

        if not message:
            logger.error("MCP: Missing 'message' in arguments")
            return func.HttpResponse(
                json.dumps({"error": "Missing 'message' in arguments"}),
                mimetype="application/json",
                status_code=400,
            )

        # Create or parse session ID
        from .._models import AgentSessionId

        if session_id:
            try:
                session = AgentSessionId.parse(session_id)
                logger.info(f"MCP: Using existing session - {session_id}")
            except Exception as e:
                logger.error(f"MCP: Invalid session ID format - {session_id}: {e}")
                return func.HttpResponse(
                    json.dumps({"error": f"Invalid session ID format: {str(e)}"}),
                    mimetype="application/json",
                    status_code=400,
                )
        else:
            session = AgentSessionId.with_random_key(tool_name)
            logger.info(f"MCP: Created new session - {session}")

        # Invoke agent via durable entity
        entity_id = session.to_entity_id()

        try:
            logger.info(f"MCP: Invoking entity - {entity_id}")

            # Generate correlation ID for tracking this request
            correlation_id = str(uuid.uuid4())

            # Signal the entity to run the agent
            await client.signal_entity(
                entity_id,
                "run_agent",
                {
                    "message": message,
                    "enable_tool_calls": enable_tool_calls,
                    "mcp_invocation": True,
                    "correlation_id": correlation_id,
                    "conversation_id": session.key,
                },
            )

            logger.info(f"MCP: Signal sent to entity - {entity_id}")

            # Poll for response using the app's method
            result = await extension.app._get_response_from_entity(
                client=client,
                entity_instance_id=entity_id,
                correlation_id=correlation_id,
                message=message,
                session_key=session.key,
            )

            logger.info(f"MCP: Entity invocation successful - {entity_id}")

            # Format response for MCP
            response_text = result.get("response", "")
            if not response_text and result.get("error"):
                response_text = f"Error: {result.get('error')}"

            response: dict[str, Any] = {
                "content": [{"type": "text", "text": response_text}],
                "metadata": {
                    "sessionId": str(session),
                    "messageCount": result.get("message_count", 0),
                    "agentName": tool_name,
                },
            }

            # Add timestamp if available
            if result.get("timestamp"):
                response["metadata"]["timestamp"] = result["timestamp"]

            # Mark as error if agent returned error
            if result.get("status") == "error":
                response["isError"] = True

            return func.HttpResponse(
                json.dumps(response), mimetype="application/json", status_code=200
            )

        except Exception as e:
            logger.error(f"MCP: Error invoking entity - {entity_id}: {str(e)}", exc_info=True)
            return func.HttpResponse(
                json.dumps(
                    {
                        "content": [{"type": "text", "text": f"Error invoking agent: {str(e)}"}],
                        "isError": True,
                        "metadata": {"sessionId": str(session), "agentName": tool_name},
                    }
                ),
                mimetype="application/json",
                status_code=500,
            )

    return call_tool


def create_list_resources_endpoint(
    extension: "MCPServerExtension",
) -> Callable[[func.HttpRequest], Awaitable[func.HttpResponse]]:
    """Create endpoint to list available resources (conversation histories)."""

    async def list_resources(req: func.HttpRequest) -> func.HttpResponse:
        """MCP endpoint: List resources."""
        logger.info("MCP: Listing resources (not yet implemented)")

        resources: list[Any] = []

        return func.HttpResponse(
            json.dumps({"resources": resources}), mimetype="application/json", status_code=200
        )

    return list_resources


def create_read_resource_endpoint(
    extension: "MCPServerExtension",
) -> Callable[
    [func.HttpRequest, str, df.DurableOrchestrationClient], Awaitable[func.HttpResponse]
]:
    """Create endpoint to read a resource (conversation history)."""

    async def read_resource(
        req: func.HttpRequest, resource_uri: str, client: df.DurableOrchestrationClient
    ) -> func.HttpResponse:
        """MCP endpoint: Read resource."""
        logger.info(f"MCP: Reading resource {resource_uri} (not yet implemented)")

        return func.HttpResponse(
            json.dumps({"error": "Resources not yet implemented"}),
            mimetype="application/json",
            status_code=501,  # Not Implemented
        )

    return read_resource


def create_list_prompts_endpoint(
    extension: "MCPServerExtension",
) -> Callable[[func.HttpRequest], Awaitable[func.HttpResponse]]:
    """Create endpoint to list available prompts."""

    async def list_prompts(req: func.HttpRequest) -> func.HttpResponse:
        """MCP endpoint: List prompts."""
        logger.info("MCP: Listing prompts (not yet implemented)")

        prompts: list[Any] = []

        return func.HttpResponse(
            json.dumps({"prompts": prompts}), mimetype="application/json", status_code=200
        )

    return list_prompts


def create_jsonrpc_handler(
    extension: "MCPServerExtension",
) -> Callable[[func.HttpRequest, df.DurableOrchestrationClient], Awaitable[func.HttpResponse]]:
    """Create JSON-RPC 2.0 message handler for MCP protocol.

    This handles the full MCP protocol including initialize handshake.
    MCP clients send JSON-RPC messages to the base endpoint.
    """

    async def handle_jsonrpc(
        req: func.HttpRequest, client: df.DurableOrchestrationClient
    ) -> func.HttpResponse:
        """Handle JSON-RPC 2.0 messages from MCP clients.

        Supported methods:
        - initialize: Handshake to establish connection
        - tools/list: List available tools
        - tools/call: Invoke a tool
        """
        try:
            body = req.get_json()
        except ValueError:
            logger.error("MCP JSON-RPC: Invalid JSON in request")
            return func.HttpResponse(
                json.dumps(
                    {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
                ),
                mimetype="application/json",
                status_code=400,
            )

        # Extract JSON-RPC fields
        jsonrpc_version = body.get("jsonrpc")
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")

        logger.info(f"MCP JSON-RPC: method={method}, id={request_id}")

        # Validate JSON-RPC version
        if jsonrpc_version != "2.0":
            return func.HttpResponse(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request - must be JSON-RPC 2.0",
                        },
                        "id": request_id,
                    }
                ),
                mimetype="application/json",
                status_code=400,
            )

        # Handle notifications (requests without an id)
        if request_id is None:
            # Notifications don't expect a response
            if method == "notifications/initialized":
                logger.info("MCP JSON-RPC: Client initialized notification received")
                return func.HttpResponse(status_code=204)  # No Content
            elif method and method.startswith("notifications/"):
                logger.info(f"MCP JSON-RPC: Notification received: {method}")
                return func.HttpResponse(status_code=204)  # No Content
            else:
                # Invalid notification
                logger.warning(f"MCP JSON-RPC: Invalid notification: {method}")
                return func.HttpResponse(status_code=204)  # Still return 204 for notifications

        # Handle different methods
        if method == "initialize":
            # MCP handshake
            logger.info("MCP JSON-RPC: Handling initialize request")
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {} if extension.enable_resources else None,
                    "prompts": {} if extension.enable_prompts else None,
                },
                "serverInfo": {"name": "durable-agent-mcp-server", "version": "1.0.0"},
            }
            # Remove None capabilities
            result["capabilities"] = {
                k: v for k, v in result["capabilities"].items() if v is not None
            }

            return func.HttpResponse(
                json.dumps({"jsonrpc": "2.0", "result": result, "id": request_id}),
                mimetype="application/json",
                status_code=200,
            )

        elif method == "tools/list":
            # List available tools
            logger.info("MCP JSON-RPC: Handling tools/list request")
            tools = []

            for agent_name in extension.get_exposed_agents():
                agent = extension.app.agents.get(agent_name)
                if not agent:
                    continue

                config = extension._tool_configs.get(agent_name, {})

                tool = {
                    "name": agent_name,
                    "description": config.get("description") or f"Invoke {agent_name} agent",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Message to send to the agent",
                            },
                            "sessionId": {
                                "type": "string",
                                "description": "Optional session ID for conversation continuity",
                            },
                        },
                        "required": ["message"],
                    },
                }

                if config.get("display_name"):
                    tool["displayName"] = config["display_name"]
                if config.get("category"):
                    tool["category"] = config["category"]
                if config.get("examples"):
                    tool["examples"] = config["examples"]

                tools.append(tool)

            return func.HttpResponse(
                json.dumps({"jsonrpc": "2.0", "result": {"tools": tools}, "id": request_id}),
                mimetype="application/json",
                status_code=200,
            )

        elif method == "tools/call":
            # Invoke a tool
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            logger.info(f"MCP JSON-RPC: Handling tools/call - name={tool_name}")

            if not tool_name:
                return func.HttpResponse(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32602, "message": "Missing tool name"},
                            "id": request_id,
                        }
                    ),
                    mimetype="application/json",
                    status_code=400,
                )

            # Check if agent exists
            if tool_name not in extension.get_exposed_agents():
                return func.HttpResponse(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32602, "message": f"Tool '{tool_name}' not found"},
                            "id": request_id,
                        }
                    ),
                    mimetype="application/json",
                    status_code=404,
                )

            # Extract parameters
            message = arguments.get("message")
            session_id = arguments.get("sessionId")
            enable_tool_calls = arguments.get("enable_tool_calls", True)

            if not message:
                return func.HttpResponse(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32602, "message": "Missing 'message' in arguments"},
                            "id": request_id,
                        }
                    ),
                    mimetype="application/json",
                    status_code=400,
                )

            # Create or parse session ID
            from .._models import AgentSessionId

            if session_id:
                try:
                    session = AgentSessionId.parse(session_id)
                except Exception as e:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "error": {"code": -32602, "message": f"Invalid session ID: {str(e)}"},
                                "id": request_id,
                            }
                        ),
                        mimetype="application/json",
                        status_code=400,
                    )
            else:
                session = AgentSessionId.with_random_key(tool_name)

            # Invoke agent
            entity_id = session.to_entity_id()

            try:
                # Generate correlation ID for tracking this request
                correlation_id = str(uuid.uuid4())

                # Signal the entity to run the agent
                await client.signal_entity(
                    entity_id,
                    "run_agent",
                    {
                        "message": message,
                        "enable_tool_calls": enable_tool_calls,
                        "mcp_invocation": True,
                        "correlation_id": correlation_id,
                        "conversation_id": session.key,
                    },
                )

                # Poll for response using the app's method
                result = await extension.app._get_response_from_entity(
                    client=client,
                    entity_instance_id=entity_id,
                    correlation_id=correlation_id,
                    message=message,
                    session_key=session.key,
                )

                response_text = result.get("response", "")
                if not response_text and result.get("error"):
                    response_text = f"Error: {result.get('error')}"

                return func.HttpResponse(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "result": {
                                "content": [{"type": "text", "text": response_text}],
                                "isError": result.get("status") == "error",
                            },
                            "id": request_id,
                        }
                    ),
                    mimetype="application/json",
                    status_code=200,
                )

            except Exception as e:
                logger.error(f"MCP JSON-RPC: Error invoking tool: {str(e)}", exc_info=True)
                return func.HttpResponse(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                            "id": request_id,
                        }
                    ),
                    mimetype="application/json",
                    status_code=500,
                )

        else:
            # Method not found
            logger.warning(f"MCP JSON-RPC: Unknown method: {method}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": request_id,
                    }
                ),
                mimetype="application/json",
                status_code=404,
            )

    return handle_jsonrpc
