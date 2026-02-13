# Copyright (c) Microsoft. All rights reserved.
"""Tests for advanced features (thinking blocks, citations) in the anthropic package."""

from __future__ import annotations

from unittest.mock import MagicMock

from conftest import create_test_client

# Thinking Block Tests


def test_parse_thinking_block(mock_anthropic_client: MagicMock) -> None:
    """Test parsing thinking content block."""
    client = create_test_client(mock_anthropic_client)

    # Create mock thinking block
    mock_block = MagicMock()
    mock_block.type = "thinking"
    mock_block.thinking = "Let me think about this..."

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "text_reasoning"


def test_parse_thinking_delta_block(mock_anthropic_client: MagicMock) -> None:
    """Test parsing thinking delta content block."""
    client = create_test_client(mock_anthropic_client)

    # Create mock thinking delta block
    mock_block = MagicMock()
    mock_block.type = "thinking_delta"
    mock_block.thinking = "more thinking..."

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "text_reasoning"


# Citation Tests


def test_parse_citations_char_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with char_location."""
    client = create_test_client(mock_anthropic_client)

    # Create mock text block with citations
    mock_citation = MagicMock()
    mock_citation.type = "char_location"
    mock_citation.title = "Source Title"
    mock_citation.snippet = "Citation snippet"
    mock_citation.start_char_index = 0
    mock_citation.end_char_index = 10
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_page_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with page_location."""
    client = create_test_client(mock_anthropic_client)

    # Create mock citation with page location
    mock_citation = MagicMock()
    mock_citation.type = "page_location"
    mock_citation.document_title = "Document Title"
    mock_citation.start_page_number = 1
    mock_citation.end_page_number = 3
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with page citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_content_block_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with content_block_location."""
    client = create_test_client(mock_anthropic_client)

    # Create mock citation with content block location
    mock_citation = MagicMock()
    mock_citation.type = "content_block_location"
    mock_citation.start_content_block_index = 0
    mock_citation.end_content_block_index = 2
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with block citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_web_search_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with web_search_result_location."""
    client = create_test_client(mock_anthropic_client)

    # Create mock citation with web search location
    mock_citation = MagicMock()
    mock_citation.type = "web_search_result_location"
    mock_citation.url = "https://example.com"
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with web citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_search_result_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with search_result_location."""
    client = create_test_client(mock_anthropic_client)

    # Create mock citation with search result location
    mock_citation = MagicMock()
    mock_citation.type = "search_result_location"
    mock_citation.source = "https://source.com"
    mock_citation.start_content_block_index = 0
    mock_citation.end_content_block_index = 1
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with search citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0
