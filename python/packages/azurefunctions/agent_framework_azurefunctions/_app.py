# Copyright (c) Microsoft. All rights reserved.

"""AgentFunctionApp - Main application class.

This module provides the AgentFunctionApp class that integrates Microsoft Agent Framework
with Azure Durable Entities, enabling stateful and durable AI agent execution.
"""

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import azure.durable_functions as df
import azure.functions as func
from agent_framework import AgentProtocol, get_logger

from ._callbacks import AgentResponseCallbackProtocol
from ._entities import create_agent_entity
from ._errors import IncomingRequestError
from ._models import AgentSessionId, ChatRole, RunRequest
from ._state import AgentState

logger = get_logger("agent_framework.azurefunctions")

SESSION_ID_FIELD: str = "sessionId"
SESSION_KEY_FIELD: str = "sessionKey"
SESSION_IDENTIFIER_KEYS: tuple[str, str] = (
    SESSION_ID_FIELD,
    SESSION_KEY_FIELD,
)


class AgentFunctionApp(df.DFApp):
    """Main application class for creating durable agent function apps using Durable Entities.

    This class uses Durable Entities pattern for agent execution, providing:
    - Stateful agent conversations
    - Conversation history management
    - Signal-based operation invocation
    - Better state management than orchestrations

    Usage:
        ```python
    from agent_framework.azurefunctions import AgentFunctionApp
        from agent_framework.azure import AzureOpenAIAssistantsClient

        # Create agents with unique names
        weather_agent = AzureOpenAIAssistantsClient(...).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=[get_weather],
        )

        math_agent = AzureOpenAIAssistantsClient(...).create_agent(
            name="MathAgent",
            instructions="You are a helpful math assistant.",
            tools=[calculate],
        )

        # Option 1: Pass list of agents during initialization
        app = AgentFunctionApp(agents=[weather_agent, math_agent])

        # Option 2: Add agents after initialization
        app = AgentFunctionApp()
        app.add_agent(weather_agent)
        app.add_agent(math_agent)
        ```

    This creates:
    - HTTP trigger endpoint for each agent's requests (if enabled)
    - Durable entity for each agent's state management and execution
    - MCP tool trigger for agents (if enabled)
    - Full access to all Azure Functions capabilities

    Attributes:
        agents: Dictionary of agent name to AgentProtocol instance
        enable_health_check: Whether health check endpoint is enabled
        enable_http_endpoints: Whether HTTP endpoints are created for agents by default
        enable_mcp_tool_triggers: Whether MCP tool triggers are created for agents by default
        agent_http_endpoint_flags: Per-agent HTTP endpoint settings
        agent_mcp_tool_flags: Per-agent MCP tool trigger settings
        max_poll_retries: Maximum polling attempts when waiting for responses
        poll_interval_seconds: Delay (seconds) between polling attempts
    """

    agents: dict[str, AgentProtocol]
    enable_health_check: bool
    enable_http_endpoints: bool
    enable_mcp_tool_triggers: bool
    agent_http_endpoint_flags: dict[str, bool]
    agent_mcp_tool_flags: dict[str, bool]

    def __init__(
        self,
        agents: list[AgentProtocol] | None = None,
        http_auth_level: func.AuthLevel = func.AuthLevel.ANONYMOUS,
        enable_health_check: bool = True,
        enable_http_endpoints: bool = True,
        enable_mcp_tool_triggers: bool = False,
        max_poll_retries: int = 10,
        poll_interval_seconds: float = 0.5,
        default_callback: AgentResponseCallbackProtocol | None = None,
    ):
        """Initialize the AgentFunctionApp.

        Args:
            agents: List of agent instances to register
            http_auth_level: HTTP authentication level (default: ANONYMOUS)
            enable_health_check: Enable built-in health check endpoint (default: True)
            enable_http_endpoints: Enable HTTP endpoints for agents by default (default: True)
            enable_mcp_tool_triggers: Enable MCP tool triggers for agents by default (default: False)
            max_poll_retries: Maximum number of polling attempts when waiting for a response
            poll_interval_seconds: Delay (in seconds) between polling attempts
            default_callback: Optional callback invoked for agents without specific callbacks

        Note:
            If no agents are provided, they can be added later using add_agent().
            Per-agent settings in add_agent() override these global defaults.
        """
        logger.debug("[AgentFunctionApp] Initializing with Durable Entities...")

        # Initialize parent DFApp
        super().__init__(http_auth_level=http_auth_level)

        # Initialize agents dictionary
        self.agents = {}
        self.enable_health_check = enable_health_check
        self.enable_http_endpoints = enable_http_endpoints
        self.enable_mcp_tool_triggers = enable_mcp_tool_triggers
        self.agent_http_endpoint_flags = {}
        self.agent_mcp_tool_flags = {}
        self.default_callback = default_callback

        try:
            retries = int(max_poll_retries)
        except (TypeError, ValueError):
            retries = 10
        self.max_poll_retries = max(1, retries)

        try:
            interval = float(poll_interval_seconds)
        except (TypeError, ValueError):
            interval = 0.5
        self.poll_interval_seconds = interval if interval > 0 else 0.5

        if agents:
            # Register all provided agents
            logger.debug(f"[AgentFunctionApp] Registering {len(agents)} agent(s)")
            for agent_instance in agents:
                self.add_agent(agent_instance)

        # Setup health check if enabled
        if self.enable_health_check:
            self._setup_health_route()

        logger.debug("[AgentFunctionApp] Initialization complete")

    def add_agent(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
        enable_http_endpoint: bool | None = None,
        enable_mcp_tool_trigger: bool | None = None,
    ) -> None:
        """Add an agent to the function app after initialization.

        Args:
            agent: The Microsoft Agent Framework agent instance (must implement AgentProtocol)
                   The agent must have a 'name' attribute.
            callback: Optional callback invoked during agent execution
            enable_http_endpoint: Optional flag to enable/disable HTTP endpoint for this agent.
                                   If None, uses the app-level enable_http_endpoints setting.
            enable_mcp_tool_trigger: Optional flag to enable/disable MCP tool trigger for this agent.
                                      If None, uses the app-level enable_mcp_tool_triggers setting.

        Raises:
            ValueError: If the agent doesn't have a 'name' attribute or if an agent
                       with the same name is already registered
        """
        # Get agent name from the agent's name attribute
        name = getattr(agent, "name", None)
        if name is None:
            raise ValueError("Agent does not have a 'name' attribute. All agents must have a 'name' attribute.")

        if name in self.agents:
            raise ValueError(f"Agent with name '{name}' is already registered. Each agent must have a unique name.")

        # Resolve effective settings (per-agent overrides global)
        effective_enable_http = (
            self.enable_http_endpoints if enable_http_endpoint is None else self._coerce_to_bool(enable_http_endpoint)
        )
        effective_enable_mcp = (
            self.enable_mcp_tool_triggers
            if enable_mcp_tool_trigger is None
            else self._coerce_to_bool(enable_mcp_tool_trigger)
        )

        logger.debug(f"[AgentFunctionApp] Adding agent: {name}")
        logger.debug(f"[AgentFunctionApp] HTTP endpoint: {'enabled' if effective_enable_http else 'disabled'}")
        logger.debug(f"[AgentFunctionApp] MCP tool trigger: {'enabled' if effective_enable_mcp else 'disabled'}")

        self.agents[name] = agent
        self.agent_http_endpoint_flags[name] = effective_enable_http
        self.agent_mcp_tool_flags[name] = effective_enable_mcp

        effective_callback = callback or self.default_callback

        self._setup_agent_functions(agent, name, effective_callback, effective_enable_http, effective_enable_mcp)

        logger.debug(f"[AgentFunctionApp] Agent '{name}' added successfully")

    def _setup_agent_functions(
        self,
        agent: AgentProtocol,
        agent_name: str,
        callback: AgentResponseCallbackProtocol | None,
        enable_http_endpoint: bool,
        enable_mcp_tool_trigger: bool,
    ) -> None:
        """Set up the HTTP trigger, entity, and MCP tool trigger for a specific agent.

        Args:
            agent: The agent instance
            agent_name: The name to use for routing and entity registration
            callback: Optional callback to receive response updates
            enable_http_endpoint: Whether to create HTTP endpoint
            enable_mcp_tool_trigger: Whether to create MCP tool trigger
        """
        logger.debug(f"[AgentFunctionApp] Setting up functions for agent '{agent_name}'...")

        # Set up HTTP endpoints if enabled
        if enable_http_endpoint:
            self._setup_http_run_route(agent_name)
            self._setup_get_state_route(agent_name)
        else:
            logger.debug(f"[AgentFunctionApp] HTTP endpoints disabled for agent '{agent_name}'")

        # Always set up entity (for state management)
        self._setup_agent_entity(agent, agent_name, callback)

        # Set up MCP tool trigger if enabled
        if enable_mcp_tool_trigger:
            agent_description = getattr(agent, "description", None)
            self._setup_mcp_tool_trigger(agent_name, agent_description)
        else:
            logger.debug(f"[AgentFunctionApp] MCP tool trigger disabled for agent '{agent_name}'")

    def _setup_http_run_route(self, agent_name: str) -> None:
        """Register the POST route that triggers agent execution.

        Args:
            agent_name: The agent name (used for both routing and entity identification)
        """
        run_function_name = self._build_function_name(agent_name, "run")

        @self.function_name(run_function_name)
        @self.route(route=f"agents/{agent_name}/run", methods=["POST"])
        @self.durable_client_input(client_name="client")
        async def http_start(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
            """HTTP trigger that calls a durable entity to execute the agent and returns the result.

            Expected request body (RunRequest format):
            {
                "message": "user message to agent",
                "sessionId": "optional session id (or sessionKey)",
                "role": "user|system" (optional, default: "user"),
                "response_format": {...} (optional JSON schema for structured responses),
                "enable_tool_calls": true|false (optional, default: true)
            }
            """
            logger.debug(f"[HTTP Trigger] Received request on route: /api/agents/{agent_name}/run")

            try:
                req_body, message = self._parse_incoming_request(req)
                session_key = self._resolve_session_key(req=req, req_body=req_body)
                wait_for_completion = self._should_wait_for_completion(req=req, req_body=req_body)

                logger.debug(f"[HTTP Trigger] Message: {message}")
                logger.debug(f"[HTTP Trigger] Session Key: {session_key}")
                logger.debug(f"[HTTP Trigger] wait_for_completion: {wait_for_completion}")

                if not message:
                    logger.warning("[HTTP Trigger] Request rejected: Missing message")
                    return func.HttpResponse(
                        json.dumps({"error": "Message is required"}), status_code=400, mimetype="application/json"
                    )

                session_id = self._create_session_id(agent_name, session_key)
                correlation_id = self._generate_unique_id()

                logger.debug(f"[HTTP Trigger] Using session ID: {session_id}")
                logger.debug(f"[HTTP Trigger] Generated correlation ID: {correlation_id}")
                logger.debug("[HTTP Trigger] Calling entity to run agent...")

                entity_instance_id = session_id.to_entity_id()
                run_request = self._build_request_data(
                    req_body,
                    message,
                    session_key,
                    correlation_id,
                )
                logger.debug("Signalling entity %s with request: %s", entity_instance_id, run_request)
                await client.signal_entity(entity_instance_id, "run_agent", run_request)

                logger.debug(f"[HTTP Trigger] Signal sent to entity {session_id}")

                if wait_for_completion:
                    result = await self._get_response_from_entity(
                        client=client,
                        entity_instance_id=entity_instance_id,
                        correlation_id=correlation_id,
                        message=message,
                        session_key=session_key,
                    )

                    logger.debug(f"[HTTP Trigger] Result status: {result.get('status', 'unknown')}")
                    return func.HttpResponse(
                        json.dumps(result),
                        status_code=200 if result.get("status") == "success" else 500,
                        mimetype="application/json",
                    )

                logger.debug("[HTTP Trigger] wait_for_completion disabled; returning correlation ID")

                accepted_response = self._build_accepted_response(
                    message=message, session_key=session_key, correlation_id=correlation_id
                )

                return func.HttpResponse(json.dumps(accepted_response), status_code=202, mimetype="application/json")

            except IncomingRequestError as exc:
                logger.warning(f"[HTTP Trigger] Request rejected: {exc!s}")
                return func.HttpResponse(
                    json.dumps({"error": str(exc)}), status_code=exc.status_code, mimetype="application/json"
                )
            except ValueError as exc:
                logger.error(f"[HTTP Trigger] Invalid JSON: {exc!s}")
                return func.HttpResponse(
                    json.dumps({"error": "Invalid JSON"}), status_code=400, mimetype="application/json"
                )
            except Exception as exc:
                logger.error(f"[HTTP Trigger] Error: {exc!s}", exc_info=True)
                return func.HttpResponse(json.dumps({"error": str(exc)}), status_code=500, mimetype="application/json")

        _ = http_start

    def _setup_agent_entity(
        self,
        agent: AgentProtocol,
        agent_name: str,
        callback: AgentResponseCallbackProtocol | None,
    ) -> None:
        """Register the durable entity responsible for agent state.

        Args:
            agent: The agent instance
            agent_name: The agent name (used for both entity identification and function naming)
            callback: Optional callback for response updates
        """
        # Use the prefixed entity name for both registration and function naming
        entity_name_with_prefix = AgentSessionId.to_entity_name(agent_name)

        def entity_function(context: df.DurableEntityContext) -> None:
            """Durable entity that manages agent execution and conversation state.

            Operations:
            - run_agent: Execute the agent with a message
            - reset: Clear conversation history
            """
            entity_handler = create_agent_entity(agent, callback)
            entity_handler(context)

        # Set function name for Azure Functions (used in function.json generation)
        # Use the prefixed entity name as the function name too.
        entity_function.__name__ = entity_name_with_prefix
        self.entity_trigger(context_name="context", entity_name=entity_name_with_prefix)(entity_function)

    def _setup_get_state_route(self, agent_name: str) -> None:
        """Register the GET route for retrieving conversation state.

        Args:
            agent_name: The agent name (used for both routing and entity identification)
        """
        state_function_name = self._build_function_name(agent_name, "state")

        @self.function_name(state_function_name)
        @self.route(
            route=f"agents/{agent_name}/{{{SESSION_ID_FIELD}}}",
            methods=["GET"],
        )
        @self.durable_client_input(client_name="client")
        async def get_conversation_state(
            req: func.HttpRequest, client: df.DurableOrchestrationClient
        ) -> func.HttpResponse:
            """GET endpoint to retrieve conversation state for a given sessionId."""
            session_key = req.route_params.get(SESSION_ID_FIELD)

            logger.debug(f"[GET State] Retrieving state for session: {session_key}")

            try:
                session_id = AgentSessionId(name=agent_name, key=session_key)
                entity_instance_id = session_id.to_entity_id()

                state_response = await client.read_entity_state(entity_instance_id)

                if not state_response or not state_response.entity_exists:
                    logger.warning(f"[GET State] Session not found: {session_key}")
                    return func.HttpResponse(
                        json.dumps({"error": "Session not found"}),
                        status_code=404,
                        mimetype="application/json",
                    )

                state = state_response.entity_state
                if isinstance(state, str):
                    state = json.loads(state) if state else {}

                logger.debug(f"[GET State] Found conversation with {state.get('message_count', 0)} messages")

                return func.HttpResponse(json.dumps(state, indent=2), status_code=200, mimetype="application/json")

            except Exception as exc:
                logger.error(f"[GET State] Error: {str(exc)}", exc_info=True)
                return func.HttpResponse(
                    json.dumps({"error": str(exc)}), status_code=500, mimetype="application/json"
                )

    def _setup_mcp_tool_trigger(self, agent_name: str, agent_description: str | None) -> None:
        """
        Register an MCP tool trigger for an agent using Azure Functions native MCP support.

        This creates a native Azure Functions MCP tool trigger that exposes the agent
        as an MCP tool, allowing it to be invoked by MCP-compatible clients.

        Args:
            agent_name: The agent name (used as the MCP tool name)
            agent_description: Optional description for the MCP tool (shown to clients)
        """
        # Match .NET naming convention: mcptool-{agentName}
        mcp_function_name = f"mcptool-{agent_name}"

        # Define tool properties as JSON (MCP tool parameters)
        tool_properties = json.dumps(
            [
                {
                    "propertyName": "query",
                    "propertyType": "string",
                    "description": "The query to send to the agent.",
                    "isRequired": True,
                    "isArray": False,
                },
                {
                    "propertyName": "threadId",
                    "propertyType": "string",
                    "description": "Optional thread identifier for conversation continuity.",
                    "isRequired": False,
                    "isArray": False,
                },
            ]
        )

        @self.function_name(mcp_function_name)
        @self.mcp_tool_trigger(
            arg_name="context",
            tool_name=agent_name,
            description=agent_description or f"Interact with {agent_name} agent",
            tool_properties=tool_properties,
            data_type=func.DataType.UNDEFINED,
        )
        @self.durable_client_input(client_name="client")
        async def mcp_tool_handler(context: str, client: df.DurableOrchestrationClient) -> str:
            """Handle MCP tool invocation for the agent."""
            return await self._handle_mcp_tool_invocation(agent_name=agent_name, context=context, client=client)

        logger.info(f"[AgentFunctionApp] Registered MCP tool trigger: {agent_name}")

    async def _handle_mcp_tool_invocation(
        self, agent_name: str, context: Any, client: df.DurableOrchestrationClient
    ) -> str:
        """
        Handle an MCP tool invocation.

        This method processes MCP tool requests and delegates to the agent entity.

        Args:
            agent_name: Name of the agent being invoked
            context: MCP tool invocation context containing arguments
            client: Durable orchestration client

        Returns:
            Agent response text

        Raises:
            ValueError: If required arguments are missing
            RuntimeError: If agent execution fails
        """
        # Parse context if it's a JSON string
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid MCP context format: {e}")
        
        # Extract arguments from MCP context
        arguments = context.get("arguments", {}) if isinstance(context, dict) else {}

        # Validate required 'query' argument
        query = arguments.get("query")
        if not query or not isinstance(query, str):
            raise ValueError("MCP Tool invocation is missing required 'query' argument of type string.")

        # Extract optional threadId
        thread_id = arguments.get("threadId")

        # Create or parse session ID
        if thread_id and isinstance(thread_id, str) and thread_id.strip():
            try:
                session_id = AgentSessionId.parse(thread_id)
            except Exception:
                # If parsing fails, create new session ID with thread_id as key
                session_id = AgentSessionId(name=agent_name, key=thread_id)
        else:
            # Generate new session ID
            session_id = AgentSessionId.with_random_key(agent_name)

        # Build entity instance ID
        entity_instance_id = session_id.to_entity_id()

        # Create run request
        correlation_id = self._generate_unique_id()
        run_request = self._build_request_data(
            req_body={"message": query, "role": "user"},
            message=query,
            conversation_id=str(session_id),
            correlation_id=correlation_id,
        )

        logger.info(
            f"[MCP Tool] Invoking agent '{agent_name}' with query: {query[:50]}..." + ("" if len(query) <= 50 else "")
        )

        # Signal entity to run agent
        await client.signal_entity(entity_instance_id, "run_agent", run_request)

        # Poll for response (similar to HTTP handler)
        try:
            result = await self._get_response_from_entity(
                client=client,
                entity_instance_id=entity_instance_id,
                correlation_id=correlation_id,
                message=query,
                session_key=str(session_id),
            )

            # Extract and return response text
            if result.get("status") == "success":
                response_text = result.get("response", "No response")
                logger.info(f"[MCP Tool] Agent '{agent_name}' responded successfully")
                return response_text
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"[MCP Tool] Agent '{agent_name}' execution failed: {error_msg}")
                raise RuntimeError(f"Agent execution failed: {error_msg}")

        except Exception as exc:
            logger.error(f"[MCP Tool] Error invoking agent '{agent_name}': {str(exc)}", exc_info=True)
            raise

    def _setup_health_route(self) -> None:
        """Register the optional health check route."""

        @self.route(route="health", methods=["GET"])
        def health_check(req: func.HttpRequest) -> func.HttpResponse:
            """Built-in health check endpoint."""
            agent_info = [
                {
                    "name": name,
                    "type": type(agent).__name__,
                    "httpEndpointEnabled": self.agent_http_endpoint_flags.get(name, self.enable_http_endpoints),
                    "mcpToolTriggerEnabled": self.agent_mcp_tool_flags.get(name, self.enable_mcp_tool_triggers),
                }
                for name, agent in self.agents.items()
            ]
            return func.HttpResponse(
                json.dumps({"status": "healthy", "agents": agent_info, "agent_count": len(self.agents)}),
                status_code=200,
                mimetype="application/json",
            )

        _ = health_check

    @staticmethod
    def _build_function_name(agent_name: str, suffix: str) -> str:
        """Generate a unique, Azure Functions-compliant name for an agent function."""
        sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", agent_name or "agent").strip("_")

        if not sanitized:
            sanitized = "agent"

        if sanitized[0].isdigit():
            sanitized = f"agent_{sanitized}"

        return f"{sanitized}_{suffix}"

    async def _get_response_from_entity(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
        correlation_id: str,
        message: str,
        session_key: str,
    ) -> dict[str, Any]:
        """Poll the entity state until a response is available or timeout occurs."""
        import asyncio

        max_retries = self.max_poll_retries
        interval = self.poll_interval_seconds
        retry_count = 0
        result: dict[str, Any] | None = None

        logger.debug(f"[HTTP Trigger] Waiting for response with correlation ID: {correlation_id}")

        while retry_count < max_retries:
            await asyncio.sleep(interval)

            result = await self._poll_entity_for_response(
                client=client,
                entity_instance_id=entity_instance_id,
                correlation_id=correlation_id,
                message=message,
                session_key=session_key,
            )
            if result is not None:
                break

            logger.debug(f"[HTTP Trigger] Response not available yet (retry {retry_count})")
            retry_count += 1

        if result is not None:
            return result

        logger.warning(
            f"[HTTP Trigger] Response with correlation ID {correlation_id} "
            f"not found in time (waited {max_retries * interval} seconds)"
        )
        return await self._build_timeout_result(message=message, session_key=session_key, correlation_id=correlation_id)

    async def _poll_entity_for_response(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
        correlation_id: str,
        message: str,
        session_key: str,
    ) -> dict[str, Any] | None:
        result: dict[str, Any] | None = None
        try:
            state = await self._read_cached_state(client, entity_instance_id)

            if state is None:
                return None

            agent_response = state.try_get_agent_response(correlation_id)
            if agent_response:
                result = self._build_success_result(
                    response_data=agent_response,
                    message=message,
                    session_key=session_key,
                    correlation_id=correlation_id,
                    state=state,
                )
                logger.debug(f"[HTTP Trigger] Found response for correlation ID: {correlation_id}")

        except Exception as exc:
            logger.warning(f"[HTTP Trigger] Error reading entity state: {exc}")

        return result

    async def _build_timeout_result(self, message: str, session_key: str, correlation_id: str) -> dict[str, Any]:
        """Create the timeout response."""
        return {
            "response": "Agent is still processing or timed out...",
            "message": message,
            SESSION_ID_FIELD: session_key,
            "status": "timeout",
            "correlationId": correlation_id,
        }

    def _build_success_result(
        self, response_data: dict[str, Any], message: str, session_key: str, correlation_id: str, state: AgentState
    ) -> dict[str, Any]:
        """Build the success result returned to the HTTP caller."""
        return {
            "response": response_data.get("content"),
            "message": message,
            SESSION_ID_FIELD: session_key,
            "status": "success",
            "message_count": response_data.get("message_count", state.message_count),
            "correlationId": correlation_id,
            "timestamp": response_data.get("timestamp"),
        }

    def _build_request_data(
        self, req_body: dict[str, Any], message: str, conversation_id: str, correlation_id: str
    ) -> dict[str, Any]:
        """Create the durable entity request payload."""
        enable_tool_calls_value = req_body.get("enable_tool_calls")
        enable_tool_calls = True if enable_tool_calls_value is None else self._coerce_to_bool(enable_tool_calls_value)

        role = self._coerce_chat_role(req_body.get("role"))

        return RunRequest(
            message=message,
            role=role,
            response_format=req_body.get("response_format"),
            enable_tool_calls=enable_tool_calls,
            conversation_id=conversation_id,
            correlation_id=correlation_id,
        ).to_dict()

    def _build_accepted_response(self, message: str, session_key: str, correlation_id: str) -> dict[str, Any]:
        """Build the response returned when not waiting for completion."""
        return {
            "response": "Agent request accepted",
            "message": message,
            SESSION_ID_FIELD: session_key,
            "status": "accepted",
            "correlationId": correlation_id,
        }

    def _generate_unique_id(self) -> str:
        """Generate a new unique identifier."""
        import uuid

        return uuid.uuid4().hex

    def _create_session_id(self, func_name: str, session_key: str | None) -> AgentSessionId:
        """Create a session identifier using the provided key or a random value."""
        if session_key:
            return AgentSessionId(name=func_name, key=session_key)
        return AgentSessionId.with_random_key(name=func_name)

    def _resolve_session_key(self, req: func.HttpRequest, req_body: dict[str, Any]) -> str:
        """Retrieve the session key from request body or query parameters."""
        params = req.params or {}

        for key in SESSION_IDENTIFIER_KEYS:
            if key in req_body:
                value = req_body.get(key)
                if value is not None:
                    return str(value)

        for key in SESSION_IDENTIFIER_KEYS:
            if key in params:
                value = params.get(key)
                if value is not None:
                    return str(value)

        logger.debug("[HTTP Trigger] No session identifier provided; using random session key")
        return self._generate_unique_id()

    def _parse_incoming_request(self, req: func.HttpRequest) -> tuple[dict[str, Any], Any]:
        """Parse the incoming run request supporting JSON and plain text bodies."""
        headers: dict[str, str] = {}
        raw_headers = req.headers
        if isinstance(raw_headers, Mapping):
            headers_mapping = cast(Mapping[Any, Any], raw_headers)
            for key, value in headers_mapping.items():
                if value is not None:
                    headers[str(key)] = str(value)

        content_type_header = headers.get("content-type")

        normalized_content_type = ""
        if content_type_header:
            normalized_content_type = content_type_header.split(";")[0].strip().lower()

        if normalized_content_type in {"application/json"} or normalized_content_type.endswith("+json"):
            parser = self._parse_json_body
        else:
            parser = self._parse_text_body

        return parser(req)

    @staticmethod
    def _parse_json_body(req: func.HttpRequest) -> tuple[dict[str, Any], Any]:
        req_body = req.get_json()
        if not isinstance(req_body, dict):
            raise IncomingRequestError("Invalid JSON payload. Expected an object.")

        typed_req_body = cast(dict[str, Any], req_body)
        message_value = typed_req_body.get("message", "")
        message = message_value if isinstance(message_value, str) else str(message_value)
        return typed_req_body, message

    @staticmethod
    def _parse_text_body(req: func.HttpRequest) -> tuple[dict[str, Any], Any]:
        body_bytes = req.get_body()
        text_body = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        message = text_body.strip()

        if not message:
            raise IncomingRequestError("Message is required")

        return {}, message

    def _should_wait_for_completion(self, req: func.HttpRequest, req_body: dict[str, Any]) -> bool:
        """Determine whether the caller requested to wait for completion."""
        header_value = None
        raw_headers = req.headers
        if isinstance(raw_headers, Mapping):
            headers_mapping = cast(Mapping[Any, Any], raw_headers)
            for key, value in headers_mapping.items():
                if str(key).lower() == "x-wait-for-completion":
                    header_value = value
                    break

        if header_value is not None:
            return self._coerce_to_bool(header_value)

        for key in ("wait_for_completion", "waitForCompletion", "WaitForCompletion"):
            if key in req_body:
                return self._coerce_to_bool(req_body.get(key))

        return False

    def _coerce_chat_role(self, value: Any) -> ChatRole:
        """Convert user-provided role to ChatRole, defaulting to user on error."""
        if isinstance(value, ChatRole):
            return value
        if isinstance(value, str):
            try:
                return ChatRole(value.strip().lower())
            except ValueError:
                logger.warning("[AgentFunctionApp] Invalid role '%s'; defaulting to user", value)
        return ChatRole.USER

    async def _read_cached_state(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
    ) -> AgentState | None:
        """Read the entity state from storage.

        Args:
            client: Durable orchestration client
            entity_instance_id: Entity ID to read

        Returns:
            AgentState if entity exists, None otherwise
        """
        state_response = await client.read_entity_state(entity_instance_id)
        if not state_response or not state_response.entity_exists:
            return None

        state_payload = state_response.entity_state
        if not isinstance(state_payload, dict):
            return None

        agent_state = AgentState()
        agent_state.restore_state(state_payload)
        return agent_state

    def _coerce_to_bool(self, value: Any) -> bool:
        """Convert various representations into a boolean flag."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "on"}
        return False
