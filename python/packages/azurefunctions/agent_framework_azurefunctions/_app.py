# Copyright (c) Microsoft. All rights reserved.

"""AgentFunctionApp - Main application class.

This module provides the AgentFunctionApp class that integrates Microsoft Agent Framework
with Azure Durable Entities, enabling stateful and durable AI agent execution.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

import azure.durable_functions as df
import azure.functions as func
from agent_framework import AgentProtocol, get_logger

from ._callbacks import AgentResponseCallbackProtocol
from ._constants import (
    DEFAULT_MAX_POLL_RETRIES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    MIMETYPE_APPLICATION_JSON,
    MIMETYPE_TEXT_PLAIN,
    REQUEST_RESPONSE_FORMAT_JSON,
    REQUEST_RESPONSE_FORMAT_TEXT,
    THREAD_ID_FIELD,
    THREAD_ID_HEADER,
    WAIT_FOR_RESPONSE_FIELD,
    WAIT_FOR_RESPONSE_HEADER,
)
from ._durable_agent_state import DurableAgentState
from ._entities import create_agent_entity
from ._errors import IncomingRequestError
from ._models import AgentSessionId, RunRequest
from ._orchestration import AgentOrchestrationContextType, DurableAIAgent

logger = get_logger("agent_framework.azurefunctions")

EntityHandler = Callable[[df.DurableEntityContext], None]
HandlerT = TypeVar("HandlerT", bound=Callable[..., Any])


@dataclass
class AgentMetadata:
    """Metadata for a registered agent.

    Attributes:
        agent: The agent instance implementing AgentProtocol
        http_endpoint_enabled: Whether HTTP endpoint is enabled for this agent
        mcp_tool_enabled: Whether MCP tool endpoint is enabled for this agent
    """

    agent: AgentProtocol
    http_endpoint_enabled: bool
    mcp_tool_enabled: bool


if TYPE_CHECKING:

    class DFAppBase:
        def __init__(self, http_auth_level: func.AuthLevel = func.AuthLevel.FUNCTION) -> None: ...

        def function_name(self, name: str) -> Callable[[HandlerT], HandlerT]: ...

        def route(self, route: str, methods: list[str]) -> Callable[[HandlerT], HandlerT]: ...

        def durable_client_input(self, client_name: str) -> Callable[[HandlerT], HandlerT]: ...

        def entity_trigger(self, context_name: str, entity_name: str) -> Callable[[EntityHandler], EntityHandler]: ...

        def orchestration_trigger(self, context_name: str) -> Callable[[HandlerT], HandlerT]: ...

        def activity_trigger(self, input_name: str) -> Callable[[HandlerT], HandlerT]: ...

        def mcp_tool_trigger(
            self,
            arg_name: str,
            tool_name: str,
            description: str,
            tool_properties: str,
            data_type: func.DataType,
        ) -> Callable[[HandlerT], HandlerT]: ...

else:
    DFAppBase = df.DFApp  # type: ignore[assignment]


class AgentFunctionApp(DFAppBase):
    """Main application class for creating durable agent function apps using Durable Entities.

    This class uses Durable Entities pattern for agent execution, providing:

    - Stateful agent conversations
    - Conversation history management
    - Signal-based operation invocation
    - Better state management than orchestrations

    Example:
    -------

    .. code-block:: python

        from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient

        # Create agents with unique names
        weather_agent = AzureOpenAIChatClient(...).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=[get_weather],
        )

        math_agent = AzureOpenAIChatClient(...).create_agent(
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


        @app.orchestration_trigger(context_name="context")
        def my_orchestration(context):
            writer = app.get_agent(context, "WeatherAgent")
            thread = writer.get_new_thread()
            forecast_task = writer.run("What's the forecast?", thread=thread)
            forecast = yield forecast_task
            return forecast

    This creates:

    - HTTP trigger endpoint for each agent's requests (if enabled)
    - Durable entity for each agent's state management and execution
    - Full access to all Azure Functions capabilities

    Attributes:
        agents: Dictionary of agent name to AgentProtocol instance
        enable_health_check: Whether health check endpoint is enabled
        enable_http_endpoints: Whether HTTP endpoints are created for agents
        enable_mcp_tool_trigger: Whether MCP tool triggers are created for agents
        max_poll_retries: Maximum polling attempts when waiting for responses
        poll_interval_seconds: Delay (seconds) between polling attempts
    """

    _agent_metadata: dict[str, AgentMetadata]
    enable_health_check: bool
    enable_http_endpoints: bool
    enable_mcp_tool_trigger: bool

    def __init__(
        self,
        agents: list[AgentProtocol] | None = None,
        http_auth_level: func.AuthLevel = func.AuthLevel.FUNCTION,
        enable_health_check: bool = True,
        enable_http_endpoints: bool = True,
        max_poll_retries: int = DEFAULT_MAX_POLL_RETRIES,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        enable_mcp_tool_trigger: bool = False,
        default_callback: AgentResponseCallbackProtocol | None = None,
    ):
        """Initialize the AgentFunctionApp.

        :param agents: List of agent instances to register.
        :param http_auth_level: HTTP authentication level (default: ``func.AuthLevel.FUNCTION``).
        :param enable_health_check: Enable the built-in health check endpoint (default: ``True``).
        :param enable_http_endpoints: Enable HTTP endpoints for agents (default: ``True``).
        :param enable_mcp_tool_trigger: Enable MCP tool triggers for agents (default: ``False``).
            When enabled, agents will be exposed as MCP tools that can be invoked by MCP-compatible clients.
        :param max_poll_retries: Maximum polling attempts when waiting for a response.
            Defaults to ``DEFAULT_MAX_POLL_RETRIES``.
        :param poll_interval_seconds: Delay in seconds between polling attempts.
            Defaults to ``DEFAULT_POLL_INTERVAL_SECONDS``.
        :param default_callback: Optional callback invoked for agents without specific callbacks.

        :note: If no agents are provided, they can be added later using :meth:`add_agent`.
        """
        logger.debug("[AgentFunctionApp] Initializing with Durable Entities...")

        # Initialize parent DFApp
        super().__init__(http_auth_level=http_auth_level)

        # Initialize agent metadata dictionary
        self._agent_metadata = {}
        self.enable_health_check = enable_health_check
        self.enable_http_endpoints = enable_http_endpoints
        self.enable_mcp_tool_trigger = enable_mcp_tool_trigger
        self.default_callback = default_callback

        try:
            retries = int(max_poll_retries)
        except (TypeError, ValueError):
            retries = DEFAULT_MAX_POLL_RETRIES
        self.max_poll_retries = max(1, retries)

        try:
            interval = float(poll_interval_seconds)
        except (TypeError, ValueError):
            interval = DEFAULT_POLL_INTERVAL_SECONDS
        self.poll_interval_seconds = interval if interval > 0 else DEFAULT_POLL_INTERVAL_SECONDS

        if agents:
            # Register all provided agents
            logger.debug(f"[AgentFunctionApp] Registering {len(agents)} agent(s)")
            for agent_instance in agents:
                self.add_agent(agent_instance)

        # Setup health check if enabled
        if self.enable_health_check:
            self._setup_health_route()

        logger.debug("[AgentFunctionApp] Initialization complete")

    @property
    def agents(self) -> dict[str, AgentProtocol]:
        """Returns dict of agent names to agent instances.

        Returns:
            Dictionary mapping agent names to their AgentProtocol instances.
        """
        return {name: metadata.agent for name, metadata in self._agent_metadata.items()}

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
                                  The app level enable_http_endpoints setting will override this setting.
            enable_mcp_tool_trigger: Optional flag to enable/disable MCP tool trigger for this agent.
                                     The app level enable_mcp_tool_trigger setting will override this setting.

        Raises:
            ValueError: If the agent doesn't have a 'name' attribute or if an agent
                       with the same name is already registered
        """
        # Get agent name from the agent's name attribute
        name = getattr(agent, "name", None)
        if name is None:
            raise ValueError("Agent does not have a 'name' attribute. All agents must have a 'name' attribute.")

        if name in self._agent_metadata:
            raise ValueError(f"Agent with name '{name}' is already registered. Each agent must have a unique name.")

        effective_enable_http_endpoint = (
            self.enable_http_endpoints if enable_http_endpoint is None else self._coerce_to_bool(enable_http_endpoint)
        )
        effective_enable_mcp_endpoint = (
            self.enable_mcp_tool_trigger
            if enable_mcp_tool_trigger is None
            else self._coerce_to_bool(enable_mcp_tool_trigger)
        )

        logger.debug(f"[AgentFunctionApp] Adding agent: {name}")
        logger.debug(f"[AgentFunctionApp] Route: /api/agents/{name}")
        logger.debug(
            "[AgentFunctionApp] HTTP endpoint %s for agent '%s'",
            "enabled" if effective_enable_http_endpoint else "disabled",
            name,
        )
        logger.debug(
            f"[AgentFunctionApp] MCP tool trigger: {'enabled' if effective_enable_mcp_endpoint else 'disabled'}"
        )

        # Store agent metadata
        self._agent_metadata[name] = AgentMetadata(
            agent=agent,
            http_endpoint_enabled=effective_enable_http_endpoint,
            mcp_tool_enabled=effective_enable_mcp_endpoint,
        )

        effective_callback = callback or self.default_callback

        self._setup_agent_functions(
            agent, name, effective_callback, effective_enable_http_endpoint, effective_enable_mcp_endpoint
        )

        logger.debug(f"[AgentFunctionApp] Agent '{name}' added successfully")

    def get_agent(
        self,
        context: AgentOrchestrationContextType,
        agent_name: str,
    ) -> DurableAIAgent:
        """Return a DurableAIAgent proxy for a registered agent.

        Args:
            context: Durable Functions orchestration context invoking the agent.
            agent_name: Name of the agent registered on this app.

        Raises:
            ValueError: If the requested agent has not been registered.

        Returns:
            DurableAIAgent wrapper bound to the orchestration context.
        """
        normalized_name = str(agent_name)

        if normalized_name not in self._agent_metadata:
            raise ValueError(f"Agent '{normalized_name}' is not registered with this app.")

        return DurableAIAgent(context, normalized_name)

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

        if enable_http_endpoint:
            self._setup_http_run_route(agent_name)
        else:
            logger.debug(
                "[AgentFunctionApp] HTTP run route disabled for agent '%s'",
                agent_name,
            )
        self._setup_agent_entity(agent, agent_name, callback)

        if enable_mcp_tool_trigger:
            agent_description = agent.description
            self._setup_mcp_tool_trigger(agent_name, agent_description)
        else:
            logger.debug(f"[AgentFunctionApp] MCP tool trigger disabled for agent '{agent_name}'")

    def _setup_http_run_route(self, agent_name: str) -> None:
        """Register the POST route that triggers agent execution.

        Args:
            agent_name: The agent name (used for both routing and entity identification)
        """
        run_function_name = self._build_function_name(agent_name, "http")

        function_name_decorator = self.function_name(run_function_name)
        route_decorator = self.route(route=f"agents/{agent_name}/run", methods=["POST"])
        durable_client_decorator = self.durable_client_input(client_name="client")

        @function_name_decorator
        @route_decorator
        @durable_client_decorator
        async def http_start(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
            """HTTP trigger that calls a durable entity to execute the agent and returns the result.

            Expected request body (RunRequest format):
            {
                "message": "user message to agent",
                "thread_id": "optional conversation identifier",
                "role": "user|system" (optional, default: "user"),
                "response_format": {...} (optional JSON schema for structured responses),
                "enable_tool_calls": true|false (optional, default: true)
            }
            """
            logger.debug(f"[HTTP Trigger] Received request on route: /api/agents/{agent_name}/run")

            request_response_format: str = REQUEST_RESPONSE_FORMAT_JSON
            thread_id: str | None = None

            try:
                req_body, message, request_response_format = self._parse_incoming_request(req)
                thread_id = self._resolve_thread_id(req=req, req_body=req_body)
                wait_for_response = self._should_wait_for_response(req=req, req_body=req_body)

                logger.debug(f"[HTTP Trigger] Message: {message}")
                logger.debug(f"[HTTP Trigger] Thread ID: {thread_id}")
                logger.debug(f"[HTTP Trigger] wait_for_response: {wait_for_response}")

                if not message:
                    logger.warning("[HTTP Trigger] Request rejected: Missing message")
                    return self._create_http_response(
                        payload={"error": "Message is required"},
                        status_code=400,
                        request_response_format=request_response_format,
                        thread_id=thread_id,
                    )

                session_id = self._create_session_id(agent_name, thread_id)
                correlation_id = self._generate_unique_id()

                logger.debug(f"[HTTP Trigger] Using session ID: {session_id}")
                logger.debug(f"[HTTP Trigger] Generated correlation ID: {correlation_id}")
                logger.debug("[HTTP Trigger] Calling entity to run agent...")

                entity_instance_id = session_id.to_entity_id()
                run_request = self._build_request_data(
                    req_body,
                    message,
                    thread_id,
                    correlation_id,
                    request_response_format,
                )
                logger.debug("Signalling entity %s with request: %s", entity_instance_id, run_request)
                await client.signal_entity(entity_instance_id, "run_agent", run_request)

                logger.debug(f"[HTTP Trigger] Signal sent to entity {session_id}")

                if wait_for_response:
                    result = await self._get_response_from_entity(
                        client=client,
                        entity_instance_id=entity_instance_id,
                        correlation_id=correlation_id,
                        message=message,
                        thread_id=thread_id,
                    )

                    logger.debug(f"[HTTP Trigger] Result status: {result.get('status', 'unknown')}")
                    return self._create_http_response(
                        payload=result,
                        status_code=200 if result.get("status") == "success" else 500,
                        request_response_format=request_response_format,
                        thread_id=thread_id,
                    )

                logger.debug("[HTTP Trigger] wait_for_response disabled; returning correlation ID")

                accepted_response = self._build_accepted_response(
                    message=message, thread_id=thread_id, correlation_id=correlation_id
                )

                return self._create_http_response(
                    payload=accepted_response,
                    status_code=202,
                    request_response_format=request_response_format,
                    thread_id=thread_id,
                )

            except IncomingRequestError as exc:
                logger.warning(f"[HTTP Trigger] Request rejected: {exc!s}")
                return self._create_http_response(
                    payload={"error": str(exc)},
                    status_code=exc.status_code,
                    request_response_format=request_response_format,
                    thread_id=thread_id,
                )
            except ValueError as exc:
                logger.error(f"[HTTP Trigger] Invalid JSON: {exc!s}")
                return self._create_http_response(
                    payload={"error": "Invalid JSON"},
                    status_code=400,
                    request_response_format=request_response_format,
                    thread_id=thread_id,
                )
            except Exception as exc:
                logger.error(f"[HTTP Trigger] Error: {exc!s}", exc_info=True)
                return self._create_http_response(
                    payload={"error": str(exc)},
                    status_code=500,
                    request_response_format=request_response_format,
                    thread_id=thread_id,
                )

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

    def _setup_mcp_tool_trigger(self, agent_name: str, agent_description: str | None) -> None:
        """Register an MCP tool trigger for an agent using Azure Functions native MCP support.

        This creates a native Azure Functions MCP tool trigger that exposes the agent
        as an MCP tool, allowing it to be invoked by MCP-compatible clients.

        Args:
            agent_name: The agent name (used as the MCP tool name)
            agent_description: Optional description for the MCP tool (shown to clients)
        """
        mcp_function_name = self._build_function_name(agent_name, "mcptool")

        # Define tool properties as JSON (MCP tool parameters)
        tool_properties = json.dumps([
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
        ])

        function_name_decorator = self.function_name(mcp_function_name)
        mcp_tool_decorator = self.mcp_tool_trigger(
            arg_name="context",
            tool_name=agent_name,
            description=agent_description or f"Interact with {agent_name} agent",
            tool_properties=tool_properties,
            data_type=func.DataType.UNDEFINED,
        )
        durable_client_decorator = self.durable_client_input(client_name="client")

        @function_name_decorator
        @mcp_tool_decorator
        @durable_client_decorator
        async def mcp_tool_handler(context: str, client: df.DurableOrchestrationClient) -> str:
            """Handle MCP tool invocation for the agent.

            Args:
                context: MCP tool invocation context containing arguments (query, threadId)
                client: Durable orchestration client for entity communication

            Returns:
                Agent response text
            """
            logger.debug("[MCP Tool Trigger] Received invocation for agent: %s", agent_name)
            return await self._handle_mcp_tool_invocation(agent_name=agent_name, context=context, client=client)

        _ = mcp_tool_handler
        logger.debug("[AgentFunctionApp] Registered MCP tool trigger for agent: %s", agent_name)

    async def _handle_mcp_tool_invocation(
        self, agent_name: str, context: str, client: df.DurableOrchestrationClient
    ) -> str:
        """Handle an MCP tool invocation.

        This method processes MCP tool requests and delegates to the agent entity.

        Args:
            agent_name: Name of the agent being invoked
            context: MCP tool invocation context as a JSON string
            client: Durable orchestration client

        Returns:
            Agent response text

        Raises:
            ValueError: If required arguments are missing or context is invalid JSON
            RuntimeError: If agent execution fails
        """
        logger.debug("[MCP Tool Handler] Processing invocation for agent '%s'", agent_name)

        # Parse JSON context string
        try:
            parsed_context: Any = json.loads(context)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid MCP context format: {e}") from e

        parsed_context = cast(Mapping[str, Any], parsed_context) if isinstance(parsed_context, dict) else {}

        # Extract arguments from MCP context
        arguments: dict[str, Any] = parsed_context.get("arguments", {})

        # Validate required 'query' argument
        query: Any = arguments.get("query")
        if not query or not isinstance(query, str):
            raise ValueError("MCP Tool invocation is missing required 'query' argument of type string.")

        # Extract optional threadId
        thread_id = arguments.get("threadId")

        # Create or parse session ID
        if thread_id and isinstance(thread_id, str) and thread_id.strip():
            try:
                session_id = AgentSessionId.parse(thread_id)
            except ValueError as e:
                logger.warning(
                    "Failed to parse AgentSessionId from thread_id '%s': %s. Falling back to new session ID.",
                    thread_id,
                    e,
                )
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
            thread_id=str(session_id),
            correlation_id=correlation_id,
            request_response_format=REQUEST_RESPONSE_FORMAT_TEXT,
        )

        query_preview = query[:50] + "..." if len(query) > 50 else query
        logger.info("[MCP Tool] Invoking agent '%s' with query: %s", agent_name, query_preview)

        # Signal entity to run agent
        await client.signal_entity(entity_instance_id, "run_agent", run_request)

        # Poll for response (similar to HTTP handler)
        try:
            result = await self._get_response_from_entity(
                client=client,
                entity_instance_id=entity_instance_id,
                correlation_id=correlation_id,
                message=query,
                thread_id=str(session_id),
            )

            # Extract and return response text
            if result.get("status") == "success":
                response_text = str(result.get("response", "No response"))
                logger.info("[MCP Tool] Agent '%s' responded successfully", agent_name)
                return response_text
            error_msg = result.get("error", "Unknown error")
            logger.error("[MCP Tool] Agent '%s' execution failed: %s", agent_name, error_msg)
            raise RuntimeError(f"Agent execution failed: {error_msg}")

        except Exception as exc:
            logger.error("[MCP Tool] Error invoking agent '%s': %s", agent_name, exc, exc_info=True)
            raise

    def _setup_health_route(self) -> None:
        """Register the optional health check route."""
        health_route = self.route(route="health", methods=["GET"])

        @health_route
        def health_check(req: func.HttpRequest) -> func.HttpResponse:
            """Built-in health check endpoint."""
            agent_info = [
                {
                    "name": name,
                    "type": type(metadata.agent).__name__,
                    "http_endpoint_enabled": metadata.http_endpoint_enabled,
                    "mcp_tool_enabled": metadata.mcp_tool_enabled,
                }
                for name, metadata in self._agent_metadata.items()
            ]
            return func.HttpResponse(
                json.dumps({"status": "healthy", "agents": agent_info, "agent_count": len(self._agent_metadata)}),
                status_code=200,
                mimetype=MIMETYPE_APPLICATION_JSON,
            )

        _ = health_check

    @staticmethod
    def _build_function_name(agent_name: str, prefix: str) -> str:
        """Generate the sanitized function name in the form "{prefix}-{sanitized_agent_name}".

        Example: agent_name="Weather Agent" and prefix="http" becomes "http-Weather_Agent".
        """
        sanitized_agent = re.sub(r"[^0-9a-zA-Z_]", "_", agent_name or "agent").strip("_")

        if not sanitized_agent:
            sanitized_agent = "agent"

        if sanitized_agent[0].isdigit():
            sanitized_agent = f"agent_{sanitized_agent}"

        return f"{prefix}-{sanitized_agent}"

    async def _read_cached_state(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
    ) -> DurableAgentState | None:
        state_response = await client.read_entity_state(entity_instance_id)
        if not state_response or not state_response.entity_exists:
            return None

        state_payload = state_response.entity_state
        if not isinstance(state_payload, dict):
            return None

        typed_state_payload = cast(dict[str, Any], state_payload)

        return DurableAgentState.from_dict(typed_state_payload)

    async def _get_response_from_entity(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
        correlation_id: str,
        message: str,
        thread_id: str,
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
                thread_id=thread_id,
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
        return await self._build_timeout_result(message=message, thread_id=thread_id, correlation_id=correlation_id)

    async def _poll_entity_for_response(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
        correlation_id: str,
        message: str,
        thread_id: str,
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
                    thread_id=thread_id,
                    correlation_id=correlation_id,
                    state=state,
                )
                logger.debug(f"[HTTP Trigger] Found response for correlation ID: {correlation_id}")

        except Exception as exc:
            logger.warning(f"[HTTP Trigger] Error reading entity state: {exc}")

        return result

    def _build_response_payload(
        self,
        *,
        response: str | None,
        message: str,
        thread_id: str,
        status: str,
        correlation_id: str,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a consistent response structure and allow optional extra fields."""
        payload = {
            "response": response,
            "message": message,
            THREAD_ID_FIELD: thread_id,
            "status": status,
            "correlation_id": correlation_id,
        }
        if extra_fields:
            payload.update(extra_fields)
        return payload

    async def _build_timeout_result(self, message: str, thread_id: str, correlation_id: str) -> dict[str, Any]:
        """Create the timeout response."""
        return self._build_response_payload(
            response="Agent is still processing or timed out...",
            message=message,
            thread_id=thread_id,
            status="timeout",
            correlation_id=correlation_id,
        )

    def _build_success_result(
        self, response_data: dict[str, Any], message: str, thread_id: str, correlation_id: str, state: DurableAgentState
    ) -> dict[str, Any]:
        """Build the success result returned to the HTTP caller."""
        return self._build_response_payload(
            response=response_data.get("content"),
            message=message,
            thread_id=thread_id,
            status="success",
            correlation_id=correlation_id,
            extra_fields={"message_count": response_data.get("message_count", state.message_count)},
        )

    def _build_request_data(
        self,
        req_body: dict[str, Any],
        message: str,
        thread_id: str,
        correlation_id: str,
        request_response_format: str,
    ) -> dict[str, Any]:
        """Create the durable entity request payload."""
        enable_tool_calls_value = req_body.get("enable_tool_calls")
        enable_tool_calls = True if enable_tool_calls_value is None else self._coerce_to_bool(enable_tool_calls_value)

        return RunRequest(
            message=message,
            role=req_body.get("role"),
            request_response_format=request_response_format,
            response_format=req_body.get("response_format"),
            enable_tool_calls=enable_tool_calls,
            thread_id=thread_id,
            correlation_id=correlation_id,
        ).to_dict()

    def _build_accepted_response(self, message: str, thread_id: str, correlation_id: str) -> dict[str, Any]:
        """Build the response returned when not waiting for completion."""
        return self._build_response_payload(
            response="Agent request accepted",
            message=message,
            thread_id=thread_id,
            status="accepted",
            correlation_id=correlation_id,
        )

    def _create_http_response(
        self,
        payload: dict[str, Any] | str,
        status_code: int,
        request_response_format: str,
        thread_id: str | None,
    ) -> func.HttpResponse:
        """Create the HTTP response using helper serializers for clarity."""
        if request_response_format == REQUEST_RESPONSE_FORMAT_TEXT:
            return self._build_plain_text_response(payload=payload, status_code=status_code, thread_id=thread_id)

        return self._build_json_response(payload=payload, status_code=status_code)

    def _build_plain_text_response(
        self,
        payload: dict[str, Any] | str,
        status_code: int,
        thread_id: str | None,
    ) -> func.HttpResponse:
        """Return a plain-text response with optional thread identifier header."""
        body_text = payload if isinstance(payload, str) else self._convert_payload_to_text(payload)
        headers = {THREAD_ID_HEADER: thread_id} if thread_id is not None else None
        return func.HttpResponse(body_text, status_code=status_code, mimetype=MIMETYPE_TEXT_PLAIN, headers=headers)

    def _build_json_response(self, payload: dict[str, Any] | str, status_code: int) -> func.HttpResponse:
        """Return the JSON response, serializing dictionaries as needed."""
        body_json = payload if isinstance(payload, str) else json.dumps(payload)
        return func.HttpResponse(body_json, status_code=status_code, mimetype=MIMETYPE_APPLICATION_JSON)

    def _convert_payload_to_text(self, payload: dict[str, Any]) -> str:
        """Convert a structured payload into a human-readable text response."""
        for key in ("response", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(payload)

    def _generate_unique_id(self) -> str:
        """Generate a new unique identifier."""
        import uuid

        return uuid.uuid4().hex

    def _create_session_id(self, func_name: str, thread_id: str | None) -> AgentSessionId:
        """Create a session identifier using the provided thread id or a random value."""
        if thread_id:
            return AgentSessionId(name=func_name, key=thread_id)
        return AgentSessionId.with_random_key(name=func_name)

    def _resolve_thread_id(self, req: func.HttpRequest, req_body: dict[str, Any]) -> str:
        """Retrieve the thread identifier from request body or query parameters."""
        params = req.params or {}

        if THREAD_ID_FIELD in req_body:
            value = req_body.get(THREAD_ID_FIELD)
            if value is not None:
                return str(value)

        if THREAD_ID_FIELD in params:
            value = params.get(THREAD_ID_FIELD)
            if value is not None:
                return str(value)

        logger.debug("[HTTP Trigger] No thread identifier provided; using random thread id")
        return self._generate_unique_id()

    def _parse_incoming_request(self, req: func.HttpRequest) -> tuple[dict[str, Any], str, str]:
        """Parse the incoming run request supporting JSON and plain text bodies."""
        headers = self._extract_normalized_headers(req)

        normalized_content_type = self._extract_content_type(headers)
        body_parser, body_format = self._select_body_parser(normalized_content_type)
        prefers_json = self._accepts_json_response(headers)
        request_response_format = self._select_request_response_format(
            body_format=body_format, prefers_json=prefers_json
        )

        req_body, message = body_parser(req)
        return req_body, message, request_response_format

    def _extract_normalized_headers(self, req: func.HttpRequest) -> dict[str, str]:
        """Create a lowercase header mapping from the incoming request."""
        headers: dict[str, str] = {}
        raw_headers = req.headers
        for key, value in cast(Mapping[str, str], raw_headers).items():
            headers[key.lower()] = value

        return headers

    @staticmethod
    def _extract_content_type(headers: dict[str, str]) -> str:
        """Return the normalized content-type value (without parameters)."""
        content_type_header = headers.get("content-type", "")
        return content_type_header.split(";")[0].strip().lower() if content_type_header else ""

    def _select_body_parser(
        self,
        normalized_content_type: str,
    ) -> tuple[Callable[[func.HttpRequest], tuple[dict[str, Any], str]], str]:
        """Choose the body parser and declared body format."""
        if normalized_content_type in {MIMETYPE_APPLICATION_JSON} or normalized_content_type.endswith("+json"):
            return self._parse_json_body, REQUEST_RESPONSE_FORMAT_JSON
        return self._parse_text_body, REQUEST_RESPONSE_FORMAT_TEXT

    @staticmethod
    def _accepts_json_response(headers: dict[str, str]) -> bool:
        """Check whether the caller explicitly requests a JSON response."""
        accept_header = headers.get("accept")
        if not accept_header:
            return False

        for value in accept_header.split(","):
            media_type = value.split(";")[0].strip().lower()
            if media_type == MIMETYPE_APPLICATION_JSON:
                return True
        return False

    @staticmethod
    def _select_request_response_format(body_format: str, prefers_json: bool) -> str:
        """Combine body format and accept preference to determine response format."""
        if body_format == REQUEST_RESPONSE_FORMAT_JSON or prefers_json:
            return REQUEST_RESPONSE_FORMAT_JSON
        return REQUEST_RESPONSE_FORMAT_TEXT

    @staticmethod
    def _parse_json_body(req: func.HttpRequest) -> tuple[dict[str, Any], str]:
        req_body = req.get_json()
        if not isinstance(req_body, dict):
            raise IncomingRequestError("Invalid JSON payload. Expected an object.")

        typed_req_body = cast(dict[str, Any], req_body)
        message_value = typed_req_body.get("message", "")
        message = message_value if isinstance(message_value, str) else str(message_value)
        return typed_req_body, message

    @staticmethod
    def _parse_text_body(req: func.HttpRequest) -> tuple[dict[str, Any], str]:
        body_bytes = req.get_body()
        text_body = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        message = text_body.strip()

        return {}, message

    def _should_wait_for_response(self, req: func.HttpRequest, req_body: dict[str, Any]) -> bool:
        """Determine whether the caller requested to wait for the response."""
        headers: dict[str, str] = self._extract_normalized_headers(req)
        header_value: str | None = headers.get(WAIT_FOR_RESPONSE_HEADER)

        if header_value is not None:
            return self._coerce_to_bool(header_value)

        params = req.params or {}
        if WAIT_FOR_RESPONSE_FIELD in params:
            return self._coerce_to_bool(params.get(WAIT_FOR_RESPONSE_FIELD))

        if WAIT_FOR_RESPONSE_FIELD in req_body:
            return self._coerce_to_bool(req_body.get(WAIT_FOR_RESPONSE_FIELD))

        return True

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
