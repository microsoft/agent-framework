# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for server functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui import DevServer
from agent_framework_devui._utils import extract_executor_message_types, select_primary_input_type
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


class _StubExecutor:
    """Simple executor stub exposing handler metadata."""

    def __init__(self, *, input_types=None, handlers=None):
        if input_types is not None:
            self.input_types = list(input_types)
        if handlers is not None:
            self._handlers = dict(handlers)


@pytest.fixture
def test_entities_dir():
    """Use the samples directory which has proper entity structure."""
    # Get the samples directory from the main python samples folder
    current_dir = Path(__file__).parent
    # Navigate to python/samples/getting_started/devui
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"
    return str(samples_dir.resolve())


async def test_server_health_endpoint(test_entities_dir):
    """Test /health endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Test entity count
    entities = await executor.discover_entities()
    assert len(entities) > 0
    # Framework name is now hardcoded since we simplified to single framework


@pytest.mark.skip("Skipping while we fix discovery")
async def test_server_entities_endpoint(test_entities_dir):
    """Test /v1/entities endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    assert len(entities) >= 1
    # Should find at least the weather agent
    agent_entities = [e for e in entities if e.type == "agent"]
    assert len(agent_entities) >= 1
    agent_names = [e.name for e in agent_entities]
    assert "WeatherAgent" in agent_names


async def test_server_execution_sync(test_entities_dir):
    """Test sync execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="San Francisco",
        stream=False,
    )

    response = await executor.execute_sync(request)
    assert response.model == "devui"  # Response model defaults to 'devui' when not specified
    assert len(response.output) > 0


async def test_server_execution_streaming(test_entities_dir):
    """Test streaming execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="New York",
        stream=True,
    )

    event_count = 0
    async for _event in executor.execute_streaming(request):
        event_count += 1
        if event_count > 5:  # Limit for testing
            break

    assert event_count > 0


def test_configuration():
    """Test basic configuration."""
    server = DevServer(entities_dir="test", port=9000, host="localhost")
    assert server.port == 9000
    assert server.host == "localhost"
    assert server.entities_dir == "test"
    assert server.cors_origins == ["*"]
    assert server.ui_enabled


def test_extract_executor_message_types_prefers_input_types():
    """Input types property is used when available."""
    stub = _StubExecutor(input_types=[str, dict])

    types = extract_executor_message_types(stub)

    assert types == [str, dict]


def test_extract_executor_message_types_falls_back_to_handlers():
    """Handlers provide message metadata when input_types missing."""
    stub = _StubExecutor(handlers={str: object(), int: object()})

    types = extract_executor_message_types(stub)

    assert str in types
    assert int in types


def test_select_primary_input_type_prefers_string_and_dict():
    """Primary type selection prefers user-friendly primitives."""
    string_first = select_primary_input_type([dict[str, str], str])
    dict_first = select_primary_input_type([dict[str, str]])
    fallback = select_primary_input_type([int, float])

    assert string_first is str
    assert dict_first is dict
    assert fallback is int


@pytest.mark.asyncio
async def test_credential_cleanup() -> None:
    """Test that async credentials are properly closed during server cleanup."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import ChatAgent

    # Create mock credential with async close
    mock_credential = AsyncMock()
    mock_credential.close = AsyncMock()

    # Create mock chat client with credential
    mock_client = Mock()
    mock_client.async_credential = mock_credential
    mock_client.model_id = "test-model"

    # Create agent with mock client
    agent = ChatAgent(name="TestAgent", chat_client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup
    await server._cleanup_entities()

    # Verify credential.close() was called
    assert mock_credential.close.called, "Async credential close should have been called"
    assert mock_credential.close.call_count == 1


@pytest.mark.asyncio
async def test_credential_cleanup_error_handling() -> None:
    """Test that credential cleanup errors are handled gracefully."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import ChatAgent

    # Create mock credential that raises error on close
    mock_credential = AsyncMock()
    mock_credential.close = AsyncMock(side_effect=Exception("Close failed"))

    # Create mock chat client with credential
    mock_client = Mock()
    mock_client.async_credential = mock_credential
    mock_client.model_id = "test-model"

    # Create agent with mock client
    agent = ChatAgent(name="TestAgent", chat_client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup - should not raise despite credential error
    await server._cleanup_entities()

    # Verify close was attempted
    assert mock_credential.close.called


@pytest.mark.asyncio
async def test_multiple_credential_attributes() -> None:
    """Test that we check all common credential attribute names."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import ChatAgent

    # Create mock credentials
    mock_cred1 = Mock()
    mock_cred1.close = Mock()
    mock_cred2 = AsyncMock()
    mock_cred2.close = AsyncMock()

    # Create mock chat client with multiple credential attributes
    mock_client = Mock()
    mock_client.credential = mock_cred1
    mock_client.async_credential = mock_cred2
    mock_client.model_id = "test-model"

    # Create agent with mock client
    agent = ChatAgent(name="TestAgent", chat_client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup
    await server._cleanup_entities()

    # Verify both credentials were closed
    assert mock_cred1.close.called, "Sync credential should be closed"
    assert mock_cred2.close.called, "Async credential should be closed"


def test_ui_mode_configuration():
    """Test UI mode configuration."""
    dev_server = DevServer(mode="developer")
    assert dev_server.mode == "developer"

    user_server = DevServer(mode="user")
    assert user_server.mode == "user"


@pytest.mark.asyncio
async def test_api_restrictions_in_user_mode():
    """Test that developer APIs are restricted in user mode."""
    from fastapi.testclient import TestClient

    # Create servers with different modes
    dev_server = DevServer(mode="developer")
    user_server = DevServer(mode="user")

    dev_app = dev_server.create_app()
    user_app = user_server.create_app()

    dev_client = TestClient(dev_app)
    user_client = TestClient(user_app)

    # Test 1: Health endpoint should work in both modes
    assert dev_client.get("/health").status_code == 200
    assert user_client.get("/health").status_code == 200

    # Test 2: Meta endpoint should reflect correct mode
    dev_meta = dev_client.get("/meta").json()
    assert dev_meta["ui_mode"] == "developer"

    user_meta = user_client.get("/meta").json()
    assert user_meta["ui_mode"] == "user"

    # Test 3: Entity listing should work in both modes
    assert dev_client.get("/v1/entities").status_code == 200
    assert user_client.get("/v1/entities").status_code == 200

    # Test 4: Entity info should be accessible in both modes (UI needs this)
    dev_response = dev_client.get("/v1/entities/test_agent/info")
    assert dev_response.status_code in [200, 404, 500]  # Not 403

    user_response = user_client.get("/v1/entities/test_agent/info")
    # Should return 404 (entity doesn't exist) or 500 (other error), but NOT 403 (forbidden)
    # User mode needs entity info to display workflows/agents in the UI
    assert user_response.status_code in [200, 404, 500]  # Not 403

    # Test 5: Hot reload should be restricted in user mode
    dev_response = dev_client.post("/v1/entities/test_agent/reload")
    assert dev_response.status_code in [200, 404, 500]  # Not 403

    user_response = user_client.post("/v1/entities/test_agent/reload")
    assert user_response.status_code == 403
    error_data = user_response.json()
    error = error_data.get("detail", {}).get("error") or error_data.get("error")
    assert "developer mode" in error["message"].lower()

    # Test 6: Deployment endpoints should be restricted in user mode
    # List deployments (simplest test - no payload needed)
    user_response = user_client.get("/v1/deployments")
    assert user_response.status_code == 403
    error_data = user_response.json()
    error = error_data.get("detail", {}).get("error") or error_data.get("error")
    assert "developer mode" in error["message"].lower()

    # Get deployment
    user_response = user_client.get("/v1/deployments/test-id")
    assert user_response.status_code == 403

    # Delete deployment
    user_response = user_client.delete("/v1/deployments/test-id")
    assert user_response.status_code == 403

    # Test 7: Conversation endpoints should work in both modes
    dev_response = dev_client.post("/v1/conversations", json={})
    assert dev_response.status_code == 200

    user_response = user_client.post("/v1/conversations", json={})
    assert user_response.status_code == 200

    # Test 8: Chat endpoint should work in both modes
    chat_payload = {"model": "test_agent", "input": "Hello"}
    dev_response = dev_client.post("/v1/responses", json=chat_payload)
    # 200=success, 400=missing entity_id in metadata, 404=entity not found
    assert dev_response.status_code in [200, 400, 404]

    user_response = user_client.post("/v1/responses", json=chat_payload)
    assert user_response.status_code in [200, 400, 404]


if __name__ == "__main__":
    # Simple test runner
    async def run_tests():
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test agent
            agent_file = temp_path / "weather_agent.py"
            agent_file.write_text("""
class WeatherAgent:
    name = "Weather Agent"
    description = "Gets weather information"

    def run_stream(self, input_str):
        return f"Weather in {input_str} is sunny"
""")

            server = DevServer(entities_dir=str(temp_path))
            executor = await server._ensure_executor()

            entities = await executor.discover_entities()

            if entities:
                request = AgentFrameworkRequest(
                    metadata={"entity_id": entities[0].id},
                    input="test location",
                    stream=False,
                )

                await executor.execute_sync(request)

    asyncio.run(run_tests())


@pytest.mark.asyncio
async def test_checkpoint_api_endpoints(test_entities_dir):
    """Test checkpoint list and delete API endpoints."""
    from agent_framework._workflows._checkpoint import WorkflowCheckpoint

    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Create a conversation
    conversation = executor.conversation_store.create_conversation(metadata={"name": "Test Session"})
    conv_id = conversation.id

    # Get checkpoint storage and add a checkpoint
    storage = executor.checkpoint_manager.get_checkpoint_storage(conv_id)
    checkpoint = WorkflowCheckpoint(
        checkpoint_id="test_checkpoint_1",
        workflow_id="test_workflow",
        shared_state={"key": "value"},
        iteration_count=1,
    )
    await storage.save_checkpoint(checkpoint)

    # Test list checkpoints endpoint
    checkpoints = await storage.list_checkpoints()
    assert len(checkpoints) == 1
    assert checkpoints[0].checkpoint_id == "test_checkpoint_1"
    assert checkpoints[0].workflow_id == "test_workflow"

    # Test delete checkpoint endpoint
    deleted = await storage.delete_checkpoint("test_checkpoint_1")
    assert deleted is True

    # Verify checkpoint was deleted
    remaining = await storage.list_checkpoints()
    assert len(remaining) == 0

    # Test delete non-existent checkpoint
    deleted = await storage.delete_checkpoint("nonexistent")
    assert deleted is False
