# Copyright (c) Microsoft. All rights reserved.
# type: ignore[reportPrivateUsage]
import os
from contextlib import _AsyncGeneratorContextManager  # type: ignore
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl, ValidationError

from agent_framework import (
    ChatMessage,
    DataContent,
    MCPStdioTool,
    MCPStreamableHTTPTool,
    MCPWebsocketTool,
    Role,
    TextContent,
    ToolProtocol,
    UriContent,
)
from agent_framework._mcp import (
    MCPTool,
    _ai_content_to_mcp_types,
    _chat_message_to_mcp_types,
    _get_input_model_from_mcp_prompt,
    _get_input_model_from_mcp_tool,
    _mcp_call_tool_result_to_ai_contents,
    _mcp_prompt_message_to_chat_message,
    _mcp_type_to_ai_content,
    _normalize_mcp_name,
)
from agent_framework.exceptions import ToolExecutionException

# Integration test skip condition
skip_if_mcp_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true" or os.getenv("LOCAL_MCP_URL", "") == "",
    reason="No LOCAL_MCP_URL provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


# Helper function tests
def test_normalize_mcp_name():
    """Test MCP name normalization."""
    assert _normalize_mcp_name("valid_name") == "valid_name"
    assert _normalize_mcp_name("name-with-dashes") == "name-with-dashes"
    assert _normalize_mcp_name("name.with.dots") == "name.with.dots"
    assert _normalize_mcp_name("name with spaces") == "name-with-spaces"
    assert _normalize_mcp_name("name@with#special$chars") == "name-with-special-chars"
    assert _normalize_mcp_name("name/with\\slashes") == "name-with-slashes"


def test_mcp_prompt_message_to_ai_content():
    """Test conversion from MCP prompt message to AI content."""
    mcp_message = types.PromptMessage(role="user", content=types.TextContent(type="text", text="Hello, world!"))
    ai_content = _mcp_prompt_message_to_chat_message(mcp_message)

    assert isinstance(ai_content, ChatMessage)
    assert ai_content.role.value == "user"
    assert len(ai_content.contents) == 1
    assert isinstance(ai_content.contents[0], TextContent)
    assert ai_content.contents[0].text == "Hello, world!"
    assert ai_content.raw_representation == mcp_message


def test_mcp_call_tool_result_to_ai_contents():
    """Test conversion from MCP tool result to AI contents."""
    mcp_result = types.CallToolResult(
        content=[
            types.TextContent(type="text", text="Result text"),
            types.ImageContent(type="image", data="data:image/png;base64,xyz", mimeType="image/png"),
        ]
    )
    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

    assert len(ai_contents) == 2
    assert isinstance(ai_contents[0], TextContent)
    assert ai_contents[0].text == "Result text"
    assert isinstance(ai_contents[1], DataContent)
    assert ai_contents[1].uri == "data:image/png;base64,xyz"
    assert ai_contents[1].media_type == "image/png"


def test_mcp_content_types_to_ai_content_text():
    """Test conversion of MCP text content to AI content."""
    mcp_content = types.TextContent(type="text", text="Sample text")
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, TextContent)
    assert ai_content.text == "Sample text"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_image():
    """Test conversion of MCP image content to AI content."""
    mcp_content = types.ImageContent(type="image", data="data:image/jpeg;base64,abc", mimeType="image/jpeg")
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, DataContent)
    assert ai_content.uri == "data:image/jpeg;base64,abc"
    assert ai_content.media_type == "image/jpeg"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_audio():
    """Test conversion of MCP audio content to AI content."""
    mcp_content = types.AudioContent(type="audio", data="data:audio/wav;base64,def", mimeType="audio/wav")
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, DataContent)
    assert ai_content.uri == "data:audio/wav;base64,def"
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
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, UriContent)
    assert ai_content.uri == "https://example.com/resource"
    assert ai_content.media_type == "application/json"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_embedded_resource_text():
    """Test conversion of MCP embedded text resource to AI content."""
    text_resource = types.TextResourceContents(
        uri=AnyUrl("file://test.txt"), mimeType="text/plain", text="Embedded text content"
    )
    mcp_content = types.EmbeddedResource(type="resource", resource=text_resource)
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, TextContent)
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
    ai_content = _mcp_type_to_ai_content(mcp_content)

    assert isinstance(ai_content, DataContent)
    assert ai_content.uri == "data:application/octet-stream;base64,dGVzdCBkYXRh"
    assert ai_content.media_type == "application/octet-stream"
    assert ai_content.raw_representation == mcp_content


def test_ai_content_to_mcp_content_types_text():
    """Test conversion of AI text content to MCP content."""
    ai_content = TextContent(text="Sample text")
    mcp_content = _ai_content_to_mcp_types(ai_content)

    assert isinstance(mcp_content, types.TextContent)
    assert mcp_content.type == "text"
    assert mcp_content.text == "Sample text"


def test_ai_content_to_mcp_content_types_data_image():
    """Test conversion of AI data content to MCP content."""
    ai_content = DataContent(uri="data:image/png;base64,xyz", media_type="image/png")
    mcp_content = _ai_content_to_mcp_types(ai_content)

    assert isinstance(mcp_content, types.ImageContent)
    assert mcp_content.type == "image"
    assert mcp_content.data == "data:image/png;base64,xyz"
    assert mcp_content.mimeType == "image/png"


def test_ai_content_to_mcp_content_types_data_audio():
    """Test conversion of AI data content to MCP content."""
    ai_content = DataContent(uri="data:audio/mpeg;base64,xyz", media_type="audio/mpeg")
    mcp_content = _ai_content_to_mcp_types(ai_content)

    assert isinstance(mcp_content, types.AudioContent)
    assert mcp_content.type == "audio"
    assert mcp_content.data == "data:audio/mpeg;base64,xyz"
    assert mcp_content.mimeType == "audio/mpeg"


def test_ai_content_to_mcp_content_types_data_binary():
    """Test conversion of AI data content to MCP content."""
    ai_content = DataContent(uri="data:application/octet-stream;base64,xyz", media_type="application/octet-stream")
    mcp_content = _ai_content_to_mcp_types(ai_content)

    assert isinstance(mcp_content, types.EmbeddedResource)
    assert mcp_content.type == "resource"
    assert mcp_content.resource.blob == "data:application/octet-stream;base64,xyz"
    assert mcp_content.resource.mimeType == "application/octet-stream"


def test_ai_content_to_mcp_content_types_uri():
    """Test conversion of AI URI content to MCP content."""
    ai_content = UriContent(uri="https://example.com/resource", media_type="application/json")
    mcp_content = _ai_content_to_mcp_types(ai_content)

    assert isinstance(mcp_content, types.ResourceLink)
    assert mcp_content.type == "resource_link"
    assert str(mcp_content.uri) == "https://example.com/resource"
    assert mcp_content.mimeType == "application/json"


def test_chat_message_to_mcp_types():
    message = ChatMessage(
        role="user",
        contents=[TextContent(text="test"), DataContent(uri="data:image/png;base64,xyz", media_type="image/png")],
    )
    mcp_contents = _chat_message_to_mcp_types(message)
    assert len(mcp_contents) == 2
    assert isinstance(mcp_contents[0], types.TextContent)
    assert isinstance(mcp_contents[1], types.ImageContent)


def test_get_input_model_from_mcp_tool():
    """Test creation of input model from MCP tool."""
    tool = types.Tool(
        name="test_tool",
        description="A test tool",
        inputSchema={
            "type": "object",
            "properties": {"param1": {"type": "string"}, "param2": {"type": "number"}},
            "required": ["param1"],
        },
    )
    model = _get_input_model_from_mcp_tool(tool)

    # Create an instance to verify the model works
    instance = model(param1="test", param2=42)
    assert instance.param1 == "test"
    assert instance.param2 == 42

    # Test validation
    with pytest.raises(ValidationError):  # Missing required param1
        model(param2=42)


def test_get_input_model_from_mcp_tool_with_nested_object():
    """Test creation of input model from MCP tool with nested object property."""
    tool = types.Tool(
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
    model = _get_input_model_from_mcp_tool(tool)

    # Create an instance to verify the model works with nested objects
    instance = model(params={"customer_id": 251})
    assert instance.params == {"customer_id": 251}
    assert isinstance(instance.params, dict)

    # Verify model_dump produces the correct nested structure
    dumped = instance.model_dump()
    assert dumped == {"params": {"customer_id": 251}}


def test_get_input_model_from_mcp_tool_with_ref_schema():
    """Test creation of input model from MCP tool with $ref schema.

    This simulates a FastMCP tool that uses Pydantic models with $ref in the schema.
    The schema should be resolved and nested objects should be preserved.
    """
    # This is similar to what FastMCP generates when you have:
    # async def get_customer_detail(params: CustomerIdParam) -> CustomerDetail
    tool = types.Tool(
        name="get_customer_detail",
        description="Get customer details",
        inputSchema={
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
    )
    model = _get_input_model_from_mcp_tool(tool)

    # Create an instance to verify the model works with $ref schemas
    instance = model(params={"customer_id": 251})
    assert instance.params == {"customer_id": 251}
    assert isinstance(instance.params, dict)

    # Verify model_dump produces the correct nested structure
    dumped = instance.model_dump()
    assert dumped == {"params": {"customer_id": 251}}


def test_get_input_model_from_mcp_prompt():
    """Test creation of input model from MCP prompt."""
    prompt = types.Prompt(
        name="test_prompt",
        description="A test prompt",
        arguments=[
            types.PromptArgument(name="arg1", description="First argument", required=True),
            types.PromptArgument(name="arg2", description="Second argument", required=False),
        ],
    )
    model = _get_input_model_from_mcp_prompt(prompt)

    # Create an instance to verify the model works
    instance = model(arg1="test", arg2="optional")
    assert instance.arg1 == "test"
    assert instance.arg2 == "optional"

    # Test validation
    with pytest.raises(ValidationError):  # Missing required arg1
        model(arg2="optional")


# MCPTool tests
async def test_local_mcp_server_initialization():
    """Test MCPTool initialization."""
    server = MCPTool(name="test_server")
    assert isinstance(server, ToolProtocol)
    assert server.name == "test_server"
    assert server.session is None
    assert server.functions == []


async def test_local_mcp_server_context_manager():
    """Test MCPTool as context manager."""

    class TestServer(MCPTool):
        async def connect(self):
            # Mock connection
            self.session = Mock(spec=ClientSession)

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None

    server = TestServer(name="test_server")
    async with server:
        assert server.session is not None

    assert server.session is None


async def test_local_mcp_server_load_functions():
    """Test loading functions from MCP server."""

    class TestServer(MCPTool):
        async def connect(self):
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
            return None

    server = TestServer(name="test_server")
    assert isinstance(server, ToolProtocol)
    async with server:
        await server.load_tools()
        assert len(server.functions) == 1
        assert server.functions[0].name == "test_tool"


async def test_local_mcp_server_load_prompts():
    """Test loading prompts from MCP server."""

    class TestServer(MCPTool):
        async def connect(self):
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
            return None

    server = TestServer(name="test_server")
    async with server:
        await server.load_prompts()
        assert len(server.functions) == 1
        assert server.functions[0].name == "test_prompt"


async def test_local_mcp_server_function_execution():
    """Test function execution through MCP server."""

    class TestServer(MCPTool):
        async def connect(self):
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
            return None

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]
        result = await func.invoke(param="test_value")

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].text == "Tool executed successfully"


async def test_local_mcp_server_function_execution_with_nested_object():
    """Test function execution through MCP server with nested object arguments."""

    class TestServer(MCPTool):
        async def connect(self):
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
            return None

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        # Call with nested object
        result = await func.invoke(params={"customer_id": 251})

        assert len(result) == 1
        assert isinstance(result[0], TextContent)

        # Verify the session.call_tool was called with the correct nested structure
        server.session.call_tool.assert_called_once()
        call_args = server.session.call_tool.call_args
        assert call_args.kwargs["arguments"] == {"params": {"customer_id": 251}}


async def test_local_mcp_server_function_execution_error():
    """Test function execution error handling."""

    class TestServer(MCPTool):
        async def connect(self):
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
            return None

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]

        with pytest.raises(ToolExecutionException):
            await func.invoke(param="test_value")


async def test_local_mcp_server_prompt_execution():
    """Test prompt execution through MCP server."""

    class TestMCPTool(MCPTool):
        async def connect(self):
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
                        types.PromptMessage(role="user", content=types.TextContent(type="text", text="Test message"))
                    ],
                )
            )

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None

    server = TestMCPTool(name="test_server")
    async with server:
        await server.load_prompts()
        prompt = server.functions[0]
        result = await prompt.invoke(arg="test_value")

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == Role.USER
        assert len(result[0].contents) == 1
        assert result[0].contents[0].text == "Test message"


@pytest.mark.parametrize(
    "approval_mode,expected_approvals",
    [
        ("always_require", {"tool_one": "always_require", "tool_two": "always_require"}),
        ("never_require", {"tool_one": "never_require", "tool_two": "never_require"}),
        (
            {"always_require_approval": ["tool_one"], "never_require_approval": ["tool_two"]},
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
        async def connect(self):
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
            return None

    server = TestServer(name="test_server", approval_mode=approval_mode)
    async with server:
        await server.load_tools()
        assert len(server.functions) == 2

        # Verify each tool has the expected approval mode
        for func in server.functions:
            assert func.approval_mode == expected_approvals[func.name]


@pytest.mark.parametrize(
    "allowed_tools,expected_count,expected_names",
    [
        (None, 3, ["tool_one", "tool_two", "tool_three"]),  # None means all tools are allowed
        (["tool_one"], 1, ["tool_one"]),  # Only tool_one is allowed
        (["tool_one", "tool_three"], 2, ["tool_one", "tool_three"]),  # Two tools allowed
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
        async def connect(self):
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
            return None

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
@skip_if_mcp_integration_tests_disabled
async def test_streamable_http_integration():
    """Test MCP StreamableHTTP integration."""
    url = os.environ.get("LOCAL_MCP_URL", "")
    if not url.startswith("http"):
        pytest.skip("LOCAL_MCP_URL is not an HTTP URL")

    tool = MCPStreamableHTTPTool(name="integration_test", url=url)

    async with tool:
        # Test that we can connect and load tools
        assert tool.session is not None
        assert isinstance(tool.functions, list)

        # If there are functions available, try to get information about one
        assert tool.functions, "The MCP server should have at least one function."

        func = tool.functions[0]

        assert hasattr(func, "name")
        assert hasattr(func, "description")

        result = await func.invoke(query="What is Agent Framework?")
        assert result[0].text is not None
