# Copyright (c) Microsoft. All rights reserved.

"""Tests for FastAPI endpoint creation (_endpoint.py)."""

import json
from typing import Any

from agent_framework import ChatAgent, TextContent
from agent_framework._types import ChatResponseUpdate
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_framework_ag_ui._agent import AgentFrameworkAgent
from agent_framework_ag_ui._endpoint import DEFAULT_TAGS, add_agent_framework_fastapi_endpoint


class MockChatClient:
    """Mock chat client for testing."""

    def __init__(self, response_text: str = "Test response"):
        self.response_text = response_text

    async def get_streaming_response(self, messages: list[Any], chat_options: Any, **kwargs: Any):
        """Mock streaming response."""
        yield ChatResponseUpdate(contents=[TextContent(text=self.response_text)])


async def test_add_endpoint_with_agent_protocol():
    """Test adding endpoint with raw AgentProtocol."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/test-agent")

    client = TestClient(app)
    response = client.post("/test-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_add_endpoint_with_wrapped_agent():
    """Test adding endpoint with pre-wrapped AgentFrameworkAgent."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())
    wrapped_agent = AgentFrameworkAgent(agent=agent, name="wrapped")

    add_agent_framework_fastapi_endpoint(app, wrapped_agent, path="/wrapped-agent")

    client = TestClient(app)
    response = client.post("/wrapped-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_endpoint_with_state_schema():
    """Test endpoint with state_schema parameter."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())
    state_schema = {"document": {"type": "string"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/stateful", state_schema=state_schema)

    client = TestClient(app)
    response = client.post(
        "/stateful", json={"messages": [{"role": "user", "content": "Hello"}], "state": {"document": ""}}
    )

    assert response.status_code == 200


async def test_endpoint_with_predict_state_config():
    """Test endpoint with predict_state_config parameter."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())
    predict_config = {"document": {"tool": "write_doc", "tool_argument": "content"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/predictive", predict_state_config=predict_config)

    client = TestClient(app)
    response = client.post("/predictive", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_request_logging():
    """Test that endpoint logs request details."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/logged")

    client = TestClient(app)
    response = client.post(
        "/logged",
        json={
            "messages": [{"role": "user", "content": "Test"}],
            "run_id": "run-123",
            "thread_id": "thread-456",
        },
    )

    assert response.status_code == 200


async def test_endpoint_event_streaming():
    """Test that endpoint streams events correctly."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient("Streamed response"))

    add_agent_framework_fastapi_endpoint(app, agent, path="/stream")

    client = TestClient(app)
    response = client.post("/stream", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200

    content = response.content.decode("utf-8")
    lines = [line for line in content.split("\n") if line.strip()]

    found_run_started = False
    found_text_content = False
    found_run_finished = False

    for line in lines:
        if line.startswith("data: "):
            event_data = json.loads(line[6:])
            if event_data.get("type") == "RUN_STARTED":
                found_run_started = True
            elif event_data.get("type") == "TEXT_MESSAGE_CONTENT":
                found_text_content = True
            elif event_data.get("type") == "RUN_FINISHED":
                found_run_finished = True

    assert found_run_started
    assert found_text_content
    assert found_run_finished


async def test_endpoint_error_handling():
    """Test endpoint error handling during request parsing.

    With Pydantic model validation, FastAPI returns 422 Unprocessable Entity
    for invalid request bodies, which is the correct HTTP semantics.
    """
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/failing")

    client = TestClient(app)

    # Send invalid JSON to trigger validation error
    response = client.post("/failing", data="invalid json", headers={"content-type": "application/json"})

    # FastAPI returns 422 for validation errors with Pydantic models
    assert response.status_code == 422
    content = json.loads(response.content)
    assert "detail" in content


async def test_endpoint_multiple_paths():
    """Test adding multiple endpoints with different paths."""
    app = FastAPI()
    agent1 = ChatAgent(name="agent1", instructions="First agent", chat_client=MockChatClient("Response 1"))
    agent2 = ChatAgent(name="agent2", instructions="Second agent", chat_client=MockChatClient("Response 2"))

    add_agent_framework_fastapi_endpoint(app, agent1, path="/agent1")
    add_agent_framework_fastapi_endpoint(app, agent2, path="/agent2")

    client = TestClient(app)

    response1 = client.post("/agent1", json={"messages": [{"role": "user", "content": "Hi"}]})
    response2 = client.post("/agent2", json={"messages": [{"role": "user", "content": "Hi"}]})

    assert response1.status_code == 200
    assert response2.status_code == 200


async def test_endpoint_default_path():
    """Test endpoint with default path."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent)

    client = TestClient(app)
    response = client.post("/", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_response_headers():
    """Test that endpoint sets correct response headers."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/headers")

    client = TestClient(app)
    response = client.post("/headers", json={"messages": [{"role": "user", "content": "Test"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert "cache-control" in response.headers
    assert response.headers["cache-control"] == "no-cache"


async def test_endpoint_empty_messages():
    """Test endpoint with empty messages list."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/empty")

    client = TestClient(app)
    response = client.post("/empty", json={"messages": []})

    assert response.status_code == 200


async def test_endpoint_complex_input():
    """Test endpoint with complex input data."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/complex")

    client = TestClient(app)
    response = client.post(
        "/complex",
        json={
            "messages": [
                {"role": "user", "content": "First message", "id": "msg-1"},
                {"role": "assistant", "content": "Response", "id": "msg-2"},
                {"role": "user", "content": "Follow-up", "id": "msg-3"},
            ],
            "run_id": "complex-run-123",
            "thread_id": "complex-thread-456",
            "state": {"custom_field": "value"},
        },
    )

    assert response.status_code == 200


async def test_endpoint_default_tags():
    """Test that endpoint uses default tags when not specified."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/default-tags")

    # Check OpenAPI schema for default tags
    openapi_schema = app.openapi()
    path_item = openapi_schema["paths"]["/default-tags"]["post"]

    assert "tags" in path_item
    assert path_item["tags"] == DEFAULT_TAGS


async def test_endpoint_custom_tags():
    """Test that endpoint uses custom tags when specified."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())
    custom_tags = ["Custom", "Agent"]

    add_agent_framework_fastapi_endpoint(app, agent, path="/custom-tags", tags=custom_tags)

    # Check OpenAPI schema for custom tags
    openapi_schema = app.openapi()
    path_item = openapi_schema["paths"]["/custom-tags"]["post"]

    assert "tags" in path_item
    assert path_item["tags"] == custom_tags


async def test_endpoint_openapi_schema_includes_request_body():
    """Test that endpoint OpenAPI schema includes request body definition."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/schema-test")

    # Check OpenAPI schema for request body
    openapi_schema = app.openapi()
    path_item = openapi_schema["paths"]["/schema-test"]["post"]

    assert "requestBody" in path_item
    assert "content" in path_item["requestBody"]
    assert "application/json" in path_item["requestBody"]["content"]

    # Verify schema reference exists
    json_content = path_item["requestBody"]["content"]["application/json"]
    assert "schema" in json_content


async def test_endpoint_openapi_schema_has_agui_request_properties():
    """Test that OpenAPI schema includes AGUIRequest properties."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent, path="/properties-test")

    openapi_schema = app.openapi()

    # Find the AGUIRequest schema in components
    assert "components" in openapi_schema
    assert "schemas" in openapi_schema["components"]
    assert "AGUIRequest" in openapi_schema["components"]["schemas"]

    agui_schema = openapi_schema["components"]["schemas"]["AGUIRequest"]
    assert "properties" in agui_schema
    assert "messages" in agui_schema["properties"]
    assert "run_id" in agui_schema["properties"]
    assert "thread_id" in agui_schema["properties"]
    assert "state" in agui_schema["properties"]


async def test_endpoint_multiple_agents_different_tags():
    """Test multiple agents with different tags."""
    app = FastAPI()
    agent1 = ChatAgent(name="agent1", instructions="First agent", chat_client=MockChatClient())
    agent2 = ChatAgent(name="agent2", instructions="Second agent", chat_client=MockChatClient())

    add_agent_framework_fastapi_endpoint(app, agent1, path="/agent1", tags=["Agent1"])
    add_agent_framework_fastapi_endpoint(app, agent2, path="/agent2", tags=["Agent2"])

    openapi_schema = app.openapi()

    assert openapi_schema["paths"]["/agent1"]["post"]["tags"] == ["Agent1"]
    assert openapi_schema["paths"]["/agent2"]["post"]["tags"] == ["Agent2"]


def test_default_tags_constant():
    """Test that DEFAULT_TAGS constant is correct."""
    assert DEFAULT_TAGS == ["AG-UI"]
    assert isinstance(DEFAULT_TAGS, list)
    assert len(DEFAULT_TAGS) == 1
