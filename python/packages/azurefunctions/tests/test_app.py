# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentFunctionApp."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from unittest.mock import ANY, AsyncMock, Mock, patch

import azure.durable_functions as df
import azure.functions as func
import pytest
from agent_framework import AgentRunResponse, ChatMessage

from agent_framework_azurefunctions import AgentFunctionApp
from agent_framework_azurefunctions._app import WAIT_FOR_RESPONSE_FIELD, WAIT_FOR_RESPONSE_HEADER
from agent_framework_azurefunctions._entities import AgentEntity, AgentState, create_agent_entity

TFunc = TypeVar("TFunc", bound=Callable[..., Any])


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
        _, _, passed_callback, enable_http_endpoint = setup_mock.call_args[0]
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
        _, _, passed_callback, enable_http_endpoint = setup_mock.call_args[0]
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
        _, _, passed_callback, enable_http_endpoint = setup_mock.call_args[0]
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
        assert app.agent_http_endpoint_flags["OverrideAgent"] is True

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
        assert app.agent_http_endpoint_flags["DisabledOverride"] is False

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
            return_value=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Test response")])
        )

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context,
            {"message": "Test message", "thread_id": "test-conv-123", "correlation_id": "corr-app-entity-1"},
        )

        assert result["status"] == "success"
        assert result["response"] == "Test response"
        assert result["message"] == "Test message"
        assert result["thread_id"] == "test-conv-123"
        assert entity.state.message_count == 1

    async def test_entity_stores_conversation_history(self) -> None:
        """Test that the entity stores conversation history."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Response 1")])
        )

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        # Send first message
        await entity.run_agent(
            mock_context, {"message": "Message 1", "thread_id": "conv-1", "correlation_id": "corr-app-entity-2"}
        )

        history = entity.state.conversation_history
        assert len(history) == 2  # User + assistant

        user_msg = history[0]
        user_role = getattr(user_msg.role, "value", user_msg.role)
        assert user_role == "user"
        assert user_msg.text == "Message 1"

        assistant_msg = history[1]
        assistant_role = getattr(assistant_msg.role, "value", assistant_msg.role)
        assert assistant_role == "assistant"
        assert assistant_msg.text == "Response 1"

    async def test_entity_increments_message_count(self) -> None:
        """Test that the entity increments the message count."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Response")])
        )

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        assert entity.state.message_count == 0

        await entity.run_agent(
            mock_context, {"message": "Message 1", "thread_id": "conv-1", "correlation_id": "corr-app-entity-3a"}
        )
        assert entity.state.message_count == 1

        await entity.run_agent(
            mock_context, {"message": "Message 2", "thread_id": "conv-1", "correlation_id": "corr-app-entity-3b"}
        )
        assert entity.state.message_count == 2

    def test_entity_reset(self) -> None:
        """Test that entity reset clears state."""
        mock_agent = Mock()
        entity = AgentEntity(mock_agent)

        # Set some state
        entity.state.message_count = 10
        entity.state.last_response = "Some response"
        entity.state.conversation_history = [
            ChatMessage(role="user", text="test", additional_properties={"timestamp": "2024-01-01T00:00:00Z"})
        ]

        # Reset
        mock_context = Mock()
        entity.reset(mock_context)

        assert entity.state.message_count == 0
        assert entity.state.last_response is None
        assert len(entity.state.conversation_history) == 0


class TestAgentEntityFactory:
    """Test suite for the entity factory function."""

    def test_create_agent_entity_returns_function(self) -> None:
        """Test that create_agent_entity returns a function."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        assert callable(entity_function)

    def test_entity_function_handles_run_agent_operation(self) -> None:
        """Test that the entity function handles the run_agent operation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(
            return_value=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Response")])
        )

        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "run_agent"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "thread_id": "conv-123",
            "correlation_id": "corr-app-factory-1",
        }
        mock_context.get_state.return_value = None

        # Execute entity function
        entity_function(mock_context)

        # Verify result was set
        assert mock_context.set_result.called
        assert mock_context.set_state.called

    def test_entity_function_handles_reset_operation(self) -> None:
        """Test that the entity function handles the reset operation."""
        mock_agent = Mock()
        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = {
            "message_count": 5,
            "conversation_history": [{"role": "user", "content": "test"}],
            "last_response": "Test",
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
            "message_count": 3,
            "conversation_history": [{"role": "user", "content": "msg1"}, {"role": "assistant", "content": "resp1"}],
            "last_response": "resp1",
        }

        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = existing_state

        with patch.object(AgentState, "restore_state") as restore_state_mock:
            entity_function(mock_context)

        restore_state_mock.assert_called_once_with(existing_state)


class TestErrorHandling:
    """Test suite for error handling."""

    async def test_entity_handles_agent_error(self) -> None:
        """Test that the entity handles agent execution errors."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Agent error"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context, {"message": "Test message", "thread_id": "conv-1", "correlation_id": "corr-app-error-1"}
        )

        assert result["status"] == "error"
        assert "error" in result
        assert "Agent error" in result["error"]
        assert result["error_type"] == "Exception"

    def test_entity_function_handles_exception(self) -> None:
        """Test that the entity function handles exceptions gracefully."""
        mock_agent = Mock()
        # Force an exception by making get_input fail
        mock_agent.run = AsyncMock(side_effect=Exception("Test error"))

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run_agent"
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
        request.headers = {"accept": "application/json"}
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
        req_body = {}

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
        assert response.mimetype == "text/plain"
        assert response.headers.get("x-ms-thread-id") is not None
        assert response.get_body().decode("utf-8") == "Agent request accepted"

        signal_args = client.signal_entity.call_args[0]
        run_request = signal_args[2]

        assert run_request["message"] == "Plain text via HTTP"
        assert run_request["role"] == "user"
        assert "thread_id" in run_request

    async def test_http_run_accept_header_returns_json(self) -> None:
        """Test that Accept header requesting JSON results in JSON response."""
        mock_agent = Mock()
        mock_agent.name = "HttpAgentJson"

        handler = self._get_run_handler(mock_agent)

        request = Mock()
        request.headers = {WAIT_FOR_RESPONSE_HEADER: "false", "Accept": "application/json"}
        request.params = {}
        request.route_params = {}
        request.get_json.side_effect = ValueError("Invalid JSON")
        request.get_body.return_value = b"Plain text via HTTP"

        client = AsyncMock()

        response = await handler(request, client)

        assert response.status_code == 202
        assert response.mimetype == "application/json"
        assert response.headers.get("x-ms-thread-id") is None
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
        assert response.mimetype == "text/plain"
        assert response.headers.get("x-ms-thread-id") is not None
        assert response.get_body().decode("utf-8") == "Message is required"
        client.signal_entity.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
