# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework_a2a._utils import get_uri_data


def test_get_uri_data_valid() -> None:
    """Test get_uri_data with valid data URIs."""
    # Simple text/plain
    uri = "data:text/plain;base64,SGVsbG8sIFdvcmxkIQ=="
    assert get_uri_data(uri) == "SGVsbG8sIFdvcmxkIQ=="

    # Image png
    uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    assert get_uri_data(uri) == "iVBORw0KGgoAAAANSUhEUgfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

    # Application octet-stream
    uri = "data:application/octet-stream;base64,AQIDBA=="
    assert get_uri_data(uri) == "AQIDBA=="

    # Media type with parameters
    uri = "data:text/plain;charset=utf-8;base64,SGVsbG8sIFdvcmxkIQ=="
    assert get_uri_data(uri) == "SGVsbG8sIFdvcmxkIQ=="

    # Media type with multiple parameters
    uri = "data:text/plain;charset=utf-8;name=hello.txt;base64,SGVsbG8sIFdvcmxkIQ=="
    assert get_uri_data(uri) == "SGVsbG8sIFdvcmxkIQ=="


def test_get_uri_data_invalid_format() -> None:
    """Test get_uri_data with invalid URI formats."""
    invalid_uris = [
        "not-a-uri",
        "http://example.com",
        "data:text/plain;SGVsbG8sIFdvcmxkIQ==",  # Missing base64 marker
        "data:base64,SGVsbG8sIFdvcmxkIQ==",  # Missing media type
        "data:text/plain;foo;base64,SGVsbG8sIFdvcmxkIQ==",  # Parameter without value
        "data:text/plain;base64;base64,SGVsbG8sIFdvcmxkIQ==",  # base64 used as a parameter name
        "data:text/plain;base64,SGVsbG8sIFdvcmxkIQ== extra",
        "data:text/plain;base64,SGVsbG8sIFdvcmxkIQ==\n",
    ]
    for uri in invalid_uris:
        with pytest.raises(ValueError, match="Invalid data URI format"):
            get_uri_data(uri)


def test_get_uri_data_empty() -> None:
    """Test get_uri_data with empty string."""
    with pytest.raises(ValueError, match="Invalid data URI format"):
        get_uri_data("")
