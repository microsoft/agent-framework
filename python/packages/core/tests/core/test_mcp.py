# Copyright (c) Microsoft. All rights reserved.
# type: ignore[reportPrivateUsage]
import os
from contextlib import _AsyncGeneratorContextManager  # type: ignore
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl, BaseModel, ValidationError

from agent_framework import (
    ChatMessage,
    Content,
    MCPStdioTool,
    MCPStreamableHTTPTool,
    MCPWebsocketTool,
    Role,
    ToolProtocol,
)
from agent_framework._mcp import (
    MCPTool,
    _get_input_model_from_mcp_prompt,
    _get_input_model_from_mcp_tool,
    _normalize_mcp_name,
    _parse_content_from_mcp,
    _parse_contents_from_mcp_tool_result,
    _parse_message_from_mcp,
    _prepare_content_for_mcp,
    _prepare_message_for_mcp,
)
from agent_framework.exceptions import ToolException, ToolExecutionException

# Integration test skip condition
skip_if_mcp_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true" or os.getenv("LOCAL_MCP_URL", "") == "",
    reason=(
        "No LOCAL_MCP_URL provided; skipping integration tests."
        if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
        else "Integration tests are disabled."
    ),
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
    ai_content = _parse_message_from_mcp(mcp_message)

    assert isinstance(ai_content, ChatMessage)
    assert ai_content.role.value == "user"
    assert len(ai_content.contents) == 1
    assert ai_content.contents[0].type == "text"
    assert ai_content.contents[0].text == "Hello, world!"
    assert ai_content.raw_representation == mcp_message


def test_parse_contents_from_mcp_tool_result():
    """Test conversion from MCP tool result to AI contents."""
    mcp_result = types.CallToolResult(
        content=[
            types.TextContent(type="text", text="Result text"),
            types.ImageContent(type="image", data="eHl6", mimeType="image/png"),  # base64 for "xyz"
            types.ImageContent(type="image", data="YWJj", mimeType="image/webp"),  # base64 for "abc"
        ]
    )
    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    assert len(ai_contents) == 3
    assert ai_contents[0].type == "text"
    assert ai_contents[0].text == "Result text"
    assert ai_contents[1].type == "data"
    assert ai_contents[1].uri == "data:image/png;base64,eHl6"
    assert ai_contents[1].media_type == "image/png"
    assert ai_contents[2].type == "data"
    assert ai_contents[2].uri == "data:image/webp;base64,YWJj"
    assert ai_contents[2].media_type == "image/webp"


def test_mcp_call_tool_result_with_meta_error():
    """Test conversion from MCP tool result with _meta field containing isError=True."""
    # Create a mock CallToolResult with _meta field containing error information
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Error occurred")],
        _meta={"isError": True, "errorCode": "TOOL_ERROR", "errorMessage": "Tool execution failed"},
    )

    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    assert len(ai_contents) == 1
    assert ai_contents[0].type == "text"
    assert ai_contents[0].text == "Error occurred"

    # Check that _meta data is merged into additional_properties
    assert ai_contents[0].additional_properties is not None
    assert ai_contents[0].additional_properties["isError"] is True
    assert ai_contents[0].additional_properties["errorCode"] == "TOOL_ERROR"
    assert ai_contents[0].additional_properties["errorMessage"] == "Tool execution failed"


def test_mcp_call_tool_result_with_meta_arbitrary_data():
    """Test conversion from MCP tool result with _meta field containing arbitrary metadata.

    Note: The _meta field is optional and can contain any structure that a specific
    MCP server chooses to provide. This test uses example metadata to verify that
    whatever is provided gets preserved in additional_properties.
    """
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Success result")],
        _meta={
            "serverVersion": "2.1.0",
            "executionId": "exec_abc123",
            "metrics": {"responseTime": 1.25, "memoryUsed": "64MB"},
            "source": "example-mcp-server",
            "customField": "arbitrary_value",
        },
    )

    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    assert len(ai_contents) == 1
    assert ai_contents[0].type == "text"
    assert ai_contents[0].text == "Success result"

    # Check that _meta data is preserved in additional_properties
    props = ai_contents[0].additional_properties
    assert props is not None
    assert props["serverVersion"] == "2.1.0"
    assert props["executionId"] == "exec_abc123"
    assert props["metrics"] == {"responseTime": 1.25, "memoryUsed": "64MB"}
    assert props["source"] == "example-mcp-server"
    assert props["customField"] == "arbitrary_value"


def test_mcp_call_tool_result_with_meta_merging_existing_properties():
    """Test that _meta data merges correctly with existing additional_properties."""
    # Create content with existing additional_properties
    text_content = types.TextContent(type="text", text="Test content")
    mcp_result = types.CallToolResult(content=[text_content], _meta={"newField": "newValue", "isError": False})

    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    assert len(ai_contents) == 1
    content = ai_contents[0]

    # Check that _meta data is present in additional_properties
    assert content.additional_properties is not None
    assert content.additional_properties["newField"] == "newValue"
    assert content.additional_properties["isError"] is False


def test_mcp_call_tool_result_with_meta_none():
    """Test that missing _meta field is handled gracefully."""
    mcp_result = types.CallToolResult(content=[types.TextContent(type="text", text="No meta test")])
    # No _meta field set

    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    assert len(ai_contents) == 1
    assert ai_contents[0].type == "text"
    assert ai_contents[0].text == "No meta test"

    # Should handle gracefully when no _meta field exists
    # additional_properties may be None or empty dict
    props = ai_contents[0].additional_properties
    assert props is None or props == {}


def test_mcp_call_tool_result_regression_successful_workflow():
    """Regression test to ensure existing successful workflows remain unchanged."""
    # Test the original successful workflow still works
    mcp_result = types.CallToolResult(
        content=[
            types.TextContent(type="text", text="Success message"),
            types.ImageContent(type="image", data="YWJjMTIz", mimeType="image/jpeg"),  # base64 for "abc123"
        ]
    )

    ai_contents = _parse_contents_from_mcp_tool_result(mcp_result)

    # Verify basic conversion still works correctly
    assert len(ai_contents) == 2

    text_content = ai_contents[0]
    assert text_content.type == "text"
    assert text_content.text == "Success message"

    image_content = ai_contents[1]
    assert image_content.type == "data"
    assert image_content.uri == "data:image/jpeg;base64,YWJjMTIz"
    assert image_content.media_type == "image/jpeg"

    # Should have no additional_properties when no _meta field
    assert text_content.additional_properties is None or text_content.additional_properties == {}
    assert image_content.additional_properties is None or image_content.additional_properties == {}


def test_mcp_content_types_to_ai_content_text():
    """Test conversion of MCP text content to AI content."""
    mcp_content = types.TextContent(type="text", text="Sample text")
    ai_content = _parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "text"
    assert ai_content.text == "Sample text"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_image():
    """Test conversion of MCP image content to AI content."""
    # MCP can send data as base64 string or as bytes
    mcp_content = types.ImageContent(type="image", data="YWJj", mimeType="image/jpeg")  # base64 for b"abc"
    ai_content = _parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "data"
    assert ai_content.uri == "data:image/jpeg;base64,YWJj"
    assert ai_content.media_type == "image/jpeg"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_audio():
    """Test conversion of MCP audio content to AI content."""
    # Use properly padded base64
    mcp_content = types.AudioContent(type="audio", data="ZGVm", mimeType="audio/wav")  # base64 for b"def"
    ai_content = _parse_content_from_mcp(mcp_content)[0]

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
    ai_content = _parse_content_from_mcp(mcp_content)[0]

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
    ai_content = _parse_content_from_mcp(mcp_content)[0]

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
    ai_content = _parse_content_from_mcp(mcp_content)[0]

    assert ai_content.type == "data"
    assert ai_content.uri == "data:application/octet-stream;base64,dGVzdCBkYXRh"
    assert ai_content.media_type == "application/octet-stream"
    assert ai_content.raw_representation == mcp_content


def test_ai_content_to_mcp_content_types_text():
    """Test conversion of AI text content to MCP content."""
    ai_content = Content.from_text(text="Sample text")
    mcp_content = _prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.TextContent)
    assert mcp_content.type == "text"
    assert mcp_content.text == "Sample text"


def test_ai_content_to_mcp_content_types_data_image():
    """Test conversion of AI data content to MCP content."""
    ai_content = Content.from_uri(uri="data:image/png;base64,xyz", media_type="image/png")
    mcp_content = _prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.ImageContent)
    assert mcp_content.type == "image"
    assert mcp_content.data == "data:image/png;base64,xyz"
    assert mcp_content.mimeType == "image/png"


def test_ai_content_to_mcp_content_types_data_audio():
    """Test conversion of AI data content to MCP content."""
    ai_content = Content.from_uri(uri="data:audio/mpeg;base64,xyz", media_type="audio/mpeg")
    mcp_content = _prepare_content_for_mcp(ai_content)

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
    mcp_content = _prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.EmbeddedResource)
    assert mcp_content.type == "resource"
    assert mcp_content.resource.blob == "data:application/octet-stream;base64,xyz"
    assert mcp_content.resource.mimeType == "application/octet-stream"


def test_ai_content_to_mcp_content_types_uri():
    """Test conversion of AI URI content to MCP content."""
    ai_content = Content.from_uri(uri="https://example.com/resource", media_type="application/json")
    mcp_content = _prepare_content_for_mcp(ai_content)

    assert isinstance(mcp_content, types.ResourceLink)
    assert mcp_content.type == "resource_link"
    assert str(mcp_content.uri) == "https://example.com/resource"
    assert mcp_content.mimeType == "application/json"


def test_prepare_message_for_mcp():
    message = ChatMessage(
        role="user",
        contents=[
            Content.from_text(text="test"),
            Content.from_uri(uri="data:image/png;base64,xyz", media_type="image/png"),
        ],
    )
    mcp_contents = _prepare_message_for_mcp(message)
    assert len(mcp_contents) == 2
    assert isinstance(mcp_contents[0], types.TextContent)
    assert isinstance(mcp_contents[1], types.ImageContent)


@pytest.mark.parametrize(
    "test_id,input_schema,valid_data,expected_values,invalid_data,validation_check",
    [
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
    ],
)
def test_get_input_model_from_mcp_tool_parametrized(
    test_id, input_schema, valid_data, expected_values, invalid_data, validation_check
):
    """Parametrized test for JSON schema to Pydantic model conversion.

    This test covers various edge cases including:
    - Basic types with required/optional fields
    - Nested objects
    - $ref resolution
    - Typed arrays (strings, integers, objects)
    - Deeply nested structures
    - Complex $ref with nested structures
    - Mixed types

    To add a new test case, add a tuple to the parametrize decorator with:
    - test_id: A descriptive name for the test case
    - input_schema: The JSON schema (inputSchema dict)
    - valid_data: Valid data to instantiate the model
    - expected_values: Dict of expected values (supports dot notation for nested access)
    - invalid_data: Invalid data to test validation errors (None to skip)
    - validation_check: Optional callable to perform additional validation checks
    """
    tool = types.Tool(name="test_tool", description="A test tool", inputSchema=input_schema)
    model = _get_input_model_from_mcp_tool(tool)

    # Test valid data
    instance = model(**valid_data)

    # Check expected values
    for field_path, expected_value in expected_values.items():
        # Support dot notation and array indexing for nested access
        current = instance
        parts = field_path.replace("]", "").replace("[", ".").split(".")
        for part in parts:
            current = current[int(part)] if part.isdigit() else getattr(current, part)
        assert current == expected_value, f"Field {field_path} = {current}, expected {expected_value}"

    # Run additional validation checks if provided
    if validation_check:
        assert validation_check(instance), f"Validation check failed for {test_id}"

    # Test invalid data if provided
    if invalid_data is not None:
        with pytest.raises(ValidationError):
            model(**invalid_data)


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


async def test_mcp_tool_call_tool_with_meta_integration():
    """Test that call_tool method properly integrates with enhanced metadata extraction."""

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

            # Create a CallToolResult with _meta field
            tool_result = types.CallToolResult(
                content=[types.TextContent(type="text", text="Tool executed with metadata")],
                _meta={"executionTime": 1.5, "cost": {"usd": 0.002}, "isError": False, "toolVersion": "1.2.3"},
            )

            self.session.call_tool = AsyncMock(return_value=tool_result)

        def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
            return None

    server = TestServer(name="test_server")
    async with server:
        await server.load_tools()
        func = server.functions[0]
        result = await func.invoke(param="test_value")

        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "Tool executed with metadata"

        # Verify that _meta data is present in additional_properties
        props = result[0].additional_properties
        assert props is not None
        assert props["executionTime"] == 1.5
        assert props["cost"] == {"usd": 0.002}
        assert props["isError"] is False
        assert props["toolVersion"] == "1.2.3"


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
        assert result[0].type == "text"
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
        assert result[0].type == "text"

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
                        types.PromptMessage(
                            role="user",
                            content=types.TextContent(type="text", text="Test message"),
                        )
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
        (
            None,
            3,
            ["tool_one", "tool_two", "tool_three"],
        ),  # None means all tools are allowed
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

        result = await func.invoke(query="What is Agent Framework?")
        assert result[0].text is not None


@pytest.mark.flaky
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

    tool = MCPStreamableHTTPTool(name="integration_test", url=url, approval_mode="never_require")

    async with tool:
        # Verify initial connection
        assert tool.session is not None
        assert tool.is_connected is True
        assert len(tool.functions) > 0, "The MCP server should have at least one function."

        # Get the first function and invoke it
        func = tool.functions[0]
        first_result = await func.invoke(query="What is Agent Framework?")
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

        tool.session.call_tool = call_tool_with_error

        # Invoke the function again - this should trigger automatic reconnection on ClosedResourceError
        second_result = await func.invoke(query="What is Agent Framework?")
        assert second_result is not None
        assert len(second_result) > 0

        # Verify we have a new session and exit stack after reconnection
        assert tool.session is not None
        assert tool.session is not original_session, "Session should be replaced after reconnection"
        assert tool._exit_stack is not original_exit_stack, "Exit stack should be replaced after reconnection"
        assert tool.is_connected is True

        # Verify tools are still available after reconnection
        assert len(tool.functions) > 0

        # Both results should be valid (we don't compare content as it may vary)
        if hasattr(first_result[0], "text"):
            assert first_result[0].text is not None
        if hasattr(second_result[0], "text"):
            assert second_result[0].text is not None


async def test_mcp_tool_message_handler_notification():
    """Test that message_handler correctly processes tools/list_changed and prompts/list_changed
    notifications."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Mock the load_tools and load_prompts methods
    tool.load_tools = AsyncMock()
    tool.load_prompts = AsyncMock()

    # Test tools list changed notification
    tools_notification = Mock(spec=types.ServerNotification)
    tools_notification.root = Mock()
    tools_notification.root.method = "notifications/tools/list_changed"

    result = await tool.message_handler(tools_notification)
    assert result is None
    tool.load_tools.assert_called_once()

    # Reset mock
    tool.load_tools.reset_mock()

    # Test prompts list changed notification
    prompts_notification = Mock(spec=types.ServerNotification)
    prompts_notification.root = Mock()
    prompts_notification.root.method = "notifications/prompts/list_changed"

    result = await tool.message_handler(prompts_notification)
    assert result is None
    tool.load_prompts.assert_called_once()

    # Test unhandled notification
    unknown_notification = Mock(spec=types.ServerNotification)
    unknown_notification.root = Mock()
    unknown_notification.root.method = "notifications/unknown"

    result = await tool.message_handler(unknown_notification)
    assert result is None


async def test_mcp_tool_message_handler_error():
    """Test that message_handler gracefully handles exceptions by logging and returning None."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Test with exception message
    test_exception = RuntimeError("Test error message")

    # The message handler should log the error and return None
    result = await tool.message_handler(test_exception)
    assert result is None


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


async def test_mcp_tool_sampling_callback_chat_client_exception():
    """Test sampling callback when chat client raises exception."""
    tool = MCPStdioTool(name="test_tool", command="python")

    # Mock chat client that raises exception
    mock_chat_client = AsyncMock()
    mock_chat_client.get_response.side_effect = RuntimeError("Chat client error")

    tool.chat_client = mock_chat_client

    # Create mock params
    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = None
    params.stopSequences = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "Failed to get chat message content: Chat client error" in result.message


async def test_mcp_tool_sampling_callback_no_valid_content():
    """Test sampling callback when response has no valid content types."""
    from agent_framework import ChatMessage, Role

    tool = MCPStdioTool(name="test_tool", command="python")

    # Mock chat client with response containing only invalid content types
    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                Content.from_uri(
                    uri="data:application/json;base64,e30K",
                    media_type="application/json",
                )
            ],
        )
    ]
    mock_response.model_id = "test-model"
    mock_chat_client.get_response.return_value = mock_response

    tool.chat_client = mock_chat_client

    # Create mock params
    params = Mock()
    mock_message = Mock()
    mock_message.role = "user"
    mock_message.content = Mock()
    mock_message.content.text = "Test question"
    params.messages = [mock_message]
    params.temperature = None
    params.maxTokens = None
    params.stopSequences = None

    result = await tool.sampling_callback(Mock(), params)

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "Failed to get right content types from the response." in result.message


# Test error handling in connect() method


async def test_connect_session_creation_failure():
    """Test connect() raises ToolException when ClientSession creation fails."""
    tool = MCPStdioTool(name="test", command="test-command")

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())  # (read_stream, write_stream)
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)

    # Mock ClientSession to raise an exception
    with patch("agent_framework._mcp.ClientSession") as mock_session_class:
        mock_session_class.side_effect = RuntimeError("Session creation failed")

        with pytest.raises(ToolException) as exc_info:
            await tool.connect()

        assert "Failed to create MCP session" in str(exc_info.value)
        assert "Session creation failed" in str(exc_info.value.__cause__)


async def test_connect_initialization_failure_http_no_command():
    """Test connect() when session.initialize() fails for HTTP tool (no command attribute)."""
    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)

    # Mock successful session creation but failed initialization
    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=ConnectionError("Server not ready"))

    with patch("agent_framework._mcp.ClientSession") as mock_session_class:
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
    tool._exit_stack.aclose = AsyncMock()

    # Mock get_mcp_client to raise an exception
    tool.get_mcp_client = Mock(side_effect=RuntimeError("Transport failed"))

    with pytest.raises(ToolException):
        await tool.connect()

    # Verify cleanup was called
    tool._exit_stack.aclose.assert_called_once()


async def test_connect_cleanup_on_initialization_failure():
    """Test that _exit_stack.aclose() is called when initialization fails."""
    tool = MCPStdioTool(name="test", command="test-command")

    # Mock _exit_stack.aclose to verify it's called
    tool._exit_stack.aclose = AsyncMock()

    # Mock successful transport creation
    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    tool.get_mcp_client = Mock(return_value=mock_context_manager)

    # Mock successful session creation but failed initialization
    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=RuntimeError("Init failed"))

    with patch("agent_framework._mcp.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException):
            await tool.connect()

        # Verify cleanup was called
        tool._exit_stack.aclose.assert_called_once()


def test_mcp_stdio_tool_get_mcp_client_with_env_and_kwargs():
    """Test MCPStdioTool.get_mcp_client() with environment variables and client kwargs."""
    env_vars = {"PATH": "/usr/bin", "DEBUG": "1"}
    tool = MCPStdioTool(
        name="test",
        command="test-command",
        env=env_vars,
        custom_param="value1",
        another_param=42,
    )

    with patch("agent_framework._mcp.stdio_client"), patch("agent_framework._mcp.StdioServerParameters") as mock_params:
        tool.get_mcp_client()

        # Verify all parameters including custom kwargs were passed
        mock_params.assert_called_once_with(
            command="test-command",
            args=[],
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

    with patch("agent_framework._mcp.streamable_http_client") as mock_http_client:
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

    with patch("agent_framework._mcp.websocket_client") as mock_ws_client:
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
    tool = MCPTool(name="test_mcp_tool")

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

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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
        patch("agent_framework._mcp.streamable_http_client") as mock_client,
        patch("agent_framework._mcp.ClientSession") as mock_session_class,
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

    tool = MCPTool(name="test_tool")

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


async def test_load_prompts_with_pagination():
    """Test that load_prompts handles pagination correctly."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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


async def test_load_tools_pagination_exception_handling():
    """Test that load_tools handles exceptions during pagination gracefully."""
    from unittest.mock import AsyncMock

    from agent_framework._mcp import MCPTool

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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

    tool = MCPTool(name="test_tool")

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
    tool._exit_stack.aclose = AsyncMock()

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
        mock_session.call_tool.return_value = MagicMock(content=[])
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
            return MagicMock(content=[])

        mock_session.call_tool = call_tool_with_error

        # This call should trigger reconnection after ClosedResourceError
        result = await tool.call_tool("test_tool", arg1="value2")
        assert result is not None
        # Verify reconnect was attempted with reset=True
        assert mock_connect.call_count >= 1
        mock_connect.assert_called_with(reset=True)
        # Verify _exit_stack.aclose was called during reconnection
        original_exit_stack.aclose.assert_called()

        # Test Case 2: Reconnection failure
        # Reset counters
        call_count = 0
        mock_connect.reset_mock()
        original_exit_stack.aclose.reset_mock()

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
    tool._exit_stack.aclose = AsyncMock()

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
        original_exit_stack.aclose.assert_called()

        # Test Case 2: Reconnection failure
        # Reset counters
        call_count = 0
        mock_connect.reset_mock()
        original_exit_stack.aclose.reset_mock()

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


async def test_mcp_tool_reconnection_handles_cross_task_cancel_scope_error():
    """Test that reconnection gracefully handles anyio cancel scope errors.

    This tests the fix for the bug where calling connect(reset=True) from a
    different task than where the connection was originally established would
    cause: RuntimeError: Attempted to exit cancel scope in a different task
    than it was entered in

    This happens when using multiple MCP tools with AG-UI streaming - the first
    tool call succeeds, but when the connection closes, the second tool call
    triggers a reconnection from within the streaming loop (a different task).
    """
    from contextlib import AsyncExitStack

    from agent_framework._mcp import MCPStdioTool

    # Use load_tools=False and load_prompts=False to avoid triggering them during connect()
    tool = MCPStdioTool(
        name="test_server",
        command="test_command",
        args=["arg1"],
        load_tools=False,
        load_prompts=False,
    )

    # Mock the exit stack to raise the cross-task cancel scope error
    mock_exit_stack = AsyncMock(spec=AsyncExitStack)
    mock_exit_stack.aclose = AsyncMock(
        side_effect=RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
    )
    tool._exit_stack = mock_exit_stack
    tool.session = Mock()
    tool.is_connected = True

    # Mock get_mcp_client to return a mock transport
    mock_transport = (Mock(), Mock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context.__aexit__ = AsyncMock()

    with (
        patch.object(tool, "get_mcp_client", return_value=mock_context),
        patch("agent_framework._mcp.ClientSession") as mock_session_class,
    ):
        mock_session = Mock()
        mock_session._request_id = 1
        mock_session.initialize = AsyncMock()
        mock_session.set_logging_level = AsyncMock()
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session_context

        # This should NOT raise even though aclose() raised the cancel scope error
        # The _safe_close_exit_stack method should catch and log the error
        await tool.connect(reset=True)

        # Verify a new exit stack was created (the old mock was replaced)
        assert tool._exit_stack is not mock_exit_stack
        assert tool.session is not None
        assert tool.is_connected is True


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
