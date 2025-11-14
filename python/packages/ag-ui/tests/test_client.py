"""Tests for AGUIChatClient."""

import json

from agent_framework import ChatMessage, ChatOptions, FunctionCallContent, Role, ai_function

from agent_framework_ag_ui._client import AGUIChatClient, ServerFunctionCallContent


class TestAGUIChatClient:
    """Test suite for AGUIChatClient."""

    async def test_client_initialization(self) -> None:
        """Test client initialization."""
        client = AGUIChatClient(endpoint="http://localhost:8888/")

        assert client._http_service is not None
        assert client._http_service.endpoint.startswith("http://localhost:8888")

    async def test_client_context_manager(self) -> None:
        """Test client as async context manager."""
        async with AGUIChatClient(endpoint="http://localhost:8888/") as client:
            assert client is not None

    async def test_extract_state_from_messages_no_state(self) -> None:
        """Test state extraction when no state is present."""
        client = AGUIChatClient(endpoint="http://localhost:8888/")
        messages = [
            ChatMessage(role="user", text="Hello"),
            ChatMessage(role="assistant", text="Hi there"),
        ]

        result_messages, state = client._extract_state_from_messages(messages)

        assert result_messages == messages
        assert state is None

    async def test_extract_state_from_messages_with_state(self) -> None:
        """Test state extraction from last message."""
        import base64

        client = AGUIChatClient(endpoint="http://localhost:8888/")

        state_data = {"key": "value", "count": 42}
        state_json = json.dumps(state_data)
        state_b64 = base64.b64encode(state_json.encode("utf-8")).decode("utf-8")

        from agent_framework import DataContent

        messages = [
            ChatMessage(role="user", text="Hello"),
            ChatMessage(
                role="user",
                contents=[DataContent(uri=f"data:application/json;base64,{state_b64}")],
            ),
        ]

        result_messages, state = client._extract_state_from_messages(messages)

        assert len(result_messages) == 1
        assert result_messages[0].text == "Hello"
        assert state == state_data

    async def test_extract_state_invalid_json(self) -> None:
        """Test state extraction with invalid JSON."""
        import base64

        client = AGUIChatClient(endpoint="http://localhost:8888/")

        invalid_json = "not valid json"
        state_b64 = base64.b64encode(invalid_json.encode("utf-8")).decode("utf-8")

        from agent_framework import DataContent

        messages = [
            ChatMessage(
                role="user",
                contents=[DataContent(uri=f"data:application/json;base64,{state_b64}")],
            ),
        ]

        result_messages, state = client._extract_state_from_messages(messages)

        assert result_messages == messages
        assert state is None

    async def test_convert_messages_to_agui_format(self) -> None:
        """Test message conversion to AG-UI format."""
        client = AGUIChatClient(endpoint="http://localhost:8888/")
        messages = [
            ChatMessage(role=Role.USER, text="What is the weather?"),
            ChatMessage(role=Role.ASSISTANT, text="Let me check.", message_id="msg_123"),
        ]

        agui_messages = client._convert_messages_to_agui_format(messages)

        assert len(agui_messages) == 2
        assert agui_messages[0]["role"] == "user"
        assert agui_messages[0]["content"] == "What is the weather?"
        assert agui_messages[1]["role"] == "assistant"
        assert agui_messages[1]["content"] == "Let me check."
        assert agui_messages[1]["id"] == "msg_123"

    async def test_get_thread_id_from_metadata(self) -> None:
        """Test thread ID extraction from metadata."""
        client = AGUIChatClient(endpoint="http://localhost:8888/")
        chat_options = ChatOptions(metadata={"thread_id": "existing_thread_123"})

        thread_id = client._get_thread_id(chat_options)

        assert thread_id == "existing_thread_123"

    async def test_get_thread_id_generation(self) -> None:
        """Test automatic thread ID generation."""
        client = AGUIChatClient(endpoint="http://localhost:8888/")
        chat_options = ChatOptions()

        thread_id = client._get_thread_id(chat_options)

        assert thread_id.startswith("thread_")
        assert len(thread_id) > 7

    async def test_get_streaming_response(self, monkeypatch) -> None:
        """Test streaming response method."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Hello"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": " world"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            for event in mock_events:
                yield event

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        messages = [ChatMessage(role="user", text="Test message")]
        chat_options = ChatOptions()

        updates = []
        async for update in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
            updates.append(update)

        assert len(updates) == 4
        assert updates[0].additional_properties["thread_id"] == "thread_1"
        assert updates[1].contents[0].text == "Hello"
        assert updates[2].contents[0].text == " world"

    async def test_get_response_non_streaming(self, monkeypatch) -> None:
        """Test non-streaming response method."""
        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Complete response"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            for event in mock_events:
                yield event

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        messages = [ChatMessage(role="user", text="Test message")]
        chat_options = ChatOptions()

        response = await client._inner_get_response(messages=messages, chat_options=chat_options)

        assert response is not None
        assert len(response.messages) > 0
        assert "Complete response" in response.text

    async def test_tool_handling(self, monkeypatch) -> None:
        """Test that client tool metadata is sent to server.

        Client tool metadata (name, description, schema) is sent to server for planning.
        When server requests a client function, @use_function_invocation decorator
        intercepts and executes it locally. This matches .NET AG-UI implementation.
        """
        from agent_framework import ai_function

        @ai_function
        def test_tool(param: str) -> str:
            """Test tool."""
            return "result"

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            # Client tool metadata should be sent to server
            tools = kwargs.get("tools")
            assert tools is not None
            assert len(tools) == 1
            assert tools[0]["name"] == "test_tool"
            assert tools[0]["description"] == "Test tool."
            assert "parameters" in tools[0]
            for event in mock_events:
                yield event

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        messages = [ChatMessage(role="user", text="Test with tools")]
        chat_options = ChatOptions(tools=[test_tool])

        response = await client._inner_get_response(messages=messages, chat_options=chat_options)

        assert response is not None

    async def test_server_tool_calls_unwrapped_after_invocation(self, monkeypatch) -> None:
        """Ensure server-side tool calls are exposed as FunctionCallContent after processing."""

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "get_time_zone"},
            {"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", "delta": '{"location": "Seattle"}'},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            for event in mock_events:
                yield event

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        messages = [ChatMessage(role="user", text="Test server tool execution")]
        chat_options = ChatOptions()

        updates = []
        async for update in client.get_streaming_response(messages, chat_options=chat_options):
            updates.append(update)

        function_calls = [
            content for update in updates for content in update.contents if isinstance(content, FunctionCallContent)
        ]
        assert function_calls
        assert function_calls[0].name == "get_time_zone"
        assert not any(
            isinstance(content, ServerFunctionCallContent) for update in updates for content in update.contents
        )

    async def test_server_tool_calls_not_executed_locally(self, monkeypatch) -> None:
        """Server tools should not trigger local function invocation even when client tools exist."""

        @ai_function
        def client_tool() -> str:
            """Client tool stub."""
            return "client"

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "get_time_zone"},
            {"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", "delta": '{"location": "Seattle"}'},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            for event in mock_events:
                yield event

        async def fake_auto_invoke(*args, **kwargs):
            function_call = kwargs.get("function_call_content") or args[0]
            raise AssertionError(f"Unexpected local execution of server tool: {getattr(function_call, 'name', '?')}")

        monkeypatch.setattr("agent_framework._tools._auto_invoke_function", fake_auto_invoke)

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        messages = [ChatMessage(role="user", text="Test server tool execution")]
        chat_options = ChatOptions(tool_choice="auto", tools=[client_tool])

        async for _ in client.get_streaming_response(messages, chat_options=chat_options):
            pass

    async def test_state_transmission(self, monkeypatch) -> None:
        """Test state is properly transmitted to server."""
        import base64

        state_data = {"user_id": "123", "session": "abc"}
        state_json = json.dumps(state_data)
        state_b64 = base64.b64encode(state_json.encode("utf-8")).decode("utf-8")

        from agent_framework import DataContent

        messages = [
            ChatMessage(role="user", text="Hello"),
            ChatMessage(
                role="user",
                contents=[DataContent(uri=f"data:application/json;base64,{state_b64}")],
            ),
        ]

        mock_events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        async def mock_post_run(*args, **kwargs):
            assert kwargs.get("state") == state_data
            for event in mock_events:
                yield event

        client = AGUIChatClient(endpoint="http://localhost:8888/")
        monkeypatch.setattr(client._http_service, "post_run", mock_post_run)

        chat_options = ChatOptions()

        response = await client._inner_get_response(messages=messages, chat_options=chat_options)

        assert response is not None
