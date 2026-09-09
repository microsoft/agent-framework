# Copyright (c) Microsoft. All rights reserved.

"""Tests for AGUIChatClient."""

import json
from collections.abc import AsyncGenerator, Awaitable, Mapping, MutableSequence
from typing import Any, cast

import httpx
import pytest
from ag_ui.core import Interrupt, ResumeEntry
from agent_framework import (
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    tool,
)
from pytest import MonkeyPatch

from agent_framework_ag_ui._client import AGUIChatClient
from agent_framework_ag_ui._http_service import AGUIHttpService


class StubAGUIChatClient(AGUIChatClient):
    """Testable wrapper exposing protected helpers."""

    @property
    def http_service(self) -> AGUIHttpService:
        """Expose http service for monkeypatching."""
        return self._http_service

    def extract_state_from_messages(self, messages: list[Message]) -> tuple[list[Message], dict[str, Any] | None]:
        """Expose state extraction helper."""
        return self._extract_state_from_messages(messages)

    def convert_messages_to_agui_format(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Expose message conversion helper."""
        return self._convert_messages_to_agui_format(messages)

    def get_thread_id(self, options: ChatOptions[Any] | dict[str, Any] | None) -> str:
        """Expose thread id helper."""
        return self._get_thread_id(options)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    def inner_get_response(
        self,
        *,
        messages: MutableSequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Proxy to protected response call."""
        return self._inner_get_response(messages=messages, options=options, stream=stream)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


class TestAGUIChatClient:
    """Test suite for AGUIChatClient."""

    async def test_client_initialization(self) -> None:
        """Test client initialization."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")

        assert client.http_service is not None
        assert client.http_service.endpoint.startswith("http://localhost:8888")

    async def test_client_context_manager(self) -> None:
        """Test client as async context manager."""
        async with StubAGUIChatClient(endpoint="http://localhost:8888/") as client:
            assert client is not None

    async def test_extract_state_from_messages_no_state(self) -> None:
        """Test state extraction when no state is present."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        messages = [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Hi there"]),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert result_messages == messages
        assert state is None

    async def test_extract_state_from_messages_with_state(self) -> None:
        """A marked state carrier populates the request state."""
        from agent_framework_ag_ui import state_carrier

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")

        state_data = {"key": "value", "count": 42}

        messages = [
            Message(role="user", contents=["Hello"]),
            Message(
                role="user",
                contents=[state_carrier(state_data)],
            ),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert len(result_messages) == 1
        assert result_messages[0].text == "Hello"
        assert state == state_data

    async def test_extract_state_from_messages_removes_historical_carriers_and_uses_latest_state(self) -> None:
        """Historical carriers are removed and the most recent carrier supplies state."""
        from agent_framework_ag_ui import state_carrier

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        old_carrier = Message(role="user", contents=[state_carrier({"version": "old"})])
        new_carrier = Message(role="user", contents=[state_carrier({"version": "new"})])
        messages = [
            Message(role="user", contents=["Initial prompt"]),
            old_carrier,
            Message(role="assistant", contents=["Initial response"]),
            new_carrier,
            Message(role="user", contents=["Follow-up prompt"]),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert result_messages == [messages[0], messages[2], messages[4]]
        assert state == {"version": "new"}

    async def test_explicit_final_carrier_wins_over_legacy_fallback(self) -> None:
        """Legacy mode does not reinterpret an earlier document after removing a final carrier."""
        from agent_framework_ag_ui import state_carrier

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        messages = [
            Message(
                role="user",
                contents=[Content.from_data(b'{"document":"keep"}', media_type="application/json")],
            ),
            Message(role="user", contents=[state_carrier({"source": "explicit"})]),
        ]

        result_messages, state = client._extract_state_from_messages(
            messages,
            allow_legacy_state_carrier=True,
        )

        assert result_messages == messages[:1]
        assert state == {"source": "explicit"}

    async def test_extract_state_from_messages_with_parameterized_data_uri(self) -> None:
        """Test state extraction from JSON data URIs with media type parameters."""
        import base64

        from agent_framework_ag_ui._state import STATE_CARRIER_KEY

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")

        state_data = {"key": "value", "count": 42}
        state_json = json.dumps(state_data)
        state_b64 = base64.b64encode(state_json.encode("utf-8")).decode("utf-8")

        messages = [
            Message(role="user", contents=["Hello"]),
            Message(
                role="user",
                contents=[
                    Content.from_uri(
                        uri=f"data:application/json;charset=utf-8;base64,{state_b64}",
                        additional_properties={STATE_CARRIER_KEY: True},
                    )
                ],
            ),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert len(result_messages) == 1
        assert result_messages[0].text == "Hello"
        assert state == state_data

    async def test_extract_state_invalid_json(self) -> None:
        """Test state extraction with invalid JSON."""
        import base64

        from agent_framework_ag_ui._state import STATE_CARRIER_KEY

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")

        invalid_json = "not valid json"
        state_b64 = base64.b64encode(invalid_json.encode("utf-8")).decode("utf-8")

        messages = [
            Message(
                role="user",
                contents=[
                    Content.from_uri(
                        uri=f"data:application/json;base64,{state_b64}",
                        additional_properties={STATE_CARRIER_KEY: True},
                    )
                ],
            ),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert result_messages == []
        assert state is None

    async def test_extract_state_invalid_base64(self) -> None:
        """Test state extraction with invalid base64."""
        from agent_framework_ag_ui._state import STATE_CARRIER_KEY

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")

        messages = [
            Message(
                role="user",
                contents=[
                    Content.from_uri(
                        uri="data:application/json;base64,not-valid-base64!",
                        additional_properties={STATE_CARRIER_KEY: True},
                    )
                ],
            ),
        ]

        result_messages, state = client.extract_state_from_messages(messages)

        assert result_messages == []
        assert state is None

    async def test_convert_messages_to_agui_format(self) -> None:
        """Test message conversion to AG-UI format."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        messages = [
            Message(role="user", contents=["What is the weather?"]),
            Message(role="assistant", contents=["Let me check."], message_id="msg_123"),
        ]

        agui_messages = client.convert_messages_to_agui_format(messages)

        assert len(agui_messages) == 2
        assert agui_messages[0]["role"] == "user"
        assert agui_messages[0]["content"] == "What is the weather?"
        assert agui_messages[1]["role"] == "assistant"
        assert agui_messages[1]["content"] == "Let me check."
        assert agui_messages[1]["id"] == "msg_123"

    async def test_sends_multimodal_messages_in_request(self) -> None:
        """The client sends ordered multimodal content in the HTTP request JSON."""
        captured_request: dict[str, Any] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"type":"RUN_STARTED","threadId":"thread_1","runId":"run_1"}\n\n'
                    b'data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"msg_1","delta":"ok"}\n\n'
                    b'data: {"type":"RUN_FINISHED","threadId":"thread_1","runId":"run_1"}\n\n'
                ),
            )

        message = Message(
            role="user",
            contents=[
                Content.from_text("describe this"),
                Content.from_uri("https://example.com/cat.png", media_type="image/png"),
                Content.from_data(b"abc", media_type="image/png"),
            ],
            message_id="msg-request",
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = StubAGUIChatClient(endpoint="http://localhost:8888/", http_client=http_client)
            response = await client.inner_get_response(messages=[message], options={})

        assert response is not None
        assert captured_request["messages"] == [
            {
                "id": "msg-request",
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "value": "https://example.com/cat.png",
                            "mimeType": "image/png",
                        },
                    },
                    {
                        "type": "image",
                        "source": {"type": "data", "value": "YWJj", "mimeType": "image/png"},
                    },
                ],
            }
        ]

    async def test_sends_mixed_json_attachment_when_legacy_compatibility_is_enabled(self) -> None:
        """Legacy compatibility does not consume a prompt with a JSON attachment."""
        captured_request: dict[str, Any] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"type":"RUN_STARTED","threadId":"thread_1","runId":"run_1"}\n\n'
                    b'data: {"type":"RUN_FINISHED","threadId":"thread_1","runId":"run_1"}\n\n'
                ),
            )

        message = Message(
            role="user",
            contents=[
                Content.from_text("summarize the attached JSON document"),
                Content.from_data(b'{"document":"keep me"}', media_type="application/json"),
            ],
            message_id="msg-json-document",
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = StubAGUIChatClient(endpoint="http://localhost:8888/", http_client=http_client)
            response = await client.inner_get_response(
                messages=[message],
                options={"allow_legacy_state_carrier": True},
            )

        assert response is not None
        assert "state" not in captured_request
        assert captured_request["messages"] == [
            {
                "id": "msg-json-document",
                "role": "user",
                "content": [
                    {"type": "text", "text": "summarize the attached JSON document"},
                    {
                        "type": "document",
                        "source": {
                            "type": "data",
                            "value": "eyJkb2N1bWVudCI6ImtlZXAgbWUifQ==",
                            "mimeType": "application/json",
                        },
                    },
                ],
            }
        ]

    async def test_sends_json_attachment_without_state_carrier_in_request(self) -> None:
        """An unmarked JSON-only document is sent as AG-UI document input."""
        captured_request: dict[str, Any] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"type":"RUN_STARTED","threadId":"thread_1","runId":"run_1"}\n\n'
                    b'data: {"type":"RUN_FINISHED","threadId":"thread_1","runId":"run_1"}\n\n'
                ),
            )

        message = Message(
            role="user",
            contents=[Content.from_data(b'{"document":"keep me"}', media_type="application/json")],
            message_id="msg-json-only-document",
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = StubAGUIChatClient(endpoint="http://localhost:8888/", http_client=http_client)
            response = await client.inner_get_response(messages=[message], options={})

        assert response is not None
        assert "state" not in captured_request
        assert captured_request["messages"] == [
            {
                "id": "msg-json-only-document",
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "data",
                            "value": "eyJkb2N1bWVudCI6ImtlZXAgbWUifQ==",
                            "mimeType": "application/json",
                        },
                    }
                ],
            }
        ]

    async def test_sends_legacy_json_state_with_compatibility_option(self) -> None:
        """The legacy option extracts an unmarked final JSON state during migration."""
        captured_request: dict[str, Any] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"type":"RUN_STARTED","threadId":"thread_1","runId":"run_1"}\n\n'
                    b'data: {"type":"RUN_FINISHED","threadId":"thread_1","runId":"run_1"}\n\n'
                ),
            )

        message = Message(
            role="user",
            contents=[Content.from_data(b'{"legacy":"keep"}', media_type="application/json")],
            message_id="msg-legacy-state",
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = StubAGUIChatClient(endpoint="http://localhost:8888/", http_client=http_client)
            with pytest.warns(DeprecationWarning, match="state_carrier"):
                response = await client.inner_get_response(
                    messages=[message],
                    options={"allow_legacy_state_carrier": True},
                )

        assert response is not None
        assert captured_request["state"] == {"legacy": "keep"}
        assert captured_request["messages"] == []

    async def test_get_thread_id_from_metadata(self) -> None:
        """Test thread ID extraction from metadata."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        chat_options = ChatOptions(metadata={"thread_id": "existing_thread_123"})

        thread_id = client.get_thread_id(chat_options)

        assert thread_id == "existing_thread_123"

    async def test_get_thread_id_generation(self) -> None:
        """Test automatic thread ID generation."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        chat_options = ChatOptions()

        thread_id = client.get_thread_id(chat_options)

        assert thread_id.startswith("thread_")
        assert len(thread_id) > 7

    async def test_get_response_streaming(self, monkeypatch: MonkeyPatch) -> None:
        """Test streaming response method."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Hello"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": " world"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test message"])]
        chat_options = ChatOptions()

        updates: list[ChatResponseUpdate] = []
        stream = client.inner_get_response(messages=messages, stream=True, options=chat_options)
        assert isinstance(stream, ResponseStream)
        async for update in stream:
            updates.append(cast(ChatResponseUpdate, update))

        assert len(updates) == 4
        assert updates[0].additional_properties is not None
        assert updates[0].additional_properties["thread_id"] == "thread_1"

        first_content = updates[1].contents[0]
        second_content = updates[2].contents[0]
        assert first_content.type == "text"
        assert second_content.type == "text"
        assert first_content.text == "Hello"
        assert second_content.text == " world"

    async def test_get_response_non_streaming(self, monkeypatch: MonkeyPatch) -> None:
        """Test non-streaming response method."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Complete response"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test message"])]
        chat_options: dict[str, Any] = {}

        response = await client.inner_get_response(messages=messages, options=chat_options)

        assert response is not None
        assert len(response.messages) > 0
        assert "Complete response" in response.text

    async def test_tool_handling(self, monkeypatch: MonkeyPatch) -> None:
        """Test that client tool metadata is sent to server.

        Client tool metadata (name, description, schema) is sent to server for planning.
        When server requests a client function, function invocation mixin
        intercepts and executes it locally. This matches .NET AG-UI implementation.
        """
        from agent_framework import tool

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return "result"

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            # Client tool metadata should be sent to server
            tools: list[dict[str, Any]] | None = kwargs.get("tools")
            assert tools is not None
            assert len(tools) == 1
            tool_entry = tools[0]
            assert tool_entry["name"] == "test_tool"
            assert tool_entry["description"] == "Test tool."
            assert "parameters" in tool_entry
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test with tools"])]
        chat_options = ChatOptions(tools=[test_tool])

        response = await client.inner_get_response(messages=messages, options=chat_options)

        assert response is not None

    async def test_server_tool_calls_unwrapped_after_invocation(self, monkeypatch: MonkeyPatch) -> None:
        """Ensure server-side tool calls are exposed as FunctionCallContent after processing."""

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "get_time_zone"},
            {"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", "delta": '{"location": "Seattle"}'},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test server tool execution"])]

        updates: list[ChatResponseUpdate] = []
        async for update in client.get_response(messages, stream=True):
            updates.append(update)

        function_calls = [
            content for update in updates for content in update.contents if content.type == "function_call"
        ]
        assert function_calls
        assert function_calls[0].name == "get_time_zone"

        assert not any(content.type == "server_function_call" for update in updates for content in update.contents)

    async def test_server_tool_calls_not_executed_locally(self, monkeypatch: MonkeyPatch) -> None:
        """Server tools should not trigger local function invocation even when client tools exist."""

        @tool
        def client_tool() -> str:
            """Client tool stub."""
            return "client"

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "get_time_zone"},
            {"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", "delta": '{"location": "Seattle"}'},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        async def fake_auto_invoke(*args: object, **kwargs: Any) -> None:
            function_call = kwargs.get("function_call_content") or args[0]
            raise AssertionError(f"Unexpected local execution of server tool: {getattr(function_call, 'name', '?')}")

        monkeypatch.setattr("agent_framework._tools._auto_invoke_function", fake_auto_invoke)

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test server tool execution"])]

        async for _ in client.get_response(
            messages, stream=True, options={"tool_choice": "auto", "tools": [client_tool]}
        ):
            pass

    async def test_state_transmission(self, monkeypatch: MonkeyPatch) -> None:
        """A marked state carrier is transmitted through the request state field."""
        from agent_framework_ag_ui import state_carrier

        state_data = {"user_id": "123", "session": "abc"}

        messages = [
            Message(role="user", contents=["Hello"]),
            Message(
                role="user",
                contents=[state_carrier(state_data)],
            ),
        ]

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            assert kwargs.get("state") == state_data
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        chat_options = ChatOptions()

        response = await client.inner_get_response(messages=messages, options=chat_options)

        assert response is not None

    async def test_extract_state_from_empty_messages(self) -> None:
        """Empty messages list returns empty list and None state."""
        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        result_messages, state = client.extract_state_from_messages([])
        assert result_messages == []
        assert state is None

    async def test_register_server_tool_non_dict_config(self) -> None:
        """Non-dict function_invocation_configuration is a no-op."""
        client = StubAGUIChatClient(
            endpoint="http://localhost:8888/",
            function_invocation_configuration=None,  # type: ignore[arg-type]
        )
        # Should not raise
        client._register_server_tool_placeholder("some_tool")

    async def test_non_streaming_response(self, monkeypatch: MonkeyPatch) -> None:
        """Non-streaming path collects updates into ChatResponse."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Hello"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test"])]
        response = await client.inner_get_response(messages=messages, options={}, stream=False)

        assert response is not None
        assert len(response.messages) > 0

    async def test_client_tool_sets_additional_properties(self, monkeypatch: MonkeyPatch) -> None:
        """Client tool content gets agui_thread_id additional property."""

        @tool
        def my_tool(param: str) -> str:
            """My tool."""
            return "result"

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "my_tool"},
            {"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", "delta": '{"param": "test"}'},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["Test"])]
        updates: list[ChatResponseUpdate] = []
        stream = client.inner_get_response(messages=messages, stream=True, options={"tools": [my_tool]})
        assert isinstance(stream, ResponseStream)
        async for update in stream:
            updates.append(cast(ChatResponseUpdate, update))

        # Find the function_call content - it should have agui_thread_id
        found = False
        for update in updates:
            for content in update.contents:
                if content.type == "function_call" and content.name == "my_tool":
                    assert content.additional_properties is not None
                    assert "agui_thread_id" in content.additional_properties
                    found = True
                    break
        assert found, "Expected to find function_call content for my_tool"

    async def test_tool_call_args_id_mismatch_does_not_execute_current_client_tool(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Mismatched TOOL_CALL_ARGS must not be rebound to the latest client tool."""
        executed: list[int] = []

        @tool
        def danger_tool(amount: int) -> str:
            """Record an invocation for the regression assertion."""
            executed.append(amount)
            return f"danger={amount}"

        call_count = 0

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_events = [
                    {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
                    {"type": "TOOL_CALL_START", "toolCallId": "safe", "toolName": "safe_tool"},
                    {"type": "TOOL_CALL_START", "toolCallId": "danger", "toolName": "danger_tool"},
                    {"type": "TOOL_CALL_ARGS", "toolCallId": "safe", "delta": '{"amount": 100}'},
                    {"type": "TOOL_CALL_END", "toolCallId": "safe"},
                    {"type": "TOOL_CALL_END", "toolCallId": "danger"},
                    {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
                ]
            else:
                mock_events = [
                    {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_2"},
                    {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "done"},
                    {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_2"},
                ]

            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        response = await client.get_response(
            [Message(role="user", contents=["Test"])],
            options={"tools": [danger_tool]},
        )

        assert response.text == "done"
        assert executed == []

    async def test_interrupt_options_transmission(self, monkeypatch: MonkeyPatch) -> None:
        """Interrupt option fields are forwarded to the HTTP service."""
        available_interrupts = [{"id": "req_1", "type": "request_info"}]
        expected_available_interrupts = [{"id": "req_1", "reason": "input_required"}]
        resume_payload = {"interrupts": [{"id": "req_1", "value": "approved"}]}
        expected_resume_payload = [{"interruptId": "req_1", "status": "resolved", "payload": "approved"}]

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            assert kwargs.get("available_interrupts") == expected_available_interrupts
            assert kwargs.get("resume") == expected_resume_payload
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        messages = [Message(role="user", contents=["continue"])]
        options = {
            "available_interrupts": available_interrupts,
            "resume": resume_payload,
        }

        response = await client.inner_get_response(messages=messages, options=options)
        assert response is not None

    async def test_typed_interrupt_options_forward_canonical_protocol_shape(self, monkeypatch: MonkeyPatch) -> None:
        """Typed interrupt options are forwarded as canonical protocol JSON."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args: object, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
            assert kwargs.get("available_interrupts") == [
                {
                    "id": "approval_1",
                    "reason": "tool_call",
                    "toolCallId": "call_1",
                    "responseSchema": {"type": "object"},
                }
            ]
            assert kwargs.get("resume") == [
                {"interruptId": "approval_1", "status": "resolved", "payload": {"approved": True}}
            ]
            for event in mock_events:
                yield event

        client = StubAGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client.http_service, "post_run", mock_post_run)

        options: dict[str, Any] = {
            "available_interrupts": [
                Interrupt(
                    id="approval_1",
                    reason="tool_call",
                    tool_call_id="call_1",
                    response_schema={"type": "object"},
                )
            ],
            "resume": [ResumeEntry(interrupt_id="approval_1", status="resolved", payload={"approved": True})],
        }

        response = await client.inner_get_response(
            messages=[Message(role="user", contents=["continue"])],
            options=options,
        )

        assert response is not None
