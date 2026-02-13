# Copyright (c) Microsoft. All rights reserved.
"""Tests for response format handling in the anthropic package."""

from __future__ import annotations

from unittest.mock import MagicMock

from conftest import create_test_client
from pydantic import BaseModel

# Response Format Tests


def test_prepare_response_format_openai_style(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with OpenAI-style json_schema."""
    client = create_test_client(mock_anthropic_client)

    response_format = {
        "json_schema": {
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        }
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["name"]["type"] == "string"


def test_prepare_response_format_direct_schema(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with direct schema key."""
    client = create_test_client(mock_anthropic_client)

    response_format = {
        "schema": {
            "type": "object",
            "properties": {"value": {"type": "number"}},
        }
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["value"]["type"] == "number"


def test_prepare_response_format_raw_schema(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with raw schema dict."""
    client = create_test_client(mock_anthropic_client)

    response_format = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["count"]["type"] == "integer"


def test_prepare_response_format_pydantic_model(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with Pydantic BaseModel."""
    client = create_test_client(mock_anthropic_client)

    class TestModel(BaseModel):
        name: str
        age: int

    result = client._prepare_response_format(TestModel)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert "properties" in result["schema"]
