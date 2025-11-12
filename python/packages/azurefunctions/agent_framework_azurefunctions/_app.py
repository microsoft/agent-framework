# Copyright (c) Microsoft. All rights reserved.

"""AgentFunctionApp - Main application class.

This module provides the AgentFunctionApp class that integrates Microsoft Agent Framework
with Azure Durable Entities, enabling stateful and durable AI agent execution.
"""

import json
import re
from collections.abc import Callable, Mapping
from typing import Any, cast

import azure.durable_functions as df
import azure.functions as func
from agent_framework import AgentProtocol, get_logger

from ._callbacks import AgentResponseCallbackProtocol
from ._entities import create_agent_entity
from ._errors import IncomingRequestError
from ._models import AgentSessionId, RunRequest
from ._state import AgentState

logger = get_logger("agent_framework.azurefunctions")

THREAD_ID_FIELD: str = "threadId"
RESPONSE_FORMAT_JSON: str = "json"
RESPONSE_FORMAT_TEXT: str = "text"


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
    - Full access to all Azure Functions capabilities

    Attributes:
        agents: Dictionary of agent name to AgentProtocol instance
        enable_health_check: Whether health check endpoint is enabled
        enable_http_endpoints: Whether HTTP endpoints are created for agents
        max_poll_retries: Maximum polling attempts when waiting for responses
        poll_interval_seconds: Delay (seconds) between polling attempts
    """

    agents: dict[str, AgentProtocol]
    enable_health_check: bool
    enable_http_endpoints: bool
    agent_http_endpoint_flags: dict[str, bool]

    def __init__(
        self,
        agents: list[AgentProtocol] | None = None,
        http_auth_level: func.AuthLevel = func.AuthLevel.ANONYMOUS,
        enable_health_check: bool = True,
        enable_http_endpoints: bool = True,
        max_poll_retries: int = 10,
        poll_interval_seconds: float = 0.5,
        default_callback: AgentResponseCallbackProtocol | None = None,
    ):
        """Initialize the AgentFunctionApp.

        Args:
            agents: List of agent instances to register
            http_auth_level: HTTP authentication level (default: ANONYMOUS)
            enable_health_check: Enable built-in health check endpoint (default: True)
            enable_http_endpoints: Enable HTTP endpoints for agents (default: True)
            max_poll_retries: Maximum number of polling attempts when waiting for a response
            poll_interval_seconds: Delay (in seconds) between polling attempts
            default_callback: Optional callback invoked for agents without specific callbacks

        Note:
            If no agents are provided, they can be added later using add_agent().
        """
        logger.debug("[AgentFunctionApp] Initializing with Durable Entities...")

        # Initialize parent DFApp
        super().__init__(http_auth_level=http_auth_level)

        # Initialize agents dictionary
        self.agents = {}
        self.agent_http_endpoint_flags = {}
        self.enable_health_check = enable_health_check
        self.enable_http_endpoints = enable_http_endpoints
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
    ) -> None:
        """Add an agent to the function app after initialization.

        Args:
            agent: The Microsoft Agent Framework agent instance (must implement AgentProtocol)
                   The agent must have a 'name' attribute.
            callback: Optional callback invoked during agent execution
            enable_http_endpoint: Optional flag that overrides the app-level
                                   HTTP endpoint setting for this agent

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

        effective_enable_http_endpoint = (
            self.enable_http_endpoints if enable_http_endpoint is None else self._coerce_to_bool(enable_http_endpoint)
        )

        logger.debug(f"[AgentFunctionApp] Adding agent: {name}")
        logger.debug(f"[AgentFunctionApp] Route: /api/agents/{name}")
        logger.debug(
            "[AgentFunctionApp] HTTP endpoint %s for agent '%s'",
            "enabled" if effective_enable_http_endpoint else "disabled",
            name,
        )

        self.agents[name] = agent
        self.agent_http_endpoint_flags[name] = effective_enable_http_endpoint

        effective_callback = callback or self.default_callback

        self._setup_agent_functions(
            agent,
            name,
            effective_callback,
            effective_enable_http_endpoint,
        )

        logger.debug(f"[AgentFunctionApp] Agent '{name}' added successfully")

    def _setup_agent_functions(
        self,
        agent: AgentProtocol,
        agent_name: str,
        callback: AgentResponseCallbackProtocol | None,
        enable_http_endpoint: bool,
    ) -> None:
        """Set up the HTTP trigger and entity for a specific agent.

        Args:
            agent: The agent instance
            agent_name: The name to use for routing and entity registration
            callback: Optional callback to receive response updates
            enable_http_endpoint: Whether the HTTP run route is enabled for
                                   this agent
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
                "threadId": "optional conversation identifier",
                "role": "user|system" (optional, default: "user"),
                "response_format": {...} (optional JSON schema for structured responses),
                "enable_tool_calls": true|false (optional, default: true)
            }
            """
            logger.debug(f"[HTTP Trigger] Received request on route: /api/agents/{agent_name}/run")

            response_format: str = RESPONSE_FORMAT_JSON
            thread_id: str | None = None

            try:
                req_body, message, response_format = self._parse_incoming_request(req)
                thread_id = self._resolve_thread_id(req=req, req_body=req_body)
                wait_for_completion = self._should_wait_for_completion(req=req, req_body=req_body)

                logger.debug(f"[HTTP Trigger] Message: {message}")
                logger.debug(f"[HTTP Trigger] Thread ID: {thread_id}")
                logger.debug(f"[HTTP Trigger] wait_for_completion: {wait_for_completion}")

                if not message:
                    logger.warning("[HTTP Trigger] Request rejected: Missing message")
                    return self._create_http_response(
                        payload={"error": "Message is required"},
                        status_code=400,
                        response_format=response_format,
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
                        thread_id=thread_id,
                    )

                    logger.debug(f"[HTTP Trigger] Result status: {result.get('status', 'unknown')}")
                    return self._create_http_response(
                        payload=result,
                        status_code=200 if result.get("status") == "success" else 500,
                        response_format=response_format,
                        thread_id=thread_id,
                    )

                logger.debug("[HTTP Trigger] wait_for_completion disabled; returning correlation ID")

                accepted_response = self._build_accepted_response(
                    message=message, thread_id=thread_id, correlation_id=correlation_id
                )

                return self._create_http_response(
                    payload=accepted_response,
                    status_code=202,
                    response_format=response_format,
                    thread_id=thread_id,
                )

            except IncomingRequestError as exc:
                logger.warning(f"[HTTP Trigger] Request rejected: {exc!s}")
                return self._create_http_response(
                    payload={"error": str(exc)},
                    status_code=exc.status_code,
                    response_format=response_format,
                    thread_id=thread_id,
                )
            except ValueError as exc:
                logger.error(f"[HTTP Trigger] Invalid JSON: {exc!s}")
                return self._create_http_response(
                    payload={"error": "Invalid JSON"},
                    status_code=400,
                    response_format=response_format,
                    thread_id=thread_id,
                )
            except Exception as exc:
                logger.error(f"[HTTP Trigger] Error: {exc!s}", exc_info=True)
                return self._create_http_response(
                    payload={"error": str(exc)},
                    status_code=500,
                    response_format=response_format,
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

    def _setup_health_route(self) -> None:
        """Register the optional health check route."""

        @self.route(route="health", methods=["GET"])
        def health_check(req: func.HttpRequest) -> func.HttpResponse:
            """Built-in health check endpoint."""
            agent_info = [
                {
                    "name": name,
                    "type": type(agent).__name__,
                    "httpEndpointEnabled": self.agent_http_endpoint_flags.get(
                        name,
                        self.enable_http_endpoints,
                    ),
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

    async def _read_cached_state(
        self,
        client: df.DurableOrchestrationClient,
        entity_instance_id: df.EntityId,
    ) -> AgentState | None:
        state_response = await client.read_entity_state(entity_instance_id)
        if not state_response or not state_response.entity_exists:
            return None

        state_payload = state_response.entity_state
        if not isinstance(state_payload, dict):
            return None

        typed_state_payload = cast(dict[str, Any], state_payload)

        agent_state = AgentState()
        agent_state.restore_state(typed_state_payload)
        return agent_state

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

    async def _build_timeout_result(self, message: str, thread_id: str, correlation_id: str) -> dict[str, Any]:
        """Create the timeout response."""
        return {
            "response": "Agent is still processing or timed out...",
            "message": message,
            THREAD_ID_FIELD: thread_id,
            "status": "timeout",
            "correlationId": correlation_id,
        }

    def _build_success_result(
        self, response_data: dict[str, Any], message: str, thread_id: str, correlation_id: str, state: AgentState
    ) -> dict[str, Any]:
        """Build the success result returned to the HTTP caller."""
        return {
            "response": response_data.get("content"),
            "message": message,
            THREAD_ID_FIELD: thread_id,
            "status": "success",
            "message_count": response_data.get("message_count", state.message_count),
            "correlationId": correlation_id,
        }

    def _build_request_data(
        self, req_body: dict[str, Any], message: str, thread_id: str, correlation_id: str
    ) -> dict[str, Any]:
        """Create the durable entity request payload."""
        enable_tool_calls_value = req_body.get("enable_tool_calls")
        enable_tool_calls = True if enable_tool_calls_value is None else self._coerce_to_bool(enable_tool_calls_value)

        return RunRequest(
            message=message,
            role=RunRequest.coerce_role(req_body.get("role")),
            response_format=req_body.get("response_format"),
            enable_tool_calls=enable_tool_calls,
            thread_id=thread_id,
            correlation_id=correlation_id,
        ).to_dict()

    def _build_accepted_response(self, message: str, thread_id: str, correlation_id: str) -> dict[str, Any]:
        """Build the response returned when not waiting for completion."""
        return {
            "response": "Agent request accepted",
            "message": message,
            THREAD_ID_FIELD: thread_id,
            "status": "accepted",
            "correlationId": correlation_id,
        }

    def _create_http_response(
        self,
        payload: dict[str, Any] | str,
        status_code: int,
        response_format: str,
        thread_id: str | None,
    ) -> func.HttpResponse:
        """Create the HTTP response using helper serializers for clarity."""
        if response_format == RESPONSE_FORMAT_TEXT:
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
        headers = {"x-ms-thread-id": thread_id} if thread_id else None
        return func.HttpResponse(body_text, status_code=status_code, mimetype="text/plain", headers=headers)

    def _build_json_response(self, payload: dict[str, Any] | str, status_code: int) -> func.HttpResponse:
        """Return the JSON response, serializing dictionaries as needed."""
        body_json = payload if isinstance(payload, str) else json.dumps(payload)
        return func.HttpResponse(body_json, status_code=status_code, mimetype="application/json")

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
        response_format = self._select_response_format(body_format=body_format, prefers_json=prefers_json)

        req_body, message = body_parser(req)
        return req_body, message, response_format

    def _extract_normalized_headers(self, req: func.HttpRequest) -> dict[str, str]:
        """Create a lowercase header mapping from the incoming request."""
        headers: dict[str, str] = {}
        raw_headers = req.headers
        if isinstance(raw_headers, Mapping):
            headers_mapping = cast(Mapping[Any, Any], raw_headers)
            for key, value in headers_mapping.items():
                if value is not None:
                    headers[str(key).lower()] = str(value)
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
        if normalized_content_type in {"application/json"} or normalized_content_type.endswith("+json"):
            return self._parse_json_body, RESPONSE_FORMAT_JSON
        return self._parse_text_body, RESPONSE_FORMAT_TEXT

    @staticmethod
    def _accepts_json_response(headers: dict[str, str]) -> bool:
        """Check whether the caller explicitly requests a JSON response."""
        accept_header = headers.get("accept")
        if not accept_header:
            return False

        for value in accept_header.split(","):
            media_type = value.split(";")[0].strip().lower()
            if media_type == "application/json":
                return True
        return False

    @staticmethod
    def _select_response_format(body_format: str, prefers_json: bool) -> str:
        """Combine body format and accept preference to determine response format."""
        if body_format == RESPONSE_FORMAT_JSON or prefers_json:
            return RESPONSE_FORMAT_JSON
        return RESPONSE_FORMAT_TEXT

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
