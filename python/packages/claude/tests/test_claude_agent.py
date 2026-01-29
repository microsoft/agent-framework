# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponseUpdate, AgentThread, ChatMessage, Content, Role, tool

from agent_framework_claude import ClaudeAgent, ClaudeAgentOptions, ClaudeAgentSettings
from agent_framework_claude._agent import TOOLS_MCP_SERVER_NAME

# region Test ClaudeAgentSettings


class TestClaudeAgentSettings:
    """Tests for ClaudeAgentSettings."""

    def test_env_prefix(self) -> None:
        """Test that env_prefix is correctly set."""
        assert ClaudeAgentSettings.env_prefix == "CLAUDE_AGENT_"

    def test_default_values(self) -> None:
        """Test default values are None."""
        settings = ClaudeAgentSettings()
        assert settings.cli_path is None
        assert settings.model is None
        assert settings.cwd is None
        assert settings.permission_mode is None
        assert settings.max_turns is None
        assert settings.max_budget_usd is None

    def test_explicit_values(self) -> None:
        """Test explicit values override defaults."""
        settings = ClaudeAgentSettings(
            cli_path="/usr/local/bin/claude",
            model="sonnet",
            cwd="/home/user/project",
            permission_mode="default",
            max_turns=10,
            max_budget_usd=5.0,
        )
        assert settings.cli_path == "/usr/local/bin/claude"
        assert settings.model == "sonnet"
        assert settings.cwd == "/home/user/project"
        assert settings.permission_mode == "default"
        assert settings.max_turns == 10
        assert settings.max_budget_usd == 5.0

    def test_env_variable_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from environment variables."""
        monkeypatch.setenv("CLAUDE_AGENT_MODEL", "opus")
        monkeypatch.setenv("CLAUDE_AGENT_MAX_TURNS", "20")
        settings = ClaudeAgentSettings()
        assert settings.model == "opus"
        assert settings.max_turns == 20


# region Test ClaudeAgent Initialization


class TestClaudeAgentInit:
    """Tests for ClaudeAgent initialization."""

    def test_default_initialization(self) -> None:
        """Test agent initializes with defaults."""
        agent = ClaudeAgent()
        assert agent.id is not None
        assert agent.name is None
        assert agent.description is None

    def test_with_name_and_description(self) -> None:
        """Test agent with name and description."""
        agent = ClaudeAgent(name="test-agent", description="A test agent")
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"

    def test_with_instructions_parameter(self) -> None:
        """Test agent with instructions parameter."""
        agent = ClaudeAgent(instructions="You are a helpful assistant.")
        assert agent._default_options.get("system_prompt") == "You are a helpful assistant."  # type: ignore[reportPrivateUsage]

    def test_with_system_prompt_in_options(self) -> None:
        """Test agent with system_prompt in options."""
        options: ClaudeAgentOptions = {
            "system_prompt": "You are a helpful assistant.",
        }
        agent = ClaudeAgent(default_options=options)
        assert agent._default_options.get("system_prompt") == "You are a helpful assistant."  # type: ignore[reportPrivateUsage]

    def test_with_default_options(self) -> None:
        """Test agent with default options."""
        options: ClaudeAgentOptions = {
            "model": "sonnet",
            "permission_mode": "default",
            "max_turns": 10,
        }
        agent = ClaudeAgent(default_options=options)
        assert agent._settings.model == "sonnet"  # type: ignore[reportPrivateUsage]
        assert agent._settings.permission_mode == "default"  # type: ignore[reportPrivateUsage]
        assert agent._settings.max_turns == 10  # type: ignore[reportPrivateUsage]

    def test_with_function_tool(self) -> None:
        """Test agent with function tool."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent(tools=[greet])
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_with_single_tool(self) -> None:
        """Test agent with single tool (not in list)."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent(tools=greet)
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_with_builtin_tools(self) -> None:
        """Test agent with built-in tool names."""
        agent = ClaudeAgent(tools=["Read", "Write", "Bash"])
        assert agent._builtin_tools == ["Read", "Write", "Bash"]  # type: ignore[reportPrivateUsage]
        assert agent._custom_tools == []  # type: ignore[reportPrivateUsage]

    def test_with_mixed_tools(self) -> None:
        """Test agent with both built-in and custom tools."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent(tools=["Read", greet, "Bash"])
        assert agent._builtin_tools == ["Read", "Bash"]  # type: ignore[reportPrivateUsage]
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]


# region Test ClaudeAgent Lifecycle


class TestClaudeAgentLifecycle:
    """Tests for ClaudeAgent tool initialization."""

    def test_custom_tools_stored_from_constructor(self) -> None:
        """Test that custom tools from constructor are stored."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent(tools=[greet])
        assert len(agent._custom_tools) == 1  # type: ignore[reportPrivateUsage]

    def test_multiple_custom_tools(self) -> None:
        """Test agent with multiple custom tools."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        @tool
        def farewell(name: str) -> str:
            """Say goodbye."""
            return f"Goodbye, {name}!"

        agent = ClaudeAgent(tools=[greet, farewell])
        assert len(agent._custom_tools) == 2  # type: ignore[reportPrivateUsage]

    def test_no_tools(self) -> None:
        """Test agent without tools."""
        agent = ClaudeAgent()
        assert agent._custom_tools == []  # type: ignore[reportPrivateUsage]
        assert agent._builtin_tools == []  # type: ignore[reportPrivateUsage]


# region Test ClaudeAgent Run


class TestClaudeAgentRun:
    """Tests for ClaudeAgent run method."""

    @staticmethod
    async def _create_async_generator(items: list[Any]) -> Any:
        """Helper to create async generator from list."""
        for item in items:
            yield item

    def _create_mock_client(self, messages: list[Any]) -> MagicMock:
        """Create a mock ClaudeSDKClient that yields given messages."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=self._create_async_generator(messages))
        return mock_client

    async def test_run_with_string_message(self) -> None:
        """Test run with string message."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        from claude_agent_sdk.types import StreamEvent

        messages = [
            StreamEvent(
                event={
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Hello!"},
                },
                uuid="event-1",
                session_id="session-123",
            ),
            AssistantMessage(
                content=[TextBlock(text="Hello!")],
                model="claude-sonnet",
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=50,
                is_error=False,
                num_turns=1,
                session_id="session-123",
            ),
        ]
        mock_client = self._create_mock_client(messages)

        with patch("agent_framework_claude._agent.ClaudeSDKClient", return_value=mock_client):
            agent = ClaudeAgent()
            response = await agent.run("Hello")
            assert response.text == "Hello!"

    async def test_run_captures_session_id(self) -> None:
        """Test that session ID is captured from ResultMessage."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        from claude_agent_sdk.types import StreamEvent

        messages = [
            StreamEvent(
                event={
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Response"},
                },
                uuid="event-1",
                session_id="test-session-id",
            ),
            AssistantMessage(
                content=[TextBlock(text="Response")],
                model="claude-sonnet",
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=50,
                is_error=False,
                num_turns=1,
                session_id="test-session-id",
            ),
        ]
        mock_client = self._create_mock_client(messages)

        with patch("agent_framework_claude._agent.ClaudeSDKClient", return_value=mock_client):
            agent = ClaudeAgent()
            thread = agent.get_new_thread()
            await agent.run("Hello", thread=thread)
            assert thread.service_thread_id == "test-session-id"

    async def test_run_with_thread(self) -> None:
        """Test run with existing thread."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        from claude_agent_sdk.types import StreamEvent

        messages = [
            StreamEvent(
                event={
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Response"},
                },
                uuid="event-1",
                session_id="session-123",
            ),
            AssistantMessage(
                content=[TextBlock(text="Response")],
                model="claude-sonnet",
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=50,
                is_error=False,
                num_turns=1,
                session_id="session-123",
            ),
        ]
        mock_client = self._create_mock_client(messages)

        with patch("agent_framework_claude._agent.ClaudeSDKClient", return_value=mock_client):
            agent = ClaudeAgent()
            thread = agent.get_new_thread()
            thread.service_thread_id = "existing-session"
            await agent.run("Hello", thread=thread)


# region Test ClaudeAgent Run Stream


class TestClaudeAgentRunStream:
    """Tests for ClaudeAgent run_stream method."""

    @staticmethod
    async def _create_async_generator(items: list[Any]) -> Any:
        """Helper to create async generator from list."""
        for item in items:
            yield item

    def _create_mock_client(self, messages: list[Any]) -> MagicMock:
        """Create a mock ClaudeSDKClient that yields given messages."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=self._create_async_generator(messages))
        return mock_client

    async def test_run_stream_yields_updates(self) -> None:
        """Test run_stream yields AgentResponseUpdate objects."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        from claude_agent_sdk.types import StreamEvent

        messages = [
            StreamEvent(
                event={
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Streaming "},
                },
                uuid="event-1",
                session_id="stream-session",
            ),
            StreamEvent(
                event={
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "response"},
                },
                uuid="event-2",
                session_id="stream-session",
            ),
            AssistantMessage(
                content=[TextBlock(text="Streaming response")],
                model="claude-sonnet",
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=50,
                is_error=False,
                num_turns=1,
                session_id="stream-session",
            ),
        ]
        mock_client = self._create_mock_client(messages)

        with patch("agent_framework_claude._agent.ClaudeSDKClient", return_value=mock_client):
            agent = ClaudeAgent()
            updates: list[AgentResponseUpdate] = []
            async for update in agent.run_stream("Hello"):
                updates.append(update)
            # StreamEvent yields text deltas
            assert len(updates) == 2
            assert updates[0].role == Role.ASSISTANT
            assert updates[0].text == "Streaming "
            assert updates[1].text == "response"


# region Test ClaudeAgent Session Management


class TestClaudeAgentSessionManagement:
    """Tests for ClaudeAgent session management."""

    def test_get_new_thread(self) -> None:
        """Test get_new_thread creates a new thread."""
        agent = ClaudeAgent()
        thread = agent.get_new_thread()
        assert isinstance(thread, AgentThread)
        assert thread.service_thread_id is None

    def test_get_new_thread_with_service_thread_id(self) -> None:
        """Test get_new_thread with existing service_thread_id."""
        agent = ClaudeAgent()
        thread = agent.get_new_thread(service_thread_id="existing-session-123")
        assert isinstance(thread, AgentThread)
        assert thread.service_thread_id == "existing-session-123"

    def test_thread_inherits_context_provider(self) -> None:
        """Test that thread inherits context provider."""
        mock_provider = MagicMock()
        agent = ClaudeAgent(context_provider=mock_provider)
        thread = agent.get_new_thread()
        assert thread.context_provider == mock_provider

    async def test_ensure_session_creates_client(self) -> None:
        """Test _ensure_session creates client when not started."""
        with patch("agent_framework_claude._agent.ClaudeSDKClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock()
            mock_client_class.return_value = mock_client

            agent = ClaudeAgent()
            await agent._ensure_session(None)  # type: ignore[reportPrivateUsage]

            assert agent._started  # type: ignore[reportPrivateUsage]
            mock_client.connect.assert_called_once()

    async def test_ensure_session_recreates_for_different_session(self) -> None:
        """Test _ensure_session recreates client for different session ID."""
        with patch("agent_framework_claude._agent.ClaudeSDKClient") as mock_client_class:
            mock_client1 = MagicMock()
            mock_client1.connect = AsyncMock()
            mock_client1.disconnect = AsyncMock()

            mock_client2 = MagicMock()
            mock_client2.connect = AsyncMock()

            mock_client_class.side_effect = [mock_client1, mock_client2]

            agent = ClaudeAgent()

            # First session
            await agent._ensure_session(None)  # type: ignore[reportPrivateUsage]
            assert agent._started  # type: ignore[reportPrivateUsage]

            # Different session should recreate client
            await agent._ensure_session("new-session-id")  # type: ignore[reportPrivateUsage]
            assert agent._current_session_id == "new-session-id"  # type: ignore[reportPrivateUsage]
            mock_client1.disconnect.assert_called_once()

    async def test_ensure_session_reuses_for_same_session(self) -> None:
        """Test _ensure_session reuses client for same session ID."""
        with patch("agent_framework_claude._agent.ClaudeSDKClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock()
            mock_client_class.return_value = mock_client

            agent = ClaudeAgent()

            # First call
            await agent._ensure_session("session-123")  # type: ignore[reportPrivateUsage]

            # Same session should not recreate
            await agent._ensure_session("session-123")  # type: ignore[reportPrivateUsage]

            # Only called once
            assert mock_client_class.call_count == 1


# region Test ClaudeAgent Tool Conversion


class TestClaudeAgentToolConversion:
    """Tests for ClaudeAgent tool conversion."""

    def test_prepare_tools_creates_mcp_server(self) -> None:
        """Test _prepare_tools creates MCP server for AF tools."""

        @tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        agent = ClaudeAgent(tools=[add])
        server, tool_names = agent._prepare_tools(agent._custom_tools)  # type: ignore[reportPrivateUsage]

        assert server is not None
        assert len(tool_names) == 1
        assert tool_names[0] == f"mcp__{TOOLS_MCP_SERVER_NAME}__add"

    def test_function_tool_to_sdk_mcp_tool(self) -> None:
        """Test converting FunctionTool to SDK MCP tool."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent()
        sdk_tool = agent._function_tool_to_sdk_mcp_tool(greet)  # type: ignore[reportPrivateUsage]

        assert sdk_tool.name == "greet"
        assert sdk_tool.description == "Greet someone."
        assert sdk_tool.input_schema is not None
        assert "properties" in sdk_tool.input_schema  # type: ignore[operator]

    async def test_tool_handler_success(self) -> None:
        """Test tool handler executes successfully."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent()
        sdk_tool = agent._function_tool_to_sdk_mcp_tool(greet)  # type: ignore[reportPrivateUsage]

        result = await sdk_tool.handler({"name": "World"})
        assert result["content"][0]["text"] == "Hello, World!"

    async def test_tool_handler_error(self) -> None:
        """Test tool handler handles errors."""

        @tool
        def failing_tool() -> str:
            """A tool that fails."""
            raise ValueError("Something went wrong")

        agent = ClaudeAgent()
        sdk_tool = agent._function_tool_to_sdk_mcp_tool(failing_tool)  # type: ignore[reportPrivateUsage]

        result = await sdk_tool.handler({})
        assert "Error:" in result["content"][0]["text"]
        assert "Something went wrong" in result["content"][0]["text"]


# region Test ClaudeAgent Permissions


class TestClaudeAgentPermissions:
    """Tests for ClaudeAgent permission handling."""

    def test_default_permission_mode(self) -> None:
        """Test default permission mode."""
        agent = ClaudeAgent()
        assert agent._settings.permission_mode is None  # type: ignore[reportPrivateUsage]

    def test_permission_mode_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test permission mode from environment settings."""
        monkeypatch.setenv("CLAUDE_AGENT_PERMISSION_MODE", "acceptEdits")
        settings = ClaudeAgentSettings()
        assert settings.permission_mode == "acceptEdits"

    def test_permission_mode_in_options(self) -> None:
        """Test permission mode in options."""
        options: ClaudeAgentOptions = {
            "permission_mode": "bypassPermissions",
        }
        agent = ClaudeAgent(default_options=options)
        assert agent._settings.permission_mode == "bypassPermissions"  # type: ignore[reportPrivateUsage]


# region Test ClaudeAgent Error Handling


class TestClaudeAgentErrorHandling:
    """Tests for ClaudeAgent error handling."""

    @staticmethod
    async def _empty_gen() -> Any:
        """Empty async generator."""
        if False:
            yield

    async def test_handles_empty_response(self) -> None:
        """Test handling of empty response."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=self._empty_gen())

        with patch("agent_framework_claude._agent.ClaudeSDKClient", return_value=mock_client):
            agent = ClaudeAgent()
            response = await agent.run("Hello")
            assert response.messages == []


# region Test Format Prompt


class TestFormatPrompt:
    """Tests for _format_prompt method."""

    def test_format_empty_messages(self) -> None:
        """Test formatting empty messages."""
        agent = ClaudeAgent()
        result = agent._format_prompt([])  # type: ignore[reportPrivateUsage]
        assert result == ""

    def test_format_none_messages(self) -> None:
        """Test formatting None messages."""
        agent = ClaudeAgent()
        result = agent._format_prompt(None)  # type: ignore[reportPrivateUsage]
        assert result == ""

    def test_format_user_message(self) -> None:
        """Test formatting user message."""
        agent = ClaudeAgent()
        msg = ChatMessage(
            role=Role.USER,
            contents=[Content.from_text(text="Hello")],
        )
        result = agent._format_prompt([msg])  # type: ignore[reportPrivateUsage]
        assert "Hello" in result

    def test_format_multiple_messages(self) -> None:
        """Test formatting multiple messages."""
        agent = ClaudeAgent()
        messages = [
            ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hi")]),
            ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text="Hello!")]),
            ChatMessage(role=Role.USER, contents=[Content.from_text(text="How are you?")]),
        ]
        result = agent._format_prompt(messages)  # type: ignore[reportPrivateUsage]
        assert "Hi" in result
        assert "Hello!" in result
        assert "How are you?" in result


# region Test Build Options


class TestPrepareClientOptions:
    """Tests for _prepare_client_options method."""

    def test_prepare_client_options_with_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test preparing options with settings."""
        monkeypatch.setenv("CLAUDE_AGENT_MODEL", "opus")
        monkeypatch.setenv("CLAUDE_AGENT_MAX_TURNS", "15")

        agent = ClaudeAgent()

        with patch("agent_framework_claude._agent.SDKOptions") as mock_opts:
            mock_opts.return_value = MagicMock()
            agent._prepare_client_options()  # type: ignore[reportPrivateUsage]
            call_kwargs = mock_opts.call_args[1]
            assert call_kwargs.get("model") == "opus"
            assert call_kwargs.get("max_turns") == 15

    def test_prepare_client_options_with_instructions(self) -> None:
        """Test building options with instructions parameter."""
        agent = ClaudeAgent(instructions="Be helpful")

        with patch("agent_framework_claude._agent.SDKOptions") as mock_opts:
            mock_opts.return_value = MagicMock()
            agent._prepare_client_options()  # type: ignore[reportPrivateUsage]
            call_kwargs = mock_opts.call_args[1]
            assert call_kwargs.get("system_prompt") == "Be helpful"

    def test_prepare_client_options_includes_custom_tools(self) -> None:
        """Test that _prepare_client_options includes custom tools MCP server."""

        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        agent = ClaudeAgent(tools=[greet])

        with patch("agent_framework_claude._agent.SDKOptions") as mock_opts:
            mock_opts.return_value = MagicMock()
            agent._prepare_client_options()  # type: ignore[reportPrivateUsage]
            call_kwargs = mock_opts.call_args[1]
            assert "mcp_servers" in call_kwargs
            assert TOOLS_MCP_SERVER_NAME in call_kwargs["mcp_servers"]


class TestApplyRuntimeOptions:
    """Tests for _apply_runtime_options method."""

    async def test_apply_runtime_model(self) -> None:
        """Test applying runtime model option."""
        mock_client = MagicMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()

        agent = ClaudeAgent()
        agent._client = mock_client  # type: ignore[reportPrivateUsage]

        await agent._apply_runtime_options({"model": "opus"})  # type: ignore[reportPrivateUsage]
        mock_client.set_model.assert_called_once_with("opus")

    async def test_apply_runtime_permission_mode(self) -> None:
        """Test applying runtime permission_mode option."""
        mock_client = MagicMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()

        agent = ClaudeAgent()
        agent._client = mock_client  # type: ignore[reportPrivateUsage]

        await agent._apply_runtime_options({"permission_mode": "acceptEdits"})  # type: ignore[reportPrivateUsage]
        mock_client.set_permission_mode.assert_called_once_with("acceptEdits")

    async def test_apply_runtime_options_none(self) -> None:
        """Test applying None options does nothing."""
        mock_client = MagicMock()
        mock_client.set_model = AsyncMock()
        mock_client.set_permission_mode = AsyncMock()

        agent = ClaudeAgent()
        agent._client = mock_client  # type: ignore[reportPrivateUsage]

        await agent._apply_runtime_options(None)  # type: ignore[reportPrivateUsage]
        mock_client.set_model.assert_not_called()
        mock_client.set_permission_mode.assert_not_called()
