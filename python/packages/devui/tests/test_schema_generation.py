# Copyright (c) Microsoft. All rights reserved.
"""Test schema generation for different input types."""

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Add parent package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_framework_devui._utils import generate_input_schema


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


if __name__ == "__main__":
    # Simple test runner for manual execution
    pytest.main([__file__, "-v"])
