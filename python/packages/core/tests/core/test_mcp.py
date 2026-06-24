# Copyright (c) Microsoft. All rights reserved.
# pyright: ignore[reportPrivateUsage]
import asyncio
import contextlib
import json
import logging
import os
import sys
from contextlib import _AsyncGeneratorContextManager  # type: ignore
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl, BaseModel

from agent_framework import (
    Content,
    FunctionInvocationContext,
    FunctionMiddleware,
    MCPStdioTool,
    MCPStreamableHTTPTool,
    MCPWebsocketTool,
    Message,
)
from agent_framework._mcp import (
    MCPTool,
    _build_prefixed_mcp_name,
    _get_input_model_from_mcp_prompt,
    _normalize_additional_tool_argument_names,
    _normalize_mcp_name,
    _should_propagate_cancelled_error,
    logger,
)
from agent_framework._middleware import FunctionMiddlewarePipeline
from agent_framework.exceptions import ToolException, ToolExecutionException

# Integration test skip condition
skip_if_mcp_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("LOCAL_MCP_URL", "") == "",
    reason="No LOCAL_MCP_URL provided; skipping integration tests.",
)


def _mcp_result_to_text(result: str | list[Content]) -> str:
    """Normalize an MCP tool result to text for assertions."""
    if isinstance(result, str):
        return result
    text = "\n".join(content.text for content in result if content.type == "text" and content.text)
    return text or str(result)


_HELPER_MCP_TOOL = MCPTool(name="helper")  # type: ignore[abstract]


# Helper function tests
def test_normalize_mcp_name():
    """Test MCP name normalization."""
    assert _normalize_mcp_name("valid_name") == "valid_name"
    assert _normalize_mcp_name("name-with-dashes") == "name-with-dashes"
    assert _normalize_mcp_name("name.with.dots") == "name.with.dots"
    assert _normalize_mcp_name("name with spaces") == "name-with-spaces"
    assert _normalize_mcp_name("name@with#special$chars") == "name-with-special-chars"
    assert _normalize_mcp_name("name/with\\slashes") == "name-with-slashes"


def test_build_prefixed_mcp_name_ignores_empty_normalized_prefix() -> None:
    assert _build_prefixed_mcp_name("search", "---") == "search"


def test_mcp_transport_subclasses_accept_tool_name_prefix() -> None:
    assert MCPStdioTool(name="stdio", command="python", tool_name_prefix="stdio").tool_name_prefix == "stdio"
    assert (
        MCPStreamableHTTPTool(
            name="http",
            url="https://example.com/mcp",
            tool_name_prefix="http",
        ).tool_name_prefix
        == "http"
    )
    assert (
        MCPWebsocketTool(
            name="ws",
            url="wss://example.com/mcp",
            tool_name_prefix="ws",
        ).tool_name_prefix
        == "ws"
    )


async def test_load_tools_with_tool_name_prefix_preserves_matching_configuration():
    """Prefixed MCP tool names should still honor unprefixed allow/approval configuration."""
    tool = MCPTool(  # type: ignore[abstract]
        name="docs",
        tool_name_prefix="docs",
        allowed_tools=["search_docs"],
        approval_mode={"always_require_approval": ["search_docs"]},
    )

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="search_docs",
            description="Search docs",
            inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
    ]
    page.nextCursor = None
    mock_session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert [function.name for function in tool._functions] == ["docs_search_docs"]
    assert [function.name for function in tool.functions] == ["docs_search_docs"]
    assert tool.functions[0].approval_mode == "always_require"


async def test_allowed_tools_does_not_authorize_normalized_remote_name_collision() -> None:
    """A normalized/local allowlist match must not authorize a different raw remote tool."""
    tool = MCPTool(name="test_server", allowed_tools=["delete-file"])  # type: ignore[abstract]

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="delete/file",
            description="Delete a file",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    page.nextCursor = None
    mock_session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert [function.name for function in tool._functions] == ["delete-file"]
    assert tool.functions == []


async def test_load_tools_rejects_colliding_normalized_tool_names() -> None:
    """A remote MCP server must not choose which raw tool backs a colliding local name."""
    tool = MCPTool(name="test_server", allowed_tools=["delete-file"])  # type: ignore[abstract]

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="delete/file",
            description="Unauthorized tool",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="delete-file",
            description="Authorized tool",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    page.nextCursor = None
    mock_session.list_tools = AsyncMock(return_value=page)

    with pytest.raises(ToolExecutionException, match="map to the same local function name"):
        await tool.load_tools()


async def test_allowed_tools_exact_raw_name_allows_normalized_function_name() -> None:
    """An exact raw remote allowlist entry still exposes that raw tool, regardless of local normalization."""
    tool = MCPTool(name="test_server", allowed_tools=["delete/file"])  # type: ignore[abstract]

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="delete/file",
            description="Delete a file",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    page.nextCursor = None
    mock_session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert [function.name for function in tool.functions] == ["delete-file"]
    assert tool.functions[0].additional_properties is not None
    assert tool.functions[0].additional_properties["_mcp_remote_name"] == "delete/file"


async def test_approval_mode_does_not_match_normalized_colliding_name() -> None:
    """Approval rules should not apply to a different raw remote tool through normalization."""
    tool = MCPTool(  # type: ignore[abstract]
        name="test_server",
        approval_mode={"always_require_approval": ["delete-file"]},
    )

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="delete/file",
            description="Delete a file",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    page.nextCursor = None
    mock_session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert tool._functions[0].name == "delete-file"
    assert tool._functions[0].approval_mode == "never_require"


async def test_load_prompts_with_tool_name_prefix() -> None:
    """Prefixed MCP prompt names should be exposed with the configured prefix."""
    tool = MCPTool(name="docs", tool_name_prefix="docs")  # type: ignore[abstract]

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    page = Mock()
    page.prompts = [
        types.Prompt(
            name="summarize docs",
            description="Summarize docs",
            arguments=[types.PromptArgument(name="topic", description="Topic", required=True)],
        ),
    ]
    page.nextCursor = None
    mock_session.list_prompts = AsyncMock(return_value=page)

    await tool.load_prompts()

    assert [function.name for function in tool._functions] == ["docs_summarize-docs"]


def test_mcp_prompt_message_to_ai_content():
    """Test conversion from MCP prompt message to AI content."""
    mcp_message = types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hello, world!"))
    ai_content = _HELPER_MCP_TOOL._parse_message_from_mcp(mcp_message)

    assert isinstance(ai_content, Message)
    assert ai_content.role == "user"
    assert len(ai_content.contents) == 1
    assert ai_content.contents[0].type == "text"
    assert ai_content.contents[0].text == "Hello, world!"
    assert ai_content.raw_representation == mcp_message


def test_mcp_tool_str_and_parse_prompt_result_rich_content() -> None:
    tool = MCPTool(name="helper", description="Helper MCP tool")  # type: ignore[abstract]
    prompt_result = types.GetPromptResult(
        messages=[
            types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hello")),
            types.PromptMessage(
                role="assistant",
                content=types.ImageContent(type="image", data="eHl6", mimeType="image/png"),
            ),
            types.PromptMessage(
                role="assistant",
                content=types.AudioContent(type="audio", data="YXVkaW8=", mimeType="audio/wav"),
            ),
            types.PromptMessage(
                role="assistant",
                content=types.EmbeddedResource(
                    type="resource",
                    resource=types.TextResourceContents(
                        uri=AnyUrl("file://prompt.txt"),
                        mimeType="text/plain",
                        text="Embedded prompt",
                    ),
                ),
            ),
            types.PromptMessage(
                role="assistant",
                content=types.EmbeddedResource(
                    type="resource",
                    resource=types.BlobResourceContents(
                        uri=AnyUrl("file://prompt.bin"),
                        mimeType="application/pdf",
                        blob="ZGF0YQ==",
                    ),
                ),
            ),
        ]
    )

    result = tool._parse_prompt_result_from_mcp(prompt_result)
    parsed = json.loads(result)

    assert str(tool) == "MCPTool(name=helper, description=Helper MCP tool)"
    assert parsed[0] == "Hello"
    assert json.loads(parsed[1]) == {"type": "image", "data": "eHl6", "mimeType": "image/png"}
    assert json.loads(parsed[2]) == {"type": "audio", "data": "YXVkaW8=", "mimeType": "audio/wav"}
    assert parsed[3] == "Embedded prompt"
    assert json.loads(parsed[4]) == {"type": "blob", "data": "ZGF0YQ==", "mimeType": "application/pdf"}


def test_parse_tool_result_from_mcp():
    """Test conversion from MCP tool result with images preserves original order."""
    mcp_result = types.CallToolResult(
        content=[
            types.TextContent(type="text", text="Result text"),
            types.ImageContent(type="image", data="eHl6", mimeType="image/png"),
            types.TextContent(type="text", text="After image"),
            types.ImageContent(type="image", data="YWJj", mimeType="image/webp"),
        ]
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    # Results with images return a list of Content objects in original order
    assert isinstance(result, list)
    assert len(result) == 4
    # Order is preserved: text, image, text, image
    assert result[0].type == "text"
    assert result[0].text == "Result text"
    assert result[1].type == "data"
    assert result[1].media_type == "image/png"
    assert "eHl6" in result[1].uri  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]
    assert result[2].type == "text"
    assert result[2].text == "After image"
    assert result[3].type == "data"
    assert result[3].media_type == "image/webp"
    assert "YWJj" in result[3].uri  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]


def test_parse_tool_result_from_mcp_single_text():
    """Test conversion from MCP tool result with a single text item."""
    mcp_result = types.CallToolResult(content=[types.TextContent(type="text", text="Simple result")])
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    # Single text item returns list with one text Content
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "Simple result"


def test_parse_tool_result_from_mcp_meta_not_in_string():
    """Test that _meta data is not included in the result (it's tool-level, not content-level)."""
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Error occurred")],
        _meta={"isError": True, "errorCode": "TOOL_ERROR"},
    )

    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].text == "Error occurred"


def test_parse_tool_result_from_mcp_empty_content():
    """Test that empty MCP content normalizes to JSON null text content."""
    mcp_result = types.CallToolResult(content=[])
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "null"

    function_result = Content.from_function_result(call_id="call_null", result=result)
    assert function_result.result == "null"


def test_parse_tool_result_from_mcp_audio_content():
    """Test conversion from MCP tool result with audio returns rich content list."""
    mcp_result = types.CallToolResult(
        content=[
            types.AudioContent(type="audio", data="YXVkaW8=", mimeType="audio/wav"),
        ]
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "data"
    assert result[0].media_type == "audio/wav"
    assert "YXVkaW8=" in result[0].uri  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]


def test_parse_tool_result_from_mcp_blob_plain_base64():
    """Test that plain base64 blob (without data: prefix) is wrapped into a data URI."""
    mcp_result = types.CallToolResult(
        content=[
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=AnyUrl("file://test.bin"),
                    mimeType="application/pdf",
                    blob="dGVzdCBkYXRh",
                ),
            ),
        ]
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "data"
    assert result[0].media_type == "application/pdf"
    assert "dGVzdCBkYXRh" in result[0].uri  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]


def test_parse_tool_result_from_mcp_resource_link_text_resource_and_unknown():
    """Test additional MCP tool result variants."""
    mcp_result = types.CallToolResult(
        content=[
            types.ResourceLink(
                type="resource_link",
                uri=AnyUrl("https://example.com/resource"),
                name="resource",
                mimeType="application/json",
            ),
            types.EmbeddedResource(
                type="resource",
                resource=types.TextResourceContents(
                    uri=AnyUrl("file://prompt.txt"),
                    mimeType="text/plain",
                    text="Embedded result",
                ),
            ),
        ]
    )

    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert result[0].type == "uri"
    assert result[0].uri == "https://example.com/resource"
    assert result[1].type == "text"
    assert result[1].text == "Embedded result"


def test_parse_tool_result_from_mcp_structured_content_only():
    """Test that structuredContent is parsed when content list is empty."""
    mcp_result = types.CallToolResult(
        content=[],
        structuredContent={"Tables": [{"Name": "Sales", "Columns": ["Amount", "Date"]}]},
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text is not None
    parsed = json.loads(result[0].text)
    assert parsed == {"Tables": [{"Name": "Sales", "Columns": ["Amount", "Date"]}]}


def test_parse_tool_result_from_mcp_structured_content_with_text():
    """Test that structuredContent is appended alongside regular content items."""
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Summary")],
        structuredContent={"data": [1, 2, 3]},
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].type == "text"
    assert result[0].text == "Summary"
    assert result[1].type == "text"
    assert result[1].text is not None
    parsed = json.loads(result[1].text)
    assert parsed == {"data": [1, 2, 3]}


def test_parse_tool_result_from_mcp_structured_content_none():
    """Test that None structuredContent does not affect results."""
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Hello")],
        structuredContent=None,
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "Hello"


def test_parse_tool_result_from_mcp_structured_content_non_serializable():
    """Test that non-JSON-serializable values in structuredContent degrade gracefully."""
    mcp_result = types.CallToolResult(
        content=[],
        structuredContent={"data": b"raw bytes", "count": 42},
    )
    result = _HELPER_MCP_TOOL._parse_tool_result_from_mcp(mcp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text is not None
    parsed = json.loads(result[0].text)
    assert parsed["count"] == 42
    # bytes should be converted to string representation via default=str
    assert "raw bytes" in parsed["data"]


def test_mcp_content_types_to_ai_content_text():
    """Test conversion of MCP text content to AI content."""
    mcp_content = types.TextContent(type="text", text="Sample text")
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "text"
    assert ai_content.text == "Sample text"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_image():
    """Test conversion of MCP image content to AI content."""
    # MCP can send data as base64 string or as bytes
    mcp_content = types.ImageContent(type="image", data="YWJj", mimeType="image/jpeg")  # base64 for b"abc"
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "data"
    assert ai_content.uri == "data:image/jpeg;base64,YWJj"
    assert ai_content.media_type == "image/jpeg"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_audio():
    """Test conversion of MCP audio content to AI content."""
    # Use properly padded base64
    mcp_content = types.AudioContent(type="audio", data="ZGVm", mimeType="audio/wav")  # base64 for b"def"
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "data"
    assert ai_content.uri == "data:audio/wav;base64,ZGVm"
    assert ai_content.media_type == "audio/wav"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_resource_link():
    """Test conversion of MCP resource link to AI content."""
    mcp_content = types.ResourceLink(
        type="resource_link",
        uri=AnyUrl("https://example.com/resource"),
        name="test_resource",
        mimeType="application/json",
    )
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "uri"
    assert ai_content.uri == "https://example.com/resource"
    assert ai_content.media_type == "application/json"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_embedded_resource_text():
    """Test conversion of MCP embedded text resource to AI content."""
    text_resource = types.TextResourceContents(
        uri=AnyUrl("file://test.txt"),
        mimeType="text/plain",
        text="Embedded text content",
    )
    mcp_content = types.EmbeddedResource(type="resource", resource=text_resource)
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "text"
    assert ai_content.text == "Embedded text content"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_embedded_resource_blob():
    """Test conversion of MCP embedded blob resource to AI content."""
    # Use a proper data URI in the blob field since that's what the MCP implementation expects
    blob_resource = types.BlobResourceContents(
        uri=AnyUrl("file://test.bin"),
        mimeType="application/octet-stream",
        blob="data:application/octet-stream;base64,dGVzdCBkYXRh",
    )
    mcp_content = types.EmbeddedResource(type="resource", resource=blob_resource)
    ai_content = _HELPER_MCP_TOOL._parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "data"
    assert ai_content.uri == "data:application/octet-stream;base64,dGVzdCBkYXRh"
    assert ai_content.media_type == "application/octet-stream"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_tool_use_and_tool_result():
    """Test conversion of MCP tool use/result content to AI function call/result content."""
    tool_use_content = types.ToolUseContent(type="tool_use", id="call-1", name="calculator", input={"x": 1})
    tool_result_content = types.ToolResultContent(
        type="tool_result",
        toolUseId="call-1",
        content=[types.TextContent(type="text", text="done")],
        isError=True,
    )

    function_call = _HELPER_MCP_TOOL._parse_content_from_mcp(tool_use_content)[0]
    function_result = _HELPER_MCP_TOOL._parse_content_from_mcp(tool_result_content)[0]

    assert function_call.type == "function_call"
    assert function_call.call_id == "call-1"
    assert function_call.name == "calculator"
    assert function_call.arguments == {"x": 1}
    assert function_result.type == "function_result"
    assert function_result.call_id == "call-1"
    assert function_result.result == "done"
    assert function_result.exception == ""


def test_ai_content_to_mcp_content_types_text():
    """Test conversion of AI text content to MCP content."""
    ai_content = Content.from_text(text="Sample text")
    mcp_content = _HELPER_MCP_TOOL._prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.TextContent)
    assert mcp_content.type == "text"
    assert mcp_content.text == "Sample text"


def test_ai_content_to_mcp_content_types_data_image():
    """Test conversion of AI data content to MCP content."""
    ai_content = Content.from_uri(uri="data:image/png;base64,xyz", media_type="image/png")
    mcp_content = _HELPER_MCP_TOOL._prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.ImageContent)
    assert mcp_content.type == "image"
    assert mcp_content.data == "data:image/png;base64,xyz"
    assert mcp_content.mimeType == "image/png"


def test_ai_content_to_mcp_content_types_data_audio():
    """Test conversion of AI data content to MCP content."""
    ai_content = Content.from_uri(uri="data:audio/mpeg;base64,xyz", media_type="audio/mpeg")
    mcp_content = _HELPER_MCP_TOOL._prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.AudioContent)
    assert mcp_content.type == "audio"
    assert mcp_content.data == "data:audio/mpeg;base64,xyz"
    assert mcp_content.mimeType == "audio/mpeg"


def test_ai_content_to_mcp_content_types_data_binary():
    """Test conversion of AI data content to MCP content."""
    ai_content = Content.from_uri(
        uri="data:application/octet-stream;base64,xyz",
        media_type="application/octet-stream",
    )
    mcp_content = _HELPER_MCP_TOOL._prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.EmbeddedResource)
    assert mcp_content.type == "resource"
    assert mcp_content.resource.blob == "data:application/octet-stream;base64,xyz"  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
    assert mcp_content.resource.mimeType == "application/octet-stream"


def test_ai_content_to_mcp_content_types_uri():
    """Test conversion of AI URI content to MCP content."""
    ai_content = Content.from_uri(uri="https://example.com/resource", media_type="application/json")
    mcp_content = _HELPER_MCP_TOOL._prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.ResourceLink)
    assert mcp_content.type == "resource_link"
    assert str(mcp_content.uri) == "https://example.com/resource"
    assert mcp_content.mimeType == "application/json"


def test_prepare_message_for_mcp():
    message = Message(
        role="user",
        contents=[
            Content.from_text(text="test"),
            Content.from_uri(uri="data:image/png;base64,xyz", media_type="image/png"),
        ],
    )
    mcp_contents = _HELPER_MCP_TOOL._prepare_message_for_mcp(message)
    assert len(mcp_contents) == 2
    assert isinstance(mcp_contents[0], types.TextContent)
    assert isinstance(mcp_contents[1], types.ImageContent)


def test_prepare_message_for_mcp_skips_unsupported_content() -> None:
    unsupported = Content(type="annotations", text="ignored")  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    assert _HELPER_MCP_TOOL._prepare_content_for_mcp(unsupported) is None

    mcp_contents = _HELPER_MCP_TOOL._prepare_message_for_mcp(
        Message(role="user", contents=[Content.from_text("kept"), unsupported])
    )
    assert len(mcp_contents) == 1
    assert isinstance(mcp_contents[0], types.TextContent)


@pytest.mark.parametrize(
    "test_id,input_schema",
    [
        (test_id, input_schema)
        for test_id, input_schema, _, _, _, _ in [  # type: ignore[assignment]
            # Basic types with required/optional fields
            (
                "basic_types",
                {
                    "type": "object",
                    "properties": {"param1": {"type": "string"}, "param2": {"type": "number"}},
                    "required": ["param1"],
                },
                {"param1": "test", "param2": 42},
                {"param1": "test", "param2": 42},
                {"param2": 42},  # Missing required param1
                None,
            ),
            # Nested object
            (
                "nested_object",
                {
                    "type": "object",
                    "properties": {
                        "params": {
                            "type": "object",
                            "properties": {"customer_id": {"type": "integer"}},
                            "required": ["customer_id"],
                        }
                    },
                    "required": ["params"],
                },
                {"params": {"customer_id": 251}},
                {"params.customer_id": 251},
                {"params": {}},  # Missing required customer_id
                lambda instance: isinstance(instance.params, BaseModel),
            ),
            # $ref resolution
            (
                "ref_schema",
                {
                    "type": "object",
                    "properties": {"params": {"$ref": "#/$defs/CustomerIdParam"}},
                    "required": ["params"],
                    "$defs": {
                        "CustomerIdParam": {
                            "type": "object",
                            "properties": {"customer_id": {"type": "integer"}},
                            "required": ["customer_id"],
                        }
                    },
                },
                {"params": {"customer_id": 251}},
                {"params.customer_id": 251},
                {"params": {}},  # Missing required customer_id
                lambda instance: isinstance(instance.params, BaseModel),
            ),
            # Array of strings (typed)
            (
                "array_of_strings",
                {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "description": "List of tags",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["tags"],
                },
                {"tags": ["tag1", "tag2", "tag3"]},
                {"tags": ["tag1", "tag2", "tag3"]},
                None,  # No validation error test for this case
                None,
            ),
            # Array of integers (typed)
            (
                "array_of_integers",
                {
                    "type": "object",
                    "properties": {
                        "numbers": {
                            "type": "array",
                            "description": "List of integers",
                            "items": {"type": "integer"},
                        }
                    },
                    "required": ["numbers"],
                },
                {"numbers": [1, 2, 3]},
                {"numbers": [1, 2, 3]},
                None,
                None,
            ),
            # Array of objects (complex nested)
            (
                "array_of_objects",
                {
                    "type": "object",
                    "properties": {
                        "users": {
                            "type": "array",
                            "description": "List of users",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer", "description": "User ID"},
                                    "name": {"type": "string", "description": "User name"},
                                },
                                "required": ["id", "name"],
                            },
                        }
                    },
                    "required": ["users"],
                },
                {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]},
                {"users[0].id": 1, "users[0].name": "Alice", "users[1].id": 2, "users[1].name": "Bob"},
                {"users": [{"id": 1}]},  # Missing required 'name'
                lambda instance: all(isinstance(user, BaseModel) for user in instance.users),
            ),
            # Deeply nested objects (3+ levels)
            (
                "deeply_nested",
                {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "object",
                            "properties": {
                                "filters": {
                                    "type": "object",
                                    "properties": {
                                        "date_range": {
                                            "type": "object",
                                            "properties": {
                                                "start": {"type": "string"},
                                                "end": {"type": "string"},
                                            },
                                            "required": ["start", "end"],
                                        },
                                        "categories": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "required": ["date_range"],
                                }
                            },
                            "required": ["filters"],
                        }
                    },
                    "required": ["query"],
                },
                {
                    "query": {
                        "filters": {
                            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                            "categories": ["tech", "science"],
                        }
                    }
                },
                {
                    "query.filters.date_range.start": "2024-01-01",
                    "query.filters.date_range.end": "2024-12-31",
                    "query.filters.categories": ["tech", "science"],
                },
                {"query": {"filters": {"date_range": {}}}},  # Missing required start and end
                None,
            ),
            # Complex $ref with nested structure
            (
                "ref_nested_structure",
                {
                    "type": "object",
                    "properties": {"order": {"$ref": "#/$defs/OrderParams"}},
                    "required": ["order"],
                    "$defs": {
                        "OrderParams": {
                            "type": "object",
                            "properties": {
                                "customer": {"$ref": "#/$defs/Customer"},
                                "items": {"type": "array", "items": {"$ref": "#/$defs/OrderItem"}},
                            },
                            "required": ["customer", "items"],
                        },
                        "Customer": {
                            "type": "object",
                            "properties": {"id": {"type": "integer"}, "email": {"type": "string"}},
                            "required": ["id", "email"],
                        },
                        "OrderItem": {
                            "type": "object",
                            "properties": {"product_id": {"type": "string"}, "quantity": {"type": "integer"}},
                            "required": ["product_id", "quantity"],
                        },
                    },
                },
                {
                    "order": {
                        "customer": {"id": 123, "email": "test@example.com"},
                        "items": [{"product_id": "prod1", "quantity": 2}],
                    }
                },
                {
                    "order.customer.id": 123,
                    "order.customer.email": "test@example.com",
                    "order.items[0].product_id": "prod1",
                    "order.items[0].quantity": 2,
                },
                {"order": {"customer": {"id": 123}, "items": []}},  # Missing email
                lambda instance: isinstance(instance.order.customer, BaseModel),
            ),
            # Mixed types (primitives, arrays, nested objects)
            (
                "mixed_types",
                {
                    "type": "object",
                    "properties": {
                        "simple_string": {"type": "string"},
                        "simple_number": {"type": "integer"},
                        "string_array": {"type": "array", "items": {"type": "string"}},
                        "nested_config": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "options": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["enabled"],
                        },
                    },
                    "required": ["simple_string", "nested_config"],
                },
                {
                    "simple_string": "test",
                    "simple_number": 42,
                    "string_array": ["a", "b"],
                    "nested_config": {"enabled": True, "options": ["opt1", "opt2"]},
                },
                {
                    "simple_string": "test",
                    "simple_number": 42,
                    "string_array": ["a", "b"],
                    "nested_config.enabled": True,
                    "nested_config.options": ["opt1", "opt2"],
                },
                None,
                None,
            ),
            # Empty schema (no properties)
            (
                "empty_schema",
                {"type": "object", "properties": {}},
                {},
                {},
                None,
                None,
            ),
            # All primitive types
            (
                "all_primitives",
                {
                    "type": "object",
                    "properties": {
                        "string_field": {"type": "string"},
                        "integer_field": {"type": "integer"},
                        "number_field": {"type": "number"},
                        "boolean_field": {"type": "boolean"},
                    },
                },
                {"string_field": "test", "integer_field": 42, "number_field": 3.14, "boolean_field": True},
                {"string_field": "test", "integer_field": 42, "number_field": 3.14, "boolean_field": True},
                None,
                None,
            ),
            # Edge case: unresolvable $ref (fallback to dict)
            (
                "unresolvable_ref",
                {
                    "type": "object",
                    "properties": {"data": {"$ref": "#/$defs/NonExistent"}},
                    "$defs": {},
                },
                {"data": {"key": "value"}},
                {"data": {"key": "value"}},
                None,
                None,
            ),
            # Edge case: array without items schema (fallback to bare list)
            (
                "array_no_items",
                {
                    "type": "object",
                    "properties": {"items": {"type": "array"}},
                },
                {"items": [1, "two", 3.0]},
                {"items": [1, "two", 3.0]},
                None,
                None,
            ),
            # Edge case: object without properties (fallback to dict)
            (
                "object_no_properties",
                {
                    "type": "object",
                    "properties": {"config": {"type": "object"}},
                },
                {"config": {"arbitrary": "data", "nested": {"key": "value"}}},
                {"config": {"arbitrary": "data", "nested": {"key": "value"}}},
                None,
                None,
            ),
        ]
    ],
)
def test_get_input_model_from_mcp_tool_parametrized(test_id: str, input_schema: dict[str, Any]) -> None:
    """Parametrized test for MCP tool input schema passthrough.

    This test verifies that MCP tool schemas are passed through as-is
    without Pydantic conversion, which improves performance and preserves
    the original schema structure.

    To add a new test case, add a tuple to the parametrize decorator with:
    - test_id: A descriptive name for the test case
    - input_schema: The JSON schema (inputSchema dict)
    """
    tool = types.Tool(name="test_tool", description="A test tool", inputSchema=input_schema)
    schema = tool.inputSchema

    # Verify schema is returned as-is (dict)
    assert isinstance(schema, dict), f"Expected dict, got {type(schema)}"
    assert schema == input_schema, "Schema should be passed through unchanged"


def test_get_input_model_from_mcp_prompt():
    """Test creation of input schema from MCP prompt."""
    prompt = types.Prompt(
        name="test_prompt",
        description="A test prompt",
        arguments=[
            types.PromptArgument(name="arg1", description="First argument", required=True),
            types.PromptArgument(name="arg2", description="Second argument", required=False),
        ],
    )
    result = _get_input_model_from_mcp_prompt(prompt)

    # Should return a dict (schema)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result["type"] == "object"
    assert "arg1" in result["properties"]
    assert "arg2" in result["properties"]
    assert "arg1" in result["required"]
    assert "arg2" not in result["required"]


def test_get_input_model_from_mcp_prompt_without_arguments():
    """Test prompt schema generation when no prompt arguments are defined."""
    prompt = types.Prompt(name="empty_prompt", description="No args prompt", arguments=[])
    result = _get_input_model_from_mcp_prompt(prompt)

    assert isinstance(result, dict)
    assert result == {"type": "object", "properties": {}}


# MCPTool tests
async def test_local_mcp_server_initialization():
    """Test MCPTool initialization."""
    server = MCPTool(name="test_server")  # type: ignore[abstract]
    # MCPTool has the same core attributes as FunctionTool
    assert hasattr(server, "name")
    assert hasattr(server, "description")
    assert hasattr(server, "additional_properties")
    assert server.name == "test_server"
    assert server.session is None
    assert server.functions == []


async def test_local_mcp_server_context_manager():
    """Test MCPTool as context manager."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            # Mock connection
            self.session = Mock(spec=ClientSession)

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        assert server.session is not None

    assert server.session is None


async def test_local_mcp_server_load_functions():
    """Test loading functions from MCP server."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            # Mock tools list response
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    # MCPTool has the same core attributes as FunctionTool
    assert hasattr(server, "name")
    assert hasattr(server, "description")
    async with server:
        await server.load_tools()
        assert len(server.functions) == 1
        assert server.functions[0].name == "test_tool"


async def test_local_mcp_server_load_prompts():
    """Test loading prompts from MCP server."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            # Mock prompts list response
            self.session.list_prompts = AsyncMock(
                return_value=types.ListPromptsResult(
                    prompts=[
                        types.Prompt(
                            name="test_prompt",
                            description="Test prompt",
                            arguments=[types.PromptArgument(name="arg", description="Test arg", required=True)],
                        )
                    ]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_prompts()
        assert len(server.functions) == 1
        assert server.functions[0].name == "test_prompt"


async def test_mcp_tool_call_tool_with_meta_integration():
    """Test that call_tool method properly integrates with enhanced metadata extraction."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )

            # Create a CallToolResult with _meta field
            tool_result = types.CallToolResult(
                content=[types.TextContent(type="text", text="Tool executed with metadata")],
                _meta={"executionTime": 1.5, "cost": {"usd": 0.002}, "isError": False, "toolVersion": "1.2.3"},
            )

            self.session.call_tool = AsyncMock(return_value=tool_result)

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]
        result = await func.invoke(param="test_value")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "Tool executed with metadata"


async def test_local_mcp_server_function_execution():
    """Test function execution through MCP server."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(
                    content=[types.TextContent(type="text", text="Tool executed successfully")]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]
        result = await func.invoke(param="test_value")

        assert isinstance(result, list)
        assert result[0].text == "Tool executed successfully"


async def test_local_mcp_server_function_execution_with_nested_object():
    """Test function execution through MCP server with nested object arguments."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="get_customer_detail",
                            description="Get customer details",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "params": {
                                        "type": "object",
                                        "properties": {"customer_id": {"type": "integer"}},
                                        "required": ["customer_id"],
                                    }
                                },
                                "required": ["params"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(
                    content=[types.TextContent(type="text", text='{"name": "John Doe", "id": 251}')]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        # Call with nested object
        result = await func.invoke(params={"customer_id": 251})

        assert isinstance(result, list)
        assert result[0].text == '{"name": "John Doe", "id": 251}'

        # Verify the session.call_tool was called with the correct nested structure
        server.session.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        call_args = server.session.call_tool.call_args  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_args.kwargs["arguments"] == {"params": {"customer_id": 251}}


async def test_local_mcp_server_function_execution_error():
    """Test function execution error handling."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            # Mock a tool call that raises an MCP error
            self.session.call_tool = AsyncMock(
                side_effect=McpError(types.ErrorData(code=-1, message="Tool execution failed"))
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        with pytest.raises(ToolExecutionException):
            await func.invoke(param="test_value")


async def test_mcp_tool_reconnects_after_session_terminated_error():
    """Session termination errors should reconnect once and retry the tool call."""

    class TestServer(MCPTool):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.connect_count = 0
            self.sessions: list[Any] = []

        async def connect(self, *, reset: bool = False) -> None:
            self.connect_count += 1
            self.session = Mock(spec=ClientSession)
            self.sessions.append(self.session)
            if self.connect_count == 1:
                self.session.call_tool = AsyncMock(
                    side_effect=McpError(types.ErrorData(code=-32000, message="Session terminated"))
                )
            else:
                self.session.call_tool = AsyncMock(
                    return_value=types.CallToolResult(content=[types.TextContent(type="text", text="recovered")])
                )
            self.is_connected = True

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    await server.connect()

    result = await server.call_tool("test_tool", param="test_value")

    assert _mcp_result_to_text(result) == "recovered"
    assert server.connect_count == 2
    assert server.sessions[0].call_tool.await_count == 1
    assert server.sessions[1].call_tool.await_count == 1


async def test_mcp_tool_call_tool_raises_on_is_error():
    """Test that call_tool raises ToolExecutionException when MCP returns isError=True."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(
                    content=[types.TextContent(type="text", text="Something went wrong")],
                    isError=True,
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        with pytest.raises(ToolExecutionException, match="Something went wrong"):
            await func.invoke(param="test_value")


async def test_mcp_tool_call_tool_succeeds_when_is_error_false():
    """Test that call_tool returns normally when MCP returns isError=False."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(
                    content=[types.TextContent(type="text", text="Success")],
                    isError=False,
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]
        result = await func.invoke(param="test_value")
        assert isinstance(result, list)
        assert result[0].text == "Success"


async def test_mcp_tool_is_error_propagates_through_function_middleware():
    """Test that MCP isError=True propagates as ToolExecutionException through function middleware."""
    error_seen_in_middleware = False

    class ErrorCheckMiddleware(FunctionMiddleware):
        async def process(self, context: FunctionInvocationContext, call_next):
            nonlocal error_seen_in_middleware
            try:
                await call_next()
            except ToolExecutionException:
                error_seen_in_middleware = True
                raise

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(
                    content=[types.TextContent(type="text", text="MCP error occurred")],
                    isError=True,
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        middleware_pipeline = FunctionMiddlewarePipeline(ErrorCheckMiddleware())

        middleware_context = FunctionInvocationContext(
            function=func,
            arguments={"param": "test_value"},
        )

        with pytest.raises(ToolExecutionException, match="MCP error occurred"):
            await middleware_pipeline.execute(
                middleware_context,
                lambda ctx: func.invoke(arguments=ctx.arguments),
            )

        assert error_seen_in_middleware, "Middleware should have seen the ToolExecutionException"


async def test_local_mcp_server_prompt_execution():
    """Test prompt execution through MCP server."""

    class TestMCPTool(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_prompts = AsyncMock(
                return_value=types.ListPromptsResult(
                    prompts=[
                        types.Prompt(
                            name="test_prompt",
                            description="Test prompt",
                            arguments=[types.PromptArgument(name="arg", description="Test arg", required=True)],
                        )
                    ]
                )
            )
            self.session.get_prompt = AsyncMock(
                return_value=types.GetPromptResult(
                    description="Generated prompt",
                    messages=[
                        types.PromptMessage(
                            role="user",
                            content=types.TextContent(type="text", text="Test message"),
                        )
                    ],
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestMCPTool(name="test_server")
    async with server:
        await server.load_prompts()
        prompt = server.functions[0]
        result = await prompt.invoke(arg="test_value")

        assert isinstance(result, list)
        assert result[0].text == "Test message"


@pytest.mark.parametrize(
    "approval_mode,expected_approvals",
    [
        (
            "always_require",
            {"tool_one": "always_require", "tool_two": "always_require"},
        ),
        ("never_require", {"tool_one": "never_require", "tool_two": "never_require"}),
        (
            {
                "always_require_approval": ["tool_one"],
                "never_require_approval": ["tool_two"],
            },
            {"tool_one": "always_require", "tool_two": "never_require"},
        ),
    ],
)
async def test_mcp_tool_approval_mode(approval_mode, expected_approvals):
    """Test MCPTool approval_mode parameter with various configurations.

    The approval_mode parameter controls whether tools require approval before execution.
    It can be set globally ("always_require" or "never_require") or per-tool using a dict.
    """

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="tool_one",
                            description="First tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                            },
                        ),
                        types.Tool(
                            name="tool_two",
                            description="Second tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                            },
                        ),
                    ]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server", approval_mode=approval_mode)
    async with server:
        await server.load_tools()
        assert len(server.functions) == 2

        # Verify each tool has the expected approval mode
        for func in server.functions:
            assert func.approval_mode == expected_approvals[func.name]


def test_mcp_tool_approval_mode_returns_none_for_unmatched_names() -> None:
    tool = MCPTool(  # type: ignore[abstract]
        name="test_tool",
        approval_mode={
            "always_require_approval": ["tool_one"],
            "never_require_approval": ["tool_two"],
        },
    )

    assert tool._determine_approval_mode("tool_three") is None


@pytest.mark.parametrize(
    "allowed_tools,expected_count,expected_names",
    [
        (
            None,
            3,
            ["tool_one", "tool_two", "tool_three"],
        ),  # None means all tools are allowed
        ([], 0, []),  # Empty list means no tools are allowed
        (["tool_one"], 1, ["tool_one"]),  # Only tool_one is allowed
        (
            ["tool_one", "tool_three"],
            2,
            ["tool_one", "tool_three"],
        ),  # Two tools allowed
        (["nonexistent_tool"], 0, []),  # No matching tools
    ],
)
async def test_mcp_tool_allowed_tools(allowed_tools, expected_count, expected_names):
    """Test MCPTool allowed_tools parameter with various configurations.

    The allowed_tools parameter filters which tools are exposed via the functions property.
    When None, all loaded tools are available. When set to a list, only tools whose names
    are in that list are exposed.
    """

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="tool_one",
                            description="First tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                            },
                        ),
                        types.Tool(
                            name="tool_two",
                            description="Second tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                            },
                        ),
                        types.Tool(
                            name="tool_three",
                            description="Third tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                            },
                        ),
                    ]
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server", allowed_tools=allowed_tools)
    async with server:
        await server.load_tools()
        # _functions should contain all tools
        assert len(server._functions) == 3

        # functions property should filter based on allowed_tools
        assert len(server.functions) == expected_count
        actual_names = [func.name for func in server.functions]
        assert sorted(actual_names) == sorted(expected_names)


# Server implementation tests
def test_local_mcp_stdio_tool_init():
    """Test MCPStdioTool initialization."""
    tool = MCPStdioTool(name="test", command="echo", args=["hello"])
    assert tool.name == "test"
    assert tool.command == "echo"
    assert tool.args == ["hello"]


def test_local_mcp_websocket_tool_init():
    """Test MCPWebsocketTool initialization."""
    tool = MCPWebsocketTool(name="test", url="ws://localhost:8080")
    assert tool.name == "test"
    assert tool.url == "ws://localhost:8080"


def test_local_mcp_streamable_http_tool_init():
    """Test MCPStreamableHTTPTool initialization."""
    tool = MCPStreamableHTTPTool(name="test", url="http://localhost:8080")
    assert tool.name == "test"
    assert tool.url == "http://localhost:8080"


# Integration test
@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mcp_integration_tests_disabled
async def test_streamable_http_integration():
    """Test MCP StreamableHTTP integration."""
    url = os.environ.get("LOCAL_MCP_URL", "")
    if not url.startswith("http"):
        pytest.skip("LOCAL_MCP_URL is not an HTTP URL")

    tool = MCPStreamableHTTPTool(name="integration_test", url=url, approval_mode="never_require")

    async with tool:
        # Test that we can connect and load tools
        assert tool.session is not None
        assert isinstance(tool.functions, list)

        # If there are functions available, try to get information about one
        assert tool.functions, "The MCP server should have at least one function."

        func = tool.functions[0]

        assert hasattr(func, "name")
        assert hasattr(func, "description")

        result = _mcp_result_to_text(await func.invoke(query="What is Agent Framework?"))
        assert len(result) > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mcp_integration_tests_disabled
async def test_mcp_connection_reset_integration():
    """Test that connection reset works correctly with a real MCP server.

    This integration test verifies:
    1. Initial connection and tool execution works
    2. Simulating connection failure triggers automatic reconnection
    3. Tool execution works after reconnection
    4. Exit stack cleanup happens properly during reconnection
    """
    url = os.environ.get("LOCAL_MCP_URL")

    tool = MCPStreamableHTTPTool(name="integration_test", url=url, approval_mode="never_require")  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    async with tool:
        # Verify initial connection
        assert tool.session is not None
        assert tool.is_connected is True
        assert len(tool.functions) > 0, "The MCP server should have at least one function."

        # Get the first function and invoke it
        func = tool.functions[0]
        first_result = _mcp_result_to_text(await func.invoke(query="What is Agent Framework?"))
        assert first_result is not None
        assert len(first_result) > 0

        # Store the original session and exit stack for comparison
        original_session = tool.session
        original_exit_stack = tool._exit_stack
        original_call_tool = tool.session.call_tool

        # Simulate connection failure by making call_tool raise ClosedResourceError once
        call_count = 0

        async def call_tool_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with connection error
                from anyio.streams.memory import ClosedResourceError

                raise ClosedResourceError
            # After reconnection, delegate to the original method
            return await original_call_tool(*args, **kwargs)

        tool.session.call_tool = call_tool_with_error  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

        # Invoke the function again - this should trigger automatic reconnection on ClosedResourceError
        second_result = _mcp_result_to_text(await func.invoke(query="What is Agent Framework?"))
        assert second_result is not None
        assert len(second_result) > 0

        # Verify we have a new session and exit stack after reconnection
        assert tool.session is not None
        assert tool.session is not original_session, "Session should be replaced after reconnection"
        assert tool._exit_stack is not original_exit_stack, "Exit stack should be replaced after reconnection"
        assert tool.is_connected is True

        # Verify tools are still available after reconnection
        assert len(tool.functions) > 0

        # Both results should include text (we don't compare content as it may vary)
        assert len(first_result) > 0
        assert len(second_result) > 0


async def test_mcp_tool_message_handler_notification():
    """Test that message_handler correctly processes tools/list_changed and prompts/list_changed
    notifications by scheduling reloads as background tasks."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Mock the load_tools and load_prompts methods
    tool.load_tools = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    tool.load_prompts = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Test tools list changed notification
    tools_notification = Mock(spec=types.ServerNotification)
    tools_notification.root = Mock()
    tools_notification.root.method = "notifications/tools/list_changed"

    result = await tool.message_handler(tools_notification)  # type: ignore[func-returns-value]
    assert result is None
    # The reload is scheduled as a background task; let it run.
    await asyncio.sleep(0)
    tool.load_tools.assert_called_once()  # ty: ignore[unresolved-attribute]

    # Reset mock
    tool.load_tools.reset_mock()  # ty: ignore[unresolved-attribute]

    # Test prompts list changed notification
    prompts_notification = Mock(spec=types.ServerNotification)
    prompts_notification.root = Mock()
    prompts_notification.root.method = "notifications/prompts/list_changed"

    result = await tool.message_handler(prompts_notification)  # type: ignore[func-returns-value]
    assert result is None
    await asyncio.sleep(0)
    tool.load_prompts.assert_called_once()  # ty: ignore[unresolved-attribute]

    # Test unhandled notification
    unknown_notification = Mock(spec=types.ServerNotification)
    unknown_notification.root = Mock()
    unknown_notification.root.method = "notifications/unknown"

    result = await tool.message_handler(unknown_notification)  # type: ignore[func-returns-value]
    assert result is None


async def test_mcp_tool_message_handler_error():
    """Test that message_handler gracefully handles exceptions by logging and returning None."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Test with exception message
    test_exception = RuntimeError("Test error message")

    # The message handler should log the error and return None
    result = await tool.message_handler(test_exception)  # type: ignore[func-returns-value]
    assert result is None


async def test_mcp_tool_message_handler_does_not_block_receive_loop():
    """Test that message_handler does not deadlock the MCP receive loop.

    Regression test for https://github.com/microsoft/agent-framework/issues/4828.
    When the MCP server sends a ``notifications/tools/list_changed``
    notification, the handler must NOT await ``load_tools()`` synchronously
    because that would block the single-threaded MCP receive loop, preventing
    it from delivering the ``list_tools`` response — a classic deadlock.
    """
    tool = MCPStdioTool(name="test_tool", command="python")

    # Use an event to make load_tools block until we release it.
    # This simulates load_tools waiting for a session response that the
    # receive loop would need to deliver.
    release = asyncio.Event()

    async def slow_load_tools():
        await release.wait()

    tool.load_tools = slow_load_tools  # type: ignore[assignment]  # ty: ignore[invalid-assignment]

    tools_notification = Mock(spec=types.ServerNotification)
    tools_notification.root = Mock()
    tools_notification.root.method = "notifications/tools/list_changed"

    # message_handler must return immediately even though load_tools blocks.
    await tool.message_handler(tools_notification)

    # If the handler had awaited load_tools synchronously, we would never
    # reach this line (deadlock). Verify the reload task is pending.
    assert len(tool._pending_reload_tasks) == 1

    # Unblock the reload so the background task finishes cleanly.
    release.set()
    # Wait for the pending reload task(s) to complete so their done-callbacks
    # have a chance to remove them from _pending_reload_tasks.
    await asyncio.wait_for(asyncio.gather(*tool._pending_reload_tasks), timeout=1)
    assert len(tool._pending_reload_tasks) == 0


async def test_mcp_tool_message_handler_reload_failure_is_logged(caplog: pytest.LogCaptureFixture):
    """Background reload errors are logged, not raised into the receive loop."""
    tool = MCPStdioTool(name="test_tool", command="python")
    tool.load_tools = AsyncMock(side_effect=RuntimeError("connection lost"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    tools_notification = Mock(spec=types.ServerNotification)
    tools_notification.root = Mock()
    tools_notification.root.method = "notifications/tools/list_changed"

    await tool.message_handler(tools_notification)
    # Let the background task run — it should not propagate the exception.
    # Snapshot tasks and await them to ensure done-callbacks fire.
    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=1)
    tool.load_tools.assert_called_once()  # ty: ignore[unresolved-attribute]
    assert len(tool._pending_reload_tasks) == 0

    # Verify the warning was actually logged with exception info.
    reload_warnings = [r for r in caplog.records if "Background MCP reload failed" in r.message]
    assert len(reload_warnings) == 1
    assert reload_warnings[0].levelname == "WARNING"
    assert reload_warnings[0].exc_info is not None


async def test_mcp_tool_message_handler_cancel_and_replace():
    """Sending two notifications in quick succession cancels the first reload task."""
    tool = MCPStdioTool(name="test_tool", command="python")

    release = asyncio.Event()
    call_count = 0

    async def blocking_load_tools():
        nonlocal call_count
        call_count += 1
        await release.wait()

    tool.load_tools = blocking_load_tools  # type: ignore[assignment]  # ty: ignore[invalid-assignment]

    notification = Mock(spec=types.ServerNotification)
    notification.root = Mock()
    notification.root.method = "notifications/tools/list_changed"

    # First notification — starts a blocking reload task.
    await tool.message_handler(notification)
    assert len(tool._pending_reload_tasks) == 1
    first_task = next(iter(tool._pending_reload_tasks))

    # Second notification — should cancel the first and replace it.
    await tool.message_handler(notification)
    # Yield to the event loop so the cancellation is processed.
    with contextlib.suppress(asyncio.CancelledError):
        await first_task

    assert first_task.cancelled()

    assert len(tool._pending_reload_tasks) == 1
    second_task = next(iter(tool._pending_reload_tasks))
    assert second_task is not first_task

    # Unblock and let the second task finish.
    release.set()
    await asyncio.wait_for(asyncio.gather(*tool._pending_reload_tasks), timeout=1)
    assert len(tool._pending_reload_tasks) == 0


def _approve(_params: object) -> bool:
    """Approving sampling gate used by tests that exercise forwarding behavior."""
    return True


def _make_sampling_response(text: str = "response", model: str = "test-model") -> Mock:
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text(text)])]
    mock_response.model = model
    return mock_response


async def test_mcp_tool_sampling_callback_no_client():
    """Test sampling callback error path when no chat client is available."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Create minimal params mock
    params = Mock()
    params.messages = []

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "No chat client available" in result.message


async def test_mcp_tool_sampling_callback_denies_by_default():
    """Sampling is denied when no approval callback is configured (safe default)."""
    tool = MCPStdioTool(name="test_tool", command="python")
    mock_chat_client = AsyncMock()
    tool.client = mock_chat_client

    params = Mock()
    params.messages = []
    params.maxTokens = 128

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INVALID_REQUEST
    assert "denied" in result.message
    assert "sampling_approval_callback" in result.message
    mock_chat_client.get_response.assert_not_called()


async def test_mcp_tool_sampling_callback_denied_by_callback():
    """Sampling is denied when the approval callback returns a falsy value."""
    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=lambda params: False)
    mock_chat_client = AsyncMock()
    tool.client = mock_chat_client

    params = Mock()
    params.messages = []
    params.maxTokens = 128

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INVALID_REQUEST
    assert "denied by the 'sampling_approval_callback'" in result.message
    mock_chat_client.get_response.assert_not_called()


async def test_mcp_tool_sampling_callback_callback_exception_denies():
    """An approval callback that raises results in denial, not an LLM call."""

    def boom(_params: object) -> bool:
        raise RuntimeError("approval error")

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=boom)
    mock_chat_client = AsyncMock()
    tool.client = mock_chat_client

    params = Mock()
    params.messages = []
    params.maxTokens = 128

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INVALID_REQUEST
    mock_chat_client.get_response.assert_not_called()


async def test_mcp_tool_sampling_callback_async_approval():
    """An async approval callback that approves allows the request through."""

    async def approve(_params: object) -> bool:
        return True

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=approve)
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.return_value = _make_sampling_response("ok")
    tool.client = mock_chat_client

    params = Mock()
    params.messages = [types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hi"))]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    assert isinstance(result.content, types.TextContent)
    assert result.content.text == "ok"
    mock_chat_client.get_response.assert_awaited_once()


async def test_mcp_tool_sampling_callback_clamps_max_tokens():
    """An approved request's maxTokens is clamped to sampling_max_tokens."""
    tool = MCPStdioTool(
        name="test_tool",
        command="python",
        sampling_approval_callback=_approve,
        sampling_max_tokens=512,
    )
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.return_value = _make_sampling_response()
    tool.client = mock_chat_client

    params = Mock()
    params.messages = [types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hi"))]
    params.temperature = None
    params.maxTokens = 1_000_000
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    options = mock_chat_client.get_response.call_args.kwargs.get("options") or {}
    assert options["max_tokens"] == 512


async def test_mcp_tool_sampling_callback_does_not_clamp_under_cap():
    """A request below the cap keeps its requested maxTokens."""
    tool = MCPStdioTool(
        name="test_tool",
        command="python",
        sampling_approval_callback=_approve,
        sampling_max_tokens=512,
    )
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.return_value = _make_sampling_response()
    tool.client = mock_chat_client

    params = Mock()
    params.messages = [types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hi"))]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    options = mock_chat_client.get_response.call_args.kwargs.get("options") or {}
    assert options["max_tokens"] == 100


async def test_mcp_tool_sampling_callback_rate_limited():
    """Sampling requests beyond sampling_max_requests are rejected per session."""
    tool = MCPStdioTool(
        name="test_tool",
        command="python",
        sampling_approval_callback=_approve,
        sampling_max_requests=2,
    )
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.return_value = _make_sampling_response()
    tool.client = mock_chat_client

    def make_params() -> Mock:
        params = Mock()
        params.messages = [types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hi"))]
        params.temperature = None
        params.maxTokens = 100
        params.stopSequences = None
        params.systemPrompt = None
        params.tools = None
        params.toolChoice = None
        return params

    first = await tool.sampling_callback(Mock(), make_params())
    second = await tool.sampling_callback(Mock(), make_params())
    third = await tool.sampling_callback(Mock(), make_params())

    assert isinstance(first, types.CreateMessageResult)
    assert isinstance(second, types.CreateMessageResult)
    assert isinstance(third, types.ErrorData)
    assert third.code == types.INVALID_REQUEST
    assert "rate limit" in third.message.lower()
    assert mock_chat_client.get_response.await_count == 2

    # The counter resets on a session reset.
    tool._reset_session_state()
    fourth = await tool.sampling_callback(Mock(), make_params())
    assert isinstance(fourth, types.CreateMessageResult)


async def test_mcp_tool_sampling_callback_chat_client_exception():
    """Test sampling callback when chat client raises exception."""
    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    # Mock chat client that raises exception
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.side_effect = RuntimeError("Chat client error")

    tool.client = mock_chat_client

    # Create mock params
    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "Failed to get chat message content" in result.message


async def test_mcp_tool_sampling_callback_no_valid_content():
    """Test sampling callback when response has no valid content types."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    # Mock chat client with response containing only invalid content types
    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [
        Message(
            role="assistant",
            contents=[
                Content.from_uri(
                    uri="data:application/json;base64,e30K",
                    media_type="application/json",
                )
            ],
        )
    ]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    # Create mock params
    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "Failed to get right content types from the response." in result.message
    mock_chat_client.get_response.assert_awaited_once()
    _, kwargs = mock_chat_client.get_response.await_args
    assert kwargs["options"] == {"max_tokens": 100}


async def test_mcp_tool_sampling_callback_no_response_and_successful_message_creation():
    """Test sampling callback when the chat client returns no response and then valid content."""
    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)
    tool.client = AsyncMock()

    params = Mock()
    params.messages = [types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hi"))]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    tool.client.get_response.return_value = None
    no_response = await tool.sampling_callback(Mock(), params)

    assert isinstance(no_response, types.ErrorData)
    assert no_response.message == "Failed to get chat message content."

    tool.client.get_response.return_value = Mock(
        messages=[Message(role="assistant", contents=[Content.from_text("Hello")])],
        model="test-model",
    )

    success = await tool.sampling_callback(Mock(), params)

    assert isinstance(success, types.CreateMessageResult)
    assert success.role == "assistant"
    assert success.model == "test-model"
    assert isinstance(success.content, types.TextContent)
    assert success.content.text == "Hello"


async def test_mcp_tool_logging_callback_logs_at_requested_level() -> None:
    tool = MCPStdioTool(name="test_tool", command="python")

    with patch.object(logger, "log") as mock_log:
        await tool.logging_callback(types.LoggingMessageNotificationParams(level="warning", data="be careful"))

    mock_log.assert_called_once_with(logging.WARNING, "be careful")


async def test_mcp_tool_sampling_callback_forwards_system_prompt():
    """Test sampling callback passes systemPrompt as instructions in options."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = "You are a helpful assistant"
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options.get("instructions") == "You are a helpful assistant"


async def test_mcp_tool_sampling_callback_forwards_tools():
    """Test sampling callback converts MCP tools to FunctionTools and passes them in options."""
    from agent_framework import FunctionTool, Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    mcp_tool = types.Tool(
        name="get_weather",
        description="Get weather",
        inputSchema={"type": "object", "properties": {"city": {"type": "string"}}},
    )

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = [mcp_tool]
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    tools = options.get("tools")
    assert tools is not None
    assert len(tools) == 1
    assert isinstance(tools[0], FunctionTool)
    assert tools[0].name == "get_weather"
    assert tools[0].description == "Get weather"


async def test_mcp_tool_sampling_callback_forwards_tool_choice():
    """Test sampling callback passes toolChoice mode in options."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = types.ToolChoice(mode="required")

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options.get("tool_choice") == "required"


async def test_mcp_tool_sampling_callback_forwards_empty_system_prompt():
    """Test sampling callback forwards empty string systemPrompt as instructions."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = ""
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options.get("instructions") == ""


async def test_mcp_tool_sampling_callback_forwards_empty_tools_list():
    """Test sampling callback forwards empty tools list in options."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = []
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options.get("tools") == []


async def test_mcp_tool_sampling_callback_forwards_generation_params_in_options():
    """Test sampling callback passes temperature, max_tokens, and stop in options."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = 0.7
    params.maxTokens = 256
    params.stopSequences = ["STOP"]
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options.get("temperature") == 0.7
    assert options.get("max_tokens") == 256
    assert options.get("stop") == ["STOP"]
    # These should not be passed as top-level kwargs
    assert "temperature" not in call_kwargs.kwargs
    assert "max_tokens" not in call_kwargs.kwargs
    assert "stop" not in call_kwargs.kwargs


async def test_mcp_tool_sampling_callback_omits_temperature_when_none():
    """Test sampling callback does not set temperature in options when it is None."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 100
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert "temperature" not in options
    assert options.get("max_tokens") == 100
    assert "stop" not in options


async def test_mcp_tool_sampling_callback_always_passes_max_tokens():
    """Test sampling callback always sets max_tokens in options since maxTokens is a required int field."""
    from agent_framework import Message

    tool = MCPStdioTool(name="test_tool", command="python", sampling_approval_callback=_approve)

    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [Message(role="assistant", contents=[Content.from_text("response")])]
    mock_response.model = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.client = mock_chat_client

    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = 200
    params.stopSequences = None
    params.systemPrompt = None
    params.tools = None
    params.toolChoice = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.CreateMessageResult)
    call_kwargs = mock_chat_client.get_response.call_args
    options = call_kwargs.kwargs.get("options") or {}
    assert options["max_tokens"] == 200


async def test_connect_sampling_capabilities_with_client():
    """Test connect() passes sampling_capabilities to ClientSession when client is set."""
    tool = MCPStdioTool(name="test", command="test-command", load_tools=False, load_prompts=False)
    tool.client = Mock()

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session._request_id = 1

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = session_cm

        await tool.connect()

        call_kwargs = mock_session_class.call_args.kwargs
        sampling_caps = call_kwargs.get("sampling_capabilities")
        assert sampling_caps is not None
        assert isinstance(sampling_caps, types.SamplingCapability)
        assert sampling_caps.tools is not None
        assert isinstance(sampling_caps.tools, types.SamplingToolsCapability)


async def test_connect_no_sampling_capabilities_without_client():
    """Test connect() does not pass sampling_capabilities when no client is set."""
    tool = MCPStdioTool(name="test", command="test-command", load_tools=False, load_prompts=False)
    # No client set

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session._request_id = 1

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = session_cm

        await tool.connect()

        call_kwargs = mock_session_class.call_args.kwargs
        assert call_kwargs.get("sampling_capabilities") is None


# Test error handling in connect() method


async def test_connect_session_creation_failure():
    """Test connect() raises ToolException when ClientSession creation fails."""
    tool = MCPStdioTool(name="test", command="test-command")

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())  # (read_stream, write_stream)
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock ClientSession to raise an exception
    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.side_effect = RuntimeError("Session creation failed")

        with pytest.raises(ToolException) as exc_info:
            await tool.connect()

        assert "Failed to create MCP session" in str(exc_info.value)
        assert "Session creation failed" in str(exc_info.value)  # exception text is now part of the message
        assert "Session creation failed" in str(exc_info.value.__cause__)


async def test_connect_initialization_failure_http_no_command():
    """Test connect() when session.initialize() fails for HTTP tool (no command attribute)."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock successful session creation but failed initialization
    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=ConnectionError("Server not ready"))

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException) as exc_info:
            await tool.connect()

        # Should use generic error message since HTTP tool doesn't have command
        assert "MCP server failed to initialize" in str(exc_info.value)
        assert "Server not ready" in str(exc_info.value)


async def test_connect_cleanup_on_transport_failure():
    """Test that _exit_stack.aclose() is called when transport creation fails."""
    tool = MCPStdioTool(name="test", command="test-command")

    # Mock _exit_stack.aclose to verify it's called
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock get_mcp_client to raise an exception
    tool.get_mcp_client = Mock(side_effect=RuntimeError("Transport failed"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolException):
        await tool.connect()

    # Verify cleanup was called
    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_connect_cleanup_on_transport_failure_http_uses_generic_message():
    """Test HTTP transport failures use the generic connection message when no command exists."""
    tool = MCPStreamableHTTPTool(name="test", url="https://example.com/mcp")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    tool.get_mcp_client = Mock(side_effect=RuntimeError("Transport failed"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolException, match="Failed to connect to MCP server: Transport failed"):
        await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_connect_cleanup_on_initialization_failure():
    """Test that _exit_stack.aclose() is called when initialization fails."""
    tool = MCPStdioTool(name="test", command="test-command")

    # Mock _exit_stack.aclose to verify it's called
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock successful session creation but failed initialization
    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=RuntimeError("Init failed"))

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException):
            await tool.connect()

        # Verify cleanup was called
        tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_connect_cancelled_error_during_transport_creation_raises_tool_exception():
    """Test that CancelledError from transport creation is wrapped in ToolException."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    tool.get_mcp_client = Mock(side_effect=asyncio.CancelledError("cancel scope"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolException, match="Failed to connect to MCP server"):
        await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_connect_cancelled_error_during_transport_creation_stdio_raises_tool_exception():
    """Test that CancelledError from transport creation uses the command-specific message for MCPStdioTool."""
    tool = MCPStdioTool(name="test", command="my-server")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    tool.get_mcp_client = Mock(side_effect=asyncio.CancelledError("cancel scope"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolException, match="Failed to start MCP server 'my-server'"):
        await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_connect_cancelled_error_during_session_creation_raises_tool_exception():
    """Test that CancelledError from session creation is wrapped in ToolException."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(side_effect=asyncio.CancelledError("cancel scope"))
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException, match="Failed to create MCP session"):
            await tool.connect()


async def test_connect_cancelled_error_during_initialize_raises_tool_exception():
    """Test that CancelledError from session.initialize() is wrapped in ToolException.

    This is the primary regression test for the bug: when an MCP server is unreachable,
    the MCP library raises asyncio.CancelledError internally, which previously escaped
    all except Exception handlers and could not be caught by user code.
    """
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=asyncio.CancelledError("Cancelled via cancel scope"))

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException, match="MCP server failed to initialize"):
            await tool.connect()


async def test_connect_cancelled_error_during_initialize_stdio_raises_tool_exception():
    """Test that CancelledError from session.initialize() uses the command-specific message for MCPStdioTool."""
    tool = MCPStdioTool(name="test", command="my-server", args=["--port", "8080"])

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=asyncio.CancelledError("Cancelled via cancel scope"))

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException, match="MCP server 'my-server --port 8080' failed to initialize"):
            await tool.connect()


@pytest.mark.skipif(sys.version_info < (3, 11), reason="task.cancelling() requires Python >= 3.11")
async def test_connect_genuine_cancellation_during_transport_creation_propagates():
    """Test that genuine task cancellation (task.cancelling() > 0) propagates as CancelledError."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_cancelled_task = Mock()
    mock_cancelled_task.cancelling.return_value = 1

    with patch("asyncio.current_task", return_value=mock_cancelled_task):
        tool.get_mcp_client = Mock(side_effect=asyncio.CancelledError("task cancelled"))  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
        with pytest.raises(asyncio.CancelledError):
            await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="task.cancelling() requires Python >= 3.11")
async def test_connect_genuine_cancellation_during_initialize_propagates():
    """Test that genuine task cancellation during initialize() propagates as CancelledError."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=asyncio.CancelledError("task cancelled"))

    mock_cancelled_task = Mock()
    mock_cancelled_task.cancelling.return_value = 1

    with (
        patch("asyncio.current_task", return_value=mock_cancelled_task),
        patch("mcp.client.session.ClientSession") as mock_session_class,
    ):
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(asyncio.CancelledError):
            await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="task.cancelling() requires Python >= 3.11")
async def test_connect_genuine_cancellation_during_session_creation_propagates():
    """Test that genuine task cancellation during session creation propagates as CancelledError."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    mock_cancelled_task = Mock()
    mock_cancelled_task.cancelling.return_value = 1

    with (
        patch("asyncio.current_task", return_value=mock_cancelled_task),
        patch("mcp.client.session.ClientSession") as mock_session_class,
    ):
        mock_session_class.return_value.__aenter__ = AsyncMock(side_effect=asyncio.CancelledError("task cancelled"))
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(asyncio.CancelledError):
            await tool.connect()

    tool._exit_stack.aclose.assert_called_once()  # ty: ignore[unresolved-attribute]


async def test_aenter_cancelled_error_during_connect_is_catchable_as_exception():
    """Test that CancelledError during __aenter__ is catchable as Exception.

    Verifies the end-to-end fix: async with MCPStreamableHTTPTool(...) raises an
    exception that can be caught by a normal `except Exception` block.
    """
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=asyncio.CancelledError("Cancelled via cancel scope"))

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        caught = None
        try:
            async with tool:
                pass
        except Exception as e:
            caught = e

        assert caught is not None, "Expected an exception to be caught by except Exception"
        assert isinstance(caught, ToolException)


# Tests for _should_propagate_cancelled_error helper


def test_should_propagate_cancelled_error_returns_false_for_non_cancelled_error():
    assert _should_propagate_cancelled_error(RuntimeError("boom")) is False


def test_should_propagate_cancelled_error_returns_false_when_no_current_task():
    with patch("asyncio.current_task", return_value=None):
        assert _should_propagate_cancelled_error(asyncio.CancelledError()) is False


@pytest.mark.skipif(sys.version_info < (3, 11), reason="task.cancelling() requires Python >= 3.11")
def test_should_propagate_cancelled_error_returns_true_when_task_is_cancelling():
    mock_task = Mock()
    mock_task.cancelling.return_value = 1
    with patch("asyncio.current_task", return_value=mock_task):
        assert _should_propagate_cancelled_error(asyncio.CancelledError()) is True


@pytest.mark.skipif(sys.version_info < (3, 11), reason="task.cancelling() requires Python >= 3.11")
def test_should_propagate_cancelled_error_returns_false_when_task_not_cancelling():
    mock_task = Mock()
    mock_task.cancelling.return_value = 0
    with patch("asyncio.current_task", return_value=mock_task):
        assert _should_propagate_cancelled_error(asyncio.CancelledError()) is False


async def test_connect_cancelled_error_during_session_creation_includes_exception_in_message():
    """Test that CancelledError from session creation includes exception details in ToolException message."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(
            side_effect=asyncio.CancelledError("cancel scope detail")
        )
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException) as exc_info:
            await tool.connect()

        assert "Failed to create MCP session" in str(exc_info.value)
        assert "cancel scope detail" in str(exc_info.value)


async def test_connect_cancelled_error_during_session_creation_logs_with_exc_info():
    """Test that CancelledError from session creation is logged with exc_info=True."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(side_effect=asyncio.CancelledError("cancel scope"))
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        from agent_framework._mcp import logger as mcp_logger

        with patch.object(mcp_logger, "debug") as mock_debug:
            with pytest.raises(ToolException):
                await tool.connect()

            # Verify logger.debug was called with exc_info=True (not an exception instance)
            debug_calls = mock_debug.call_args_list
            cancel_calls = [c for c in debug_calls if "Failed to create MCP session" in str(c)]
            assert cancel_calls, "Expected a debug log for the cancelled session creation"
            _, kwargs = cancel_calls[0]
            assert kwargs.get("exc_info") is True


def test_mcp_stdio_tool_get_mcp_client_with_env_and_kwargs():
    """Test MCPStdioTool.get_mcp_client() with environment variables and client kwargs."""
    env_vars = {"PATH": "/usr/bin", "DEBUG": "1"}
    tool = MCPStdioTool(
        name="test",
        command="test-command",
        encoding="utf-16",
        env=env_vars,
        custom_param="value1",
        another_param=42,
    )

    with patch("mcp.client.stdio.stdio_client"), patch("mcp.client.stdio.StdioServerParameters") as mock_params:
        tool.get_mcp_client()

        # Verify all parameters including custom kwargs were passed
        mock_params.assert_called_once_with(
            command="test-command",
            args=[],
            encoding="utf-16",
            env=env_vars,
            custom_param="value1",
            another_param=42,
        )


def test_mcp_streamable_http_tool_get_mcp_client_all_params():
    """Test MCPStreamableHTTPTool.get_mcp_client() with all parameters."""
    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com",
        terminate_on_close=True,
    )

    with patch("mcp.client.streamable_http.streamable_http_client") as mock_http_client:
        tool.get_mcp_client()

        # Verify streamable_http_client was called with None for http_client
        # (since we didn't provide one, the API will create its own)
        mock_http_client.assert_called_once_with(
            url="http://example.com",
            http_client=None,
            terminate_on_close=True,
        )


def test_mcp_websocket_tool_get_mcp_client_with_kwargs():
    """Test MCPWebsocketTool.get_mcp_client() with client kwargs."""
    tool = MCPWebsocketTool(
        name="test",
        url="wss://example.com",
        max_size=1024,
        ping_interval=30,
        compression="deflate",
    )

    with patch("mcp.client.websocket.websocket_client") as mock_ws_client:
        tool.get_mcp_client()

        # Verify all kwargs were passed
        mock_ws_client.assert_called_once_with(
            url="wss://example.com",
            max_size=1024,
            ping_interval=30,
            compression="deflate",
        )


async def test_mcp_tool_deduplication():
    """Test that MCP tools are not duplicated in MCPTool"""
    from agent_framework._mcp import MCPTool
    from agent_framework._tools import FunctionTool

    # Create MCPStreamableHTTPTool instance
    tool = MCPTool(name="test_mcp_tool")  # type: ignore[abstract]

    # Manually set up functions list
    tool._functions = []

    # Add initial functions
    func1 = FunctionTool(
        func=lambda x: f"Result: {x}",
        name="analyze_content",
        description="Analyzes content",
    )
    func2 = FunctionTool(
        func=lambda x: f"Extract: {x}",
        name="extract_info",
        description="Extracts information",
    )

    tool._functions.append(func1)
    tool._functions.append(func2)

    # Verify initial state
    assert len(tool._functions) == 2
    assert len({f.name for f in tool._functions}) == 2

    # Simulate deduplication logic
    existing_names = {func.name for func in tool._functions}

    # Attempt to add duplicates
    test_tools = [
        ("analyze_content", "Duplicate"),
        ("extract_info", "Duplicate"),
        ("new_function", "New"),
    ]

    added_count = 0
    for tool_name, description in test_tools:
        if tool_name in existing_names:
            continue  # Skip duplicates

        new_func = FunctionTool(func=lambda x: f"Process: {x}", name=tool_name, description=description)
        tool._functions.append(new_func)
        existing_names.add(tool_name)
        added_count += 1

    # Verify results
    final_names = [f.name for f in tool._functions]
    unique_names = set(final_names)

    # Should have exactly 3 functions (2 original + 1 new)
    assert len(tool._functions) == 3
    assert len(unique_names) == 3
    assert len(final_names) == len(unique_names)  # No duplicates
    assert added_count == 1  # Only 1 new function added


async def test_load_tools_prevents_multiple_calls():
    """Test that connect() prevents calling load_tools() multiple times"""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Verify initial state
    assert tool._tools_loaded is False

    # Mock the session and list_tools
    mock_session = AsyncMock()
    mock_tool_list = MagicMock()
    mock_tool_list.tools = []
    mock_tool_list.nextCursor = None  # No pagination
    mock_session.list_tools = AsyncMock(return_value=mock_tool_list)
    mock_session.initialize = AsyncMock()

    tool.session = mock_session
    tool.load_tools_flag = True
    tool.load_prompts_flag = False

    # Simulate connect() behavior
    if tool.load_tools_flag and not tool._tools_loaded:
        await tool.load_tools()
        tool._tools_loaded = True

    assert tool._tools_loaded is True
    assert mock_session.list_tools.call_count == 1

    # Second call to connect should be skipped
    if tool.load_tools_flag and not tool._tools_loaded:
        await tool.load_tools()
        tool._tools_loaded = True

    assert mock_session.list_tools.call_count == 1  # Still 1, not incremented


async def test_load_prompts_prevents_multiple_calls():
    """Test that connect() prevents calling load_prompts() multiple times"""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Verify initial state
    assert tool._prompts_loaded is False

    # Mock the session and list_prompts
    mock_session = AsyncMock()
    mock_prompt_list = MagicMock()
    mock_prompt_list.prompts = []
    mock_prompt_list.nextCursor = None  # No pagination
    mock_session.list_prompts = AsyncMock(return_value=mock_prompt_list)

    tool.session = mock_session
    tool.load_tools_flag = False
    tool.load_prompts_flag = True

    # Simulate connect() behavior
    if tool.load_prompts_flag and not tool._prompts_loaded:
        await tool.load_prompts()
        tool._prompts_loaded = True

    assert tool._prompts_loaded is True
    assert mock_session.list_prompts.call_count == 1

    # Second call to connect should be skipped
    if tool.load_prompts_flag and not tool._prompts_loaded:
        await tool.load_prompts()
        tool._prompts_loaded = True

    assert mock_session.list_prompts.call_count == 1  # Still 1, not incremented


async def test_mcp_streamable_http_tool_httpx_client_cleanup():
    """Test that MCPStreamableHTTPTool properly passes through httpx clients."""
    from unittest.mock import AsyncMock, Mock, patch

    from agent_framework import MCPStreamableHTTPTool

    # Mock the streamable_http_client to avoid actual connections
    with (
        patch("mcp.client.streamable_http.streamable_http_client") as mock_client,
        patch("mcp.client.session.ClientSession") as mock_session_class,
    ):
        # Setup mock context manager for streamable_http_client
        mock_transport = (Mock(), Mock())
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_context_manager

        # Setup mock session
        mock_session = Mock()
        mock_session.initialize = AsyncMock()
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        # Test 1: Tool without provided client (passes None to streamable_http_client)
        tool1 = MCPStreamableHTTPTool(
            name="test",
            url="http://localhost:8081/mcp",
            load_tools=False,
            load_prompts=False,
            terminate_on_close=False,
        )
        await tool1.connect()
        # When no client is provided, _httpx_client should be None
        assert tool1._httpx_client is None, "httpx client should be None when not provided"

        # Test 2: Tool with user-provided client
        user_client = Mock()
        tool2 = MCPStreamableHTTPTool(
            name="test",
            url="http://localhost:8081/mcp",
            load_tools=False,
            load_prompts=False,
            terminate_on_close=False,
            http_client=user_client,
        )
        await tool2.connect()

        # Verify the user-provided client was stored
        assert tool2._httpx_client is user_client, "User-provided client should be stored"

        # Verify streamable_http_client was called with the user's client
        # Get the last call (should be from tool2.connect())
        call_args = mock_client.call_args
        assert call_args.kwargs["http_client"] is user_client, "User's client should be passed through"


async def test_load_tools_with_pagination():
    """Test that load_tools handles pagination correctly."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    # Create paginated responses
    page1 = MagicMock()
    page1.tools = [
        types.Tool(
            name="tool_1",
            description="First tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
        types.Tool(
            name="tool_2",
            description="Second tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
    ]
    page1.nextCursor = "cursor_page2"

    page2 = MagicMock()
    page2.tools = [
        types.Tool(
            name="tool_3",
            description="Third tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
    ]
    page2.nextCursor = "cursor_page3"

    page3 = MagicMock()
    page3.tools = [
        types.Tool(
            name="tool_4",
            description="Fourth tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
    ]
    page3.nextCursor = None  # No more pages

    # Mock list_tools to return different pages based on params
    async def mock_list_tools(params=None):
        if params is None:
            return page1
        if params.cursor == "cursor_page2":
            return page2
        if params.cursor == "cursor_page3":
            return page3
        raise ValueError("Unexpected cursor value")

    mock_session.list_tools = AsyncMock(side_effect=mock_list_tools)

    # Load tools with pagination
    await tool.load_tools()

    # Verify all pages were fetched
    assert mock_session.list_tools.call_count == 3
    assert len(tool._functions) == 4
    assert [f.name for f in tool._functions] == ["tool_1", "tool_2", "tool_3", "tool_4"]


async def test_load_tools_adds_properties_to_zero_arg_tool_schema():
    """Test that load_tools normalizes inputSchema for zero-argument MCP tools.

    Some MCP servers (e.g. matlab-mcp-core-server) declare zero-argument tools
    with inputSchema={"type": "object"} and no "properties" key.  OpenAI's API
    requires "properties" to be present on object schemas, so load_tools must
    inject an empty "properties" dict when it is missing.
    """
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    original_zero_arg_schema = {"type": "object"}
    original_string_schema = {"type": "string"}
    original_empty_schema: dict[str, object] = {}

    page = MagicMock()
    page.tools = [
        types.Tool(
            name="zero_arg_tool",
            description="A tool with no parameters",
            inputSchema=original_zero_arg_schema,
        ),
        types.Tool(
            name="normal_tool",
            description="A tool with parameters",
            inputSchema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        ),
        types.Tool(
            name="string_schema_tool",
            description="A tool with a non-object schema",
            inputSchema=original_string_schema,
        ),
        types.Tool(
            name="empty_schema_tool",
            description="A tool with an empty schema",
            inputSchema=original_empty_schema,
        ),
    ]

    # Simulate a non-conforming MCP server that sends inputSchema=None.
    # types.Tool requires inputSchema to be a dict, so we use a MagicMock.
    none_schema_tool = MagicMock()
    none_schema_tool.name = "none_schema_tool"
    none_schema_tool.description = "A tool with None inputSchema"
    none_schema_tool.inputSchema = None
    none_schema_tool.meta = None
    page.tools.append(none_schema_tool)
    page.nextCursor = None

    mock_session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert len(tool._functions) == 5

    funcs_by_name = {f.name: f for f in tool._functions}

    # Zero-arg tool must have "properties" injected
    zero_params = funcs_by_name["zero_arg_tool"].parameters()
    assert "properties" in zero_params
    assert zero_params["properties"] == {}
    assert zero_params["type"] == "object"

    # Normal tool must retain its existing properties
    normal_params = funcs_by_name["normal_tool"].parameters()
    assert "properties" in normal_params
    assert "x" in normal_params["properties"]
    assert normal_params["required"] == ["x"]

    # Non-object schema must NOT have "properties" injected
    string_params = funcs_by_name["string_schema_tool"].parameters()
    assert "properties" not in string_params
    assert string_params["type"] == "string"

    # Empty schema (no "type" key) must NOT have "properties" injected
    empty_params = funcs_by_name["empty_schema_tool"].parameters()
    assert "properties" not in empty_params

    # None inputSchema must produce an empty dict (guard against non-conforming servers)
    none_params = funcs_by_name["none_schema_tool"].parameters()
    assert none_params == {}

    # Original inputSchema dicts must not be mutated
    assert "properties" not in original_zero_arg_schema
    assert "properties" not in original_string_schema
    assert "properties" not in original_empty_schema


async def test_load_prompts_with_pagination():
    """Test that load_prompts handles pagination correctly."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    # Create paginated responses
    page1 = MagicMock()
    page1.prompts = [
        types.Prompt(
            name="prompt_1",
            description="First prompt",
            arguments=[types.PromptArgument(name="arg1", description="Arg 1", required=True)],
        ),
        types.Prompt(
            name="prompt_2",
            description="Second prompt",
            arguments=[types.PromptArgument(name="arg2", description="Arg 2", required=True)],
        ),
    ]
    page1.nextCursor = "cursor_page2"

    page2 = MagicMock()
    page2.prompts = [
        types.Prompt(
            name="prompt_3",
            description="Third prompt",
            arguments=[types.PromptArgument(name="arg3", description="Arg 3", required=False)],
        ),
    ]
    page2.nextCursor = None  # No more pages

    # Mock list_prompts to return different pages based on params
    async def mock_list_prompts(params=None):
        if params is None:
            return page1
        if params.cursor == "cursor_page2":
            return page2
        raise ValueError("Unexpected cursor value")

    mock_session.list_prompts = AsyncMock(side_effect=mock_list_prompts)

    # Load prompts with pagination
    await tool.load_prompts()

    # Verify all pages were fetched
    assert mock_session.list_prompts.call_count == 2
    assert len(tool._functions) == 3
    assert [f.name for f in tool._functions] == ["prompt_1", "prompt_2", "prompt_3"]


async def test_load_tools_pagination_with_duplicates():
    """Test that load_tools prevents duplicates across paginated results."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    # Create paginated responses with duplicate tool names
    page1 = MagicMock()
    page1.tools = [
        types.Tool(
            name="tool_1",
            description="First tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
        types.Tool(
            name="tool_2",
            description="Second tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
    ]
    page1.nextCursor = "cursor_page2"

    page2 = MagicMock()
    page2.tools = [
        types.Tool(
            name="tool_1",  # Duplicate from page1
            description="Duplicate tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
        types.Tool(
            name="tool_3",
            description="Third tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        ),
    ]
    page2.nextCursor = None

    # Mock list_tools to return different pages
    async def mock_list_tools(params=None):
        if params is None:
            return page1
        if params.cursor == "cursor_page2":
            return page2
        raise ValueError("Unexpected cursor value")

    mock_session.list_tools = AsyncMock(side_effect=mock_list_tools)

    # Load tools with pagination
    await tool.load_tools()

    # Verify duplicates were skipped
    assert mock_session.list_tools.call_count == 2
    assert len(tool._functions) == 3
    assert [f.name for f in tool._functions] == ["tool_1", "tool_2", "tool_3"]


async def test_load_prompts_pagination_with_duplicates():
    """Test that load_prompts prevents duplicates across paginated results."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    # Create paginated responses with duplicate prompt names
    page1 = MagicMock()
    page1.prompts = [
        types.Prompt(
            name="prompt_1",
            description="First prompt",
            arguments=[types.PromptArgument(name="arg1", description="Arg 1", required=True)],
        ),
    ]
    page1.nextCursor = "cursor_page2"

    page2 = MagicMock()
    page2.prompts = [
        types.Prompt(
            name="prompt_1",  # Duplicate from page1
            description="Duplicate prompt",
            arguments=[types.PromptArgument(name="arg2", description="Arg 2", required=False)],
        ),
        types.Prompt(
            name="prompt_2",
            description="Second prompt",
            arguments=[types.PromptArgument(name="arg3", description="Arg 3", required=True)],
        ),
    ]
    page2.nextCursor = None

    # Mock list_prompts to return different pages
    async def mock_list_prompts(params=None):
        if params is None:
            return page1
        if params.cursor == "cursor_page2":
            return page2
        raise ValueError("Unexpected cursor value")

    mock_session.list_prompts = AsyncMock(side_effect=mock_list_prompts)

    # Load prompts with pagination
    await tool.load_prompts()

    # Verify duplicates were skipped
    assert mock_session.list_prompts.call_count == 2
    assert len(tool._functions) == 2
    assert [f.name for f in tool._functions] == ["prompt_1", "prompt_2"]


async def test_load_tools_concurrent_reload_does_not_duplicate_tools_and_preserves_meta():
    """Concurrent tool reloads should not duplicate functions or lose tools/list metadata."""
    tool = MCPTool(name="test_tool")  # type: ignore[abstract]
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="tool_1",
            description="First tool",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
            _meta={"echo": "tool_1"},
        ),
    ]
    page.nextCursor = None

    async def mock_list_tools(params: Any = None) -> Any:
        assert params is None
        await asyncio.sleep(0)
        return page

    mock_session.list_tools = AsyncMock(side_effect=mock_list_tools)

    await asyncio.wait_for(asyncio.gather(tool.load_tools(), tool.load_tools()), timeout=1)

    assert mock_session.list_tools.call_count == 2
    assert [f.name for f in tool._functions] == ["tool_1"]
    assert tool._tool_call_meta_by_name == {"tool_1": {"echo": "tool_1"}}


async def test_load_prompts_concurrent_reload_does_not_duplicate_prompts():
    """Concurrent prompt reloads should not duplicate functions."""
    tool = MCPTool(name="test_tool")  # type: ignore[abstract]
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    page = Mock()
    page.prompts = [
        types.Prompt(
            name="prompt_1",
            description="First prompt",
            arguments=[types.PromptArgument(name="arg1", description="Arg 1", required=True)],
        ),
    ]
    page.nextCursor = None

    async def mock_list_prompts(params: Any = None) -> Any:
        assert params is None
        await asyncio.sleep(0)
        return page

    mock_session.list_prompts = AsyncMock(side_effect=mock_list_prompts)

    await asyncio.wait_for(asyncio.gather(tool.load_prompts(), tool.load_prompts()), timeout=1)

    assert mock_session.list_prompts.call_count == 2
    assert [f.name for f in tool._functions] == ["prompt_1"]


async def test_load_tools_pagination_exception_handling():
    """Test that load_tools handles exceptions during pagination gracefully."""
    from unittest.mock import AsyncMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    # Mock list_tools to raise an exception on first call
    mock_session.list_tools = AsyncMock(side_effect=RuntimeError("Connection error"))

    # Load tools should raise the exception (not handled gracefully)
    with pytest.raises(RuntimeError, match="Connection error"):
        await tool.load_tools()

    # Verify exception was raised on first call
    assert mock_session.list_tools.call_count == 1
    assert len(tool._functions) == 0


async def test_load_prompts_pagination_exception_handling():
    """Test that load_prompts handles exceptions during pagination gracefully."""
    from unittest.mock import AsyncMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    # Mock list_prompts to raise an exception on first call
    mock_session.list_prompts = AsyncMock(side_effect=RuntimeError("Connection error"))

    # Load prompts should raise the exception (not handled gracefully)
    with pytest.raises(RuntimeError, match="Connection error"):
        await tool.load_prompts()

    # Verify exception was raised on first call
    assert mock_session.list_prompts.call_count == 1
    assert len(tool._functions) == 0


async def test_load_tools_empty_pagination():
    """Test that load_tools handles empty paginated results."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_tools_flag = True

    # Create empty response
    page1 = MagicMock()
    page1.tools = []
    page1.nextCursor = None

    mock_session.list_tools = AsyncMock(return_value=page1)

    # Load tools
    await tool.load_tools()

    # Verify
    assert mock_session.list_tools.call_count == 1
    assert len(tool._functions) == 0


async def test_load_prompts_empty_pagination():
    """Test that load_prompts handles empty paginated results."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")  # type: ignore[abstract]

    # Mock the session
    mock_session = AsyncMock()
    tool.session = mock_session
    tool.load_prompts_flag = True

    # Create empty response
    page1 = MagicMock()
    page1.prompts = []
    page1.nextCursor = None

    mock_session.list_prompts = AsyncMock(return_value=page1)

    # Load prompts
    await tool.load_prompts()

    # Verify
    assert mock_session.list_prompts.call_count == 1
    assert len(tool._functions) == 0


async def test_mcp_tool_connection_properly_invalidated_after_closed_resource_error():
    """Test that verifies reconnection on ClosedResourceError for issue #2884.

    This test verifies the fix for issue #2884: the tool tries operations optimistically
    and only reconnects when ClosedResourceError is encountered, avoiding extra latency.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from anyio.streams.memory import ClosedResourceError

    from agent_framework._mcp import MCPStdioTool
    from agent_framework.exceptions import ToolExecutionException

    # Create a mock MCP tool
    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=True,
    )

    # Mock the session
    mock_session = MagicMock()
    mock_session._request_id = 1
    mock_session.call_tool = AsyncMock()

    # Mock _exit_stack.aclose to track cleanup calls
    original_exit_stack = tool._exit_stack
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock connect() to avoid trying to start actual process
    with patch.object(tool, "connect", new_callable=AsyncMock) as mock_connect:

        async def restore_session(*, reset=False):
            if reset:
                await original_exit_stack.aclose()
            tool.session = mock_session
            tool.is_connected = True
            tool._tools_loaded = True

        mock_connect.side_effect = restore_session

        # Simulate initial connection
        tool.session = mock_session
        tool.is_connected = True
        tool._tools_loaded = True

        # First call should work - connection is valid
        mock_session.call_tool.return_value = types.CallToolResult(content=[])
        result = await tool.call_tool("test_tool", arg1="value1")
        assert result is not None

        # Test Case 1: Connection closed unexpectedly, should reconnect and retry
        # Simulate ClosedResourceError on first call, then succeed
        call_count = 0

        async def call_tool_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClosedResourceError
            return types.CallToolResult(content=[])

        mock_session.call_tool = call_tool_with_error

        # This call should trigger reconnection after ClosedResourceError
        result = await tool.call_tool("test_tool", arg1="value2")
        assert result is not None
        # Verify reconnect was attempted with reset=True
        assert mock_connect.call_count >= 1
        mock_connect.assert_called_with(reset=True)
        # Verify _exit_stack.aclose was called during reconnection
        original_exit_stack.aclose.assert_called()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        # Test Case 2: Reconnection failure
        # Reset counters
        call_count = 0
        mock_connect.reset_mock()
        original_exit_stack.aclose.reset_mock()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        # Make call_tool always raise ClosedResourceError
        async def always_fail(*args, **kwargs):
            raise ClosedResourceError

        mock_session.call_tool = always_fail

        # Change mock_connect to simulate failed reconnection
        mock_connect.side_effect = Exception("Failed to reconnect")

        # This should raise ToolExecutionException when reconnection fails
        with pytest.raises(ToolExecutionException) as exc_info:
            await tool.call_tool("test_tool", arg1="value3")

        # Verify reconnection was attempted
        assert mock_connect.call_count >= 1
        # Verify error message indicates reconnection failure
        assert "failed to reconnect" in str(exc_info.value).lower()


async def test_mcp_tool_get_prompt_reconnection_on_closed_resource_error():
    """Test that get_prompt also reconnects on ClosedResourceError.

    This verifies that the fix for issue #2884 applies to get_prompt as well,
    and that _exit_stack.aclose() is properly called during reconnection.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from anyio.streams.memory import ClosedResourceError

    from agent_framework._mcp import MCPStdioTool
    from agent_framework.exceptions import ToolExecutionException

    # Create a mock MCP tool
    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_prompts=True,
    )

    # Mock the session
    mock_session = MagicMock()
    mock_session._request_id = 1
    mock_session.get_prompt = AsyncMock()

    # Mock _exit_stack.aclose to track cleanup calls
    original_exit_stack = tool._exit_stack
    tool._exit_stack.aclose = AsyncMock()  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    # Mock connect() to avoid trying to start actual process
    with patch.object(tool, "connect", new_callable=AsyncMock) as mock_connect:

        async def restore_session(*, reset=False):
            if reset:
                await original_exit_stack.aclose()
            tool.session = mock_session
            tool.is_connected = True
            tool._prompts_loaded = True

        mock_connect.side_effect = restore_session

        # Simulate initial connection
        tool.session = mock_session
        tool.is_connected = True
        tool._prompts_loaded = True

        # First call should work - connection is valid
        mock_session.get_prompt.return_value = MagicMock(messages=[])
        result = await tool.get_prompt("test_prompt", arg1="value1")
        assert result is not None

        # Test Case 1: Connection closed unexpectedly, should reconnect and retry
        # Simulate ClosedResourceError on first call, then succeed
        call_count = 0

        async def get_prompt_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClosedResourceError
            return MagicMock(messages=[])

        mock_session.get_prompt = get_prompt_with_error

        # This call should trigger reconnection after ClosedResourceError
        result = await tool.get_prompt("test_prompt", arg1="value2")
        assert result is not None
        # Verify reconnect was attempted with reset=True
        assert mock_connect.call_count >= 1
        mock_connect.assert_called_with(reset=True)
        # Verify _exit_stack.aclose was called during reconnection
        original_exit_stack.aclose.assert_called()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        # Test Case 2: Reconnection failure
        # Reset counters
        call_count = 0
        mock_connect.reset_mock()
        original_exit_stack.aclose.reset_mock()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        # Make get_prompt always raise ClosedResourceError
        async def always_fail(*args, **kwargs):
            raise ClosedResourceError

        mock_session.get_prompt = always_fail

        # Change mock_connect to simulate failed reconnection
        mock_connect.side_effect = Exception("Failed to reconnect")

        # This should raise ToolExecutionException when reconnection fails
        with pytest.raises(ToolExecutionException) as exc_info:
            await tool.get_prompt("test_prompt", arg1="value3")

        # Verify reconnection was attempted
        assert mock_connect.call_count >= 1
        # Verify error message indicates reconnection failure
        assert "failed to reconnect" in str(exc_info.value).lower()


async def test_mcp_tool_call_tool_requires_loaded_tools() -> None:
    tool = MCPTool(name="test_tool", load_tools=False)  # type: ignore[abstract]

    with pytest.raises(ToolExecutionException, match="Tools are not loaded"):
        await tool.call_tool("remote_tool")


async def test_mcp_tool_get_prompt_requires_loaded_prompts() -> None:
    tool = MCPTool(name="test_tool", load_prompts=False)  # type: ignore[abstract]

    with pytest.raises(ToolExecutionException, match="Prompts are not loaded"):
        await tool.get_prompt("remote_prompt")


async def test_mcp_tool_call_tool_raises_after_reconnection_still_fails() -> None:
    from anyio.streams.memory import ClosedResourceError

    tool = MCPTool(name="test_tool", load_tools=True)  # type: ignore[abstract]
    tool.session = Mock(call_tool=AsyncMock(side_effect=[ClosedResourceError(), ClosedResourceError()]))

    with (
        patch.object(tool, "connect", AsyncMock()) as mock_connect,
        patch.object(logger, "error") as mock_error,
        pytest.raises(ToolExecutionException, match="connection lost"),
    ):
        await tool.call_tool("remote_tool")

    mock_connect.assert_awaited_once_with(reset=True)
    mock_error.assert_called_once()


async def test_mcp_tool_get_prompt_raises_after_reconnection_still_fails() -> None:
    from anyio.streams.memory import ClosedResourceError

    tool = MCPTool(name="test_tool", load_prompts=True)  # type: ignore[abstract]
    tool.session = Mock(get_prompt=AsyncMock(side_effect=[ClosedResourceError(), ClosedResourceError()]))

    with (
        patch.object(tool, "connect", AsyncMock()) as mock_connect,
        patch.object(logger, "error") as mock_error,
        pytest.raises(ToolExecutionException, match="connection lost"),
    ):
        await tool.get_prompt("remote_prompt")

    mock_connect.assert_awaited_once_with(reset=True)
    mock_error.assert_called_once()


async def test_mcp_tool_wraps_unexpected_call_tool_and_get_prompt_errors() -> None:
    tool = MCPTool(name="test_tool", load_tools=True, load_prompts=True)  # type: ignore[abstract]
    tool.session = Mock()
    tool.session.call_tool = AsyncMock(side_effect=RuntimeError("tool boom"))
    tool.session.get_prompt = AsyncMock(side_effect=RuntimeError("prompt boom"))

    with pytest.raises(ToolExecutionException, match="Failed to call tool 'remote_tool'"):
        await tool.call_tool("remote_tool")

    with pytest.raises(ToolExecutionException, match="Failed to call prompt 'remote_prompt'"):
        await tool.get_prompt("remote_prompt")


async def test_mcp_tool_aenter_wraps_unexpected_errors_and_closes() -> None:
    tool = MCPStdioTool(name="test_tool", command="python")

    with (
        patch.object(tool, "connect", AsyncMock(side_effect=RuntimeError("boom"))),
        patch.object(tool, "close", AsyncMock()) as mock_close,
        pytest.raises(ToolExecutionException, match="Failed to enter context manager"),
    ):
        await tool.__aenter__()

    mock_close.assert_awaited_once()


async def test_mcp_tool_close_cleans_up_in_original_task(caplog):
    """Closing an MCP tool from another task should still unwind contexts in the owner task."""
    import asyncio

    class TaskBoundTransportContext:
        def __init__(self) -> None:
            self.enter_task = None
            self.exit_task = None
            self.closed_cleanly = False

        async def __aenter__(self):
            self.enter_task = asyncio.current_task()  # type: ignore[assignment]
            return (Mock(), Mock())

        async def __aexit__(self, exc_type, exc, tb):
            self.exit_task = asyncio.current_task()  # type: ignore[assignment]
            if self.exit_task is not self.enter_task:
                raise RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
            self.closed_cleanly = True
            return

    tool = MCPStreamableHTTPTool(
        name="test_server",
        url="https://example.com/mcp",
        load_tools=False,
        load_prompts=False,
    )

    transport_context = TaskBoundTransportContext()
    mock_session = Mock()
    mock_session._request_id = 1
    mock_session.initialize = AsyncMock()

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(tool, "get_mcp_client", return_value=transport_context),
        patch("mcp.client.session.ClientSession", return_value=mock_session_context),
    ):
        await asyncio.create_task(tool.connect())

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=logger.name):
            await tool.close()

    assert transport_context.closed_cleanly is True
    assert transport_context.exit_task is transport_context.enter_task
    assert not any("cancel scope" in record.getMessage().lower() for record in caplog.records)


async def test_mcp_tool_connect_reset_cleans_up_in_original_task(caplog):
    """Resetting an MCP tool from another task should unwind and reconnect on the owner task."""
    import asyncio

    class TaskBoundTransportContext:
        def __init__(self) -> None:
            self.enter_task = None
            self.exit_task = None
            self.closed_cleanly = False

        async def __aenter__(self):
            self.enter_task = asyncio.current_task()  # type: ignore[assignment]
            return (Mock(), Mock())

        async def __aexit__(self, exc_type, exc, tb):
            self.exit_task = asyncio.current_task()  # type: ignore[assignment]
            if self.exit_task is not self.enter_task:
                raise RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
            self.closed_cleanly = True
            return

    tool = MCPStreamableHTTPTool(
        name="test_server",
        url="https://example.com/mcp",
        load_tools=False,
        load_prompts=False,
    )

    transport_contexts = [TaskBoundTransportContext(), TaskBoundTransportContext()]
    sessions = []
    session_contexts = []
    for _ in range(2):
        session = Mock()
        session._request_id = 1
        session.initialize = AsyncMock()
        session.set_logging_level = AsyncMock()
        sessions.append(session)

        session_context = AsyncMock()
        session_context.__aenter__ = AsyncMock(return_value=session)
        session_context.__aexit__ = AsyncMock(return_value=None)
        session_contexts.append(session_context)

    with (
        patch.object(tool, "get_mcp_client", side_effect=transport_contexts),
        patch("mcp.client.session.ClientSession", side_effect=session_contexts),
    ):
        await tool.connect()

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=logger.name):
            await asyncio.create_task(tool.connect(reset=True))

        assert transport_contexts[0].closed_cleanly is True
        assert transport_contexts[0].exit_task is transport_contexts[0].enter_task
        assert transport_contexts[1].enter_task is transport_contexts[0].enter_task
        assert tool.session is sessions[1]
        assert tool.is_connected is True
        assert not any("cancel scope" in record.getMessage().lower() for record in caplog.records)

        await tool.close()


async def test_mcp_tool_connect_from_lifecycle_owner_bypasses_request_lock() -> None:
    """connect(reset=True) should bypass the request queue when already on the owner task."""
    import asyncio

    tool = MCPStreamableHTTPTool(
        name="test_server",
        url="https://example.com/mcp",
        load_tools=False,
        load_prompts=False,
    )

    async def connect_from_owner_task() -> None:
        tool._lifecycle_owner_task = asyncio.current_task()
        try:
            async with tool._lifecycle_request_lock:
                await tool.connect(reset=True)
        finally:
            tool._lifecycle_owner_task = None

    with patch.object(tool, "_connect_on_owner", AsyncMock()) as mock_connect_on_owner:
        await asyncio.wait_for(connect_from_owner_task(), timeout=0.1)

    mock_connect_on_owner.assert_awaited_once_with(reset=True)


async def test_mcp_tool_close_from_lifecycle_owner_bypasses_request_lock() -> None:
    """close() should bypass the request queue when already on the owner task."""
    import asyncio

    tool = MCPStreamableHTTPTool(
        name="test_server",
        url="https://example.com/mcp",
        load_tools=False,
        load_prompts=False,
    )

    async def close_from_owner_task() -> None:
        tool._lifecycle_owner_task = asyncio.current_task()
        try:
            async with tool._lifecycle_request_lock:
                await tool.close()
        finally:
            tool._lifecycle_owner_task = None

    with patch.object(tool, "_close_on_owner", AsyncMock()) as mock_close_on_owner:
        await asyncio.wait_for(close_from_owner_task(), timeout=0.1)

    mock_close_on_owner.assert_awaited_once_with()


async def test_mcp_tool_safe_close_reraises_other_runtime_errors():
    """Test that _safe_close_exit_stack re-raises RuntimeErrors that aren't cancel scope related."""
    from contextlib import AsyncExitStack

    from agent_framework._mcp import MCPStdioTool

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=True,
    )

    # Mock the exit stack to raise a different RuntimeError
    mock_exit_stack = AsyncMock(spec=AsyncExitStack)
    mock_exit_stack.aclose = AsyncMock(side_effect=RuntimeError("Some other runtime error"))
    tool._exit_stack = mock_exit_stack

    # This should re-raise the RuntimeError since it's not about cancel scopes
    with pytest.raises(RuntimeError) as exc_info:
        await tool._safe_close_exit_stack()

    assert "Some other runtime error" in str(exc_info.value)


async def test_mcp_tool_safe_close_handles_alternate_cancel_scope_error():
    """Test that _safe_close_exit_stack handles the alternate cancel scope error message.

    anyio has multiple variants of cancel scope errors:
    - "Attempted to exit cancel scope in a different task than it was entered in"
    - "Attempted to exit a cancel scope that isn't the current task's current cancel scope"
    """
    from contextlib import AsyncExitStack

    from agent_framework._mcp import MCPStdioTool

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the exit stack to raise the alternate cancel scope error
    mock_exit_stack = AsyncMock(spec=AsyncExitStack)
    mock_exit_stack.aclose = AsyncMock(
        side_effect=RuntimeError("Attempted to exit a cancel scope that isn't the current task's current cancel scope")
    )
    tool._exit_stack = mock_exit_stack

    # This should NOT raise - the error should be caught and logged
    await tool._safe_close_exit_stack()

    # Verify aclose was called
    mock_exit_stack.aclose.assert_called_once()


async def test_mcp_tool_safe_close_handles_cancelled_error():
    """Test that _safe_close_exit_stack handles asyncio.CancelledError.

    CancelledError can occur during cleanup when anyio cancel scopes are involved.
    """
    import asyncio
    from contextlib import AsyncExitStack

    from agent_framework._mcp import MCPStdioTool

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the exit stack to raise CancelledError
    mock_exit_stack = AsyncMock(spec=AsyncExitStack)
    mock_exit_stack.aclose = AsyncMock(side_effect=asyncio.CancelledError())
    tool._exit_stack = mock_exit_stack

    # This should NOT raise - the CancelledError should be caught and logged
    await tool._safe_close_exit_stack()

    # Verify aclose was called
    mock_exit_stack.aclose.assert_called_once()


async def test_mcp_tool_safe_close_handles_cleanup_exception_group():
    """Cleanup task groups should not hide the original connect failure."""
    import builtins
    from contextlib import AsyncExitStack

    exception_group_type = getattr(builtins, "ExceptionGroup", None)
    if exception_group_type is None:
        pytest.skip("ExceptionGroup is not available on this Python version")

    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com/mcp",
        load_tools=False,
        load_prompts=False,
    )

    mock_exit_stack = AsyncMock(spec=AsyncExitStack)
    mock_exit_stack.aclose = AsyncMock(side_effect=exception_group_type("cleanup failed", [RuntimeError("reader")]))
    tool._exit_stack = mock_exit_stack

    await tool._safe_close_exit_stack()

    mock_exit_stack.aclose.assert_called_once()


async def test_connect_sets_logging_level_when_logger_level_is_set():
    """Test that connect() sets the MCP server logging level when the logger level is not NOTSET."""

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the transport and session
    mock_transport = (Mock(), Mock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context.__aexit__ = AsyncMock()

    mock_session = Mock()
    mock_session._request_id = 1
    mock_session.initialize = AsyncMock()
    mock_session.set_logging_level = AsyncMock()

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock()

    with (
        patch.object(tool, "get_mcp_client", return_value=mock_context),
        patch("mcp.client.session.ClientSession", return_value=mock_session_context),
        patch.object(logger, "level", logging.DEBUG),  # Set logger level to DEBUG
    ):
        await tool.connect()

        # Verify set_logging_level was called with "debug"
        mock_session.set_logging_level.assert_called_once_with("debug")


async def test_connect_does_not_set_logging_level_when_logger_level_is_notset():
    """Test that connect() does not set logging level when logger level is NOTSET."""

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the transport and session
    mock_transport = (Mock(), Mock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context.__aexit__ = AsyncMock()

    mock_session = Mock()
    mock_session._request_id = 1
    mock_session.initialize = AsyncMock()
    mock_session.set_logging_level = AsyncMock()

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock()

    with (
        patch.object(tool, "get_mcp_client", return_value=mock_context),
        patch("mcp.client.session.ClientSession", return_value=mock_session_context),
        patch.object(logger, "level", logging.NOTSET),  # Set logger level to NOTSET
    ):
        await tool.connect()

        # Verify set_logging_level was NOT called
        mock_session.set_logging_level.assert_not_called()


async def test_connect_handles_set_logging_level_exception():
    """Test that connect() handles exceptions from set_logging_level gracefully."""

    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the transport and session
    mock_transport = (Mock(), Mock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context.__aexit__ = AsyncMock()

    mock_session = Mock()
    mock_session._request_id = 1
    mock_session.initialize = AsyncMock()
    # Make set_logging_level raise an exception
    mock_session.set_logging_level = AsyncMock(side_effect=RuntimeError("Server doesn't support logging level"))

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock()

    with (
        patch.object(tool, "get_mcp_client", return_value=mock_context),
        patch("mcp.client.session.ClientSession", return_value=mock_session_context),
        patch.object(logger, "level", logging.INFO),  # Set logger level to INFO
        patch.object(logger, "warning") as mock_warning,
    ):
        # Should NOT raise - the exception should be caught and logged
        await tool.connect()

        # Verify set_logging_level was called
        mock_session.set_logging_level.assert_called_once_with("info")

        # Verify warning was logged
        mock_warning.assert_called_once()
        call_args = mock_warning.call_args
        assert "Failed to set log level" in call_args[0][0]


async def test_connect_reinitializes_existing_session_and_loads_tools_and_prompts() -> None:
    tool = MCPTool(name="test_tool", load_tools=True, load_prompts=True)  # type: ignore[abstract]
    tool.is_connected = True
    tool.session = Mock()
    tool.session._request_id = 0
    tool.session.initialize = AsyncMock()

    with (
        patch.object(tool, "load_tools", AsyncMock()) as mock_load_tools,
        patch.object(tool, "load_prompts", AsyncMock()) as mock_load_prompts,
        patch.object(logger, "level", logging.NOTSET),
    ):
        await tool._connect_on_owner()

    tool.session.initialize.assert_awaited_once()
    mock_load_tools.assert_awaited_once()
    mock_load_prompts.assert_awaited_once()
    assert tool._tools_loaded is True
    assert tool._prompts_loaded is True


async def test_connect_skips_tools_and_prompts_when_server_does_not_advertise_capabilities() -> None:
    tool = MCPTool(name="test_tool", load_tools=True, load_prompts=True)  # type: ignore[abstract]
    tool.is_connected = True
    tool.session = Mock()
    tool.session._request_id = 0
    tool.session.initialize = AsyncMock(
        return_value=types.InitializeResult(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ServerCapabilities(),
            serverInfo=types.Implementation(name="test", version="1.0"),
        )
    )
    tool.session.list_tools = AsyncMock()
    tool.session.list_prompts = AsyncMock()
    tool.session.set_logging_level = AsyncMock()

    with patch.object(logger, "level", logging.INFO):
        await tool._connect_on_owner()

    tool.session.initialize.assert_awaited_once()
    tool.session.list_tools.assert_not_called()
    tool.session.list_prompts.assert_not_called()
    tool.session.set_logging_level.assert_not_called()
    assert tool.is_connected is True
    assert tool._supports_tools is False
    assert tool._supports_prompts is False
    assert tool._supports_logging is False
    assert tool._tools_loaded is True
    assert tool._prompts_loaded is True


async def test_connect_treats_missing_capabilities_as_unsupported() -> None:
    tool = MCPTool(name="test_tool", load_tools=True, load_prompts=True)  # type: ignore[abstract]
    tool.is_connected = True
    tool.session = Mock()
    tool.session._request_id = 0
    tool.session.initialize = AsyncMock(return_value=Mock(capabilities=None))
    tool.session.list_tools = AsyncMock()
    tool.session.list_prompts = AsyncMock()

    with patch.object(logger, "level", logging.NOTSET):
        await tool._connect_on_owner()

    tool.session.list_tools.assert_not_called()
    tool.session.list_prompts.assert_not_called()
    assert tool._supports_tools is False
    assert tool._supports_prompts is False
    assert tool._supports_logging is False


async def test_connect_sets_logging_level_when_server_advertises_logging() -> None:
    tool = MCPTool(name="test_tool", load_tools=False, load_prompts=False)  # type: ignore[abstract]
    tool.is_connected = True
    tool.session = Mock()
    tool.session._request_id = 0
    tool.session.initialize = AsyncMock(
        return_value=types.InitializeResult(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ServerCapabilities(logging=types.LoggingCapability()),
            serverInfo=types.Implementation(name="test", version="1.0"),
        )
    )
    tool.session.set_logging_level = AsyncMock()

    with patch.object(logger, "level", logging.INFO):
        await tool._connect_on_owner()

    tool.session.set_logging_level.assert_awaited_once_with("info")
    assert tool._supports_logging is True


async def test_ensure_connected_skips_future_pings_when_ping_is_not_available() -> None:
    tool = MCPTool(name="test_tool")  # type: ignore[abstract]
    tool.session = Mock(
        send_ping=AsyncMock(
            side_effect=McpError(types.ErrorData(code=-32601, message="Method 'ping' is not available."))
        )
    )

    with patch.object(tool, "_reconnect_without_loading", AsyncMock()) as mock_reconnect:
        await tool._ensure_connected()
        await tool._ensure_connected()

    tool.session.send_ping.assert_awaited_once()
    mock_reconnect.assert_not_awaited()
    assert tool._ping_available is False


async def test_ensure_connected_reconnects_on_failed_ping() -> None:
    tool = MCPTool(name="test_tool")  # type: ignore[abstract]
    tool.session = Mock(send_ping=AsyncMock(side_effect=RuntimeError("closed")))

    with patch.object(tool, "_reconnect_without_loading", AsyncMock()) as mock_reconnect:
        await tool._ensure_connected()

    mock_reconnect.assert_awaited_once_with()


async def test_ensure_connected_wraps_reconnect_failure() -> None:
    tool = MCPTool(name="test_tool")  # type: ignore[abstract]
    tool.session = Mock(send_ping=AsyncMock(side_effect=RuntimeError("closed")))

    with (
        patch.object(tool, "_reconnect_without_loading", AsyncMock(side_effect=RuntimeError("still closed"))),
        pytest.raises(ToolExecutionException, match="Failed to establish MCP connection"),
    ):
        await tool._ensure_connected()


async def test_load_tools_reconnects_on_closed_resource_when_ping_is_unavailable() -> None:
    from anyio import ClosedResourceError

    tool = MCPTool(name="test_tool", load_tools=True)  # type: ignore[abstract]
    tool._ping_available = False

    first_session = Mock()
    first_session.list_tools = AsyncMock(side_effect=ClosedResourceError())
    tool.session = first_session

    page = Mock()
    page.tools = []
    page.nextCursor = None

    second_session = Mock()
    second_session.list_tools = AsyncMock(return_value=page)

    async def reconnect() -> None:
        tool.session = second_session
        tool._supports_tools = True

    with patch.object(tool, "_reconnect_without_loading", AsyncMock(side_effect=reconnect)) as mock_reconnect:
        await tool.load_tools()

    first_session.list_tools.assert_awaited_once()
    mock_reconnect.assert_awaited_once_with()
    second_session.list_tools.assert_awaited_once()


async def test_load_prompts_reconnects_on_closed_resource_when_ping_is_unavailable() -> None:
    from anyio import ClosedResourceError

    tool = MCPTool(name="test_tool", load_prompts=True)  # type: ignore[abstract]
    tool._ping_available = False

    first_session = Mock()
    first_session.list_prompts = AsyncMock(side_effect=ClosedResourceError())
    tool.session = first_session

    page = Mock()
    page.prompts = []
    page.nextCursor = None

    second_session = Mock()
    second_session.list_prompts = AsyncMock(return_value=page)

    async def reconnect() -> None:
        tool.session = second_session
        tool._supports_prompts = True

    with patch.object(tool, "_reconnect_without_loading", AsyncMock(side_effect=reconnect)) as mock_reconnect:
        await tool.load_prompts()

    first_session.list_prompts.assert_awaited_once()
    mock_reconnect.assert_awaited_once_with()
    second_session.list_prompts.assert_awaited_once()


async def test_mcp_tool_filters_framework_kwargs():
    """Test that call_tool filters out framework-specific kwargs before calling MCP session.

    This verifies that non-serializable kwargs like response_format (Pydantic model class),
    chat_options, tools, tool_choice, thread, conversation_id, and options are filtered out
    before being passed to the external MCP server.
    """

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            # Mock call_tool to capture the arguments it receives
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Success")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    # Create a mock Pydantic model class to use as response_format
    class MockResponseFormat(BaseModel):
        result: str

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        # Invoke the tool with framework kwargs that should be filtered out
        await func.invoke(
            context=FunctionInvocationContext(
                function=func,
                arguments={"param": "test_value"},
                kwargs={
                    "response_format": MockResponseFormat,  # Should be filtered
                    "chat_options": {"some": "option"},  # Should be filtered
                    "tools": [Mock()],  # Should be filtered
                    "tool_choice": "auto",  # Should be filtered
                    "session": Mock(),  # Should be filtered
                    "conversation_id": "conv-123",  # Should be filtered
                    "options": {"metadata": "value"},  # Should be filtered
                },
            ),
        )

        # Verify call_tool was called with only the valid argument
        server.session.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        call_args = server.session.call_tool.call_args  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]

        # Check that the arguments dict only contains 'param' and none of the framework kwargs
        arguments = call_args.kwargs.get("arguments", call_args[1] if len(call_args) > 1 else {})
        assert arguments == {"param": "test_value"}, f"Expected only 'param' but got: {arguments}"

        # Explicitly verify that framework kwargs were NOT passed
        assert "response_format" not in arguments
        assert "chat_options" not in arguments
        assert "tools" not in arguments
        assert "tool_choice" not in arguments
        assert "thread" not in arguments
        assert "conversation_id" not in arguments
        assert "options" not in arguments


# region: OTel trace context propagation via _meta


@pytest.mark.parametrize(
    "use_span,expect_traceparent",
    [
        (True, True),
        (False, False),
    ],
)
async def test_mcp_tool_call_tool_otel_meta(use_span, expect_traceparent, span_exporter):
    """call_tool propagates OTel trace context via meta only when a span is active."""
    from opentelemetry import trace

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()

        if use_span:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test_span"):
                await server.functions[0].invoke(param="test_value")
        else:
            # Use an invalid span to ensure no trace context is injected;
            # call server.call_tool directly to bypass FunctionTool.invoke's own span.
            with trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)):
                await server.call_tool("test_tool", param="test_value")

        meta = server.session.call_tool.call_args.kwargs.get("meta")  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        if expect_traceparent:
            # When a valid span is active, we expect some propagation fields to be injected,
            # but we do not assume any specific header name to keep this test propagator-agnostic.
            assert meta is not None
            assert isinstance(meta, dict)
            assert len(meta) > 0
        else:
            assert meta is None


async def test_mcp_tool_call_tool_forwards_tool_list_meta():
    """call_tool echoes per-tool metadata returned by tools/list."""
    from opentelemetry import trace

    tool_meta = {
        "tool_configuration": {
            "name": "WorkIQSharePoint.readSmallBinaryFile",
            "type": "foundry_toolbox",
        }
    }

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="WorkIQSharePoint.readSmallBinaryFile",
                            description="Read a binary file",
                            inputSchema={
                                "type": "object",
                                "properties": {"fileId": {"type": "string"}},
                                "required": ["fileId"],
                            },
                            _meta=tool_meta,
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )
            self.session.list_prompts = AsyncMock(return_value=types.ListPromptsResult(prompts=[]))

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        await server.load_prompts()

        with trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)):
            await server.call_tool("WorkIQSharePoint.readSmallBinaryFile", fileId="file-1")

        assert server.session.call_tool.call_args.kwargs["meta"] == tool_meta  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_mcp_tool_call_tool_user_meta_merges_with_tool_list_meta():
    """Tools/list _meta should win over caller-provided _meta on conflicts."""
    from opentelemetry import trace

    tool_meta = {"from_tool": "tool-value", "shared": "tool-value"}
    user_meta = {"from_user": "user-value", "shared": "user-value"}

    class TestServer(MCPTool):
        async def connect(self) -> None:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
                            _meta=tool_meta,
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()

        with trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)):
            await server.call_tool("test_tool", param="test_value", _meta=user_meta)

        call_kwargs = server.session.call_tool.call_args.kwargs  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_kwargs["arguments"] == {"param": "test_value"}
        assert call_kwargs["meta"] == {
            "from_tool": "tool-value",
            "from_user": "user-value",
            "shared": "tool-value",
        }
        assert user_meta == {"from_user": "user-value", "shared": "user-value"}


async def test_mcp_tool_function_invocation_strips_model_supplied_meta() -> None:
    """Model-supplied _meta should not become MCP request metadata."""
    from opentelemetry import trace

    class TestServer(MCPTool):
        async def connect(self) -> None:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()

        with (
            trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)),
            patch("agent_framework._mcp.propagate.inject", side_effect=lambda carrier: None),
        ):
            await server.functions[0].invoke(
                arguments={"param": "test_value", "_meta": {"attacker.example/route": "evil"}}
            )

        call_kwargs = server.session.call_tool.call_args.kwargs  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_kwargs["arguments"] == {"param": "test_value"}
        assert call_kwargs["meta"] is None


async def test_mcp_tool_function_invocation_preserves_trusted_meta_over_model_meta() -> None:
    """Trusted function-invocation _meta should be restored after model arguments are merged."""
    from opentelemetry import trace

    trusted_meta = {"trusted.example/route": "trusted"}

    class TestServer(MCPTool):
        async def connect(self) -> None:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()

        context = FunctionInvocationContext(
            function=server.functions[0],
            arguments={},
            kwargs={"_meta": trusted_meta},
        )
        with (
            trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)),
            patch("agent_framework._mcp.propagate.inject", side_effect=lambda carrier: None),
        ):
            await server.functions[0].invoke(
                arguments={"param": "test_value", "_meta": {"attacker.example/route": "evil"}},
                context=context,
            )

        call_kwargs = server.session.call_tool.call_args.kwargs  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_kwargs["arguments"] == {"param": "test_value"}
        assert call_kwargs["meta"] == trusted_meta


async def test_mcp_tool_call_tool_otel_meta_overrides_user_meta_but_not_tool_list_meta() -> None:
    """OpenTelemetry should override caller metadata while tools/list metadata remains most trusted."""
    from opentelemetry import trace

    tool_meta = {"traceparent": "tool-traceparent", "from_tool": "tool-value"}
    user_meta = {"traceparent": "user-traceparent", "from_user": "user-value"}

    class TestServer(MCPTool):
        async def connect(self) -> None:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
                            _meta=tool_meta,
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="result")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()

        with (
            trace.use_span(trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)),
            patch(
                "agent_framework._mcp.propagate.inject",
                side_effect=lambda carrier: carrier.update({"traceparent": "otel-traceparent"}),
            ),
        ):
            await server.call_tool("test_tool", param="test_value", _meta=user_meta)

        call_kwargs = server.session.call_tool.call_args.kwargs  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_kwargs["meta"] == {
            "traceparent": "tool-traceparent",
            "from_tool": "tool-value",
            "from_user": "user-value",
        }


async def test_mcp_streamable_http_tool_hook_not_duplicated_on_repeated_get_mcp_client():
    """Test that calling get_mcp_client multiple times does not accumulate duplicate hooks."""
    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com/mcp",
        header_provider=lambda kw: {"X-Token": kw.get("token", "")},
    )

    try:
        with patch("agent_framework._mcp.streamable_http_client"):
            tool.get_mcp_client()
            tool.get_mcp_client()
            tool.get_mcp_client()

            assert tool._httpx_client is not None
            hooks = tool._httpx_client.event_hooks.get("request", [])
            assert len(hooks) == 1, f"Expected exactly one hook, got {len(hooks)}"
    finally:
        if getattr(tool, "_httpx_client", None) is not None:
            await tool._httpx_client.aclose()  # type: ignore[union-attr]


# endregion


# region: MCPStreamableHTTPTool header_provider


async def test_mcp_streamable_http_tool_header_provider_injects_headers():
    """Test that header_provider integrates with call_tool via runtime kwargs.

    When header_provider is configured, runtime kwargs from FunctionInvocationContext
    are passed to the provider and the MCP session.call_tool is invoked successfully.
    """

    class _TestServer(MCPStreamableHTTPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="greet",
                            description="Says hello",
                            inputSchema={
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Hello!")])
            )
            self.session.send_ping = AsyncMock()
            self.is_connected = True

        def get_mcp_client(self):  # pyrefly: ignore[bad-override]
            return None

    def provider(kwargs):
        return {"X-Some-Token": kwargs.get("some_token", "")}

    server = _TestServer(
        name="test",
        url="http://example.com/mcp",
        header_provider=provider,
    )
    async with server:
        await server.load_tools()

        # Simulate the runtime kwargs that flow from FunctionInvocationContext.kwargs
        await server.call_tool("greet", name="Alice", some_token="my-secret")

        # Verify the MCP session.call_tool was called
        server.session.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_mcp_streamable_http_tool_header_provider_sets_contextvar():
    """Test that call_tool sets the contextvar with headers from header_provider."""
    from agent_framework._mcp import _mcp_call_headers

    observed_headers: list[dict[str, str]] = []
    original_call_tool = MCPTool.call_tool

    async def spy_call_tool(self, tool_name, **kwargs):
        # Capture the contextvar value during the super call
        try:
            observed_headers.append(_mcp_call_headers.get())
        except LookupError:
            observed_headers.append({})
        return await original_call_tool(self, tool_name, **kwargs)

    class _TestServer(MCPStreamableHTTPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="greet",
                            description="Says hello",
                            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Hello!")])
            )
            self.session.send_ping = AsyncMock()
            self.is_connected = True

        def get_mcp_client(self):  # pyrefly: ignore[bad-override]
            return None

    server = _TestServer(
        name="test",
        url="http://example.com/mcp",
        header_provider=lambda kw: {"X-Auth": kw.get("auth_token", "")},
    )
    async with server:
        await server.load_tools()

        with patch.object(MCPTool, "call_tool", spy_call_tool):
            await server.call_tool("greet", name="Alice", auth_token="bearer-xyz")

    assert len(observed_headers) == 1
    assert observed_headers[0] == {"X-Auth": "bearer-xyz"}


async def test_mcp_streamable_http_tool_header_provider_contextvar_reset_after_call():
    """Test that the contextvar is properly reset after call_tool completes."""
    from agent_framework._mcp import _mcp_call_headers

    class _TestServer(MCPStreamableHTTPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="greet",
                            description="Says hello",
                            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Hello!")])
            )
            self.session.send_ping = AsyncMock()
            self.is_connected = True

        def get_mcp_client(self):  # pyrefly: ignore[bad-override]
            return None

    server = _TestServer(
        name="test",
        url="http://example.com/mcp",
        header_provider=lambda kw: {"X-Token": kw.get("token", "")},
    )
    async with server:
        await server.load_tools()
        await server.call_tool("greet", name="Alice", token="secret")

    # After call_tool, the contextvar should be unset (reset to no value)
    with pytest.raises(LookupError):
        _mcp_call_headers.get()


async def test_mcp_streamable_http_tool_without_header_provider():
    """Test that call_tool works normally when no header_provider is configured."""

    class _TestServer(MCPStreamableHTTPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="greet",
                            description="Says hello",
                            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Hello!")])
            )
            self.session.send_ping = AsyncMock()
            self.is_connected = True

        def get_mcp_client(self):  # pyrefly: ignore[bad-override]
            return None

    server = _TestServer(
        name="test",
        url="http://example.com/mcp",
    )
    async with server:
        await server.load_tools()
        await server.call_tool("greet", name="Alice")
        server.session.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]

    # Without header_provider, call_tool should delegate directly to MCPTool
    assert server._header_provider is None


async def test_mcp_streamable_http_tool_header_provider_with_httpx_event_hook():
    """Test that the httpx event hook injects headers from the contextvar."""
    import httpx

    from agent_framework._mcp import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT, _mcp_call_headers

    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com/mcp",
        header_provider=lambda kw: {"X-Custom": kw.get("custom", "")},
    )

    try:
        with patch("agent_framework._mcp.streamable_http_client"):
            # Trigger get_mcp_client to set up the event hook
            tool.get_mcp_client()

            # The tool should have created an httpx client with the event hook
            assert tool._httpx_client is not None
            assert tool._httpx_client.follow_redirects is True
            assert tool._httpx_client.timeout.connect == MCP_DEFAULT_TIMEOUT
            assert tool._httpx_client.timeout.read == MCP_DEFAULT_SSE_READ_TIMEOUT
            hooks = tool._httpx_client.event_hooks.get("request", [])
            assert len(hooks) == 1, "Expected one request event hook"

            # Simulate what happens during a call_tool: contextvar is set
            token = _mcp_call_headers.set({"X-Custom": "test-value"})
            try:
                request = httpx.Request("POST", "http://example.com/mcp")
                await hooks[0](request)
                assert request.headers.get("X-Custom") == "test-value"
            finally:
                _mcp_call_headers.reset(token)
    finally:
        # Ensure any created httpx client is properly closed
        if getattr(tool, "_httpx_client", None) is not None:
            await tool._httpx_client.aclose()  # type: ignore[union-attr]


async def test_mcp_streamable_http_tool_header_provider_skips_cross_origin_redirect():
    """The request hook must not re-add caller headers after a cross-origin redirect."""
    import httpx

    from agent_framework._mcp import _mcp_call_headers

    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com/mcp",
        header_provider=lambda kw: {"Authorization": f"Bearer {kw.get('token', '')}"},
    )

    try:
        with patch("agent_framework._mcp.streamable_http_client"):
            tool.get_mcp_client()

            assert tool._httpx_client is not None
            hooks = tool._httpx_client.event_hooks.get("request", [])
            assert len(hooks) == 1

            token = _mcp_call_headers.set({"Authorization": "Bearer secret"})
            try:
                same_origin = httpx.Request("POST", "http://example.com/redirected")
                await hooks[0](same_origin)
                assert same_origin.headers.get("Authorization") == "Bearer secret"

                cross_origin = httpx.Request("POST", "http://attacker.example/capture")
                await hooks[0](cross_origin)
                assert "Authorization" not in cross_origin.headers
            finally:
                _mcp_call_headers.reset(token)
    finally:
        if getattr(tool, "_httpx_client", None) is not None:
            await tool._httpx_client.aclose()  # type: ignore[union-attr]


async def test_mcp_streamable_http_tool_header_provider_with_user_httpx_client():
    """Test that header_provider works when the user provides their own httpx client."""
    import httpx

    from agent_framework._mcp import _mcp_call_headers

    user_client = httpx.AsyncClient(headers={"X-Base": "static"})

    tool = MCPStreamableHTTPTool(
        name="test",
        url="http://example.com/mcp",
        http_client=user_client,
        header_provider=lambda kw: {"X-Dynamic": kw.get("dynamic", "")},
    )

    with patch("agent_framework._mcp.streamable_http_client"):
        tool.get_mcp_client()

        # The user's client should still be used
        assert tool._httpx_client is user_client
        hooks = user_client.event_hooks.get("request", [])
        assert len(hooks) == 1

        # Verify the hook injects headers
        token = _mcp_call_headers.set({"X-Dynamic": "per-request"})
        try:
            request = httpx.Request("POST", "http://example.com/mcp")
            await hooks[0](request)
            assert request.headers.get("X-Dynamic") == "per-request"
        finally:
            _mcp_call_headers.reset(token)

    await user_client.aclose()


async def test_mcp_streamable_http_tool_header_provider_via_invoke_with_context():
    """Test that header_provider receives kwargs via FunctionTool.invoke with FunctionInvocationContext.

    This exercises the full pipeline: FunctionInvocationContext.kwargs -> FunctionTool.invoke
    -> MCPStreamableHTTPTool.call_tool -> header_provider.
    """
    from agent_framework._mcp import _mcp_call_headers

    observed_headers: list[dict[str, str]] = []
    original_call_tool = MCPStreamableHTTPTool.call_tool

    async def spy_call_tool(self, tool_name, **kwargs):
        # Capture the contextvar value set by call_tool before delegating
        result = await original_call_tool(self, tool_name, **kwargs)
        try:
            observed_headers.append(_mcp_call_headers.get())
        except LookupError:
            observed_headers.append({})
        return result

    class _TestServer(MCPStreamableHTTPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="greet",
                            description="Says hello",
                            inputSchema={
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="Hello!")])
            )
            self.session.send_ping = AsyncMock()
            self.is_connected = True

        def get_mcp_client(self):  # pyrefly: ignore[bad-override]
            return None

    provider_received: list[dict] = []

    def provider(kwargs):
        provider_received.append(dict(kwargs))
        return {"X-Some-Token": kwargs.get("some_token", "")}

    server = _TestServer(
        name="test",
        url="http://example.com/mcp",
        header_provider=provider,
    )
    async with server:
        await server.load_tools()
        func = server.functions[0]

        # Build a FunctionInvocationContext with runtime kwargs, as the agent framework would
        context = FunctionInvocationContext(
            function=func,
            arguments={"name": "Alice"},
            kwargs={"some_token": "my-secret"},
        )

        with patch.object(MCPStreamableHTTPTool, "call_tool", spy_call_tool):
            result = await func.invoke(arguments={"name": "Alice"}, context=context)

        # Verify the invoke produced a result
        assert isinstance(result, list)
        assert result[0].text == "Hello!"

        # Verify header_provider was called with the runtime kwargs
        assert len(provider_received) == 1
        assert provider_received[0]["some_token"] == "my-secret"

        # Verify session.call_tool was called with the tool arguments (not the runtime kwargs)
        server.session.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        call_args = server.session.call_tool.call_args  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_args.kwargs.get("arguments", {}).get("name") == "Alice"


# endregion


# region: MCP long-running task (SEP-2663) tests


def _utc_now() -> Any:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _make_task_snapshot(
    *,
    task_id: str = "task-1",
    status: str = "working",
    status_message: str | None = None,
    poll_interval_ms: int | None = None,
) -> types.GetTaskResult:
    now = _utc_now()
    return types.GetTaskResult(
        taskId=task_id,
        status=status,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        statusMessage=status_message,
        createdAt=now,
        lastUpdatedAt=now,
        ttl=None,
        pollInterval=poll_interval_ms,
    )


def _make_create_task_result(task_id: str = "task-1") -> types.CreateTaskResult:
    now = _utc_now()
    return types.CreateTaskResult(
        task=types.Task(
            taskId=task_id,
            status="working",
            statusMessage=None,
            createdAt=now,
            lastUpdatedAt=now,
            ttl=None,
        )
    )


def _make_payload(text: str = "done!", is_error: bool = False) -> types.GetTaskPayloadResult:
    return types.GetTaskPayloadResult.model_validate({
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    })


def _make_task_tool(
    tool_name: str = "slow_op",
    *,
    task_support: str | None = "required",
    task_options: Any = None,
) -> MCPTool:
    from agent_framework import MCPTaskOptions

    tool = MCPTool(  # type: ignore[abstract]
        name="lro",
        task_options=task_options if task_options is not None else MCPTaskOptions(),
    )
    tool.session = AsyncMock(spec=ClientSession)
    if task_support is not None:
        tool._tool_task_support_by_name[tool_name] = task_support
    return tool


def _send_request_dispatcher(*responses_by_method: tuple[str, Any]) -> Any:
    """Build a send_request side_effect that returns responses keyed by request method.

    Each tuple is ``(method_name, response_or_exception_or_callable)``. The dispatcher
    advances a per-method queue on every call. A callable response is invoked with no
    args so tests can raise exceptions deterministically.
    """
    from collections import defaultdict

    queues: dict[str, list[Any]] = defaultdict(list)
    for method, response in responses_by_method:
        queues[method].append(response)

    async def _dispatch(request: Any, _result_type: Any, *_args: Any, **_kw: Any) -> Any:
        method = getattr(request.root, "method", None) or getattr(request, "method", None)
        queue = queues.get(method)  # type: ignore[arg-type, call-overload]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        if not queue:
            raise AssertionError(f"No mocked send_request response for method '{method}'.")
        item = queue.pop(0)
        if callable(item):
            return item()
        if isinstance(item, BaseException):
            raise item
        return item

    return _dispatch


async def test_task_options_defaults_are_sane() -> None:
    from agent_framework import MCPTaskOptions

    opts = MCPTaskOptions()
    assert opts.default_ttl is None
    assert opts.cancel_remote_task_on_local_cancellation is True


async def test_task_options_rejects_non_positive_default_ttl() -> None:
    from datetime import timedelta

    from agent_framework import MCPTaskOptions

    with pytest.raises(ValueError, match="positive"):
        MCPTaskOptions(default_ttl=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="positive"):
        MCPTaskOptions(default_ttl=timedelta(0))


async def test_load_tools_captures_task_support() -> None:
    tool = MCPTool(name="lro")  # type: ignore[abstract]
    tool.session = AsyncMock()
    tool.load_tools_flag = True

    page = Mock()
    page.tools = [
        types.Tool(
            name="slow_op",
            description="slow",
            inputSchema={"type": "object", "properties": {}},
            execution=types.ToolExecution(taskSupport="required"),
        ),
        types.Tool(
            name="fast_op",
            description="fast",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    page.nextCursor = None
    tool.session.list_tools = AsyncMock(return_value=page)

    await tool.load_tools()

    assert tool._tool_task_support_by_name == {"slow_op": "required"}


async def test_call_tool_routes_required_through_task_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="working")),
            ("tasks/get", _make_task_snapshot(status="completed")),
            ("tasks/result", _make_payload("hello task")),
        )
    )

    result = await tool.call_tool("slow_op", x=1)

    assert _mcp_result_to_text(result) == "hello task"
    # Plain session.call_tool must NOT be used for required tools.
    tool.session.call_tool.assert_not_called()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_call_tool_as_task_default_ttl_propagates() -> None:
    from datetime import timedelta

    from agent_framework import MCPTaskOptions

    tool = _make_task_tool(task_options=MCPTaskOptions(default_ttl=timedelta(minutes=7)))

    captured: list[Any] = []

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        captured.append(request)
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result()
        if method == "tasks/get":
            return _make_task_snapshot(status="completed")
        if method == "tasks/result":
            return _make_payload("ok")
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    await tool.call_tool("slow_op")

    create_req = captured[0]
    assert create_req.root.method == "tools/call"
    assert create_req.root.params.task is not None
    assert create_req.root.params.task.ttl == 7 * 60 * 1000


async def test_call_tool_as_task_sends_empty_task_metadata_when_ttl_none() -> None:
    # Without a TTL we still mark the call as task-augmented (servers require
    # the `task` field to route through the lifecycle).
    tool = _make_task_tool()

    captured: list[Any] = []

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        captured.append(request)
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result()
        if method == "tasks/get":
            return _make_task_snapshot(status="completed")
        if method == "tasks/result":
            return _make_payload("ok")
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    await tool.call_tool("slow_op")

    create_req = captured[0]
    assert create_req.root.method == "tools/call"
    assert create_req.root.params.task is not None
    assert create_req.root.params.task.ttl is None


async def test_call_tool_skips_task_path_for_optional_and_forbidden() -> None:
    for support in ("optional", "forbidden", None):
        tool = _make_task_tool(task_support=support)
        tool.session.call_tool = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
            return_value=types.CallToolResult(content=[types.TextContent(type="text", text="plain")])
        )
        tool.session.send_request = AsyncMock(side_effect=AssertionError("task path should not be used"))  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

        result = await tool.call_tool("slow_op")
        assert _mcp_result_to_text(result) == "plain"


async def test_call_tool_as_task_cancelled_status_raises() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="cancelled", status_message="server stop")),
        )
    )

    with pytest.raises(ToolExecutionException, match="cancelled.*server stop"):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_failed_status_raises() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="failed", status_message="boom")),
        )
    )

    with pytest.raises(ToolExecutionException, match="failed.*boom"):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_input_required_raises() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="input_required", status_message="need more")),
        )
    )

    with pytest.raises(ToolExecutionException, match="input_required.*need more"):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_payload_iserror_raises() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="completed")),
            ("tasks/result", _make_payload("payload exploded", is_error=True)),
        )
    )

    with pytest.raises(ToolExecutionException, match="payload exploded"):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_malformed_payload_raises() -> None:
    tool = _make_task_tool()
    bad_payload = types.GetTaskPayloadResult.model_validate({"random": "stuff"})
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result(task_id="abc")),
            ("tasks/get", _make_task_snapshot(task_id="abc", status="completed")),
            ("tasks/result", bad_payload),
        )
    )

    with pytest.raises(ToolExecutionException, match="task 'abc' result payload"):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_method_not_found_falls_back() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=McpError(types.ErrorData(code=types.METHOD_NOT_FOUND, message="no tasks here"))
    )
    tool.session.call_tool = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        return_value=types.CallToolResult(content=[types.TextContent(type="text", text="fell back")])
    )

    result = await tool.call_tool("slow_op")

    assert _mcp_result_to_text(result) == "fell back"
    tool.session.call_tool.assert_awaited_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_call_tool_as_task_invalid_params_falls_back() -> None:
    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=McpError(types.ErrorData(code=types.INVALID_PARAMS, message="unknown field"))
    )
    tool.session.call_tool = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        return_value=types.CallToolResult(content=[types.TextContent(type="text", text="plain ok")])
    )

    result = await tool.call_tool("slow_op")

    assert _mcp_result_to_text(result) == "plain ok"


async def test_call_tool_as_task_legacy_calltoolresult_response_used_directly() -> None:
    """Server may ignore augmentation and return CallToolResult; treat it as the result."""
    # Build a lenient Result whose extras match a CallToolResult shape.
    legacy_payload = types.Result.model_validate({
        "content": [{"type": "text", "text": "legacy ok"}],
        "isError": False,
    })

    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(return_value=legacy_payload)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    result = await tool.call_tool("slow_op")

    assert _mcp_result_to_text(result) == "legacy ok"
    # Polling must not occur: a single tools/call was enough.
    assert tool.session.send_request.call_count == 1  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_call_tool_as_task_poll_interval_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta as _td

    from agent_framework import _mcp as _mcp_module

    # Stub asyncio.sleep so we can capture delays without actually sleeping.
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(_mcp_module.asyncio, "sleep", fake_sleep)

    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
        side_effect=_send_request_dispatcher(
            ("tools/call", _make_create_task_result()),
            ("tasks/get", _make_task_snapshot(status="working", poll_interval_ms=50)),  # below 500ms min
            ("tasks/get", _make_task_snapshot(status="working", poll_interval_ms=10_000)),  # above 5s max
            ("tasks/get", _make_task_snapshot(status="working", poll_interval_ms=None)),  # default to min
            ("tasks/get", _make_task_snapshot(status="working", poll_interval_ms=0)),  # invalid -> min
            ("tasks/get", _make_task_snapshot(status="working", poll_interval_ms=2_000)),  # in-band
            ("tasks/get", _make_task_snapshot(status="completed")),
            ("tasks/result", _make_payload("ok")),
        )
    )

    await tool.call_tool("slow_op")

    expected = [
        _td(milliseconds=500).total_seconds(),  # clamp up
        _td(seconds=5).total_seconds(),  # clamp down
        _td(milliseconds=500).total_seconds(),  # missing -> min
        _td(milliseconds=500).total_seconds(),  # zero    -> min
        _td(milliseconds=2_000).total_seconds(),
    ]
    assert delays == expected


async def test_call_tool_as_task_local_cancellation_fires_remote_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    cancel_seen = asyncio.Event()
    create_seen = asyncio.Event()

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        method = request.root.method
        if method == "tools/call":
            create_seen.set()
            return _make_create_task_result()
        if method == "tasks/get":
            await asyncio.sleep(0)
            return _make_task_snapshot(status="working")
        if method == "tasks/cancel":
            cancel_seen.set()
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    task = asyncio.create_task(tool.call_tool("slow_op"))
    await asyncio.wait_for(create_seen.wait(), timeout=1.0)
    # Let polling iterate a few times.
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Wait for the fire-and-forget cancel to complete.
    await asyncio.wait_for(cancel_seen.wait(), timeout=1.0)
    # Drain any tracked background tasks.
    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def test_call_tool_as_task_cancellation_suppressed_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_framework import MCPTaskOptions
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool(
        task_options=MCPTaskOptions(cancel_remote_task_on_local_cancellation=False),
    )

    cancel_called = False
    create_seen = asyncio.Event()

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            create_seen.set()
            return _make_create_task_result()
        if method == "tasks/get":
            await asyncio.sleep(0)
            return _make_task_snapshot(status="working")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    task = asyncio.create_task(tool.call_tool("slow_op"))
    await asyncio.wait_for(create_seen.wait(), timeout=1.0)
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Let any (incorrect) background work settle, then verify cancel was NOT sent.
    await asyncio.sleep(0.02)
    assert cancel_called is False


async def test_call_tool_as_task_reconnects_during_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    from anyio import ClosedResourceError

    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    poll_calls = 0

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal poll_calls
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="abc")
        if method == "tasks/get":
            poll_calls += 1
            assert request.root.params.taskId == "abc"
            if poll_calls == 1:
                raise ClosedResourceError
            return _make_task_snapshot(task_id="abc", status="completed")
        if method == "tasks/result":
            return _make_payload("recovered")
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    reconnect_calls = 0

    async def fake_connect(reset: bool = False) -> None:
        nonlocal reconnect_calls
        reconnect_calls += 1
        assert reset is True

    with patch.object(MCPTool, "connect", side_effect=fake_connect):
        result = await tool.call_tool("slow_op")

    assert _mcp_result_to_text(result) == "recovered"
    assert reconnect_calls == 1
    # Critically, tools/call must NOT be re-issued after task_id is known.
    assert (
        sum(
            1  # type: ignore[misc]
            for c in tool.session.send_request.await_args_list  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
            if c.args[0].root.method == "tools/call"
        )
        == 1
    )


async def test_call_tool_as_task_second_disconnect_raises_connection_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from anyio import ClosedResourceError

    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="abc")
        if method == "tasks/get":
            raise ClosedResourceError
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with (
        patch.object(MCPTool, "connect", new=AsyncMock(return_value=None)),
        pytest.raises(ToolExecutionException, match="task state unknown"),
    ):
        await tool.call_tool("slow_op")


async def test_call_tool_as_task_create_disconnect_does_not_retry() -> None:
    """A connection loss during the augmented tools/call must NOT retry.

    Retrying could spawn a duplicate long-running task on the server, because the
    first request may have been accepted before the response was lost.
    """
    from anyio import ClosedResourceError

    tool = _make_task_tool()

    send_calls = 0

    async def fake_send(_request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal send_calls
        send_calls += 1
        raise ClosedResourceError

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    reconnect_mock = AsyncMock(return_value=None)
    with (
        patch.object(MCPTool, "connect", new=reconnect_mock),
        pytest.raises(ToolExecutionException, match="task state unknown"),
    ):
        await tool.call_tool("slow_op")

    # Exactly one tools/call was issued — the server-side task state is unknown,
    # so retry is unsafe and must be skipped.
    assert send_calls == 1
    reconnect_mock.assert_not_awaited()


async def test_fetch_task_result_reconnects_during_fetch() -> None:
    from anyio import ClosedResourceError

    tool = _make_task_tool()

    fetch_calls = 0

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal fetch_calls
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="r1")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="r1", status="completed")
        if method == "tasks/result":
            fetch_calls += 1
            if fetch_calls == 1:
                raise ClosedResourceError
            return _make_payload("fetched after reconnect")
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    reconnect_calls = 0

    async def fake_connect(reset: bool = False) -> None:
        nonlocal reconnect_calls
        reconnect_calls += 1
        assert reset is True

    with patch.object(MCPTool, "connect", side_effect=fake_connect):
        result = await tool.call_tool("slow_op")

    assert _mcp_result_to_text(result) == "fetched after reconnect"
    assert reconnect_calls == 1
    assert fetch_calls == 2


async def test_fetch_task_result_second_disconnect_raises_task_state_unknown_and_cancels() -> None:
    from anyio import ClosedResourceError

    tool = _make_task_tool()

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="r2")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="r2", status="completed")
        if method == "tasks/result":
            raise ClosedResourceError
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with (
        patch.object(MCPTool, "connect", new=AsyncMock(return_value=None)),
        pytest.raises(ToolExecutionException, match="task state unknown"),
    ):
        await tool.call_tool("slow_op")

    # Drain the fire-and-forget cancel so the assertion is deterministic.
    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is True


async def test_call_tool_as_task_create_unparseable_success_raises() -> None:
    """An unparseable success-shaped response must NOT silently retry tools/call."""
    # Result with neither task.taskId nor a valid CallToolResult shape.
    unparseable = types.Result.model_validate({"foo": "bar"})

    tool = _make_task_tool()
    tool.session.send_request = AsyncMock(return_value=unparseable)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]
    tool.session.call_tool = AsyncMock(return_value=types.CallToolResult(content=[]))  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="unparseable response"):
        await tool.call_tool("slow_op")

    # Critically: no plain tools/call fallback (would risk double execution).
    tool.session.call_tool.assert_not_called()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


async def test_call_tool_as_task_max_wait_exceeded_raises_and_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_framework import MCPTaskOptions
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool(task_options=MCPTaskOptions(max_task_wait=timedelta(milliseconds=50)))

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="mw")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="mw", status="working")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="exceeded max_task_wait"):
        await tool.call_tool("slow_op")

    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is True


async def test_call_tool_as_task_max_wait_cancels_even_when_local_cancel_option_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locks contract: max_task_wait abandonment ignores the local-cancel option."""
    from agent_framework import MCPTaskOptions
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool(
        task_options=MCPTaskOptions(
            cancel_remote_task_on_local_cancellation=False,
            max_task_wait=timedelta(milliseconds=50),
        ),
    )

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="mw2")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="mw2", status="working")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="exceeded max_task_wait"):
        await tool.call_tool("slow_op")

    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is True


async def test_call_tool_as_task_poll_transient_request_timeout_keeps_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    poll_calls = 0
    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal poll_calls, cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="t1")
        if method == "tasks/get":
            poll_calls += 1
            if poll_calls == 1:
                raise McpError(types.ErrorData(code=int(httpx.codes.REQUEST_TIMEOUT), message="slow poll"))
            return _make_task_snapshot(task_id="t1", status="completed")
        if method == "tasks/result":
            return _make_payload("recovered after transient")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    result = await tool.call_tool("slow_op")
    assert _mcp_result_to_text(result) == "recovered after transient"
    assert poll_calls == 2
    # Transient retry must not fire cancel.
    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is False


async def test_call_tool_as_task_poll_hard_mcperror_cancels_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="h1")
        if method == "tasks/get":
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="bad task id"))
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="bad task id"):
        await tool.call_tool("slow_op")

    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is True


async def test_call_tool_as_task_malformed_tasks_get_response_cancels_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed tasks/get response counts as abandonment (task may still be running)."""
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    # Result without a valid GetTaskResult shape (no taskId/status/etc.).
    malformed = types.Result.model_validate({"some": "junk"})

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="m1")
        if method == "tasks/get":
            return malformed
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="malformed tasks/get"):
        await tool.call_tool("slow_op")

    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    assert cancel_called is True


async def test_call_tool_as_task_failed_terminal_does_not_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminal failures (server already done) must NOT fire tasks/cancel."""
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="f1")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="f1", status="failed", status_message="boom")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="task failed: boom"):
        await tool.call_tool("slow_op")

    # Let any (incorrect) background work settle, then verify no cancel.
    await asyncio.sleep(0.02)
    assert cancel_called is False


async def test_try_cancel_task_logs_warning_on_timeout(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_framework import _mcp as _mcp_module

    # Shorten cancel timeout so the test is fast.
    monkeypatch.setattr(_mcp_module, "_MCP_TASK_CANCEL_TIMEOUT", _mcp_module.timedelta(milliseconds=20))

    tool = _make_task_tool()

    async def hang(*_a: Any, **_kw: Any) -> Any:
        await asyncio.sleep(10.0)

    tool.session.send_request = AsyncMock(side_effect=hang)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with caplog.at_level(logging.WARNING, logger=_mcp_module.logger.name):
        await tool._try_cancel_task("hang-1")

    assert any("timed out" in r.getMessage() and "hang-1" in r.getMessage() for r in caplog.records)


async def test_mcp_task_options_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    from agent_framework import MCPTaskOptions

    opts = MCPTaskOptions()
    with pytest.raises(FrozenInstanceError):
        opts.default_ttl = timedelta(seconds=5)  # type: ignore[misc]  # ty: ignore[invalid-assignment]


async def test_mcp_task_options_max_task_wait_rejects_non_positive() -> None:
    from agent_framework import MCPTaskOptions

    with pytest.raises(ValueError, match="positive"):
        MCPTaskOptions(max_task_wait=timedelta(0))
    with pytest.raises(ValueError, match="positive"):
        MCPTaskOptions(max_task_wait=timedelta(seconds=-1))


async def test_fetch_task_result_hard_mcperror_raises_without_cancel() -> None:
    """tasks/result hard McpError must wrap as ToolExecutionException without cancel (server done)."""
    tool = _make_task_tool()

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="hf")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="hf", status="completed")
        if method == "tasks/result":
            raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message="payload vanished"))
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(ToolExecutionException, match="payload vanished"):
        await tool.call_tool("slow_op")

    # No raw McpError leak and no cancel — server already reported the task as done.
    await asyncio.sleep(0.02)
    assert cancel_called is False


async def test_completion_wait_timeout_without_max_wait_is_not_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stray asyncio.TimeoutError during the completion wait must not pretend the deadline
    expired when max_task_wait is None (and must not fire a spurious tasks/cancel).
    """
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    tool = _make_task_tool()

    def boom_parser(_: Any) -> list[Content]:
        raise asyncio.TimeoutError

    tool.parse_tool_results = boom_parser

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="t2")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="t2", status="completed")
        if method == "tasks/result":
            return _make_payload("ok")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(asyncio.TimeoutError):
        await tool.call_tool("slow_op")

    # Must NOT translate to max_task_wait expiry and must NOT cancel.
    await asyncio.sleep(0.02)
    assert cancel_called is False


async def test_completion_wait_inner_timeout_with_max_wait_set_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An asyncio.TimeoutError raised by the completion wait itself must propagate
    unchanged even when max_task_wait IS set, and must NOT fire a spurious cancel.
    """
    from agent_framework import MCPTaskOptions
    from agent_framework import _mcp as _mcp_module

    monkeypatch.setattr(_mcp_module, "_MCP_TASK_MIN_POLL_INTERVAL", _mcp_module.timedelta(milliseconds=1))

    # Deadline set comfortably above the actual test run time.
    tool = _make_task_tool(task_options=MCPTaskOptions(max_task_wait=timedelta(seconds=5)))

    def boom_parser(_: Any) -> list[Content]:
        raise asyncio.TimeoutError("inner parser timeout")

    tool.parse_tool_results = boom_parser

    cancel_called = False

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        nonlocal cancel_called
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="t3")
        if method == "tasks/get":
            return _make_task_snapshot(task_id="t3", status="completed")
        if method == "tasks/result":
            return _make_payload("ok")
        if method == "tasks/cancel":
            cancel_called = True
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    with pytest.raises(asyncio.TimeoutError, match="inner parser timeout"):
        await tool.call_tool("slow_op")

    # Inner TimeoutError must NOT be translated into "exceeded max_task_wait" and must NOT cancel.
    await asyncio.sleep(0.02)
    assert cancel_called is False


async def test_max_wait_interrupts_long_poll_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deadline must cancel through a long ``asyncio.sleep`` (clamped to MAX), not wait it out."""
    from agent_framework import MCPTaskOptions

    tool = _make_task_tool(task_options=MCPTaskOptions(max_task_wait=timedelta(milliseconds=100)))

    async def fake_send(request: Any, _result_type: Any, *_a: Any, **_kw: Any) -> Any:
        method = request.root.method
        if method == "tools/call":
            return _make_create_task_result(task_id="ds")
        if method == "tasks/get":
            # Suggest a 5s poll interval (gets clamped to MAX=5s); wait_for must cut through it.
            return _make_task_snapshot(task_id="ds", status="working", poll_interval_ms=5000)
        if method == "tasks/cancel":
            return types.CancelTaskResult()  # type: ignore[call-arg]  # pyrefly: ignore[missing-argument]  # ty: ignore[missing-argument]
        raise AssertionError(method)

    tool.session.send_request = AsyncMock(side_effect=fake_send)  # type: ignore[method-assign, union-attr]  # ty: ignore[invalid-assignment]

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(ToolExecutionException, match="exceeded max_task_wait"):
        await tool.call_tool("slow_op")
    elapsed = loop.time() - started

    # Should fire near the 100ms deadline, well below the 5s clamped sleep.
    assert elapsed < 1.0, f"deadline did not interrupt long sleep (elapsed={elapsed:.3f}s)"

    pending = list(tool._pending_reload_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


# endregion


# region additional_tool_argument_names / allowlist filtering


def test_normalize_additional_tool_argument_names_none() -> None:
    global_extras, per_tool = _normalize_additional_tool_argument_names(None)
    assert global_extras == set()
    assert per_tool == {}


def test_normalize_additional_tool_argument_names_sequence() -> None:
    global_extras, per_tool = _normalize_additional_tool_argument_names(["a", "b", "a"])
    assert global_extras == {"a", "b"}
    assert per_tool == {}


def test_normalize_additional_tool_argument_names_single_string() -> None:
    # A bare string must be treated as a single name, not split into characters.
    global_extras, per_tool = _normalize_additional_tool_argument_names("conversation_id")
    assert global_extras == {"conversation_id"}
    assert per_tool == {}


def test_normalize_additional_tool_argument_names_mapping_with_global_key() -> None:
    global_extras, per_tool = _normalize_additional_tool_argument_names({
        "*": ["g1"],
        "tool_a": ["a1", "a2"],
        "tool_b": ["b1"],
    })
    assert global_extras == {"g1"}
    assert per_tool == {"tool_a": {"a1", "a2"}, "tool_b": {"b1"}}


def test_normalize_additional_tool_argument_names_mapping_with_string_values() -> None:
    # A bare string mapping value is a single name, not an iterable of characters.
    global_extras, per_tool = _normalize_additional_tool_argument_names({
        "*": "conversation_id",
        "tool_a": "custom",
    })
    assert global_extras == {"conversation_id"}
    assert per_tool == {"tool_a": {"custom"}}


def test_prepare_call_kwargs_strips_undeclared_arguments() -> None:
    server = MCPTool(name="test_server")  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param"}}

    filtered, meta = server._prepare_call_kwargs(
        "test_tool",
        {"param": "value", "conversation_id": "c", "thread": object(), "unexpected": 1},
    )

    assert filtered == {"param": "value"}
    assert meta is None


def test_prepare_call_kwargs_global_extras_allowed() -> None:
    server = MCPTool(name="test_server", additional_tool_argument_names=["conversation_id"])  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param"}}

    filtered, _ = server._prepare_call_kwargs(
        "test_tool",
        {"param": "value", "conversation_id": "c", "options": {}},
    )

    assert filtered == {"param": "value", "conversation_id": "c"}


def test_prepare_call_kwargs_per_tool_and_global_extras() -> None:
    server = MCPTool(  # type: ignore[abstract]
        name="test_server",
        additional_tool_argument_names={"*": ["conversation_id"], "test_tool": ["custom"]},
    )
    server._tool_param_names_by_name = {"test_tool": {"param"}, "other_tool": {"x"}}

    filtered, _ = server._prepare_call_kwargs(
        "test_tool",
        {"param": "v", "conversation_id": "c", "custom": "y", "thread": object()},
    )
    assert filtered == {"param": "v", "conversation_id": "c", "custom": "y"}

    # The per-tool extra does not leak to other tools; the global one still applies.
    filtered_other, _ = server._prepare_call_kwargs(
        "other_tool",
        {"x": 1, "conversation_id": "c", "custom": "y"},
    )
    assert filtered_other == {"x": 1, "conversation_id": "c"}


def test_prepare_call_kwargs_denylist_guards_server_declared_names() -> None:
    # The denylist is a safety net for framework-named params a server *declares* in its
    # schema: they are dropped so internal objects never leak. Names explicitly opted in
    # via extras always win.
    server = MCPTool(name="test_server", additional_tool_argument_names=["conversation_id"])  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param", "thread"}}

    filtered, _ = server._prepare_call_kwargs(
        "test_tool",
        {"param": "v", "thread": object(), "conversation_id": "c"},
    )
    # "thread" is declared by the schema but denylisted -> dropped; conversation_id opted in -> kept.
    assert filtered == {"param": "v", "conversation_id": "c"}


def test_prepare_call_kwargs_extras_override_denylist() -> None:
    # Opting a denylisted framework name back in via extras takes precedence over the
    # denylist safety net. "thread" is on the framework denylist, but an explicit extra wins.
    server = MCPTool(name="test_server", additional_tool_argument_names=["thread"])  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param"}}

    sentinel = object()
    filtered, _ = server._prepare_call_kwargs(
        "test_tool",
        {"param": "v", "thread": sentinel, "conversation_id": "c"},
    )
    # "thread" opted in via extras -> kept despite the denylist; conversation_id is denylisted,
    # not declared, and not opted in -> dropped.
    assert filtered == {"param": "v", "thread": sentinel}


def test_prepare_call_kwargs_zero_arg_tool_passes_no_arguments() -> None:
    server = MCPTool(name="test_server")  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": set()}

    filtered, _ = server._prepare_call_kwargs(
        "test_tool",
        {"conversation_id": "c", "thread": object(), "stray": 1},
    )
    assert filtered == {}


def test_prepare_call_kwargs_unknown_tool_passes_only_global_extras() -> None:
    server = MCPTool(name="test_server", additional_tool_argument_names=["conversation_id"])  # type: ignore[abstract]
    # No entry in _tool_param_names_by_name for this tool name.

    filtered, _ = server._prepare_call_kwargs(
        "unknown_tool",
        {"conversation_id": "c", "other": 1},
    )
    assert filtered == {"conversation_id": "c"}


def test_prepare_call_kwargs_extracts_meta() -> None:
    server = MCPTool(name="test_server")  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param"}}

    filtered, meta = server._prepare_call_kwargs(
        "test_tool",
        {"param": "v", "_meta": {"trace": "abc"}},
    )
    assert filtered == {"param": "v"}
    assert meta is not None
    assert meta.get("trace") == "abc"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "_leading-underscore",
        "trailing-underscore_",
        "abc/",
        "1bad.example/name",
        "bad..example/name",
        "bad.example/_name",
        "bad.example/name_",
    ],
)
def test_prepare_call_kwargs_rejects_invalid_meta_key_names(key: str) -> None:
    server = MCPTool(name="test_server")  # type: ignore[abstract]
    server._tool_param_names_by_name = {"test_tool": {"param"}}

    with pytest.raises(ToolExecutionException, match="Invalid MCP _meta key name"):
        server._prepare_call_kwargs(
            "test_tool",
            {"param": "v", "_meta": {key: "value"}},
        )


async def test_call_tool_forwards_only_declared_arguments() -> None:
    """End-to-end: framework runtime kwargs are stripped before reaching the server."""

    class TestServer(MCPTool):
        async def connect(self):  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
            self.session = Mock(spec=ClientSession)
            self.session.list_tools = AsyncMock(
                return_value=types.ListToolsResult(
                    tools=[
                        types.Tool(
                            name="test_tool",
                            description="Test tool",
                            inputSchema={
                                "type": "object",
                                "properties": {"param": {"type": "string"}},
                                "required": ["param"],
                            },
                        )
                    ]
                )
            )
            self.session.call_tool = AsyncMock(
                return_value=types.CallToolResult(content=[types.TextContent(type="text", text="ok")])
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None  # type: ignore[return-value]  # pyrefly: ignore[bad-return]  # ty: ignore[invalid-return-type]

    server = TestServer(name="test_server", additional_tool_argument_names=["conversation_id"])
    async with server:
        await server.load_tools()
        session_mock = server.session
        await server.call_tool(
            "test_tool",
            param="value",
            conversation_id="c",
            thread=object(),
            response_format=object(),
        )

        session_mock.call_tool.assert_called_once()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        _, call_kwargs = session_mock.call_tool.call_args  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert call_kwargs["arguments"] == {"param": "value", "conversation_id": "c"}


# endregion
