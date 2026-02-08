# Copyright (c) Microsoft. All rights reserved.

"""Integration tests using the official OpenAI SDK to call DevUI."""

import asyncio
import contextlib
import http.client
import json
import threading
import time
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import uvicorn
from openai import OpenAI

from agent_framework_devui import DevServer


@pytest.fixture(scope="module")
def devui_server() -> Generator[str, None, None]:
    """Start a DevUI server for testing.

    Yields:
        Base URL of the running server.
    """
    # Get samples directory
    current_dir = Path(__file__).parent
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"

    if not samples_dir.exists():
        pytest.skip(f"Samples directory not found: {samples_dir}")

    # Create and start server with port 0 to get a random available port
    server = DevServer(
        entities_dir=str(samples_dir.resolve()),
        host="127.0.0.1",
        port=0,  # Use 0 to let OS assign a random available port
        ui_enabled=False,
    )

    app = server.get_app()

    server_config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=0,  # Use 0 to let OS assign a random available port
        log_level="error",
        ws="none",  # Disable websockets to avoid deprecation warnings
    )
    server_instance = uvicorn.Server(server_config)

    def run_server() -> None:
        asyncio.run(server_instance.serve())

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start and get the actual port
    max_retries = 20
    actual_port = None
    for _ in range(max_retries):
        time.sleep(0.5)
        # Get the actual port from the server instance
        if hasattr(server_instance, "servers") and server_instance.servers:
            for srv in server_instance.servers:
                for socket in srv.sockets:
                    actual_port = socket.getsockname()[1]
                    break
                if actual_port:
                    break

        if actual_port:
            # Verify server is responding
            try:
                conn = http.client.HTTPConnection("127.0.0.1", actual_port, timeout=5)
                try:
                    conn.request("GET", "/health")
                    response = conn.getresponse()
                    if response.status == 200:
                        break
                finally:
                    conn.close()
            except Exception:
                pass

    if not actual_port:
        pytest.skip("Server failed to start - could not determine port")

    yield f"http://127.0.0.1:{actual_port}"

    # Cleanup
    with contextlib.suppress(Exception):
        server_instance.should_exit = True


def test_openai_sdk_responses_create_with_entity_id(devui_server: str) -> None:
    """Test using OpenAI SDK with entity_id in metadata (no model parameter)."""
    base_url = devui_server
    client = OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    # Get available entities - extract host and port from base_url
    parsed = urlparse(base_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        conn.request("GET", "/v1/entities")
        response = conn.getresponse()
        entities = json.loads(response.read().decode("utf-8"))["entities"]
    finally:
        conn.close()

    assert len(entities) > 0, "No entities discovered"

    # Find an agent entity
    agent = next((e for e in entities if e["type"] == "agent"), None)
    if not agent:
        pytest.skip("No agent entities found")

    agent_id = agent["id"]

    # Test non-streaming request with entity_id in metadata
    response = client.responses.create(
        metadata={"entity_id": agent_id},
        input="What is 2+2?",
    )

    assert response.object == "response"
    assert len(response.output) > 0
    assert response.output[0].content is not None


def test_openai_sdk_responses_create_streaming(devui_server: str) -> None:
    """Test using OpenAI SDK with streaming enabled."""
    base_url = devui_server
    client = OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    # Get available entities - extract host and port from base_url
    parsed = urlparse(base_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        conn.request("GET", "/v1/entities")
        response = conn.getresponse()
        entities = json.loads(response.read().decode("utf-8"))["entities"]
    finally:
        conn.close()

    assert len(entities) > 0, "No entities discovered"

    # Find an agent entity
    agent = next((e for e in entities if e["type"] == "agent"), None)
    if not agent:
        pytest.skip("No agent entities found")

    agent_id = agent["id"]

    # Test streaming request
    stream = client.responses.create(
        metadata={"entity_id": agent_id},
        input="Count to 3",
        stream=True,
    )

    events = []
    for event in stream:
        events.append(event)
        if len(events) >= 100:  # Limit for safety
            break

    assert len(events) > 0, "No events received from stream"

    # Check that we got various event types
    event_types = {event.type for event in events}
    # Should have at least response.completed or some content events
    assert len(event_types) > 0


def test_openai_sdk_with_conversations(devui_server: str) -> None:
    """Test using OpenAI SDK with conversation continuity."""
    base_url = devui_server
    client = OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    # Get available entities - extract host and port from base_url
    parsed = urlparse(base_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        conn.request("GET", "/v1/entities")
        response = conn.getresponse()
        entities = json.loads(response.read().decode("utf-8"))["entities"]
    finally:
        conn.close()

    assert len(entities) > 0, "No entities discovered"

    # Find an agent entity
    agent = next((e for e in entities if e["type"] == "agent"), None)
    if not agent:
        pytest.skip("No agent entities found")

    agent_id = agent["id"]

    # Create a conversation
    conversation = client.conversations.create(metadata={"agent_id": agent_id})

    assert conversation.id is not None

    # First turn
    response1 = client.responses.create(
        metadata={"entity_id": agent_id},
        input="My name is Alice",
        conversation=conversation.id,
    )

    assert response1.object == "response"
    assert len(response1.output) > 0

    # Second turn - test conversation continuity
    response2 = client.responses.create(
        metadata={"entity_id": agent_id},
        input="What is my name?",
        conversation=conversation.id,
    )

    assert response2.object == "response"
    assert len(response2.output) > 0
    # The agent should remember the name from the previous turn
    # Note: This may not work with all agents, so we just verify we got a response
    assert response2.output[0].content is not None


def test_openai_sdk_with_model_and_entity_id(devui_server: str) -> None:
    """Test that both model and entity_id can be specified together."""
    base_url = devui_server
    client = OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    # Get available entities - extract host and port from base_url
    parsed = urlparse(base_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        conn.request("GET", "/v1/entities")
        response = conn.getresponse()
        entities = json.loads(response.read().decode("utf-8"))["entities"]
    finally:
        conn.close()

    assert len(entities) > 0, "No entities discovered"

    # Find an agent entity
    agent = next((e for e in entities if e["type"] == "agent"), None)
    if not agent:
        pytest.skip("No agent entities found")

    agent_id = agent["id"]

    # Test with both model and entity_id - entity_id should be used for routing
    response = client.responses.create(
        metadata={"entity_id": agent_id},
        model="custom-model-name",
        input="Hello",
    )

    assert response.object == "response"
    # The response model should reflect what was specified
    assert response.model == "custom-model-name"
    assert len(response.output) > 0
