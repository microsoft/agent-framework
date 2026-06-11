# Copyright (c) Microsoft. All rights reserved.

"""Tests for MCP client span instrumentation per OTel GenAI Semantic Conventions.

See: https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/#client
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from mcp import types
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from agent_framework import MCPStdioTool, MCPStreamableHTTPTool, MCPWebsocketTool
from agent_framework._mcp import MCPTool
from agent_framework.exceptions import ToolExecutionException
from agent_framework.observability import OtelAttr

# region helpers


def _make_connected_mcp_tool(
    name: str = "test-mcp",
    *,
    supports_tools: bool = True,
    supports_prompts: bool = True,
) -> MCPTool:
    """Create an MCPTool with a mocked session, ready for testing."""
    tool = MCPTool(name=name)
    tool.session = AsyncMock()
    tool.is_connected = True
    tool._supports_tools = supports_tools
    tool._supports_prompts = supports_prompts
    tool.load_tools_flag = True
    tool.load_prompts_flag = True
    return tool


def _make_tool_list_result(
    tools: list[dict[str, Any]] | None = None,
) -> Mock:
    """Create a mock ListToolsResult."""
    if tools is None:
        tools = [{"name": "get-weather", "description": "Get weather", "inputSchema": {"type": "object"}}]
    result = Mock()
    result.tools = [
        types.Tool(name=t["name"], description=t.get("description", ""), inputSchema=t.get("inputSchema", {}))
        for t in tools
    ]
    result.nextCursor = None
    return result


def _make_prompt_list_result(
    prompts: list[dict[str, Any]] | None = None,
) -> Mock:
    """Create a mock ListPromptsResult."""
    if prompts is None:
        prompts = [{"name": "analyze-code", "description": "Analyze code"}]
    result = Mock()
    result.prompts = [
        types.Prompt(name=p["name"], description=p.get("description", ""), arguments=None) for p in prompts
    ]
    result.nextCursor = None
    return result


def _make_call_tool_result(text: str = "result", is_error: bool = False) -> Mock:
    """Create a mock CallToolResult."""
    result = Mock()
    result.isError = is_error
    result.content = [types.TextContent(type="text", text=text)]
    result.structuredContent = None
    return result


def _make_get_prompt_result(text: str = "prompt result") -> types.GetPromptResult:
    """Create a mock GetPromptResult."""
    return types.GetPromptResult(
        description="test prompt",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=text),
            )
        ],
    )


# endregion


# region initialize span


async def test_mcp_initialize_span(span_exporter: InMemorySpanExporter):
    """session.initialize() should produce an MCP CLIENT span named 'initialize'."""
    tool = MCPTool(name="test-server")

    mock_session_cls = AsyncMock()
    init_result = Mock()
    init_result.capabilities = None
    init_result.protocolVersion = "2025-06-18"
    mock_session_cls.initialize = AsyncMock(return_value=init_result)

    # Create a mock transport context manager
    mock_transport = AsyncMock()
    mock_transport.__aenter__ = AsyncMock(return_value=(Mock(), Mock()))
    mock_transport.__aexit__ = AsyncMock(return_value=False)

    # Mock get_mcp_client and the session creation
    tool.session = None
    tool.load_tools_flag = False
    tool.load_prompts_flag = False

    span_exporter.clear()

    with pytest.MonkeyPatch.context() as m:
        m.setattr(tool, "get_mcp_client", lambda: mock_transport)

        async def patched_connect(self_: Any, *, reset: bool = False, load_configured: bool = True) -> None:
            # Simulate _connect_on_owner: create initialize span and call session.initialize()
            from agent_framework._mcp import create_mcp_client_span
            from agent_framework.observability import OtelAttr

            with create_mcp_client_span("initialize", attributes=self_._mcp_base_span_attributes()) as init_span:
                result = await mock_session_cls.initialize()
                protocol_version = getattr(result, "protocolVersion", None)
                if protocol_version:
                    init_span.set_attribute(OtelAttr.MCP_PROTOCOL_VERSION, protocol_version)

            self_.session = mock_session_cls
            self_.is_connected = True

        m.setattr(MCPTool, "_connect_on_owner", patched_connect)
        await tool.connect()

    mock_session_cls.initialize.assert_awaited_once()
    spans = span_exporter.get_finished_spans()
    init_spans = [s for s in spans if s.name == "initialize"]
    assert len(init_spans) == 1
    span = init_spans[0]
    assert span.kind == SpanKind.CLIENT
    assert span.attributes[OtelAttr.MCP_METHOD_NAME] == "initialize"
    assert span.attributes.get(OtelAttr.MCP_PROTOCOL_VERSION) == "2025-06-18"


# endregion


# region tools/list span


async def test_mcp_tools_list_span(span_exporter: InMemorySpanExporter):
    """session.list_tools() should produce an MCP CLIENT span named 'tools/list'."""
    tool = _make_connected_mcp_tool()
    tool.session.list_tools = AsyncMock(return_value=_make_tool_list_result())

    span_exporter.clear()
    await tool.load_tools()

    spans = span_exporter.get_finished_spans()
    list_spans = [s for s in spans if s.name == "tools/list"]
    assert len(list_spans) == 1
    span = list_spans[0]
    assert span.kind == SpanKind.CLIENT
    assert span.attributes[OtelAttr.MCP_METHOD_NAME] == "tools/list"


# endregion


# region prompts/list span


async def test_mcp_prompts_list_span(span_exporter: InMemorySpanExporter):
    """session.list_prompts() should produce an MCP CLIENT span named 'prompts/list'."""
    tool = _make_connected_mcp_tool()
    tool.session.list_prompts = AsyncMock(return_value=_make_prompt_list_result())

    span_exporter.clear()
    await tool.load_prompts()

    spans = span_exporter.get_finished_spans()
    list_spans = [s for s in spans if s.name == "prompts/list"]
    assert len(list_spans) == 1
    span = list_spans[0]
    assert span.kind == SpanKind.CLIENT
    assert span.attributes[OtelAttr.MCP_METHOD_NAME] == "prompts/list"


# endregion


# region tools/call span


async def test_mcp_tools_call_creates_client_span_when_no_parent(span_exporter: InMemorySpanExporter):
    """Direct call_tool() without FunctionTool wrapper creates new MCP CLIENT span."""
    tool = _make_connected_mcp_tool()
    tool.session.call_tool = AsyncMock(return_value=_make_call_tool_result("hello"))

    span_exporter.clear()
    result = await tool.call_tool("get-weather", city="Seattle")

    assert result is not None
    spans = span_exporter.get_finished_spans()
    call_spans = [s for s in spans if "tools/call" in s.name]
    assert len(call_spans) == 1
    span = call_spans[0]
    assert span.kind == SpanKind.CLIENT
    assert span.name == "tools/call get-weather"
    assert span.attributes[OtelAttr.MCP_METHOD_NAME] == "tools/call"
    assert span.attributes[OtelAttr.TOOL_NAME] == "get-weather"


async def test_mcp_tools_call_tool_error_sets_error_type(span_exporter: InMemorySpanExporter):
    """When CallToolResult.isError is true, error.type should be 'tool_error' per MCP spec."""
    tool = _make_connected_mcp_tool()
    tool.session.call_tool = AsyncMock(return_value=_make_call_tool_result("bad input", is_error=True))

    span_exporter.clear()
    with pytest.raises(ToolExecutionException):
        await tool.call_tool("get-weather", city="invalid")

    spans = span_exporter.get_finished_spans()
    call_spans = [s for s in spans if "tools/call" in s.name]
    assert len(call_spans) == 1
    span = call_spans[0]
    assert span.attributes.get(OtelAttr.ERROR_TYPE) == "tool_error"
    assert span.status.status_code == StatusCode.ERROR


async def test_mcp_tools_call_mcp_error_sets_error_type(span_exporter: InMemorySpanExporter):
    """When session.call_tool() raises McpError, error.type should be the exception class name."""
    tool = _make_connected_mcp_tool()
    tool.session.call_tool = AsyncMock(side_effect=McpError(ErrorData(code=-32600, message="invalid request")))

    span_exporter.clear()
    with pytest.raises(ToolExecutionException):
        await tool.call_tool("get-weather")

    spans = span_exporter.get_finished_spans()
    call_spans = [s for s in spans if "tools/call" in s.name]
    assert len(call_spans) == 1
    span = call_spans[0]
    assert span.attributes.get(OtelAttr.ERROR_TYPE) == "McpError"
    assert span.status.status_code == StatusCode.ERROR


# endregion


# region prompts/get span


async def test_mcp_prompts_get_creates_client_span(span_exporter: InMemorySpanExporter):
    """get_prompt() should always create a new MCP CLIENT span (not enrich execute_tool)."""
    tool = _make_connected_mcp_tool()
    tool.session.get_prompt = AsyncMock(return_value=_make_get_prompt_result("code analysis"))

    span_exporter.clear()
    result = await tool.get_prompt("analyze-code", language="python")

    assert "code analysis" in result
    spans = span_exporter.get_finished_spans()
    prompt_spans = [s for s in spans if "prompts/get" in s.name]
    assert len(prompt_spans) == 1
    span = prompt_spans[0]
    assert span.kind == SpanKind.CLIENT
    assert span.name == "prompts/get analyze-code"
    assert span.attributes[OtelAttr.MCP_METHOD_NAME] == "prompts/get"
    assert span.attributes[OtelAttr.PROMPT_NAME] == "analyze-code"


async def test_mcp_prompts_get_mcp_error_sets_error_type(span_exporter: InMemorySpanExporter):
    """When session.get_prompt() raises McpError, the span should have error.type and ERROR status."""
    tool = _make_connected_mcp_tool()
    tool.session.get_prompt = AsyncMock(side_effect=McpError(ErrorData(code=-32602, message="prompt not found")))

    span_exporter.clear()
    with pytest.raises(ToolExecutionException):
        await tool.get_prompt("missing-prompt")

    spans = span_exporter.get_finished_spans()
    prompt_spans = [s for s in spans if "prompts/get" in s.name]
    assert len(prompt_spans) == 1
    span = prompt_spans[0]
    assert span.attributes.get(OtelAttr.ERROR_TYPE) == "McpError"
    assert span.status.status_code == StatusCode.ERROR


# endregion


# region transport attributes


def test_mcp_stdio_tool_transport_attributes():
    """MCPStdioTool should have network.transport='pipe'."""
    tool = MCPStdioTool(name="test", command="python")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.NETWORK_TRANSPORT] == "pipe"
    assert OtelAttr.ADDRESS not in attrs


def test_mcp_http_tool_transport_attributes():
    """MCPStreamableHTTPTool should have tcp transport and URL-based server address/port."""
    tool = MCPStreamableHTTPTool(name="test", url="https://api.example.com:8443/mcp")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.NETWORK_TRANSPORT] == "tcp"
    assert attrs[OtelAttr.NETWORK_PROTOCOL_NAME] == "http"
    assert attrs[OtelAttr.ADDRESS] == "api.example.com"
    assert attrs[OtelAttr.PORT] == 8443


def test_mcp_http_tool_default_port():
    """MCPStreamableHTTPTool should default to 443 for https."""
    tool = MCPStreamableHTTPTool(name="test", url="https://api.example.com/mcp")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.PORT] == 443


def test_mcp_http_tool_http_default_port():
    """MCPStreamableHTTPTool should default to 80 for http."""
    tool = MCPStreamableHTTPTool(name="test", url="http://localhost/mcp")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.PORT] == 80


def test_mcp_websocket_tool_transport_attributes():
    """MCPWebsocketTool should have tcp transport and URL-based server address/port."""
    tool = MCPWebsocketTool(name="test", url="wss://ws.example.com:9090/mcp")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.NETWORK_TRANSPORT] == "tcp"
    assert attrs[OtelAttr.NETWORK_PROTOCOL_NAME] == "websocket"
    assert attrs[OtelAttr.ADDRESS] == "ws.example.com"
    assert attrs[OtelAttr.PORT] == 9090


def test_mcp_websocket_tool_default_port():
    """MCPWebsocketTool should default to 443 for wss."""
    tool = MCPWebsocketTool(name="test", url="wss://ws.example.com/mcp")
    attrs = tool._mcp_base_span_attributes()
    assert attrs[OtelAttr.PORT] == 443


# endregion


# region observability disabled


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_mcp_spans_not_created_when_observability_disabled(span_exporter: InMemorySpanExporter):
    """No MCP spans should be created when observability is disabled."""
    tool = _make_connected_mcp_tool()
    tool.session.list_tools = AsyncMock(return_value=_make_tool_list_result())
    tool.session.call_tool = AsyncMock(return_value=_make_call_tool_result("ok"))

    span_exporter.clear()
    await tool.load_tools()
    await tool.call_tool("get-weather", city="Seattle")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0


# endregion
