# Copyright (c) Microsoft. All rights reserved.
"""Test schema generation for different input types."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

# Add parent package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_framework_devui._utils import extract_response_type_from_executor, generate_input_schema


@dataclass
class InputData:
    text: str
    source: str


@dataclass
class Address:
    street: str
    city: str
    zipcode: str


@dataclass
class PersonData:
    name: str
    age: int
    address: Address


def test_builtin_types_schema_generation():
    """Test schema generation for built-in types."""
    # Test str schema
    str_schema = generate_input_schema(str)
    assert str_schema is not None
    assert isinstance(str_schema, dict)

    # Test dict schema
    dict_schema = generate_input_schema(dict)
    assert dict_schema is not None
    assert isinstance(dict_schema, dict)

    # Test int schema
    int_schema = generate_input_schema(int)
    assert int_schema is not None
    assert isinstance(int_schema, dict)


def test_dataclass_schema_generation():
    """Test schema generation for dataclass."""
    schema = generate_input_schema(InputData)

    assert schema is not None
    assert isinstance(schema, dict)

    # Basic schema structure checks
    if "properties" in schema:
        properties = schema["properties"]
        assert "text" in properties
        assert "source" in properties


def test_chat_message_schema_generation():
    """Test schema generation for ChatMessage (SerializationMixin)."""
    try:
        from agent_framework import ChatMessage

        schema = generate_input_schema(ChatMessage)
        assert schema is not None
        assert isinstance(schema, dict)

    except ImportError:
        pytest.skip("ChatMessage not available - agent_framework not installed")


def test_pydantic_model_schema_generation():
    """Test schema generation for Pydantic models."""
    try:
        from pydantic import BaseModel, Field

        class UserInput(BaseModel):
            name: str = Field(description="User's name")
            age: int = Field(description="User's age")
            email: str | None = Field(default=None, description="Optional email")

        schema = generate_input_schema(UserInput)
        assert schema is not None
        assert isinstance(schema, dict)

        # Check if properties exist
        if "properties" in schema:
            properties = schema["properties"]
            assert "name" in properties
            assert "age" in properties
            assert "email" in properties

    except ImportError:
        pytest.skip("Pydantic not available")


def test_nested_dataclass_schema_generation():
    """Test schema generation for nested dataclass."""
    schema = generate_input_schema(PersonData)

    assert schema is not None
    assert isinstance(schema, dict)

    # Basic schema structure checks
    if "properties" in schema:
        properties = schema["properties"]
        assert "name" in properties
        assert "age" in properties
        assert "address" in properties


def test_schema_generation_error_handling():
    """Test schema generation with invalid inputs."""
    # Test with a non-type object - should handle gracefully
    try:
        # Use a non-type object that might cause issues
        schema = generate_input_schema("not_a_type")  # type: ignore
        # If it doesn't raise an exception, the result should be valid
        if schema is not None:
            assert isinstance(schema, dict)
    except (TypeError, ValueError, AttributeError):
        # It's acceptable for this to raise an error
        pass


def test_extract_response_type_from_executor():
    """Test extraction of response type from @response_handler methods."""
    try:
        from agent_framework import Executor, WorkflowContext, handler, response_handler
        from pydantic import BaseModel, Field

        # Define test request and response types
        @dataclass
        class TestApprovalRequest:
            """Test request for approval."""

            prompt: str
            context: str

        class TestDecision(BaseModel):
            """Test decision response."""

            decision: Literal["approve", "reject"] = Field(description="User's decision")
            reason: str = Field(description="Reason for decision", default="")

        # Create test executor with @response_handler
        class TestExecutor(Executor):
            """Test executor with response handler."""

            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def handle_message(self, message: str, ctx: WorkflowContext) -> None:
                """Regular handler to satisfy executor requirements."""
                # Request info that will be handled by response_handler
                request = TestApprovalRequest(prompt="Test", context="Test context")
                await ctx.request_info(request, TestDecision)

            @response_handler
            async def handle_approval(
                self, original_request: TestApprovalRequest, response: TestDecision, ctx: WorkflowContext
            ) -> None:
                """Handle approval response."""
                pass

        # Test extraction
        executor = TestExecutor()
        extracted_type = extract_response_type_from_executor(executor, TestApprovalRequest)

        # Verify correct type was extracted
        assert extracted_type is not None, "Should extract response type from @response_handler"
        assert extracted_type == TestDecision, f"Expected TestDecision, got {extracted_type}"

        # Test full schema generation pipeline
        schema = generate_input_schema(extracted_type)
        assert schema is not None
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "decision" in schema["properties"]
        assert "enum" in schema["properties"]["decision"]
        assert schema["properties"]["decision"]["enum"] == ["approve", "reject"]

    except ImportError as e:
        pytest.skip(f"Required dependencies not available: {e}")


def test_extract_response_type_no_match():
    """Test that extraction returns None when no matching handler exists."""
    try:
        from agent_framework import Executor, WorkflowContext, handler

        @dataclass
        class UnmatchedRequest:
            """Request type with no handler."""

            data: str

        class MinimalExecutor(Executor):
            """Executor with a handler but no matching response_handler."""

            def __init__(self):
                super().__init__(id="minimal_executor")

            @handler
            async def handle_message(self, message: str, ctx: WorkflowContext) -> None:
                """Regular handler."""
                pass

        executor = MinimalExecutor()
        extracted_type = extract_response_type_from_executor(executor, UnmatchedRequest)

        assert extracted_type is None, "Should return None when no matching handler exists"

    except ImportError as e:
        pytest.skip(f"Required dependencies not available: {e}")


if __name__ == "__main__":
    # Simple test runner for manual execution
    pytest.main([__file__, "-v"])
