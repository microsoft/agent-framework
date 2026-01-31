# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentFunctionApp."""

# pyright: reportPrivateUsage=false

import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from unittest.mock import ANY, AsyncMock, Mock, patch

import azure.durable_functions as df
import azure.functions as func
import pytest
from agent_framework import AgentResponse, ChatMessage
from agent_framework_durabletask import (
    MIMETYPE_APPLICATION_JSON,
    MIMETYPE_TEXT_PLAIN,
    THREAD_ID_HEADER,
    WAIT_FOR_RESPONSE_FIELD,
    WAIT_FOR_RESPONSE_HEADER,
    AgentEntity,
    AgentEntityStateProviderMixin,
    DurableAgentState,
)

from agent_framework_azurefunctions import AgentFunctionApp
from agent_framework_azurefunctions._entities import create_agent_entity

TFunc = TypeVar("TFunc", bound=Callable[..., Any])


def _identity_decorator(func: TFunc) -> TFunc:
    return func


class _InMemoryStateProvider(AgentEntityStateProviderMixin):
    def __init__(self, *, thread_id: str = "test-thread", initial_state: dict[str, Any] | None = None) -> None:
        self._thread_id = thread_id
        self._state_dict: dict[str, Any] = initial_state or {}

    def _get_state_dict(self) -> dict[str, Any]:
        return self._state_dict

    def _set_state_dict(self, state: dict[str, Any]) -> None:
        self._state_dict = state

    def _get_thread_id_from_entity(self) -> str:
        return self._thread_id


class TestAgentFunctionAppInit:
    """Test suite for AgentFunctionApp initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])

        assert len(app.agents) == 1
        assert "TestAgent" in app.agents
        assert app.enable_health_check is True

    def test_init_with_custom_auth_level(self) -> None:
        """Test initialization with custom auth level."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent], http_auth_level=func.AuthLevel.FUNCTION)

        # App should be created successfully
        assert "TestAgent" in app.agents

    def test_init_with_health_check_disabled(self) -> None:
        """Test initialization with health check disabled."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent], enable_health_check=False)

        assert app.enable_health_check is False

    def test_init_with_http_endpoints_disabled(self) -> None:
        """Test initialization with HTTP endpoints disabled."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent], enable_http_endpoints=False)

        assert app.enable_http_endpoints is False

    def test_init_stores_agent_reference(self) -> None:
        """Test that agent reference is stored correctly."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])

        assert app.agents["TestAgent"].name == "TestAgent"

    def test_add_agent_uses_specific_callback(self) -> None:
        """Verify that a per-agent callback overrides the default."""

        mock_agent = Mock()
        mock_agent.name = "CallbackAgent"
        specific_callback = Mock()

        with patch.object(AgentFunctionApp, "_setup_agent_functions") as setup_mock:
            app = AgentFunctionApp(default_callback=Mock())
            app.add_agent(mock_agent, callback=specific_callback)

        setup_mock.assert_called_once()
        _, _, passed_callback, enable_http_endpoint, _enable_mcp_tool_trigger = setup_mock.call_args[0]
        assert passed_callback is specific_callback
        assert enable_http_endpoint is True

    def test_default_callback_applied_when_no_specific(self) -> None:
        """Ensure the default callback is supplied when add_agent lacks override."""

        mock_agent = Mock()
        mock_agent.name = "DefaultAgent"
        default_callback = Mock()

        with patch.object(AgentFunctionApp, "_setup_agent_functions") as setup_mock:
            app = AgentFunctionApp(default_callback=default_callback)
            app.add_agent(mock_agent)

        setup_mock.assert_called_once()
        _, _, passed_callback, enable_http_endpoint, _enable_mcp_tool_trigger = setup_mock.call_args[0]
        assert passed_callback is default_callback
        assert enable_http_endpoint is True

    def test_init_with_agents_uses_default_callback(self) -> None:
        """Agents provided in __init__ should receive the default callback."""

        mock_agent = Mock()
        mock_agent.name = "InitAgent"
        default_callback = Mock()

        with patch.object(AgentFunctionApp, "_setup_agent_functions") as setup_mock:
            AgentFunctionApp(agents=[mock_agent], default_callback=default_callback)

        setup_mock.assert_called_once()
        _, _, passed_callback, enable_http_endpoint, _enable_mcp_tool_trigger = setup_mock.call_args[0]
        assert passed_callback is default_callback
        assert enable_http_endpoint is True


class TestAgentFunctionAppSetup:
    """Test suite for AgentFunctionApp setup and configuration."""

    def test_app_is_dfapp_instance(self) -> None:
        """Test that AgentFunctionApp is a DFApp instance."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])

        assert isinstance(app, df.DFApp)

    def test_setup_creates_http_trigger(self) -> None:
        """Test that setup creates an HTTP trigger."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        def passthrough_decorator(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                return func

            return decorator

        with (
            patch.object(AgentFunctionApp, "route", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "durable_client_input", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "entity_trigger", new=passthrough_decorator),
        ):
            app = AgentFunctionApp(agents=[mock_agent])

        # Verify agent is registered
        assert "TestAgent" in app.agents

    def test_http_function_name_uses_prefix_format(self) -> None:
        """Ensure function names follow the prefix-agent naming convention."""
        mock_agent = Mock()
        mock_agent.name = "Agent 42"

        captured_names: list[str] = []

        def capture_function_name(
            self: AgentFunctionApp, name: str, *args: Any, **kwargs: Any
        ) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                captured_names.append(name)
                return func

            return decorator

        def passthrough_decorator(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                return func

            return decorator

        with (
            patch.object(AgentFunctionApp, "function_name", new=capture_function_name),
            patch.object(AgentFunctionApp, "route", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "durable_client_input", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "entity_trigger", new=passthrough_decorator),
        ):
            AgentFunctionApp(agents=[mock_agent])

        assert captured_names == ["http-Agent_42"]

    def test_setup_skips_http_trigger_when_disabled(self) -> None:
        """Test that HTTP trigger is not created when disabled."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        captured_routes: list[str | None] = []

        def capture_route(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                route_key = kwargs.get("route") if kwargs else None
                captured_routes.append(route_key)
                return func

            return decorator

        def passthrough_decorator(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                return func

            return decorator

        with (
            patch.object(AgentFunctionApp, "function_name", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "route", new=capture_route),
            patch.object(AgentFunctionApp, "durable_client_input", new=passthrough_decorator),
            patch.object(AgentFunctionApp, "entity_trigger", new=passthrough_decorator),
        ):
            app = AgentFunctionApp(agents=[mock_agent], enable_http_endpoints=False)

        # Verify agent is registered
        assert "TestAgent" in app.agents

        # Verify that no HTTP run route was created
        run_route = f"agents/{mock_agent.name}/run"
        assert run_route not in captured_routes

    def test_agent_override_enables_http_route_when_app_disabled(self) -> None:
        """Agent-level override should enable HTTP route even when app disables it."""

        mock_agent = Mock()
        mock_agent.name = "OverrideAgent"

        with (
            patch.object(AgentFunctionApp, "_setup_http_run_route") as http_route_mock,
            patch.object(AgentFunctionApp, "_setup_agent_entity") as agent_entity_mock,
        ):
            app = AgentFunctionApp(enable_health_check=False, enable_http_endpoints=False)
            app.add_agent(mock_agent, enable_http_endpoint=True)

        http_route_mock.assert_called_once_with("OverrideAgent")
        agent_entity_mock.assert_called_once_with(mock_agent, "OverrideAgent", ANY)
        assert app._agent_metadata["OverrideAgent"].http_endpoint_enabled is True

    def test_agent_override_disables_http_route_when_app_enabled(self) -> None:
        """Agent-level override should disable HTTP route even when app enables it."""

        mock_agent = Mock()
        mock_agent.name = "DisabledOverride"

        with (
            patch.object(AgentFunctionApp, "_setup_http_run_route") as http_route_mock,
            patch.object(AgentFunctionApp, "_setup_agent_entity") as agent_entity_mock,
        ):
            app = AgentFunctionApp(enable_health_check=False, enable_http_endpoints=True)
            app.add_agent(mock_agent, enable_http_endpoint=False)

        http_route_mock.assert_not_called()
        agent_entity_mock.assert_called_once_with(mock_agent, "DisabledOverride", ANY)
        assert app._agent_metadata["DisabledOverride"].http_endpoint_enabled is False

    def test_multiple_apps_independent(self) -> None:
        """Test that multiple AgentFunctionApp instances are independent."""
        agent1 = Mock()
        agent1.name = "Agent1"
        agent2 = Mock()
        agent2.name = "Agent2"

        app1 = AgentFunctionApp(agents=[agent1])
        app2 = AgentFunctionApp(agents=[agent2])

        assert app1.agents["Agent1"].name == "Agent1"
        assert app2.agents["Agent2"].name == "Agent2"
        assert "Agent1" in app1.agents
        assert "Agent2" in app2.agents


class TestWaitForResponseAndCorrelationId:
    """Tests for wait_for_response flag and correlation ID handling."""

    def _create_app(self) -> AgentFunctionApp:
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "MockAgent"
        mock_agent.name = "MockAgent"
        return AgentFunctionApp(agents=[mock_agent], enable_health_check=False)

    def _make_request(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Mock:
        request = Mock()
        request.headers = headers or {}
        request.params = params or {}
        return request

    def test_wait_for_response_header_true(self) -> None:
        """Test that the wait-for-response header is honored."""
        app = self._create_app()
        request = self._make_request(headers={WAIT_FOR_RESPONSE_HEADER: "true"})

        assert app._should_wait_for_response(request, {}) is True

    def test_wait_for_response_body_snake_case(self) -> None:
        """Test that payload controls wait_for_response."""
        app = self._create_app()
        request = self._make_request()

        assert app._should_wait_for_response(request, {WAIT_FOR_RESPONSE_FIELD: "true"}) is True
        assert app._should_wait_for_response(request, {WAIT_FOR_RESPONSE_FIELD: "false"}) is False
        assert app._should_wait_for_response(request, {WAIT_FOR_RESPONSE_FIELD: "0"}) is False

    def test_wait_for_response_query_parameter(self) -> None:
        """Test that query parameter controls wait_for_response."""
        app = self._create_app()
        request = self._make_request(params={WAIT_FOR_RESPONSE_FIELD: "true"})

        assert app._should_wait_for_response(request, {}) is True

    def test_wait_for_response_query_precedence(self) -> None:
        """Test that query parameter overrides body value."""
        app = self._create_app()
        request = self._make_request(params={WAIT_FOR_RESPONSE_FIELD: "false"})

        assert app._should_wait_for_response(request, {WAIT_FOR_RESPONSE_FIELD: "true"}) is False


class TestAgentEntityOperations:
    """Test suite for entity operations."""

    async def test_entity_run_agent_operation(self) -> None:
        """Test that entity can run agent operation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[ChatMessage(role="assistant", text="Test response")])
        )

        entity = AgentEntity(mock_agent, state_provider=_InMemoryStateProvider(thread_id="test-conv-123"))

        result = await entity.run({
            "message": "Test message",
            "correlationId": "corr-app-entity-1",
        })

        assert isinstance(result, AgentResponse)
        assert result.text == "Test response"
        assert entity.state.message_count == 2

    async def test_entity_stores_conversation_history(self) -> None:
        """Test that the entity stores conversation history."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[ChatMessage(role="assistant", text="Response 1")])
        )

        entity = AgentEntity(mock_agent, state_provider=_InMemoryStateProvider(thread_id="conv-1"))

        # Send first message
        await entity.run({"message": "Message 1", "correlationId": "corr-app-entity-2"})

        # Each conversation turn creates 2 entries: request and response
        history = entity.state.data.conversation_history[0].messages  # Request entry
        assert len(history) == 1  # Just the user message

        # Send second message
        await entity.run({"message": "Message 2", "correlationId": "corr-app-entity-2b"})

        # Now we have 4 entries total (2 requests + 2 responses)
        # Access the first request entry
        history2 = entity.state.data.conversation_history[2].messages  # Second request entry
        assert len(history2) == 1  # Just the user message

        user_msg = history[0]
        user_role = getattr(user_msg.role, "value", user_msg.role)
        assert user_role == "user"
        assert user_msg.text == "Message 1"

        assistant_msg = entity.state.data.conversation_history[1].messages[0]
        assistant_role = getattr(assistant_msg.role, "value", assistant_msg.role)
        assert assistant_role == "assistant"
        assert assistant_msg.text == "Response 1"

    async def test_entity_increments_message_count(self) -> None:
        """Test that the entity increments the message count."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[ChatMessage(role="assistant", text="Response")])
        )

        entity = AgentEntity(mock_agent, state_provider=_InMemoryStateProvider(thread_id="conv-1"))

        assert len(entity.state.data.conversation_history) == 0

        await entity.run({"message": "Message 1", "correlationId": "corr-app-entity-3a"})
        assert len(entity.state.data.conversation_history) == 2

        await entity.run({"message": "Message 2", "correlationId": "corr-app-entity-3b"})
        assert len(entity.state.data.conversation_history) == 4

    def test_entity_reset(self) -> None:
        """Test that entity reset clears state."""
        mock_agent = Mock()
        entity = AgentEntity(mock_agent, state_provider=_InMemoryStateProvider())

        # Set some state
        entity.state = DurableAgentState()

        # Reset
        entity.reset()

        assert len(entity.state.data.conversation_history) == 0


class TestAgentEntityFactory:
    """Test suite for the entity factory function."""

    def test_create_agent_entity_returns_function(self) -> None:
        """Test that create_agent_entity returns a function."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        assert callable(entity_function)

    def test_entity_function_handles_run_operation(self) -> None:
        """Test that the entity function handles the run operation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[ChatMessage(role="assistant", text="Response")])
        )

        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "correlationId": "corr-app-factory-1",
        }
        mock_context.get_state.return_value = None

        # Execute entity function
        entity_function(mock_context)

        # Verify result was set
        assert mock_context.set_result.called
        assert mock_context.set_state.called
        result_call = mock_context.set_result.call_args[0][0]
        assert "error" not in result_call

    def test_entity_function_handles_run_agent_operation(self) -> None:
        """Test that the entity function handles the deprecated run_agent operation for backward compatibility."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[ChatMessage(role="assistant", text="Response")])
        )

        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "run_agent"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "correlationId": "corr-app-factory-1",
        }
        mock_context.get_state.return_value = None

        # Execute entity function
        entity_function(mock_context)

        # Verify result was set
        assert mock_context.set_result.called
        assert mock_context.set_state.called
        result_call = mock_context.set_result.call_args[0][0]
        assert "error" not in result_call

    def test_entity_function_handles_reset_operation(self) -> None:
        """Test that the entity function handles the reset operation."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "corr-reset-test",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "test",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }

        # Execute entity function
        entity_function(mock_context)

        # Verify result was set
        assert mock_context.set_result.called
        result_call = mock_context.set_result.call_args[0][0]
        assert result_call["status"] == "reset"

    def test_entity_function_handles_unknown_operation(self) -> None:
        """Test that the entity function handles an unknown operation."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        # Mock context with unknown operation
        mock_context = Mock()
        mock_context.operation_name = "unknown_operation"
        mock_context.get_state.return_value = None

        # Execute entity function
        entity_function(mock_context)

        # Verify error result was set
        assert mock_context.set_result.called
        result_call = mock_context.set_result.call_args[0][0]
        assert "error" in result_call
        assert "unknown_operation" in result_call["error"]

    def test_entity_function_restores_state(self) -> None:
        """Test that the entity function restores state from the context."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        # Mock context with existing state
        existing_state = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "msg1",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "$type": "response",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:05:00Z",
                        "messages": [
                            {
                                "role": "assistant",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "resp1",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        }

        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "correlationId": "corr-restore-1",
        }
        mock_context.get_state.return_value = existing_state

        with patch.object(DurableAgentState, "from_dict", wraps=DurableAgentState.from_dict) as from_dict_mock:
            entity_function(mock_context)

        from_dict_mock.assert_called_once_with(existing_state)


class TestErrorHandling:
    """Test suite for error handling."""

    async def test_entity_handles_agent_error(self) -> None:
        """Test that the entity handles agent execution errors."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Agent error"))

        entity = AgentEntity(mock_agent, state_provider=_InMemoryStateProvider(thread_id="conv-1"))

        result = await entity.run({
            "message": "Test message",
            "correlationId": "corr-app-error-1",
        })

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert content.type == "error"
        assert "Agent error" in (content.message or "")
        assert content.error_code == "Exception"

    def test_entity_function_handles_exception(self) -> None:
        """Test that the entity function handles exceptions gracefully."""
        mock_agent = Mock()
        # Force an exception by making get_input fail
        mock_agent.run = AsyncMock(side_effect=Exception("Test error"))

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.get_input.side_effect = Exception("Input error")
        mock_context.get_state.return_value = None

        # Execute entity function - should not raise
        entity_function(mock_context)

        # Verify error result was set
        assert mock_context.set_result.called
        result_call = mock_context.set_result.call_args[0][0]
        assert "error" in result_call


class TestIncomingRequestParsing:
    """Tests for parsing run requests with JSON and plain text bodies."""

    def _create_app(self) -> AgentFunctionApp:
        mock_agent = Mock()
        mock_agent.name = "ParserAgent"
        return AgentFunctionApp(agents=[mock_agent], enable_health_check=False)

    def test_parse_plain_text_body(self) -> None:
        """Test parsing a plain-text request body."""
        app = self._create_app()

        request = Mock()
        request.headers = {}
        request.params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"Plain text message"

        req_body, message, response_format = app._parse_incoming_request(request)

        assert req_body == {}
        assert message == "Plain text message"

        assert response_format == "text"

    def test_parse_plain_text_trims_whitespace(self) -> None:
        """Plain-text parser returns an empty string when the body contains only whitespace."""
        app = self._create_app()

        request = Mock()
        request.headers = {}
        request.params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"   "

        req_body, message, response_format = app._parse_incoming_request(request)

        assert req_body == {}
        assert message == ""
        assert response_format == "text"

    def test_accept_header_prefers_json(self) -> None:
        """Test that the Accept header can force JSON responses for plain-text bodies."""
        app = self._create_app()

        request = Mock()
        request.headers = {"accept": MIMETYPE_APPLICATION_JSON}
        request.params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"Plain text message"

        _, message, response_format = app._parse_incoming_request(request)

        assert message == "Plain text message"
        assert response_format == "json"

    def test_extract_thread_id_from_query_params(self) -> None:
        """Test thread identifier extraction from query parameters."""
        app = self._create_app()

        request = Mock()
        request.params = {"thread_id": "query-thread"}
        req_body: dict[str, Any] = {}

        thread_id = app._resolve_thread_id(request, req_body)

        assert thread_id == "query-thread"


class TestHttpRunRoute:
    """Tests for the HTTP run route behavior."""

    @staticmethod
    def _get_run_handler(agent: Mock) -> Callable[[func.HttpRequest, Any], Awaitable[func.HttpResponse]]:
        captured_handlers: dict[str | None, Callable[..., Awaitable[func.HttpResponse]]] = {}

        def capture_decorator(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                return func

            return decorator

        def capture_route(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                route_key = kwargs.get("route") if kwargs else None
                captured_handlers[route_key] = func
                return func

            return decorator

        with (
            patch.object(AgentFunctionApp, "function_name", new=capture_decorator),
            patch.object(AgentFunctionApp, "route", new=capture_route),
            patch.object(AgentFunctionApp, "durable_client_input", new=capture_decorator),
            patch.object(AgentFunctionApp, "entity_trigger", new=capture_decorator),
        ):
            AgentFunctionApp(agents=[agent], enable_health_check=False)

        run_route = f"agents/{agent.name}/run"
        return captured_handlers[run_route]

    async def test_http_run_accepts_plain_text(self) -> None:
        """Test that the HTTP handler accepts plain-text requests."""
        mock_agent = Mock()
        mock_agent.name = "HttpAgent"

        handler = self._get_run_handler(mock_agent)

        request = Mock()
        request.headers = {WAIT_FOR_RESPONSE_HEADER: "false"}
        request.params = {}
        request.route_params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"Plain text via HTTP"

        client = AsyncMock()

        response = await handler(request, client)

        assert response.status_code == 202
        assert response.mimetype == MIMETYPE_TEXT_PLAIN
        assert response.headers.get(THREAD_ID_HEADER) is not None
        assert response.get_body().decode("utf-8") == "Agent request accepted"

        signal_args = client.signal_entity.call_args[0]
        run_request = signal_args[2]

        assert run_request["message"] == "Plain text via HTTP"
        assert run_request["role"] == "user"
        assert "thread_id" not in run_request

    async def test_http_run_accept_header_returns_json(self) -> None:
        """Test that Accept header requesting JSON results in JSON response."""
        mock_agent = Mock()
        mock_agent.name = "HttpAgentJson"

        handler = self._get_run_handler(mock_agent)

        request = Mock()
        request.headers = {WAIT_FOR_RESPONSE_HEADER: "false", "Accept": MIMETYPE_APPLICATION_JSON}
        request.params = {}
        request.route_params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"Plain text via HTTP"

        client = AsyncMock()

        response = await handler(request, client)

        assert response.status_code == 202
        assert response.mimetype == MIMETYPE_APPLICATION_JSON
        assert response.headers.get(THREAD_ID_HEADER) is None
        body = response.get_body().decode("utf-8")
        assert '"status": "accepted"' in body

    async def test_http_run_rejects_empty_message(self) -> None:
        """Test that the HTTP handler rejects empty messages with a 400 response."""
        mock_agent = Mock()
        mock_agent.name = "HttpAgentEmpty"

        handler = self._get_run_handler(mock_agent)

        request = Mock()
        request.headers = {WAIT_FOR_RESPONSE_HEADER: "false"}
        request.params = {}
        request.route_params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"   "

        client = AsyncMock()

        response = await handler(request, client)

        assert response.status_code == 400
        assert response.mimetype == MIMETYPE_TEXT_PLAIN
        assert response.headers.get(THREAD_ID_HEADER) is not None
        assert response.get_body().decode("utf-8") == "Message is required"
        client.signal_entity.assert_not_called()


class TestMCPToolEndpoint:
    """Test suite for MCP tool endpoint functionality."""

    def test_init_with_mcp_tool_endpoint_enabled(self) -> None:
        """Test initialization with MCP tool endpoint enabled."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent], enable_mcp_tool_trigger=True)

        assert app.enable_mcp_tool_trigger is True

    def test_init_with_mcp_tool_endpoint_disabled(self) -> None:
        """Test initialization with MCP tool endpoint disabled (default)."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])

        assert app.enable_mcp_tool_trigger is False

    def test_add_agent_with_mcp_tool_trigger_enabled(self) -> None:
        """Test adding an agent with MCP tool trigger explicitly enabled."""
        mock_agent = Mock()
        mock_agent.name = "MCPAgent"
        mock_agent.description = "Test MCP Agent"

        with patch.object(AgentFunctionApp, "_setup_agent_functions") as setup_mock:
            app = AgentFunctionApp()
            app.add_agent(mock_agent, enable_mcp_tool_trigger=True)

        setup_mock.assert_called_once()
        _, _, _, _, enable_mcp = setup_mock.call_args[0]
        assert enable_mcp is True

    def test_add_agent_with_mcp_tool_trigger_disabled(self) -> None:
        """Test adding an agent with MCP tool trigger explicitly disabled."""
        mock_agent = Mock()
        mock_agent.name = "NoMCPAgent"

        with patch.object(AgentFunctionApp, "_setup_agent_functions") as setup_mock:
            app = AgentFunctionApp(enable_mcp_tool_trigger=True)
            app.add_agent(mock_agent, enable_mcp_tool_trigger=False)

        setup_mock.assert_called_once()
        _, _, _, _, enable_mcp = setup_mock.call_args[0]
        assert enable_mcp is False

    def test_agent_override_enables_mcp_when_app_disabled(self) -> None:
        """Test that per-agent override can enable MCP when app-level is disabled."""
        mock_agent = Mock()
        mock_agent.name = "OverrideAgent"

        with patch.object(AgentFunctionApp, "_setup_mcp_tool_trigger") as mcp_setup_mock:
            app = AgentFunctionApp(enable_mcp_tool_trigger=False)
            app.add_agent(mock_agent, enable_mcp_tool_trigger=True)

        mcp_setup_mock.assert_called_once()

    def test_agent_override_disables_mcp_when_app_enabled(self) -> None:
        """Test that per-agent override can disable MCP when app-level is enabled."""
        mock_agent = Mock()
        mock_agent.name = "NoOverrideAgent"

        with patch.object(AgentFunctionApp, "_setup_mcp_tool_trigger") as mcp_setup_mock:
            app = AgentFunctionApp(enable_mcp_tool_trigger=True)
            app.add_agent(mock_agent, enable_mcp_tool_trigger=False)

        mcp_setup_mock.assert_not_called()

    def test_setup_mcp_tool_trigger_registers_decorators(self) -> None:
        """Test that _setup_mcp_tool_trigger registers the correct decorators."""
        mock_agent = Mock()
        mock_agent.name = "MCPToolAgent"
        mock_agent.description = "Test MCP Tool"

        app = AgentFunctionApp()

        # Mock the decorators
        with (
            patch.object(app, "function_name") as func_name_mock,
            patch.object(app, "mcp_tool_trigger") as mcp_trigger_mock,
            patch.object(app, "durable_client_input") as client_mock,
        ):
            # Setup mock decorator chain
            func_name_mock.return_value = _identity_decorator
            mcp_trigger_mock.return_value = _identity_decorator
            client_mock.return_value = _identity_decorator

            app._setup_mcp_tool_trigger(mock_agent.name, mock_agent.description)

            # Verify decorators were called with correct parameters
            func_name_mock.assert_called_once()
            mcp_trigger_mock.assert_called_once_with(
                arg_name="context",
                tool_name=mock_agent.name,
                description=mock_agent.description,
                tool_properties=ANY,
                data_type=func.DataType.UNDEFINED,
            )
            client_mock.assert_called_once_with(client_name="client")

    def test_setup_mcp_tool_trigger_uses_default_description(self) -> None:
        """Test that _setup_mcp_tool_trigger uses default description when none provided."""
        mock_agent = Mock()
        mock_agent.name = "NoDescAgent"

        app = AgentFunctionApp()

        with (
            patch.object(app, "function_name", return_value=_identity_decorator),
            patch.object(app, "mcp_tool_trigger") as mcp_trigger_mock,
            patch.object(app, "durable_client_input", return_value=_identity_decorator),
        ):
            mcp_trigger_mock.return_value = _identity_decorator

            app._setup_mcp_tool_trigger(mock_agent.name, None)

            # Verify default description was used
            call_args = mcp_trigger_mock.call_args
            assert call_args[1]["description"] == f"Interact with {mock_agent.name} agent"

    async def test_handle_mcp_tool_invocation_with_json_string(self) -> None:
        """Test _handle_mcp_tool_invocation with JSON string context."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Mock the entity response
        mock_state = Mock()
        mock_state.entity_state = {
            "schemaVersion": "1.0.0",
            "data": {"conversationHistory": []},
        }
        client.read_entity_state.return_value = mock_state

        # Create JSON string context
        context = '{"arguments": {"query": "test query", "threadId": "test-thread"}}'

        with patch.object(app, "_get_response_from_entity") as get_response_mock:
            get_response_mock.return_value = {"status": "success", "response": "Test response"}

            result = await app._handle_mcp_tool_invocation("TestAgent", context, client)

            assert result == "Test response"
            get_response_mock.assert_called_once()

    async def test_handle_mcp_tool_invocation_with_json_context(self) -> None:
        """Test _handle_mcp_tool_invocation with JSON string context."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Mock the entity response
        mock_state = Mock()
        mock_state.entity_state = {
            "schemaVersion": "1.0.0",
            "data": {"conversationHistory": []},
        }
        client.read_entity_state.return_value = mock_state

        # Create JSON string context
        context = json.dumps({"arguments": {"query": "test query", "threadId": "test-thread"}})

        with patch.object(app, "_get_response_from_entity") as get_response_mock:
            get_response_mock.return_value = {"status": "success", "response": "Test response"}

            result = await app._handle_mcp_tool_invocation("TestAgent", context, client)

            assert result == "Test response"
            get_response_mock.assert_called_once()

    async def test_handle_mcp_tool_invocation_missing_query(self) -> None:
        """Test _handle_mcp_tool_invocation raises ValueError when query is missing."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Context missing query (as JSON string)
        context = json.dumps({"arguments": {}})

        with pytest.raises(ValueError, match="missing required 'query' argument"):
            await app._handle_mcp_tool_invocation("TestAgent", context, client)

    async def test_handle_mcp_tool_invocation_invalid_json(self) -> None:
        """Test _handle_mcp_tool_invocation raises ValueError for invalid JSON."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Invalid JSON string
        context = "not valid json"

        with pytest.raises(ValueError, match="Invalid MCP context format"):
            await app._handle_mcp_tool_invocation("TestAgent", context, client)

    async def test_handle_mcp_tool_invocation_runtime_error(self) -> None:
        """Test _handle_mcp_tool_invocation raises RuntimeError when agent fails."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Mock the entity response
        mock_state = Mock()
        mock_state.entity_state = {
            "schemaVersion": "1.0.0",
            "data": {"conversationHistory": []},
        }
        client.read_entity_state.return_value = mock_state

        context = '{"arguments": {"query": "test query"}}'

        with patch.object(app, "_get_response_from_entity") as get_response_mock:
            get_response_mock.return_value = {"status": "failed", "error": "Agent error"}

            with pytest.raises(RuntimeError, match="Agent execution failed"):
                await app._handle_mcp_tool_invocation("TestAgent", context, client)

    async def test_handle_mcp_tool_invocation_ignores_agent_name_in_thread_id(self) -> None:
        """Test that MCP tool invocation uses the agent_name parameter, not the name from thread_id."""
        mock_agent = Mock()
        mock_agent.name = "PlantAdvisor"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        # Mock the entity response
        mock_state = Mock()
        mock_state.entity_state = {
            "schemaVersion": "1.0.0",
            "data": {"conversationHistory": []},
        }
        client.read_entity_state.return_value = mock_state

        # Thread ID contains a different agent name (@StockAdvisor@poc123)
        # but we're invoking PlantAdvisor - it should use PlantAdvisor's entity
        context = json.dumps({"arguments": {"query": "test query", "threadId": "@StockAdvisor@test123"}})

        with patch.object(app, "_get_response_from_entity") as get_response_mock:
            get_response_mock.return_value = {"status": "success", "response": "Test response"}

            await app._handle_mcp_tool_invocation("PlantAdvisor", context, client)

            # Verify signal_entity was called with PlantAdvisor's entity, not StockAdvisor's
            client.signal_entity.assert_called_once()
            call_args = client.signal_entity.call_args
            entity_id = call_args[0][0]

            # Entity name should be dafx-PlantAdvisor, not dafx-StockAdvisor
            assert entity_id.name == "dafx-PlantAdvisor"
            assert entity_id.key == "test123"

    async def test_handle_mcp_tool_invocation_uses_plain_thread_id_as_key(self) -> None:
        """Test that a plain thread_id (not in @name@key format) is used as-is for the key."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        app = AgentFunctionApp(agents=[mock_agent])
        client = AsyncMock()

        mock_state = Mock()
        mock_state.entity_state = {
            "schemaVersion": "1.0.0",
            "data": {"conversationHistory": []},
        }
        client.read_entity_state.return_value = mock_state

        # Plain thread_id without @name@key format
        context = json.dumps({"arguments": {"query": "test query", "threadId": "simple-thread-123"}})

        with patch.object(app, "_get_response_from_entity") as get_response_mock:
            get_response_mock.return_value = {"status": "success", "response": "Test response"}

            await app._handle_mcp_tool_invocation("TestAgent", context, client)

            client.signal_entity.assert_called_once()
            call_args = client.signal_entity.call_args
            entity_id = call_args[0][0]

            assert entity_id.name == "dafx-TestAgent"
            assert entity_id.key == "simple-thread-123"

    def test_health_check_includes_mcp_tool_enabled(self) -> None:
        """Test that health check endpoint includes mcp_tool_enabled field."""
        mock_agent = Mock()
        mock_agent.name = "HealthAgent"

        app = AgentFunctionApp(agents=[mock_agent], enable_mcp_tool_trigger=True)

        # Capture the health check handler function
        captured_handler: Callable[[func.HttpRequest], func.HttpResponse] | None = None

        def capture_decorator(*args: Any, **kwargs: Any) -> Callable[[TFunc], TFunc]:
            def decorator(func: TFunc) -> TFunc:
                nonlocal captured_handler
                captured_handler = func
                return func

            return decorator

        with patch.object(app, "route", side_effect=capture_decorator):
            app._setup_health_route()

        # Verify we captured the handler
        assert captured_handler is not None

        # Call the health handler
        request = Mock()
        response = captured_handler(request)

        # Verify response includes mcp_tool_enabled
        import json

        body = json.loads(response.get_body().decode("utf-8"))
        assert "agents" in body
        assert len(body["agents"]) == 1
        assert "mcp_tool_enabled" in body["agents"][0]
        assert body["agents"][0]["mcp_tool_enabled"] is True


class TestAgentFunctionAppWorkflow:
    """Test suite for AgentFunctionApp workflow support."""

    def test_init_with_workflow_stores_workflow(self) -> None:
        """Test that workflow is stored when provided."""
        mock_workflow = Mock()
        mock_workflow.executors = {}

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity"),
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration"),
        ):
            app = AgentFunctionApp(workflow=mock_workflow)

        assert app.workflow is mock_workflow

    def test_init_with_workflow_extracts_agents(self) -> None:
        """Test that agents are extracted from workflow executors."""
        from agent_framework import AgentExecutor

        mock_agent = Mock()
        mock_agent.name = "WorkflowAgent"

        mock_executor = Mock(spec=AgentExecutor)
        mock_executor.agent = mock_agent

        mock_workflow = Mock()
        mock_workflow.executors = {"WorkflowAgent": mock_executor}

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity"),
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration"),
            patch.object(AgentFunctionApp, "_setup_agent_functions"),
        ):
            app = AgentFunctionApp(workflow=mock_workflow)

        assert "WorkflowAgent" in app.agents

    def test_init_with_workflow_calls_setup_methods(self) -> None:
        """Test that workflow setup methods are called."""
        mock_workflow = Mock()
        mock_workflow.executors = {}

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity") as setup_exec,
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration") as setup_orch,
        ):
            AgentFunctionApp(workflow=mock_workflow)

        setup_exec.assert_called_once()
        setup_orch.assert_called_once()

    def test_init_without_workflow_does_not_call_workflow_setup(self) -> None:
        """Test that workflow setup is not called when no workflow provided."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity") as setup_exec,
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration") as setup_orch,
        ):
            AgentFunctionApp(agents=[mock_agent])

        setup_exec.assert_not_called()
        setup_orch.assert_not_called()

    def test_build_status_url(self) -> None:
        """Test _build_status_url constructs correct URL."""
        mock_workflow = Mock()
        mock_workflow.executors = {}

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity"),
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration"),
        ):
            app = AgentFunctionApp(workflow=mock_workflow)

        url = app._build_status_url("http://localhost:7071/api/workflow/run", "instance-123")

        assert url == "http://localhost:7071/api/workflow/status/instance-123"

    def test_build_status_url_handles_trailing_slash(self) -> None:
        """Test _build_status_url handles URLs without /api/ correctly."""
        mock_workflow = Mock()
        mock_workflow.executors = {}

        with (
            patch.object(AgentFunctionApp, "_setup_executor_activity"),
            patch.object(AgentFunctionApp, "_setup_workflow_orchestration"),
        ):
            app = AgentFunctionApp(workflow=mock_workflow)

        url = app._build_status_url("http://localhost:7071/", "instance-456")

        assert "instance-456" in url


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
