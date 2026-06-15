# Copyright (c) Microsoft. All rights reserved.

"""Tests for FastAPI endpoint creation (_endpoint.py)."""

import json
from typing import Any

import pytest
from ag_ui.core import MessagesSnapshotEvent, RunStartedEvent, StateSnapshotEvent
from agent_framework import (
    Agent,
    ChatResponseUpdate,
    Content,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.orchestrations import SequentialBuilder
from fastapi import FastAPI, Header, HTTPException
from fastapi.params import Depends
from fastapi.testclient import TestClient

from agent_framework_ag_ui import InMemoryAGUIThreadSnapshotStore, add_agent_framework_fastapi_endpoint
from agent_framework_ag_ui._agent import AgentFrameworkAgent
from agent_framework_ag_ui._workflow import AgentFrameworkWorkflow


def _decode_sse_events(response: Any) -> list[dict[str, Any]]:
    content = response.content.decode("utf-8")
    return [json.loads(line[6:]) for line in content.splitlines() if line.startswith("data: ")]


def _latest_messages_snapshot(response: Any) -> list[dict[str, Any]]:
    snapshots = [
        event["messages"] for event in _decode_sse_events(response) if event.get("type") == "MESSAGES_SNAPSHOT"
    ]
    assert snapshots
    return snapshots[-1]


@pytest.fixture
def build_chat_client(streaming_chat_client_stub, stream_from_updates_fixture):
    """Create a typed chat client stub for endpoint tests."""

    def _build(response_text: str = "Test response"):
        updates = [ChatResponseUpdate(contents=[Content.from_text(text=response_text)])]
        return streaming_chat_client_stub(stream_from_updates_fixture(updates))

    return _build


async def test_add_endpoint_with_agent_protocol(build_chat_client):
    """Test adding endpoint with raw SupportsAgentRun."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/test-agent")

    client = TestClient(app)
    response = client.post("/test-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_add_endpoint_with_wrapped_agent(build_chat_client):
    """Test adding endpoint with pre-wrapped AgentFrameworkAgent."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    wrapped_agent = AgentFrameworkAgent(agent=agent, name="wrapped")

    add_agent_framework_fastapi_endpoint(app, wrapped_agent, path="/wrapped-agent")

    client = TestClient(app)
    response = client.post("/wrapped-agent", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_add_endpoint_with_workflow_protocol():
    """Test adding endpoint with native Workflow support."""

    @executor(id="start")
    async def start(message: Any, ctx: WorkflowContext) -> None:
        await ctx.yield_output("Workflow response")

    app = FastAPI()
    workflow = WorkflowBuilder(start_executor=start).build()

    add_agent_framework_fastapi_endpoint(app, workflow, path="/workflow")

    client = TestClient(app)
    response = client.post("/workflow", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    content = response.content.decode("utf-8")
    lines = [line for line in content.split("\n") if line.startswith("data: ")]
    event_types = [json.loads(line[6:]).get("type") for line in lines]
    assert "RUN_STARTED" in event_types
    assert "TEXT_MESSAGE_CONTENT" in event_types
    assert "RUN_FINISHED" in event_types


async def test_endpoint_with_state_schema(build_chat_client):
    """Test endpoint with state_schema parameter."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    state_schema = {"document": {"type": "string"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/stateful", state_schema=state_schema)

    client = TestClient(app)
    response = client.post(
        "/stateful", json={"messages": [{"role": "user", "content": "Hello"}], "state": {"document": ""}}
    )

    assert response.status_code == 200


async def test_endpoint_with_default_state_seed(build_chat_client):
    """Test endpoint seeds default state when client omits it."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
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


async def test_endpoint_with_predict_state_config(build_chat_client):
    """Test endpoint with predict_state_config parameter."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    predict_config = {"document": {"tool": "write_doc", "tool_argument": "content"}}

    add_agent_framework_fastapi_endpoint(app, agent, path="/predictive", predict_state_config=predict_config)

    client = TestClient(app)
    response = client.post("/predictive", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_request_logging(build_chat_client):
    """Test that endpoint logs request details."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

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


async def test_endpoint_event_streaming(build_chat_client):
    """Test that endpoint streams events correctly."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client("Streamed response"))

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


async def test_endpoint_with_workflow_as_agent_stream_output(build_chat_client):
    """Test endpoint handles workflow-as-agent stream outputs."""
    app = FastAPI()
    brainstorm_agent = Agent(name="brainstorm", instructions="Brainstorm ideas", client=build_chat_client("Idea"))
    reviewer_agent = Agent(name="reviewer", instructions="Review ideas", client=build_chat_client("Review"))
    agent = SequentialBuilder(participants=[brainstorm_agent, reviewer_agent]).build().as_agent()

    add_agent_framework_fastapi_endpoint(app, agent, path="/workflow-like")

    client = TestClient(app)
    response = client.post("/workflow-like", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    lines = [line for line in content.split("\n") if line.startswith("data: ")]
    event_types = [json.loads(line[6:]).get("type") for line in lines]

    assert "RUN_STARTED" in event_types
    assert "TEXT_MESSAGE_CONTENT" in event_types
    assert "RUN_FINISHED" in event_types


async def test_endpoint_error_handling(build_chat_client):
    """Test endpoint error handling during request parsing."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/failing")

    client = TestClient(app)

    # Send invalid JSON to trigger parsing error before streaming
    response = client.post("/failing", data=b"invalid json", headers={"content-type": "application/json"})  # type: ignore

    # Pydantic validation now returns 422 for invalid request body
    assert response.status_code == 422


async def test_endpoint_multiple_paths(build_chat_client):
    """Test adding multiple endpoints with different paths."""
    app = FastAPI()
    agent1 = Agent(name="agent1", instructions="First agent", client=build_chat_client("Response 1"))
    agent2 = Agent(name="agent2", instructions="Second agent", client=build_chat_client("Response 2"))

    add_agent_framework_fastapi_endpoint(app, agent1, path="/agent1")
    add_agent_framework_fastapi_endpoint(app, agent2, path="/agent2")

    client = TestClient(app)

    response1 = client.post("/agent1", json={"messages": [{"role": "user", "content": "Hi"}]})
    response2 = client.post("/agent2", json={"messages": [{"role": "user", "content": "Hi"}]})

    assert response1.status_code == 200
    assert response2.status_code == 200


async def test_endpoint_default_path(build_chat_client):
    """Test endpoint with default path."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent)

    client = TestClient(app)
    response = client.post("/", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200


async def test_endpoint_response_headers(build_chat_client):
    """Test that endpoint sets correct response headers."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/headers")

    client = TestClient(app)
    response = client.post("/headers", json={"messages": [{"role": "user", "content": "Test"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert "cache-control" in response.headers
    assert response.headers["cache-control"] == "no-cache"


async def test_endpoint_empty_messages(streaming_chat_client_stub):
    """Empty messages keep the existing no-op run behavior when snapshot persistence is not configured."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        yield ChatResponseUpdate(contents=[Content.from_text(text="Should not run")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))

    add_agent_framework_fastapi_endpoint(app, agent, path="/empty")

    client = TestClient(app)
    response = client.post("/empty", json={"messages": []})

    assert response.status_code == 200
    assert call_count == 0
    assert [event.get("type") for event in _decode_sse_events(response)] == ["RUN_STARTED", "RUN_FINISHED"]


async def test_endpoint_complex_input(build_chat_client):
    """Test endpoint with complex input data."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

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


async def test_endpoint_openapi_schema(build_chat_client):
    """Test that endpoint generates proper OpenAPI schema with request model."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

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


async def test_endpoint_default_tags(build_chat_client):
    """Test that endpoint uses default 'AG-UI' tag."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/default-tags")

    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_spec = response.json()

    endpoint_spec = openapi_spec["paths"]["/default-tags"]["post"]
    assert "tags" in endpoint_spec
    assert endpoint_spec["tags"] == ["AG-UI"]


async def test_endpoint_custom_tags(build_chat_client):
    """Test that endpoint accepts custom tags."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/custom-tags", tags=["Custom", "Agent"])

    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_spec = response.json()

    endpoint_spec = openapi_spec["paths"]["/custom-tags"]["post"]
    assert "tags" in endpoint_spec
    assert endpoint_spec["tags"] == ["Custom", "Agent"]


async def test_endpoint_missing_required_field(build_chat_client):
    """Test that endpoint validates required fields with Pydantic."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    add_agent_framework_fastapi_endpoint(app, agent, path="/validation")

    client = TestClient(app)

    # Missing required 'messages' field should trigger validation error
    response = client.post("/validation", json={"run_id": "test-123"})

    assert response.status_code == 422
    error_detail = response.json()
    assert "detail" in error_detail


async def test_endpoint_internal_error_handling(build_chat_client):
    """Test endpoint error handling when an exception occurs before streaming starts."""
    from unittest.mock import patch

    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    # Use default_state to trigger the code path that can raise an exception
    add_agent_framework_fastapi_endpoint(app, agent, path="/error-test", default_state={"key": "value"})

    client = TestClient(app)

    # Mock copy.deepcopy to raise an exception during default_state processing
    with patch("agent_framework_ag_ui._endpoint.copy.deepcopy") as mock_deepcopy:
        mock_deepcopy.side_effect = Exception("Simulated internal error")
        response = client.post("/error-test", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 500
    assert response.json() == {"detail": "An internal error has occurred."}


async def test_endpoint_streaming_error_emits_run_error_event():
    """Streaming exceptions should emit RUN_ERROR instead of terminating silently."""

    class FailingStreamWorkflow(AgentFrameworkWorkflow):
        async def run(self, input_data: dict[str, Any]):
            del input_data
            yield RunStartedEvent(run_id="run-1", thread_id="thread-1")
            raise RuntimeError("stream exploded")

    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, FailingStreamWorkflow(), path="/stream-error")
    client = TestClient(app)

    response = client.post("/stream-error", json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 200

    content = response.content.decode("utf-8")
    lines = [line for line in content.split("\n") if line.startswith("data: ")]
    event_types = [json.loads(line[6:]).get("type") for line in lines]

    assert "RUN_STARTED" in event_types
    assert "RUN_ERROR" in event_types


async def test_endpoint_with_dependencies_blocks_unauthorized(build_chat_client):
    """Test that endpoint blocks requests when authentication dependency fails."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    async def require_api_key(x_api_key: str | None = Header(None)):
        if x_api_key != "secret-key":
            raise HTTPException(status_code=401, detail="Unauthorized")

    add_agent_framework_fastapi_endpoint(app, agent, path="/protected", dependencies=[Depends(require_api_key)])

    client = TestClient(app)

    # Request without API key should be rejected
    response = client.post("/protected", json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_endpoint_with_dependencies_allows_authorized(build_chat_client):
    """Test that endpoint allows requests when authentication dependency passes."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

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


async def test_endpoint_with_multiple_dependencies(build_chat_client):
    """Test that endpoint supports multiple dependencies."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

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


async def test_endpoint_without_dependencies_is_accessible(build_chat_client):
    """Test that endpoint without dependencies remains accessible (backward compatibility)."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())

    # No dependencies parameter - should be accessible without auth
    add_agent_framework_fastapi_endpoint(app, agent, path="/open")

    client = TestClient(app)
    response = client.post("/open", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_endpoint_invalid_agent_type_raises_typeerror():
    """Passing an invalid agent type raises TypeError."""
    app = FastAPI()

    with pytest.raises(TypeError, match="must be SupportsAgentRun"):
        add_agent_framework_fastapi_endpoint(app, agent="not_an_agent")  # type: ignore[arg-type]


async def test_endpoint_requires_snapshot_scope_resolver_when_store_configured(build_chat_client):
    """Snapshot persistence setup must require an explicit Snapshot Scope resolver."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    store = InMemoryAGUIThreadSnapshotStore()

    with pytest.raises(ValueError, match="snapshot_scope_resolver is required"):
        add_agent_framework_fastapi_endpoint(app, agent, path="/snapshots", snapshot_store=store)


async def test_endpoint_requires_snapshot_scope_resolver_when_wrapped_runner_has_store(build_chat_client):
    """Pre-wrapped runners with snapshot stores must also provide a Snapshot Scope resolver."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    wrapped_agent = AgentFrameworkAgent(agent=agent, snapshot_store=InMemoryAGUIThreadSnapshotStore())

    with pytest.raises(ValueError, match="snapshot_scope_resolver is required"):
        add_agent_framework_fastapi_endpoint(app, wrapped_agent, path="/snapshots")


async def test_endpoint_accepts_snapshot_store_with_scope_resolver(build_chat_client):
    """Endpoint behavior remains the normal event stream when snapshot persistence is explicitly configured."""
    app = FastAPI()
    agent = Agent(name="test", instructions="Test agent", client=build_chat_client())
    store = InMemoryAGUIThreadSnapshotStore()

    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )

    client = TestClient(app)
    response = client.post(
        "/snapshots",
        json={"messages": [{"role": "user", "content": "Hello"}], "thread_id": "thread-1"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


async def test_agent_endpoint_hydrates_stored_thread_snapshot_without_invoking_agent(streaming_chat_client_stub):
    """A Hydrate Request replays stored agent messages and state without invoking the wrapped agent."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        yield ChatResponseUpdate(contents=[Content.from_text(text="Stored reply")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"recipe": {"type": "string"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"role": "user", "content": "Hello"}],
            "state": {"recipe": "pasta"},
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1

    hydrate_response = client.post("/snapshots", json={"thread_id": "thread-1", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    event_types = [event.get("type") for event in events]
    assert event_types == ["RUN_STARTED", "STATE_SNAPSHOT", "MESSAGES_SNAPSHOT", "RUN_FINISHED"]
    assert events[1]["snapshot"] == {"recipe": "pasta"}
    assert any(message.get("role") == "user" and message.get("content") == "Hello" for message in events[2]["messages"])
    assert any(
        message.get("role") == "assistant" and message.get("content") == "Stored reply"
        for message in events[2]["messages"]
    )


async def test_agent_endpoint_hydrates_snapshots_by_scope_and_thread(streaming_chat_client_stub):
    """Hydration uses Snapshot Scope and AG-UI Thread id together when reading stored snapshots."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        yield ChatResponseUpdate(contents=[Content.from_text(text="Tenant A reply")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"tenant": {"type": "string"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda request: request.forwarded_props["tenant"],
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"role": "user", "content": "Hello tenant A"}],
            "state": {"tenant": "tenant-a"},
            "forwardedProps": {"tenant": "tenant-a"},
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1

    tenant_b_response = client.post(
        "/snapshots",
        json={"thread_id": "thread-1", "messages": [], "forwardedProps": {"tenant": "tenant-b"}},
    )
    assert tenant_b_response.status_code == 200
    assert call_count == 1
    assert [event.get("type") for event in _decode_sse_events(tenant_b_response)] == [
        "RUN_STARTED",
        "RUN_FINISHED",
    ]

    tenant_a_response = client.post(
        "/snapshots",
        json={"thread_id": "thread-1", "messages": [], "forwardedProps": {"tenant": "tenant-a"}},
    )
    assert tenant_a_response.status_code == 200
    assert call_count == 1
    tenant_a_events = _decode_sse_events(tenant_a_response)
    assert [event.get("type") for event in tenant_a_events] == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "MESSAGES_SNAPSHOT",
        "RUN_FINISHED",
    ]
    assert tenant_a_events[1]["snapshot"] == {"tenant": "tenant-a"}
    assert any(message.get("content") == "Tenant A reply" for message in tenant_a_events[2]["messages"])


async def test_agent_endpoint_prepends_stored_snapshot_for_new_user_turn(streaming_chat_client_stub):
    """A normal agent turn with a known thread id prepends stored history and keeps the new user input."""
    app = FastAPI()
    captured_messages: list[list[tuple[str, str]]] = []

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del options, kwargs
        captured_messages.append([(message.role, message.text) for message in messages])
        yield ChatResponseUpdate(contents=[Content.from_text(text=f"Reply {len(captured_messages)}")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"recipe": {"type": "string"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-1", "role": "user", "content": "Plan dinner"}],
            "state": {"recipe": "pasta"},
        },
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-2", "role": "user", "content": "Add dessert"}],
        },
    )

    assert second_response.status_code == 200
    assert len(captured_messages) == 2
    assert captured_messages[1] == [
        ("user", "Plan dinner"),
        ("assistant", "Reply 1"),
        (
            "system",
            (
                "Current state of the application:\n"
                '{\n  "recipe": "pasta"\n}\n\n'
                "When modifying state, you MUST include ALL existing data plus your changes.\n"
                "For example, if adding one new item to a list, include ALL existing items PLUS the new item.\n"
                "Never replace existing data - always preserve and append or merge."
            ),
        ),
        ("user", "Add dessert"),
    ]
    events = _decode_sse_events(second_response)
    state_snapshots = [event for event in events if event.get("type") == "STATE_SNAPSHOT"]
    assert state_snapshots[0]["snapshot"] == {"recipe": "pasta"}


async def test_agent_endpoint_deduplicates_full_history_and_merges_fresh_state(streaming_chat_client_stub):
    """Stored prior history is authoritative while incoming full history and fresh state remain supported."""
    app = FastAPI()
    captured_messages: list[list[tuple[str, str]]] = []

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del options, kwargs
        captured_messages.append([(message.role, message.text) for message in messages])
        yield ChatResponseUpdate(contents=[Content.from_text(text=f"Reply {len(captured_messages)}")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"recipe": {"type": "string"}, "theme": {"type": "string"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-1", "role": "user", "content": "Plan dinner"}],
            "state": {"recipe": "pasta", "theme": "dark"},
        },
    )
    assert first_response.status_code == 200
    first_snapshot = _latest_messages_snapshot(first_response)

    second_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [*first_snapshot, {"id": "user-2", "role": "user", "content": "Add dessert"}],
            "state": {"recipe": "salad"},
        },
    )
    assert second_response.status_code == 200

    second_non_system_messages = [message for message in captured_messages[1] if message[0] != "system"]
    assert second_non_system_messages == [
        ("user", "Plan dinner"),
        ("assistant", "Reply 1"),
        ("user", "Add dessert"),
    ]
    second_events = _decode_sse_events(second_response)
    second_state_snapshots = [event for event in second_events if event.get("type") == "STATE_SNAPSHOT"]
    assert second_state_snapshots[0]["snapshot"] == {"recipe": "salad", "theme": "dark"}

    second_snapshot = _latest_messages_snapshot(second_response)
    conflicting_history = [message.copy() for message in second_snapshot]
    conflicting_history[0]["content"] = "Tampered dinner plan"
    conflicting_history[1]["content"] = "Tampered reply"
    third_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [*conflicting_history, {"id": "user-3", "role": "user", "content": "Pick wine"}],
        },
    )
    assert third_response.status_code == 200

    third_texts = [text for role, text in captured_messages[2] if role != "system"]
    assert third_texts == ["Plan dinner", "Reply 1", "Add dessert", "Reply 2", "Pick wine"]
    assert "Tampered dinner plan" not in third_texts
    assert "Tampered reply" not in third_texts
    third_state_snapshots = [
        event for event in _decode_sse_events(third_response) if event.get("type") == "STATE_SNAPSHOT"
    ]
    assert third_state_snapshots[0]["snapshot"] == {"recipe": "salad", "theme": "dark"}


async def test_agent_endpoint_hydrates_interrupted_thread_without_invoking_agent(streaming_chat_client_stub):
    """Hydrating an interrupted agent replays state, messages, and interrupt metadata without resuming it."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        yield ChatResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="draft_steps",
                    call_id="draft-call",
                    arguments=json.dumps({"steps": [{"description": "Draft outline"}]}),
                )
            ],
            role="assistant",
        )

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"steps": {"type": "array", "items": {"type": "object"}}},
        predict_state_config={"steps": {"tool": "draft_steps", "tool_argument": "steps"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "agent-thread",
            "messages": [{"role": "user", "content": "Draft the plan"}],
            "state": {"steps": []},
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1
    first_events = _decode_sse_events(first_response)
    first_finished = [event for event in first_events if event.get("type") == "RUN_FINISHED"]
    assert first_finished[-1]["interrupt"][0]["value"]["function_call"]["call_id"] == "draft-call"

    hydrate_response = client.post("/snapshots", json={"thread_id": "agent-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    assert [event.get("type") for event in events] == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "MESSAGES_SNAPSHOT",
        "RUN_FINISHED",
    ]
    assert events[1]["snapshot"] == {"steps": [{"description": "Draft outline"}]}
    assert events[-1]["interrupt"][0]["value"]["function_call"]["name"] == "draft_steps"


async def test_agent_endpoint_run_error_does_not_overwrite_previous_snapshot(streaming_chat_client_stub):
    """A failing agent turn leaves the last good AG-UI Thread Snapshot available for hydration."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        if call_count == 1:
            yield ChatResponseUpdate(contents=[Content.from_text(text="Stable reply")])
            return
        raise RuntimeError("agent exploded")

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={"thread_id": "agent-thread", "messages": [{"role": "user", "content": "Start"}]},
    )
    assert first_response.status_code == 200
    assert call_count == 1

    error_response = client.post(
        "/snapshots",
        json={"thread_id": "agent-thread", "messages": [{"role": "user", "content": "Break the run"}]},
    )
    assert error_response.status_code == 200
    assert call_count == 2
    assert "RUN_ERROR" in [event.get("type") for event in _decode_sse_events(error_response)]

    hydrate_response = client.post("/snapshots", json={"thread_id": "agent-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 2
    messages = _latest_messages_snapshot(hydrate_response)
    assert any(message.get("role") == "assistant" and message.get("content") == "Stable reply" for message in messages)
    assert not any(message.get("content") == "Break the run" for message in messages)


async def test_workflow_endpoint_hydrates_emitted_snapshots_without_invoking_workflow():
    """A workflow Hydrate Request replays emitted snapshots without invoking the wrapped workflow."""
    app = FastAPI()
    call_count = 0

    @executor(id="snapshotter")
    async def snapshotter(message: Any, ctx: WorkflowContext) -> None:
        nonlocal call_count
        del message
        call_count += 1
        await ctx.yield_output(StateSnapshotEvent(snapshot={"active_agent": "flights"}))
        await ctx.yield_output(
            MessagesSnapshotEvent(
                messages=[{"id": "assistant-snapshot", "role": "assistant", "content": "Stored workflow reply"}]
            )
        )

    workflow = WorkflowBuilder(start_executor=snapshotter).build()
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        workflow,
        path="/workflow-snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/workflow-snapshots",
        json={"thread_id": "workflow-thread", "messages": [{"role": "user", "content": "Start workflow"}]},
    )
    assert first_response.status_code == 200
    assert call_count == 1

    hydrate_response = client.post("/workflow-snapshots", json={"thread_id": "workflow-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    assert [event.get("type") for event in events] == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "MESSAGES_SNAPSHOT",
        "RUN_FINISHED",
    ]
    assert events[1]["snapshot"] == {"active_agent": "flights"}
    assert events[2]["messages"] == [
        {"id": "assistant-snapshot", "role": "assistant", "content": "Stored workflow reply"}
    ]


async def test_workflow_endpoint_hydrates_synthesized_text_and_tool_snapshot():
    """Workflow text and tool output are synthesized into replayable snapshot messages."""
    app = FastAPI()
    call_count = 0

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext) -> None:
        nonlocal call_count
        del message
        call_count += 1
        await ctx.yield_output("Workflow answer")
        await ctx.yield_output(
            [
                Content.from_function_call(
                    name="lookup_weather",
                    call_id="call-1",
                    arguments='{"city":"SF"}',
                ),
                Content.from_function_result(call_id="call-1", result="72F"),
            ]
        )
        await ctx.yield_output({"diagnostic": "not persisted"})

    workflow = WorkflowBuilder(start_executor=responder).build()
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        workflow,
        path="/workflow-snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/workflow-snapshots",
        json={
            "thread_id": "workflow-thread",
            "messages": [{"id": "user-1", "role": "user", "content": "Start workflow"}],
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1

    hydrate_response = client.post("/workflow-snapshots", json={"thread_id": "workflow-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    assert [event.get("type") for event in events] == ["RUN_STARTED", "MESSAGES_SNAPSHOT", "RUN_FINISHED"]
    messages = events[1]["messages"]
    assert any(message.get("role") == "user" and message.get("content") == "Start workflow" for message in messages)
    assert any(
        message.get("role") == "assistant" and message.get("content") == "Workflow answer" for message in messages
    )
    tool_call_messages = [
        message for message in messages if message.get("role") == "assistant" and message.get("toolCalls")
    ]
    assert len(tool_call_messages) == 1
    tool_call = tool_call_messages[0]["toolCalls"][0]
    assert tool_call["id"] == "call-1"
    assert tool_call["function"] == {"name": "lookup_weather", "arguments": '{"city":"SF"}'}
    assert any(
        message.get("role") == "tool" and message.get("toolCallId") == "call-1" and message.get("content") == "72F"
        for message in messages
    )


async def test_workflow_endpoint_hydrates_interrupted_thread_without_invoking_workflow():
    """Hydrating an interrupted workflow replays state, messages, and interrupt metadata without resuming it."""
    app = FastAPI()
    call_count = 0

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        nonlocal call_count
        del message
        call_count += 1
        await ctx.yield_output(StateSnapshotEvent(snapshot={"step": "approval"}))
        await ctx.request_info(
            {"message": "Approve workflow step", "options": ["Approve", "Reject"]},
            dict,
            request_id="workflow-approval",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        workflow,
        path="/workflow-snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/workflow-snapshots",
        json={"thread_id": "workflow-thread", "messages": [{"role": "user", "content": "Start workflow"}]},
    )
    assert first_response.status_code == 200
    assert call_count == 1
    first_finished = [event for event in _decode_sse_events(first_response) if event.get("type") == "RUN_FINISHED"]
    assert first_finished[-1]["interrupt"][0]["id"] == "workflow-approval"

    hydrate_response = client.post("/workflow-snapshots", json={"thread_id": "workflow-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    assert [event.get("type") for event in events] == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "MESSAGES_SNAPSHOT",
        "RUN_FINISHED",
    ]
    assert events[1]["snapshot"] == {"step": "approval"}
    assert events[-1]["interrupt"][0]["id"] == "workflow-approval"
    assert events[-1]["interrupt"][0]["value"]["message"] == "Approve workflow step"


async def test_workflow_endpoint_run_error_does_not_overwrite_previous_snapshot():
    """A failing workflow turn leaves the last good AG-UI Thread Snapshot available for hydration."""
    app = FastAPI()
    call_count = 0

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext) -> None:
        nonlocal call_count
        del message
        call_count += 1
        if call_count == 1:
            await ctx.yield_output("Stable workflow reply")
            return
        raise RuntimeError("workflow exploded")

    workflow = WorkflowBuilder(start_executor=responder).build()
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        workflow,
        path="/workflow-snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/workflow-snapshots",
        json={"thread_id": "workflow-thread", "messages": [{"role": "user", "content": "Start workflow"}]},
    )
    assert first_response.status_code == 200
    assert call_count == 1

    error_response = client.post(
        "/workflow-snapshots",
        json={"thread_id": "workflow-thread", "messages": [{"role": "user", "content": "Break workflow"}]},
    )
    assert error_response.status_code == 200
    assert call_count == 2
    assert "RUN_ERROR" in [event.get("type") for event in _decode_sse_events(error_response)]

    hydrate_response = client.post("/workflow-snapshots", json={"thread_id": "workflow-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 2
    messages = _latest_messages_snapshot(hydrate_response)
    assert any(
        message.get("role") == "assistant" and message.get("content") == "Stable workflow reply" for message in messages
    )
    assert not any(message.get("content") == "Break workflow" for message in messages)


async def test_endpoint_encoding_failure_emits_run_error():
    """Event encoding failure emits RUN_ERROR event in the SSE stream."""
    from unittest.mock import patch

    class SimpleWorkflow(AgentFrameworkWorkflow):
        async def run(self, input_data: dict[str, Any]):
            del input_data
            yield RunStartedEvent(run_id="run-1", thread_id="thread-1")

    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, SimpleWorkflow(), path="/encode-fail")
    client = TestClient(app)

    with patch("ag_ui.encoder.EventEncoder.encode") as mock_encode:
        # First call fails (the RUN_STARTED event), second call succeeds (the error event)
        mock_encode.side_effect = [ValueError("encode boom"), 'data: {"type":"RUN_ERROR"}\n\n']
        response = client.post("/encode-fail", json={"messages": [{"role": "user", "content": "go"}]})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "RUN_ERROR" in content


async def test_endpoint_double_encoding_failure_terminates():
    """When both event and error encoding fail, stream terminates gracefully."""
    from unittest.mock import patch

    class SimpleWorkflow(AgentFrameworkWorkflow):
        async def run(self, input_data: dict[str, Any]):
            del input_data
            yield RunStartedEvent(run_id="run-1", thread_id="thread-1")

    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, SimpleWorkflow(), path="/double-fail")
    client = TestClient(app)

    with patch("ag_ui.encoder.EventEncoder.encode") as mock_encode:
        # Both calls fail - event encode and error event encode
        mock_encode.side_effect = ValueError("always fails")
        response = client.post("/double-fail", json={"messages": [{"role": "user", "content": "go"}]})

    # Should still get 200 (SSE stream), just with no events
    assert response.status_code == 200


async def test_agent_endpoint_confirm_changes_clears_persisted_interrupt(streaming_chat_client_stub):
    """A confirm_changes response persists the completed turn and clears the stored interrupt."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        yield ChatResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="draft_steps",
                    call_id="draft-call",
                    arguments=json.dumps({"steps": [{"description": "Draft outline"}]}),
                )
            ],
            role="assistant",
        )

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"steps": {"type": "array", "items": {"type": "object"}}},
        predict_state_config={"steps": {"tool": "draft_steps", "tool_argument": "steps"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "agent-thread",
            "messages": [{"id": "user-1", "role": "user", "content": "Draft the plan"}],
            "state": {"steps": []},
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1
    first_events = _decode_sse_events(first_response)
    first_finished = [event for event in first_events if event.get("type") == "RUN_FINISHED"]
    assert first_finished[-1]["interrupt"]
    confirm_call_id = first_finished[-1]["interrupt"][0]["id"]

    confirm_response = client.post(
        "/snapshots",
        json={
            "thread_id": "agent-thread",
            "messages": [],
            "resume": {"interrupts": [{"id": confirm_call_id, "value": json.dumps({"accepted": True, "steps": []})}]},
        },
    )
    assert confirm_response.status_code == 200
    assert call_count == 1
    confirm_event_types = [event.get("type") for event in _decode_sse_events(confirm_response)]
    assert "TEXT_MESSAGE_CONTENT" in confirm_event_types

    hydrate_response = client.post("/snapshots", json={"thread_id": "agent-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 1
    events = _decode_sse_events(hydrate_response)
    assert not events[-1].get("interrupt")
    messages = _latest_messages_snapshot(hydrate_response)
    assert any(
        message.get("role") == "assistant" and message.get("content") == "Changes confirmed and applied successfully!"
        for message in messages
    )
    assert any(message.get("role") == "user" and message.get("content") == "Draft the plan" for message in messages)


async def test_agent_endpoint_default_state_does_not_reset_persisted_state(streaming_chat_client_stub):
    """Endpoint defaults fill missing keys but never override persisted Shared State."""
    app = FastAPI()

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del messages, options, kwargs
        yield ChatResponseUpdate(contents=[Content.from_text(text="Reply")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"recipe": {"type": "string"}},
        default_state={"recipe": ""},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    fresh_response = client.post(
        "/snapshots",
        json={"thread_id": "thread-fresh", "messages": [{"id": "user-0", "role": "user", "content": "Hi"}]},
    )
    assert fresh_response.status_code == 200
    fresh_state_snapshots = [
        event for event in _decode_sse_events(fresh_response) if event.get("type") == "STATE_SNAPSHOT"
    ]
    assert fresh_state_snapshots[0]["snapshot"] == {"recipe": ""}

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-1", "role": "user", "content": "Plan dinner"}],
            "state": {"recipe": "pasta"},
        },
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-2", "role": "user", "content": "Add dessert"}],
        },
    )
    assert second_response.status_code == 200
    second_state_snapshots = [
        event for event in _decode_sse_events(second_response) if event.get("type") == "STATE_SNAPSHOT"
    ]
    assert second_state_snapshots[0]["snapshot"] == {"recipe": "pasta"}

    hydrate_response = client.post("/snapshots", json={"thread_id": "thread-1", "messages": []})
    assert hydrate_response.status_code == 200
    hydrate_events = _decode_sse_events(hydrate_response)
    hydrate_state_snapshots = [event for event in hydrate_events if event.get("type") == "STATE_SNAPSHOT"]
    assert hydrate_state_snapshots[0]["snapshot"] == {"recipe": "pasta"}


async def test_agent_endpoint_persists_turn_output_when_intermediate_snapshot_suppressed(streaming_chat_client_stub):
    """A no-confirmation predictive turn persists tool output even when the outbound snapshot is suppressed."""
    app = FastAPI()

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del messages, options, kwargs
        yield ChatResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="write_doc",
                    call_id="doc-call",
                    arguments=json.dumps({"document": "Draft text"}),
                )
            ],
            role="assistant",
        )
        yield ChatResponseUpdate(
            contents=[Content.from_function_result(call_id="doc-call", result="ok")],
            role="tool",
        )
        yield ChatResponseUpdate(contents=[Content.from_text(text="Done writing")], role="assistant")

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    wrapped = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "document"}},
        require_confirmation=False,
    )
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        wrapped,
        path="/snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "doc-thread",
            "messages": [{"id": "user-1", "role": "user", "content": "Write the doc"}],
        },
    )
    assert first_response.status_code == 200
    first_event_types = [event.get("type") for event in _decode_sse_events(first_response)]
    assert "MESSAGES_SNAPSHOT" not in first_event_types

    hydrate_response = client.post("/snapshots", json={"thread_id": "doc-thread", "messages": []})

    assert hydrate_response.status_code == 200
    messages = _latest_messages_snapshot(hydrate_response)
    assert any(message.get("role") == "assistant" and message.get("content") == "Done writing" for message in messages)
    assert any(message.get("role") == "tool" and message.get("toolCallId") == "doc-call" for message in messages)


async def test_workflow_preserves_history_across_turns():
    """Workflow follow-up turns merge stored history so persisted snapshots keep earlier turns.

    Uses async runner.run() directly instead of HTTP TestClient because the sync
    TestClient runs each request in a different event loop, which conflicts with
    the workflow's asyncio Queue across turns.
    """
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY

    call_count = 0

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext) -> None:
        nonlocal call_count
        del message
        call_count += 1
        await ctx.yield_output(f"Workflow reply {call_count}")

    workflow = WorkflowBuilder(start_executor=responder).build()
    store = InMemoryAGUIThreadSnapshotStore()
    runner = AgentFrameworkWorkflow(workflow=workflow, snapshot_store=store)

    first_events = [
        event
        async for event in runner.run(
            {
                "thread_id": "workflow-thread",
                "run_id": "run-1",
                "messages": [{"id": "user-1", "role": "user", "content": "First question"}],
                _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
            }
        )
    ]
    assert first_events
    assert call_count == 1

    second_events = [
        event
        async for event in runner.run(
            {
                "thread_id": "workflow-thread",
                "run_id": "run-2",
                "messages": [{"id": "user-2", "role": "user", "content": "Second question"}],
                _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
            }
        )
    ]
    assert second_events
    assert call_count == 2

    snapshot = await store.get(scope="tenant-a", thread_id="workflow-thread")
    assert snapshot is not None
    contents = [message.get("content") for message in snapshot.messages]
    assert "First question" in contents
    assert "Workflow reply 1" in contents
    assert "Second question" in contents
    assert "Workflow reply 2" in contents

    hydrate_events = [
        event
        async for event in runner.run(
            {
                "thread_id": "workflow-thread",
                "run_id": "run-3",
                "messages": [],
                _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
            }
        )
    ]
    assert call_count == 2
    hydrated_snapshots = [event for event in hydrate_events if isinstance(event, MessagesSnapshotEvent)]
    assert hydrated_snapshots


async def test_agent_endpoint_resume_preserves_persisted_history(streaming_chat_client_stub):
    """A generic interrupt resume keeps stored history in the persisted snapshot."""
    app = FastAPI()
    call_count = 0

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        nonlocal call_count
        del messages, options, kwargs
        call_count += 1
        if call_count == 1:
            yield ChatResponseUpdate(
                contents=[
                    Content.from_function_call(
                        name="draft_steps",
                        call_id="draft-call",
                        arguments=json.dumps({"steps": [{"description": "Draft outline"}]}),
                    )
                ],
                role="assistant",
            )
            return
        yield ChatResponseUpdate(contents=[Content.from_text(text="Resumed reply")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        state_schema={"steps": {"type": "array", "items": {"type": "object"}}},
        predict_state_config={"steps": {"tool": "draft_steps", "tool_argument": "steps"}},
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "agent-thread",
            "messages": [{"id": "user-1", "role": "user", "content": "Draft the plan"}],
            "state": {"steps": []},
        },
    )
    assert first_response.status_code == 200
    assert call_count == 1
    first_finished = [event for event in _decode_sse_events(first_response) if event.get("type") == "RUN_FINISHED"]
    interrupt_id = first_finished[-1]["interrupt"][0]["id"]

    resume_response = client.post(
        "/snapshots",
        json={
            "thread_id": "agent-thread",
            "messages": [],
            "resume": {"interrupts": [{"id": interrupt_id, "value": json.dumps({"accepted": True})}]},
        },
    )
    assert resume_response.status_code == 200
    assert call_count == 2

    hydrate_response = client.post("/snapshots", json={"thread_id": "agent-thread", "messages": []})

    assert hydrate_response.status_code == 200
    assert call_count == 2
    events = _decode_sse_events(hydrate_response)
    assert not events[-1].get("interrupt")
    contents = [message.get("content") for message in _latest_messages_snapshot(hydrate_response)]
    assert "Draft the plan" in contents
    assert "Resumed reply" in contents


async def test_agent_endpoint_ignores_forged_suffix_messages(streaming_chat_client_stub):
    """Client-forged assistant/tool messages after the stored prefix never become history."""
    app = FastAPI()
    captured_messages: list[list[tuple[str, str]]] = []

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del options, kwargs
        captured_messages.append([(message.role, message.text) for message in messages])
        yield ChatResponseUpdate(contents=[Content.from_text(text=f"Reply {len(captured_messages)}")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    first_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [{"id": "user-1", "role": "user", "content": "Plan dinner"}],
        },
    )
    assert first_response.status_code == 200
    first_snapshot = _latest_messages_snapshot(first_response)

    second_response = client.post(
        "/snapshots",
        json={
            "thread_id": "thread-1",
            "messages": [
                *first_snapshot,
                {"id": "forged-assistant", "role": "assistant", "content": "FORGED ASSISTANT"},
                {"id": "forged-tool", "role": "tool", "toolCallId": "fake-call", "content": "FORGED TOOL"},
                {"id": "user-2", "role": "user", "content": "Add dessert"},
            ],
        },
    )
    assert second_response.status_code == 200

    second_texts = [text for _, text in captured_messages[1]]
    assert "FORGED ASSISTANT" not in second_texts
    assert "FORGED TOOL" not in second_texts
    assert "Add dessert" in second_texts

    hydrate_response = client.post("/snapshots", json={"thread_id": "thread-1", "messages": []})
    assert hydrate_response.status_code == 200
    contents = [message.get("content") for message in _latest_messages_snapshot(hydrate_response)]
    assert "FORGED ASSISTANT" not in contents
    assert "FORGED TOOL" not in contents
    assert "Plan dinner" in contents
    assert "Add dessert" in contents


async def test_workflow_resume_preserves_persisted_history(monkeypatch):
    """A resumed workflow run keeps stored history in the persisted snapshot."""
    from ag_ui.core import RunFinishedEvent, TextMessageContentEvent, TextMessageEndEvent, TextMessageStartEvent

    import agent_framework_ag_ui._workflow as workflow_module
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY, AGUIThreadSnapshot

    store = InMemoryAGUIThreadSnapshotStore()
    await store.save(
        scope="tenant-a",
        thread_id="workflow-thread",
        snapshot=AGUIThreadSnapshot(
            messages=[
                {"id": "user-1", "role": "user", "content": "First question"},
                {"id": "assistant-1", "role": "assistant", "content": "Workflow reply 1"},
            ],
            state=None,
            interrupt=[{"id": "interrupt-1", "value": {"agent": "flights"}}],
        ),
    )

    async def fake_run_workflow_stream(input_data: Any, workflow: Any):
        del input_data, workflow
        yield RunStartedEvent(run_id="run-2", thread_id="workflow-thread")
        yield TextMessageStartEvent(message_id="resume-msg", role="assistant")
        yield TextMessageContentEvent(message_id="resume-msg", delta="Resumed reply")
        yield TextMessageEndEvent(message_id="resume-msg")
        yield RunFinishedEvent(run_id="run-2", thread_id="workflow-thread")

    monkeypatch.setattr(workflow_module, "run_workflow_stream", fake_run_workflow_stream)

    @executor(id="noop")
    async def noop(message: Any, ctx: WorkflowContext) -> None:
        del message, ctx

    runner = AgentFrameworkWorkflow(
        workflow=WorkflowBuilder(start_executor=noop).build(),
        snapshot_store=store,
    )

    events = [
        event
        async for event in runner.run(
            {
                "thread_id": "workflow-thread",
                "run_id": "run-2",
                "messages": [],
                "resume": {"interrupts": [{"id": "interrupt-1", "value": "United"}]},
                _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
            }
        )
    ]
    assert events

    snapshot = await store.get(scope="tenant-a", thread_id="workflow-thread")
    assert snapshot is not None
    contents = [message.get("content") for message in snapshot.messages]
    assert "First question" in contents
    assert "Workflow reply 1" in contents
    assert "Resumed reply" in contents
    assert snapshot.interrupt is None


class _FailingSaveStore(InMemoryAGUIThreadSnapshotStore):
    """Store whose save always fails, simulating a transient backend outage."""

    async def save(self, *, scope: str, thread_id: str, snapshot: Any) -> None:
        raise RuntimeError("store down")


async def test_agent_endpoint_snapshot_save_failure_does_not_fail_run(streaming_chat_client_stub):
    """A failing snapshot save must not turn a completed agent run into RUN_ERROR."""
    app = FastAPI()

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del messages, options, kwargs
        yield ChatResponseUpdate(contents=[Content.from_text(text="Reply")])

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        snapshot_store=_FailingSaveStore(),
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    response = client.post(
        "/snapshots",
        json={"thread_id": "thread-1", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 200
    event_types = [event.get("type") for event in _decode_sse_events(response)]
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types


async def test_workflow_endpoint_snapshot_save_failure_does_not_emit_run_error():
    """A failing snapshot save after RUN_FINISHED must not emit a second terminal RUN_ERROR."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.yield_output("Workflow reply")

    app = FastAPI()
    workflow = WorkflowBuilder(start_executor=responder).build()
    add_agent_framework_fastapi_endpoint(
        app,
        workflow,
        path="/workflow-snapshots",
        snapshot_store=_FailingSaveStore(),
        snapshot_scope_resolver=lambda _request: "tenant-a",
    )
    client = TestClient(app)

    response = client.post(
        "/workflow-snapshots",
        json={"thread_id": "workflow-thread", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 200
    event_types = [event.get("type") for event in _decode_sse_events(response)]
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types


async def test_endpoint_supports_async_snapshot_scope_resolver(streaming_chat_client_stub):
    """An async snapshot_scope_resolver is awaited before snapshots load or save."""
    app = FastAPI()

    async def stream_fn(messages: Any, options: Any, **kwargs: Any):
        del messages, options, kwargs
        yield ChatResponseUpdate(contents=[Content.from_text(text="Reply")])

    async def resolve_scope(_request: Any) -> str:
        return "tenant-async"

    agent = Agent(name="test", instructions="Test agent", client=streaming_chat_client_stub(stream_fn))
    store = InMemoryAGUIThreadSnapshotStore()
    add_agent_framework_fastapi_endpoint(
        app,
        agent,
        path="/snapshots",
        snapshot_store=store,
        snapshot_scope_resolver=resolve_scope,
    )
    client = TestClient(app)

    response = client.post(
        "/snapshots",
        json={"thread_id": "thread-1", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 200
    snapshot = await store.get(scope="tenant-async", thread_id="thread-1")
    assert snapshot is not None
    assert any(message.get("content") == "Reply" for message in snapshot.messages)


def test_workflow_factory_cache_is_scoped_by_snapshot_scope():
    """The same thread id under different Snapshot Scopes must not share a workflow instance."""

    @executor(id="noop")
    async def noop(message: Any, ctx: WorkflowContext) -> None:
        del message, ctx

    def factory(thread_id: str) -> Any:
        del thread_id
        return WorkflowBuilder(start_executor=noop).build()

    runner = AgentFrameworkWorkflow(workflow_factory=factory)

    workflow_a = runner._resolve_workflow("thread-1", "tenant-a")
    workflow_b = runner._resolve_workflow("thread-1", "tenant-b")
    assert workflow_a is not workflow_b
    assert runner._resolve_workflow("thread-1", "tenant-a") is workflow_a

    runner.clear_thread_workflow("thread-1", snapshot_scope="tenant-a")
    assert runner._resolve_workflow("thread-1", "tenant-a") is not workflow_a
    assert runner._resolve_workflow("thread-1", "tenant-b") is workflow_b

    runner.clear_thread_workflow("thread-1")
    assert runner._resolve_workflow("thread-1", "tenant-b") is not workflow_b
