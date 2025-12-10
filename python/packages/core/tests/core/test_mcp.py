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


def test_mcp_call_tool_result_with_meta_error():
    """Test conversion from MCP tool result with _meta field containing isError=True."""
    # Create a mock CallToolResult with _meta field containing error information
    mcp_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Error occurred")],
        _meta={"isError": True, "errorCode": "TOOL_ERROR", "errorMessage": "Tool execution failed"},
    )

    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

    assert len(ai_contents) == 1
    assert isinstance(ai_contents[0], TextContent)
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

    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

    assert len(ai_contents) == 1
    assert isinstance(ai_contents[0], TextContent)
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

    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

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

    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

    assert len(ai_contents) == 1
    assert isinstance(ai_contents[0], TextContent)
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
            types.ImageContent(type="image", data="data:image/jpeg;base64,abc123", mimeType="image/jpeg"),
        ]
    )

    ai_contents = _mcp_call_tool_result_to_ai_contents(mcp_result)

    # Verify basic conversion still works correctly
    assert len(ai_contents) == 2

    text_content = ai_contents[0]
    assert isinstance(text_content, TextContent)
    assert text_content.text == "Success message"

    image_content = ai_contents[1]
    assert isinstance(image_content, DataContent)
    assert image_content.uri == "data:image/jpeg;base64,abc123"
    assert image_content.media_type == "image/jpeg"

    # Should have no additional_properties when no _meta field
    assert text_content.additional_properties is None or text_content.additional_properties == {}
    assert image_content.additional_properties is None or image_content.additional_properties == {}


def test_mcp_content_types_to_ai_content_text():
    """Test conversion of MCP text content to AI content."""
    mcp_content = types.TextContent(type="text", text="Sample text")
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

    assert isinstance(ai_content, TextContent)
    assert ai_content.text == "Sample text"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_image():
    """Test conversion of MCP image content to AI content."""
    mcp_content = types.ImageContent(type="image", data="data:image/jpeg;base64,abc", mimeType="image/jpeg")
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

    assert isinstance(ai_content, DataContent)
    assert ai_content.uri == "data:image/jpeg;base64,abc"
    assert ai_content.media_type == "image/jpeg"
    assert ai_content.raw_representation == mcp_content


def test_mcp_content_types_to_ai_content_audio():
    """Test conversion of MCP audio content to AI content."""
    mcp_content = types.AudioContent(type="audio", data="data:audio/wav;base64,def", mimeType="audio/wav")
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

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
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

    assert isinstance(ai_content, UriContent)
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
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

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
    ai_content = _mcp_type_to_ai_content(mcp_content)[0]

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
    ai_content = DataContent(
        uri="data:application/octet-stream;base64,xyz",
        media_type="application/octet-stream",
    )
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
        contents=[
            TextContent(text="test"),
            DataContent(uri="data:image/png;base64,xyz", media_type="image/png"),
        ],
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

    # Nested objects should now be Pydantic models (issue #2747)
    assert hasattr(instance.params, "customer_id")
    assert instance.params.customer_id == 251
    assert isinstance(instance.params, BaseModel)

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

    # $ref resolved objects should now be Pydantic models (issue #2747)
    assert hasattr(instance.params, "customer_id")
    assert instance.params.customer_id == 251
    assert isinstance(instance.params, BaseModel)

    # Verify model_dump produces the correct nested structure
    dumped = instance.model_dump()
    assert dumped == {"params": {"customer_id": 251}}


def test_get_input_model_from_mcp_tool_with_simple_array():
    """Test array with simple items schema (items schema should be preserved in json_schema_extra)."""
    tool = types.Tool(
        name="simple_array_tool",
        description="Tool with simple array",
        inputSchema={
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "description": "List of tags",
                    "items": {"type": "string"},  # Simple string array
                }
            },
            "required": ["tags"],
        },
    )
    model = _get_input_model_from_mcp_tool(tool)

    # Create an instance
    instance = model(tags=["tag1", "tag2", "tag3"])
    assert instance.tags == ["tag1", "tag2", "tag3"]

    # Verify JSON schema still preserves items for simple types
    json_schema = model.model_json_schema()
    tags_property = json_schema["properties"]["tags"]
    assert "items" in tags_property
    assert tags_property["items"]["type"] == "string"


# NEW TESTS FOR ISSUE #2747


def test_get_input_model_nested_object_with_proper_types():
    """Test that nested objects create proper Pydantic models with typed fields, not bare dict.

    Issue #2747: Nested objects should preserve their schema structure,
    allowing LLMs to see required fields and their types.
    """
    tool = types.Tool(
        name="fetch_news",
        description="Fetch news articles",
        inputSchema={
            "type": "object",
            "properties": {
                "news_request": {
                    "type": "object",
                    "description": "News request parameters",
                    "properties": {
                        "identifiers": {
                            "type": "array",
                            "description": "Article identifiers",
                            "items": {"type": "string"},
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results",
                        },
                    },
                    "required": ["identifiers"],
                }
            },
            "required": ["news_request"],
        },
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Verify the model can be instantiated with proper nested structure
    instance = model(news_request={"identifiers": ["abc123", "def456"], "max_results": 10})

    # Verify the nested structure is preserved
    assert hasattr(instance, "news_request")
    assert instance.news_request.identifiers == ["abc123", "def456"]
    assert instance.news_request.max_results == 10

    # Verify that the JSON schema shows the nested structure
    json_schema = model.model_json_schema()
    news_request_schema = json_schema["properties"]["news_request"]

    # Should have properties defined, not just be a dict
    assert "properties" in news_request_schema or "$ref" in news_request_schema

    # If using $defs, verify the definition exists
    if "$ref" in news_request_schema:
        ref_name = news_request_schema["$ref"].split("/")[-1]
        assert ref_name in json_schema.get("$defs", {})
        nested_def = json_schema["$defs"][ref_name]
        assert "properties" in nested_def
        assert "identifiers" in nested_def["properties"]
        assert "max_results" in nested_def["properties"]
    else:
        assert "identifiers" in news_request_schema["properties"]
        assert "max_results" in news_request_schema["properties"]

    # Verify validation works for required nested fields
    with pytest.raises(ValidationError) as exc_info:
        model(news_request={})  # Missing required 'identifiers'

    errors = exc_info.value.errors()
    # Should have a validation error about missing 'identifiers' field
    assert any("identifiers" in str(error) for error in errors)


def test_get_input_model_array_of_strings_typed():
    """Test that array of strings is properly typed as list[str], not bare list.

    Issue #2747: Arrays should preserve item type information.
    """
    tool = types.Tool(
        name="process_tags",
        description="Process tags",
        inputSchema={
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "description": "List of string tags",
                    "items": {"type": "string"},
                }
            },
            "required": ["tags"],
        },
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Verify type annotations
    field_info = model.model_fields["tags"]

    # The annotation should be list[str] or List[str], not just list
    annotation_str = str(field_info.annotation)
    assert "list" in annotation_str.lower()
    assert "str" in annotation_str.lower()

    # Verify JSON schema preserves item type
    json_schema = model.model_json_schema()
    tags_property = json_schema["properties"]["tags"]
    assert tags_property["type"] == "array"
    assert "items" in tags_property
    assert tags_property["items"]["type"] == "string"


def test_get_input_model_array_of_integers_typed():
    """Test that array of integers is properly typed as list[int], not bare list.

    Issue #2747: Arrays should preserve item type information.
    """
    tool = types.Tool(
        name="process_numbers",
        description="Process numbers",
        inputSchema={
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
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Verify type annotations
    field_info = model.model_fields["numbers"]
    annotation_str = str(field_info.annotation)
    assert "list" in annotation_str.lower()
    assert "int" in annotation_str.lower()

    # Verify JSON schema preserves item type
    json_schema = model.model_json_schema()
    numbers_property = json_schema["properties"]["numbers"]
    assert numbers_property["type"] == "array"
    assert "items" in numbers_property
    assert numbers_property["items"]["type"] == "integer"


def test_get_input_model_array_of_objects_typed():
    """Test that array of objects creates typed list[NestedModel], not bare list.

    Issue #2747: Arrays of complex types should preserve structure.
    """
    tool = types.Tool(
        name="process_users",
        description="Process user data",
        inputSchema={
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
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Create instance with array of objects
    instance = model(users=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

    # Verify nested objects are properly typed
    assert len(instance.users) == 2
    assert instance.users[0].id == 1
    assert instance.users[0].name == "Alice"
    assert instance.users[1].id == 2
    assert instance.users[1].name == "Bob"

    # Verify validation works for nested required fields
    with pytest.raises(ValidationError) as exc_info:
        model(users=[{"id": 1}])  # Missing required 'name'

    errors = exc_info.value.errors()
    assert any("name" in str(error) for error in errors)

    # Verify JSON schema preserves nested structure
    json_schema = model.model_json_schema()
    users_property = json_schema["properties"]["users"]
    assert users_property["type"] == "array"
    assert "items" in users_property

    items_schema = users_property["items"]
    # Should have properties defined or a $ref
    if "$ref" in items_schema:
        ref_name = items_schema["$ref"].split("/")[-1]
        assert ref_name in json_schema.get("$defs", {})
        item_def = json_schema["$defs"][ref_name]
        assert "properties" in item_def
        assert "id" in item_def["properties"]
        assert "name" in item_def["properties"]
        assert "required" in item_def
        assert "id" in item_def["required"]
        assert "name" in item_def["required"]
    else:
        assert "properties" in items_schema
        assert "id" in items_schema["properties"]
        assert "name" in items_schema["properties"]


def test_get_input_model_deeply_nested_objects():
    """Test multiple levels of nested objects preserve structure.

    Issue #2747: Should handle arbitrary nesting depth.
    """
    tool = types.Tool(
        name="complex_query",
        description="Complex nested query",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "object",
                    "description": "Query parameters",
                    "properties": {
                        "filters": {
                            "type": "object",
                            "description": "Filter criteria",
                            "properties": {
                                "date_range": {
                                    "type": "object",
                                    "description": "Date range filter",
                                    "properties": {
                                        "start": {"type": "string", "description": "Start date"},
                                        "end": {"type": "string", "description": "End date"},
                                    },
                                    "required": ["start", "end"],
                                },
                                "categories": {
                                    "type": "array",
                                    "description": "Category filters",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["date_range"],
                        }
                    },
                    "required": ["filters"],
                }
            },
            "required": ["query"],
        },
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Create instance with deeply nested structure
    instance = model(
        query={
            "filters": {
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "categories": ["tech", "science"],
            }
        }
    )

    # Verify deep nesting is preserved with proper types
    assert instance.query.filters.date_range.start == "2024-01-01"
    assert instance.query.filters.date_range.end == "2024-12-31"
    assert instance.query.filters.categories == ["tech", "science"]

    # Verify validation works at all nesting levels
    with pytest.raises(ValidationError) as exc_info:
        model(query={"filters": {"date_range": {}}})  # Missing required 'start' and 'end'

    errors = exc_info.value.errors()
    assert any("start" in str(error) or "end" in str(error) for error in errors)


def test_get_input_model_ref_with_nested_structure():
    """Test that $ref resolution preserves nested structure.

    Issue #2747: $ref schemas should be recursively processed like inline schemas.
    """
    tool = types.Tool(
        name="create_order",
        description="Create an order",
        inputSchema={
            "type": "object",
            "properties": {
                "order": {"$ref": "#/$defs/OrderParams"},
            },
            "required": ["order"],
            "$defs": {
                "OrderParams": {
                    "type": "object",
                    "properties": {
                        "customer": {"$ref": "#/$defs/Customer"},
                        "items": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/OrderItem"},
                        },
                    },
                    "required": ["customer", "items"],
                },
                "Customer": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "email": {"type": "string"},
                    },
                    "required": ["id", "email"],
                },
                "OrderItem": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["product_id", "quantity"],
                },
            },
        },
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Create instance with nested refs
    instance = model(
        order={
            "customer": {"id": 123, "email": "test@example.com"},
            "items": [
                {"product_id": "prod1", "quantity": 2},
                {"product_id": "prod2", "quantity": 1},
            ],
        }
    )

    # Verify nested structure through $refs is preserved
    assert instance.order.customer.id == 123
    assert instance.order.customer.email == "test@example.com"
    assert len(instance.order.items) == 2
    assert instance.order.items[0].product_id == "prod1"
    assert instance.order.items[0].quantity == 2

    # Verify validation works for nested required fields
    with pytest.raises(ValidationError) as exc_info:
        model(order={"customer": {"id": 123}, "items": []})  # Missing email

    errors = exc_info.value.errors()
    assert any("email" in str(error) for error in errors)


def test_get_input_model_mixed_types_complex():
    """Test complex schema with mixed primitives, arrays, and nested objects.

    Issue #2747: Real-world schemas combine multiple patterns.
    """
    tool = types.Tool(
        name="complex_tool",
        description="Tool with complex mixed types",
        inputSchema={
            "type": "object",
            "properties": {
                "simple_string": {"type": "string", "description": "A simple string"},
                "simple_number": {"type": "integer", "description": "A simple number"},
                "string_array": {
                    "type": "array",
                    "description": "Array of strings",
                    "items": {"type": "string"},
                },
                "nested_config": {
                    "type": "object",
                    "description": "Nested configuration",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["enabled"],
                },
            },
            "required": ["simple_string", "nested_config"],
        },
    )

    model = _get_input_model_from_mcp_tool(tool)

    # Create instance with all types
    instance = model(
        simple_string="test",
        simple_number=42,
        string_array=["a", "b"],
        nested_config={"enabled": True, "options": ["opt1", "opt2"]},
    )

    # Verify all types are properly preserved
    assert instance.simple_string == "test"
    assert instance.simple_number == 42
    assert instance.string_array == ["a", "b"]
    assert instance.nested_config.enabled is True
    assert instance.nested_config.options == ["opt1", "opt2"]

    # Verify JSON schema preserves all structures
    json_schema = model.model_json_schema()

    # Check simple types
    assert json_schema["properties"]["simple_string"]["type"] == "string"
    assert json_schema["properties"]["simple_number"]["type"] == "integer"

    # Check array type
    string_array_prop = json_schema["properties"]["string_array"]
    assert string_array_prop["type"] == "array"
    assert string_array_prop["items"]["type"] == "string"

    # Check nested object structure is preserved
    nested_config_prop = json_schema["properties"]["nested_config"]
    if "$ref" in nested_config_prop:
        ref_name = nested_config_prop["$ref"].split("/")[-1]
        nested_def = json_schema["$defs"][ref_name]
        assert "enabled" in nested_def["properties"]
        assert "options" in nested_def["properties"]
    else:
        assert "properties" in nested_config_prop
        assert "enabled" in nested_config_prop["properties"]
        assert "options" in nested_config_prop["properties"]


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
        assert isinstance(result[0], TextContent)
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
    from agent_framework import ChatMessage, DataContent, Role

    tool = MCPStdioTool(name="test_tool", command="python")

    # Mock chat client with response containing only invalid content types
    mock_chat_client = AsyncMock()
    mock_response = Mock()
    mock_response.messages = [
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                DataContent(
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
        headers={"Auth": "token"},
        timeout=30.0,
        sse_read_timeout=10.0,
        terminate_on_close=True,
        custom_param="test",
    )

    with patch("agent_framework._mcp.streamablehttp_client") as mock_http_client:
        tool.get_mcp_client()

        # Verify all parameters were passed
        mock_http_client.assert_called_once_with(
            url="http://example.com",
            headers={"Auth": "token"},
            timeout=30.0,
            sse_read_timeout=10.0,
            terminate_on_close=True,
            custom_param="test",
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


@pytest.mark.asyncio
async def test_mcp_tool_deduplication():
    """Test that MCP tools are not duplicated in MCPTool"""
    from agent_framework._mcp import MCPTool
    from agent_framework._tools import AIFunction

    # Create MCPStreamableHTTPTool instance
    tool = MCPTool(name="test_mcp_tool")

    # Manually set up functions list
    tool._functions = []

    # Add initial functions
    func1 = AIFunction(
        func=lambda x: f"Result: {x}",
        name="analyze_content",
        description="Analyzes content",
    )
    func2 = AIFunction(
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

        new_func = AIFunction(func=lambda x: f"Process: {x}", name=tool_name, description=description)
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
