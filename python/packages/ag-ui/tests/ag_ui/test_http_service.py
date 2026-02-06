# Copyright (c) Microsoft. All rights reserved.

"""Tests for AGUIHttpService."""

import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from agent_framework_ag_ui._http_service import AGUIHttpService


@pytest.fixture
def mock_http_client():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def sample_events():
    """Sample AG-UI events for testing."""
    return [
        {"type": "RUN_STARTED", "threadId": "thread_123", "runId": "run_456"},
        {"type": "TEXT_MESSAGE_START", "messageId": "msg_1", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Hello"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": " world"},
        {"type": "TEXT_MESSAGE_END", "messageId": "msg_1"},
        {"type": "RUN_FINISHED", "threadId": "thread_123", "runId": "run_456"},
    ]


def create_sse_response(events: list[dict]) -> str:
    """Create SSE formatted response from events."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}\n")
    return "\n".join(lines)


async def test_http_service_initialization():
    """Test AGUIHttpService initialization."""
    # Test with default client
    service = AGUIHttpService("http://localhost:8888/")
    assert service.endpoint == "http://localhost:8888"
    assert service._owns_client is True
    assert isinstance(service.http_client, httpx.AsyncClient)
    await service.close()

    # Test with custom client
    custom_client = httpx.AsyncClient()
    service = AGUIHttpService("http://localhost:8888/", http_client=custom_client)
    assert service._owns_client is False
    assert service.http_client is custom_client
    # Shouldn't close the custom client
    await service.close()
    await custom_client.aclose()


async def test_http_service_strips_trailing_slash():
    """Test that endpoint trailing slash is stripped."""
    service = AGUIHttpService("http://localhost:8888/")
    assert service.endpoint == "http://localhost:8888"
    await service.close()


async def test_post_run_successful_streaming(mock_http_client, sample_events):
    """Test successful streaming of events."""

    # Create async generator for lines
    async def mock_aiter_lines():
        sse_data = create_sse_response(sample_events)
        for line in sse_data.split("\n"):
            if line:
                yield line

    # Create mock response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    # aiter_lines is called as a method, so it should return a new generator each time
    mock_response.aiter_lines = mock_aiter_lines

    # Setup mock streaming context manager
    mock_stream_context = AsyncMock()
    mock_stream_context.__aenter__.return_value = mock_response
    mock_stream_context.__aexit__.return_value = None
    mock_http_client.stream.return_value = mock_stream_context

    service = AGUIHttpService("http://localhost:8888/", http_client=mock_http_client)

    events = []
    async for event in service.post_run(
        thread_id="thread_123", run_id="run_456", messages=[{"role": "user", "content": "Hello"}]
    ):
        events.append(event)

    assert len(events) == len(sample_events)
    assert events[0]["type"] == "RUN_STARTED"
    assert events[-1]["type"] == "RUN_FINISHED"

    # Verify request was made correctly
    mock_http_client.stream.assert_called_once()
    call_args = mock_http_client.stream.call_args
    assert call_args.args[0] == "POST"
    assert call_args.args[1] == "http://localhost:8888"
    assert call_args.kwargs["headers"] == {"Accept": "text/event-stream"}


async def test_post_run_with_state_and_tools(mock_http_client):
    """Test posting run with state and tools."""

    async def mock_aiter_lines():
        return
        yield  # Make it an async generator

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_context = AsyncMock()
    mock_stream_context.__aenter__.return_value = mock_response
    mock_stream_context.__aexit__.return_value = None
    mock_http_client.stream.return_value = mock_stream_context

    service = AGUIHttpService("http://localhost:8888/", http_client=mock_http_client)

    state = {"user_context": {"name": "Alice"}}
    tools = [{"type": "function", "function": {"name": "test_tool"}}]

    async for _ in service.post_run(thread_id="thread_123", run_id="run_456", messages=[], state=state, tools=tools):
        pass

    # Verify state and tools were included in request
    call_args = mock_http_client.stream.call_args
    request_data = call_args.kwargs["json"]
    assert request_data["state"] == state
    assert request_data["tools"] == tools


async def test_post_run_http_error(mock_http_client):
    """Test handling of HTTP errors."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    def raise_http_error():
        raise httpx.HTTPStatusError("Server error", request=Mock(), response=mock_response)

    mock_response_async = AsyncMock()
    mock_response_async.raise_for_status = raise_http_error

    mock_stream_context = AsyncMock()
    mock_stream_context.__aenter__.return_value = mock_response_async
    mock_stream_context.__aexit__.return_value = None
    mock_http_client.stream.return_value = mock_stream_context

    service = AGUIHttpService("http://localhost:8888/", http_client=mock_http_client)

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in service.post_run(thread_id="thread_123", run_id="run_456", messages=[]):
            pass


async def test_post_run_invalid_json(mock_http_client):
    """Test handling of invalid JSON in SSE stream."""
    invalid_sse = "data: {invalid json}\n\ndata: " + json.dumps({"type": "RUN_FINISHED"}) + "\n"

    async def mock_aiter_lines():
        for line in invalid_sse.split("\n"):
            if line:
                yield line

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_context = AsyncMock()
    mock_stream_context.__aenter__.return_value = mock_response
    mock_stream_context.__aexit__.return_value = None
    mock_http_client.stream.return_value = mock_stream_context

    service = AGUIHttpService("http://localhost:8888/", http_client=mock_http_client)

    events = []
    async for event in service.post_run(thread_id="thread_123", run_id="run_456", messages=[]):
        events.append(event)

    # Should skip invalid JSON and continue with valid events
    assert len(events) == 1
    assert events[0]["type"] == "RUN_FINISHED"


async def test_context_manager():
    """Test context manager functionality."""
    async with AGUIHttpService("http://localhost:8888/") as service:
        assert service.http_client is not None
        assert service._owns_client is True

    # Client should be closed after exiting context


async def test_context_manager_with_external_client():
    """Test context manager doesn't close external client."""
    external_client = httpx.AsyncClient()

    async with AGUIHttpService("http://localhost:8888/", http_client=external_client) as service:
        assert service.http_client is external_client
        assert service._owns_client is False

    # External client should still be open
    # (caller's responsibility to close)
    await external_client.aclose()


async def test_post_run_empty_response(mock_http_client):
    """Test handling of empty response stream."""

    async def mock_aiter_lines():
        return
        yield  # Make it an async generator

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_context = AsyncMock()
    mock_stream_context.__aenter__.return_value = mock_response
    mock_stream_context.__aexit__.return_value = None
    mock_http_client.stream.return_value = mock_stream_context

    service = AGUIHttpService("http://localhost:8888/", http_client=mock_http_client)

    events = []
    async for event in service.post_run(thread_id="thread_123", run_id="run_456", messages=[]):
        events.append(event)

    assert len(events) == 0
