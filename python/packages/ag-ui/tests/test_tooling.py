# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock

from agent_framework import ChatAgent, tool

from agent_framework_ag_ui._orchestration._tooling import (
    collect_server_tools,
    merge_tools,
    register_additional_client_tools,
)


class DummyTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.declaration_only = True


class MockMCPTool:
    """Mock MCP tool that simulates connected MCP tool with functions."""

    def __init__(self, functions: list[DummyTool], is_connected: bool = True) -> None:
        self.functions = functions
        self.is_connected = is_connected


@tool
def regular_tool() -> str:
    """Regular tool for testing."""
    return "result"


def _create_chat_agent_with_tool(tool_name: str = "regular_tool") -> ChatAgent:
    """Create a ChatAgent with a mocked chat client and a simple tool.

    Note: tool_name parameter is kept for API compatibility but the tool
    will always be named 'regular_tool' since tool uses the function name.
    """
    mock_chat_client = MagicMock()
    return ChatAgent(chat_client=mock_chat_client, tools=[regular_tool])


def test_merge_tools_filters_duplicates() -> None:
    server = [DummyTool("a"), DummyTool("b")]
    client = [DummyTool("b"), DummyTool("c")]

    merged = merge_tools(server, client)

    assert merged is not None
    names = [getattr(t, "name", None) for t in merged]
    assert names == ["a", "b", "c"]


def test_register_additional_client_tools_assigns_when_configured() -> None:
    """register_additional_client_tools should set additional_tools on the chat client."""
    from agent_framework import BaseChatClient, FunctionInvocationConfiguration

    mock_chat_client = MagicMock(spec=BaseChatClient)
    mock_chat_client.function_invocation_configuration = FunctionInvocationConfiguration()

    agent = ChatAgent(chat_client=mock_chat_client)

    tools = [DummyTool("x")]
    register_additional_client_tools(agent, tools)

    assert mock_chat_client.function_invocation_configuration.additional_tools == tools


def test_collect_server_tools_includes_mcp_tools_when_connected() -> None:
    """MCP tool functions should be included when the MCP tool is connected."""
    mcp_function1 = DummyTool("mcp_function_1")
    mcp_function2 = DummyTool("mcp_function_2")
    mock_mcp = MockMCPTool([mcp_function1, mcp_function2], is_connected=True)

    agent = _create_chat_agent_with_tool("regular_tool")
    agent.mcp_tools = [mock_mcp]

    tools = collect_server_tools(agent)

    names = [getattr(t, "name", None) for t in tools]
    assert "regular_tool" in names
    assert "mcp_function_1" in names
    assert "mcp_function_2" in names
    assert len(tools) == 3


def test_collect_server_tools_excludes_mcp_tools_when_not_connected() -> None:
    """MCP tool functions should be excluded when the MCP tool is not connected."""
    mcp_function = DummyTool("mcp_function")
    mock_mcp = MockMCPTool([mcp_function], is_connected=False)

    agent = _create_chat_agent_with_tool("regular_tool")
    agent.mcp_tools = [mock_mcp]

    tools = collect_server_tools(agent)

    names = [getattr(t, "name", None) for t in tools]
    assert "regular_tool" in names
    assert "mcp_function" not in names
    assert len(tools) == 1


def test_collect_server_tools_works_with_no_mcp_tools() -> None:
    """collect_server_tools should work when there are no MCP tools."""
    agent = _create_chat_agent_with_tool("regular_tool")

    tools = collect_server_tools(agent)

    names = [getattr(t, "name", None) for t in tools]
    assert "regular_tool" in names
    assert len(tools) == 1


def test_collect_server_tools_with_mcp_tools_via_public_property() -> None:
    """collect_server_tools should access MCP tools via the public mcp_tools property."""
    mcp_function = DummyTool("mcp_function")
    mock_mcp = MockMCPTool([mcp_function], is_connected=True)

    agent = _create_chat_agent_with_tool("regular_tool")
    agent.mcp_tools = [mock_mcp]

    # Verify the public property works
    assert agent.mcp_tools == [mock_mcp]

    tools = collect_server_tools(agent)

    names = [getattr(t, "name", None) for t in tools]
    assert "regular_tool" in names
    assert "mcp_function" in names
    assert len(tools) == 2


# Additional tests for tooling coverage


def test_collect_server_tools_no_default_options() -> None:
    """collect_server_tools returns empty list when agent has no default_options."""

    class MockAgent:
        pass

    agent = MockAgent()
    tools = collect_server_tools(agent)
    assert tools == []


def test_register_additional_client_tools_no_tools() -> None:
    """register_additional_client_tools does nothing with None tools."""
    mock_chat_client = MagicMock()
    agent = ChatAgent(chat_client=mock_chat_client)

    # Should not raise
    register_additional_client_tools(agent, None)


def test_register_additional_client_tools_no_chat_client() -> None:
    """register_additional_client_tools does nothing when agent has no chat_client."""
    from agent_framework_ag_ui._orchestration._tooling import register_additional_client_tools

    class MockAgent:
        pass

    agent = MockAgent()
    tools = [DummyTool("x")]

    # Should not raise
    register_additional_client_tools(agent, tools)


def test_merge_tools_no_client_tools() -> None:
    """merge_tools returns None when no client tools."""
    server = [DummyTool("a")]
    result = merge_tools(server, None)
    assert result is None


def test_merge_tools_all_duplicates() -> None:
    """merge_tools returns None when all client tools duplicate server tools."""
    server = [DummyTool("a"), DummyTool("b")]
    client = [DummyTool("a"), DummyTool("b")]
    result = merge_tools(server, client)
    assert result is None


def test_merge_tools_empty_server() -> None:
    """merge_tools works with empty server tools."""
    server: list = []
    client = [DummyTool("a"), DummyTool("b")]
    result = merge_tools(server, client)
    assert result is not None
    assert len(result) == 2


def test_merge_tools_with_approval_tools_no_client() -> None:
    """merge_tools returns server tools when they have approval mode even without client tools."""

    class ApprovalTool:
        def __init__(self, name: str):
            self.name = name
            self.approval_mode = "always_require"

    server = [ApprovalTool("write_doc")]
    result = merge_tools(server, None)
    assert result is not None
    assert len(result) == 1
    assert result[0].name == "write_doc"


def test_merge_tools_with_approval_tools_all_duplicates() -> None:
    """merge_tools returns server tools with approval mode even when client duplicates."""

    class ApprovalTool:
        def __init__(self, name: str):
            self.name = name
            self.approval_mode = "always_require"

    server = [ApprovalTool("write_doc")]
    client = [DummyTool("write_doc")]  # Same name as server
    result = merge_tools(server, client)
    assert result is not None
    assert len(result) == 1
    assert result[0].approval_mode == "always_require"
