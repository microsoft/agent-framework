# Copyright (c) Microsoft. All rights reserved.

"""Tests for FastAPI endpoint creation (_endpoint.py)."""

import json
import sys
from pathlib import Path

from agent_framework import ChatAgent, ChatResponseUpdate, Content
from fastapi import FastAPI, Header, HTTPException
from fastapi.params import Depends
from fastapi.testclient import TestClient

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework_ag_ui._agent import AgentFrameworkAgent

sys.path.insert(0, str(Path(__file__).parent))
from utils_test_ag_ui import StreamingChatClientStub, stream_from_updates


def build_chat_client(response_text: str = "Test response") -> StreamingChatClientStub:
    """Create a typed chat client stub for endpoint tests."""
    updates = [ChatResponseUpdate(contents=[Content.from_text(text=response_text)])]
    return StreamingChatClientStub(stream_from_updates(updates))


async def test_add_endpoint_with_agent_protocol():
    """Test adding endpoint with raw AgentProtocol."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/test-agent")

    client = TestClient(app)
    response = client.post("/test-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_add_endpoint_with_wrapped_agent():
    """Test adding endpoint with pre-wrapped AgentFrameworkAgent."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())
    wrapped_agent = AgentFrameworkAgent(agent=agent, name="wrapped")

    add_agent_framework_fastapi_endpoint(app, wrapped_agent, path="/wrapped-agent")

    client = TestClient(app)
    response = client.post("/wrapped-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_endpoint_with_state_schema():
    """Test endpoint with state_schema parameter."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())
    state_schema = {"document": {"type": "string"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/stateful", state_schema=state_schema)

    client = TestClient(app)
    response = client.post(
        "/stateful", json={"messages": [{"role": "user", "content": "Hello"}], "state": {"document": ""}}
    )

    assert response.status_code == 200


async def test_endpoint_with_default_state_seed():
    """Test endpoint seeds default state when client omits it."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())
    state_schema = {"proverbs": {"type": "array"}}
    default_state = {"proverbs": ["Keep the original."]}

    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/default-state",
        state_schema=state_schema,
        default_state=default_state,
    )

    client = TestClient(app)
    response = client.post("/default-state", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200

    content = response.content.decode("utf-8")
    lines = [line for line in content.split("\n") if line.startswith("data: ")]
    snapshots = [json.loads(line[6:]) for line in lines if json.loads(line[6:]).get("type") == "STATE_SNAPSHOT"]
    assert snapshots, "Expected a STATE_SNAPSHOT event"
    assert snapshots[0]["snapshot"]["proverbs"] == default_state["proverbs"]


async def test_endpoint_with_predict_state_config():
    """Test endpoint with predict_state_config parameter."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())
    predict_config = {"document": {"tool": "write_doc", "tool_argument": "content"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/predictive", predict_state_config=predict_config)

    client = TestClient(app)
    response = client.post("/predictive", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_request_logging():
    """Test that endpoint logs request details."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

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
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client("Streamed response"))

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
    """Test endpoint error handling during request parsing."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/failing")

    client = TestClient(app)

    # Send invalid JSON to trigger parsing error before streaming
    response = client.post("/failing", data=b"invalid json", headers={"content-type": "application/json"})  # type: ignore

    # Pydantic validation now returns 422 for invalid request body
    assert response.status_code == 422


async def test_endpoint_multiple_paths():
    """Test adding multiple endpoints with different paths."""
    app = FastAPI()
    agent1 = ChatAgent(name="agent1", instructions="First agent", chat_client=build_chat_client("Response 1"))
    agent2 = ChatAgent(name="agent2", instructions="Second agent", chat_client=build_chat_client("Response 2"))

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
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent)

    client = TestClient(app)
    response = client.post("/", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_response_headers():
    """Test that endpoint sets correct response headers."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

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
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/empty")

    client = TestClient(app)
    response = client.post("/empty", json={"messages": []})

    assert response.status_code == 200


async def test_endpoint_complex_input():
    """Test endpoint with complex input data."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

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


async def test_endpoint_openapi_schema():
    """Test that endpoint generates proper OpenAPI schema with request model."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/schema-test")

    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_spec = response.json()

    # Verify the endpoint exists in the schema
    assert "/schema-test" in openapi_spec["paths"]
    endpoint_spec = openapi_spec["paths"]["/schema-test"]["post"]

    # Verify request body schema is defined
    assert "requestBody" in endpoint_spec
    request_body = endpoint_spec["requestBody"]
    assert "content" in request_body
    assert "application/json" in request_body["content"]

    # Verify schema references AGUIRequest model
    schema_ref = request_body["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref
    assert "AGUIRequest" in schema_ref["$ref"]

    # Verify AGUIRequest model is in components
    assert "components" in openapi_spec
    assert "schemas" in openapi_spec["components"]
    assert "AGUIRequest" in openapi_spec["components"]["schemas"]

    # Verify AGUIRequest has required fields
    agui_request_schema = openapi_spec["components"]["schemas"]["AGUIRequest"]
    assert "properties" in agui_request_schema
    assert "messages" in agui_request_schema["properties"]
    assert "run_id" in agui_request_schema["properties"]
    assert "thread_id" in agui_request_schema["properties"]
    assert "state" in agui_request_schema["properties"]
    assert "required" in agui_request_schema
    assert "messages" in agui_request_schema["required"]


async def test_endpoint_default_tags():
    """Test that endpoint uses default 'AG-UI' tag."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/default-tags")

    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_spec = response.json()

    endpoint_spec = openapi_spec["paths"]["/default-tags"]["post"]
    assert "tags" in endpoint_spec
    assert endpoint_spec["tags"] == ["AG-UI"]


async def test_endpoint_custom_tags():
    """Test that endpoint accepts custom tags."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/custom-tags", tags=["Custom", "Agent"])

    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_spec = response.json()

    endpoint_spec = openapi_spec["paths"]["/custom-tags"]["post"]
    assert "tags" in endpoint_spec
    assert endpoint_spec["tags"] == ["Custom", "Agent"]


async def test_endpoint_missing_required_field():
    """Test that endpoint validates required fields with Pydantic."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/validation")

    client = TestClient(app)

    # Missing required 'messages' field should trigger validation error
    response = client.post("/validation", json={"run_id": "test-123"})

    assert response.status_code == 422
    error_detail = response.json()
    assert "detail" in error_detail


async def test_endpoint_internal_error_handling():
    """Test endpoint error handling when an exception occurs before streaming starts."""
    from unittest.mock import patch

    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    # Use default_state to trigger the code path that can raise an exception
    add_agent_framework_fastapi_endpoint(app, agent, path="/error-test", default_state={"key": "value"})

    client = TestClient(app)

    # Mock copy.deepcopy to raise an exception during default_state processing
    with patch("agent_framework_ag_ui._endpoint.copy.deepcopy") as mock_deepcopy:
        mock_deepcopy.side_effect = Exception("Simulated internal error")
        response = client.post("/error-test", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.json() == {"error": "An internal error has occurred."}


async def test_endpoint_with_dependencies_blocks_unauthorized():
    """Test that endpoint blocks requests when authentication dependency fails."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    async def require_api_key(x_api_key: str | None = Header(None)):
        if x_api_key != "secret-key":
            raise HTTPException(status_code=401, detail="Unauthorized")

    add_agent_framework_fastapi_endpoint(app, agent, path="/protected", dependencies=[Depends(require_api_key)])

    client = TestClient(app)

    # Request without API key should be rejected
    response = client.post("/protected", json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_endpoint_with_dependencies_allows_authorized():
    """Test that endpoint allows requests when authentication dependency passes."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    async def require_api_key(x_api_key: str | None = Header(None)):
        if x_api_key != "secret-key":
            raise HTTPException(status_code=401, detail="Unauthorized")

    add_agent_framework_fastapi_endpoint(app, agent, path="/protected", dependencies=[Depends(require_api_key)])

    client = TestClient(app)

    # Request with valid API key should succeed
    response = client.post(
        "/protected",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers={"x-api-key": "secret-key"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_endpoint_with_multiple_dependencies():
    """Test that endpoint supports multiple dependencies."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    execution_order: list[str] = []

    async def first_dependency():
        execution_order.append("first")

    async def second_dependency():
        execution_order.append("second")

    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/multi-deps",
        dependencies=[Depends(first_dependency), Depends(second_dependency)],
    )

    client = TestClient(app)
    response = client.post("/multi-deps", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert "first" in execution_order
    assert "second" in execution_order


async def test_endpoint_without_dependencies_is_accessible():
    """Test that endpoint without dependencies remains accessible (backward compatibility)."""
    app = FastAPI()
    agent = ChatAgent(name="test", instructions="Test agent", chat_client=build_chat_client())

    # No dependencies parameter - should be accessible without auth
    add_agent_framework_fastapi_endpoint(app, agent, path="/open")

    client = TestClient(app)
    response = client.post("/open", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
