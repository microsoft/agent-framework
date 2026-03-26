# Copyright (c) Microsoft. All rights reserved.

"""Tests for FoundryAgentClient and FoundryAgent classes."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework._tools import tool


class TestRawFoundryAgentChatClient:
    """Tests for RawFoundryAgentChatClient."""

    def test_init_requires_agent_name(self) -> None:
        """Test that agent_name is required."""
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        with pytest.raises(ValueError, match="Agent name is required"):
            RawFoundryAgentChatClient(
                project_client=MagicMock(),
            )

    def test_init_with_agent_name(self) -> None:
        """Test construction with agent_name and project_client."""
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert client.agent_name == "test-agent"
        assert client.agent_version == "1.0"

    def test_get_agent_reference_with_version(self) -> None:
        """Test agent reference includes version when provided."""
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="my-agent",
            agent_version="2.0",
        )

        ref = client._get_agent_reference()
        assert ref == {"name": "my-agent", "version": "2.0", "type": "agent_reference"}

    def test_get_agent_reference_without_version(self) -> None:
        """Test agent reference omits version for HostedAgents."""
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="hosted-agent",
        )

        ref = client._get_agent_reference()
        assert ref == {"name": "hosted-agent", "type": "agent_reference"}
        assert "version" not in ref

    def test_as_agent_returns_foundry_agent_and_preserves_client_type(self) -> None:
        """Test that as_agent() wraps the client in FoundryAgent using the same client class."""
        from agent_framework_foundry._foundry_agent import FoundryAgent
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        class CustomClient(RawFoundryAgentChatClient):
            pass

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = CustomClient(
            project_client=mock_project,
            agent_name="test-agent",
            agent_version="1.0",
        )

        agent = client.as_agent(instructions="You are helpful.")

        assert isinstance(agent, FoundryAgent)
        assert agent.name == "test-agent"
        assert isinstance(agent.client, CustomClient)
        assert agent.client.project_client is mock_project
        assert agent.client.agent_name == "test-agent"
        assert agent.client.agent_version == "1.0"

        named_agent = client.as_agent(name="display-name", instructions="You are helpful.")
        assert named_agent.name == "display-name"
        assert named_agent.client.agent_name == "test-agent"

    async def test_prepare_options_validates_tools(self) -> None:
        """Test that _prepare_options rejects non-FunctionTool objects."""
        from agent_framework import Message

        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="test-agent",
        )

        # A dict tool should be rejected
        with pytest.raises(TypeError, match="Only FunctionTool objects are accepted"):
            await client._prepare_options(
                messages=[Message(role="user", contents="hi")],
                options={"tools": [{"type": "function", "function": {"name": "bad"}}]},
            )

    async def test_prepare_options_accepts_function_tools(self) -> None:
        """Test that _prepare_options accepts FunctionTool objects."""
        from agent_framework import Message

        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_openai = MagicMock()
        mock_project.get_openai_client.return_value = mock_openai

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="test-agent",
        )

        @tool(approval_mode="never_require")
        def my_func() -> str:
            """A test function."""
            return "ok"

        # Should not raise — patch the parent's _prepare_options
        with patch(
            "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await client._prepare_options(
                messages=[Message(role="user", contents="hi")],
                options={"tools": [my_func]},
            )
            assert "extra_body" in result
            assert result["extra_body"]["agent_reference"]["name"] == "test-agent"

    def test_check_model_presence_is_noop(self) -> None:
        """Test that _check_model_presence does nothing (model is on service)."""
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = RawFoundryAgentChatClient(
            project_client=mock_project,
            agent_name="test-agent",
        )

        options: dict[str, Any] = {}
        client._check_model_presence(options)
        assert "model" not in options


class TestFoundryAgentChatClient:
    """Tests for _FoundryAgentChatClient (full middleware)."""

    def test_init(self) -> None:
        """Test construction of the full-middleware client."""
        from agent_framework_foundry._foundry_agent_client import _FoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        client = _FoundryAgentChatClient(
            project_client=mock_project,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert client.agent_name == "test-agent"


class TestRawFoundryAgent:
    """Tests for RawFoundryAgent."""

    def test_init_creates_client(self) -> None:
        """Test that RawFoundryAgent creates a client internally."""
        from agent_framework_foundry._foundry_agent import RawFoundryAgent

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        agent = RawFoundryAgent(
            project_client=mock_project,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert agent.client is not None
        assert agent.client.agent_name == "test-agent"

    def test_init_with_custom_client_type(self) -> None:
        """Test that client_type parameter is respected."""
        from agent_framework_foundry._foundry_agent import RawFoundryAgent
        from agent_framework_foundry._foundry_agent_client import RawFoundryAgentChatClient

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        agent = RawFoundryAgent(
            project_client=mock_project,
            agent_name="test-agent",
            client_type=RawFoundryAgentChatClient,
        )

        assert isinstance(agent.client, RawFoundryAgentChatClient)

    def test_init_rejects_invalid_client_type(self) -> None:
        """Test that invalid client_type raises TypeError."""
        from agent_framework_foundry._foundry_agent import RawFoundryAgent

        with pytest.raises(TypeError, match="must be a subclass of RawFoundryAgentChatClient"):
            RawFoundryAgent(
                project_client=MagicMock(),
                agent_name="test-agent",
                client_type=object,  # type: ignore[arg-type]
            )

    def test_init_with_function_tools(self) -> None:
        """Test that FunctionTool and callables are accepted."""
        from agent_framework_foundry._foundry_agent import RawFoundryAgent

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        @tool(approval_mode="never_require")
        def my_func() -> str:
            """A test function."""
            return "ok"

        agent = RawFoundryAgent(
            project_client=mock_project,
            agent_name="test-agent",
            tools=[my_func],
        )

        assert agent.default_options.get("tools") is not None


class TestFoundryAgent:
    """Tests for FoundryAgent (full middleware)."""

    def test_init(self) -> None:
        """Test construction of the full-middleware agent."""
        from agent_framework_foundry._foundry_agent import FoundryAgent

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        agent = FoundryAgent(
            project_client=mock_project,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert agent.client is not None
        assert agent.client.agent_name == "test-agent"

    def test_init_with_middleware(self) -> None:
        """Test that agent-level middleware is accepted."""
        from agent_framework import ChatContext, ChatMiddleware

        from agent_framework_foundry._foundry_agent import FoundryAgent

        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = MagicMock()

        class MyMiddleware(ChatMiddleware):
            async def process(self, context: ChatContext) -> None:
                pass

        agent = FoundryAgent(
            project_client=mock_project,
            agent_name="test-agent",
            middleware=[MyMiddleware()],
        )

        assert agent.client is not None


class TestFoundryChatClientToolMethods:
    """Tests for RawFoundryChatClient tool factory methods."""

    def test_get_code_interpreter_tool(self) -> None:
        """Test code interpreter tool creation."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_code_interpreter_tool()
        assert tool_obj is not None

    def test_get_code_interpreter_tool_with_file_ids(self) -> None:
        """Test code interpreter tool with file IDs."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_code_interpreter_tool(file_ids=["file-abc123"])
        assert tool_obj is not None

    def test_get_file_search_tool(self) -> None:
        """Test file search tool creation."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_file_search_tool(vector_store_ids=["vs_abc123"])
        assert tool_obj is not None

    def test_get_file_search_tool_requires_vector_store_ids(self) -> None:
        """Test that empty vector_store_ids raises ValueError."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        with pytest.raises(ValueError, match="vector_store_ids"):
            RawFoundryChatClient.get_file_search_tool(vector_store_ids=[])

    def test_get_web_search_tool(self) -> None:
        """Test web search tool creation."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_web_search_tool()
        assert tool_obj is not None

    def test_get_web_search_tool_with_location(self) -> None:
        """Test web search tool with user location."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_web_search_tool(
            user_location={"city": "Seattle", "country": "US"},
            search_context_size="high",
        )
        assert tool_obj is not None

    def test_get_image_generation_tool(self) -> None:
        """Test image generation tool creation."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_image_generation_tool()
        assert tool_obj is not None

    def test_get_mcp_tool(self) -> None:
        """Test MCP tool creation."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_mcp_tool(
            name="my_mcp",
            url="https://mcp.example.com",
        )
        assert tool_obj is not None

    def test_get_mcp_tool_with_connection_id(self) -> None:
        """Test MCP tool with project connection ID."""
        from agent_framework_foundry._foundry_chat_client import RawFoundryChatClient

        tool_obj = RawFoundryChatClient.get_mcp_tool(
            name="github_mcp",
            project_connection_id="conn_abc123",
            description="GitHub MCP via Foundry",
        )
        assert tool_obj is not None
