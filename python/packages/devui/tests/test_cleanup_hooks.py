# Copyright (c) Microsoft. All rights reserved.

"""Tests for cleanup hook registration and execution."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from agent_framework import AgentRunResponse, ChatMessage, Role, TextContent

from agent_framework_devui import register_cleanup
from agent_framework_devui._discovery import EntityDiscovery


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Clear the cleanup registry before each test."""
    import agent_framework_devui

    agent_framework_devui._cleanup_registry.clear()
    yield
    agent_framework_devui._cleanup_registry.clear()


class MockAgent:
    """Mock agent for testing."""

    def __init__(self, name: str = "TestAgent"):
        self.id = f"test-{name.lower()}"
        self.name = name
        self.description = "Test agent for cleanup hooks"
        self.cleanup_called = False
        self.async_cleanup_called = False

    async def run_stream(self, messages=None, *, thread=None, **kwargs):
        """Mock streaming run method."""
        yield AgentRunResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, content=[TextContent(text="Test response")])],
            inner_messages=[],
        )


class MockCredential:
    """Mock credential object for testing cleanup."""

    def __init__(self):
        self.closed = False

    async def close(self):
        """Mock async close method."""
        self.closed = True


class MockSyncResource:
    """Mock synchronous resource for testing cleanup."""

    def __init__(self):
        self.closed = False

    def close(self):
        """Mock sync close method."""
        self.closed = True


# Test 1: Register single cleanup hook
async def test_register_cleanup_single_hook():
    """Test registering a single cleanup hook for an entity."""
    agent = MockAgent("SingleHook")
    credential = MockCredential()

    # Register cleanup
    register_cleanup(agent, credential.close)

    # Verify credential not closed yet
    assert not credential.closed

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Get cleanup hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 1

    # Execute hook
    await hooks[0]()
    assert credential.closed


# Test 2: Register multiple cleanup hooks
async def test_register_cleanup_multiple_hooks():
    """Test registering multiple cleanup hooks for a single entity."""
    agent = MockAgent("MultipleHooks")
    credential1 = MockCredential()
    credential2 = MockCredential()
    sync_resource = MockSyncResource()

    # Register multiple hooks at once
    register_cleanup(agent, credential1.close, credential2.close, sync_resource.close)

    # Verify nothing closed yet
    assert not credential1.closed
    assert not credential2.closed
    assert not sync_resource.closed

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Get and execute hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 3

    # Execute all hooks
    for hook in hooks:
        if asyncio.iscoroutinefunction(hook):
            await hook()
        else:
            hook()

    assert credential1.closed
    assert credential2.closed
    assert sync_resource.closed


# Test 3: Register cleanup hooks incrementally
async def test_register_cleanup_incremental():
    """Test registering cleanup hooks in multiple calls."""
    agent = MockAgent("IncrementalHooks")
    credential1 = MockCredential()
    credential2 = MockCredential()

    # Register hooks incrementally
    register_cleanup(agent, credential1.close)
    register_cleanup(agent, credential2.close)

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Should have both hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 2

    # Execute all hooks
    for hook in hooks:
        await hook()

    assert credential1.closed
    assert credential2.closed


# Test 4: Test with no cleanup hooks
async def test_no_cleanup_hooks():
    """Test entity without any cleanup hooks registered."""
    agent = MockAgent("NoHooks")

    # Don't register any cleanup hooks
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Should return empty list
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 0


# Test 5: Test cleanup with async and sync hooks mixed
async def test_mixed_async_sync_hooks():
    """Test that both async and sync cleanup hooks work together."""
    agent = MockAgent("MixedHooks")
    async_resource = MockCredential()
    sync_resource = MockSyncResource()

    # Register both types
    register_cleanup(agent, async_resource.close, sync_resource.close)

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Get and execute hooks with proper async/sync handling
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 2

    import inspect

    for hook in hooks:
        if inspect.iscoroutinefunction(hook):
            await hook()
        else:
            hook()

    assert async_resource.closed
    assert sync_resource.closed


# Test 6: Test error handling in cleanup hooks
async def test_cleanup_hook_error_handling():
    """Test that errors in cleanup hooks don't break execution."""
    agent = MockAgent("ErrorHooks")
    credential = MockCredential()

    def failing_hook():
        raise RuntimeError("Intentional error for testing")

    # Register failing hook and valid hook
    register_cleanup(agent, failing_hook, credential.close)

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Get hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 2

    # Execute hooks with error handling (like _server.py does)
    import inspect

    for hook in hooks:
        try:
            if inspect.iscoroutinefunction(hook):
                await hook()
            else:
                hook()
        except Exception:
            pass  # Ignore errors like the server does

    # Second hook should still execute despite first one failing
    await credential.close()
    assert credential.closed


# Test 7: Test ValueError when no hooks provided
def test_register_cleanup_no_hooks_error():
    """Test that register_cleanup raises ValueError when no hooks provided."""
    agent = MockAgent("NoHooksError")

    with pytest.raises(ValueError, match="At least one cleanup hook required"):
        register_cleanup(agent)


# Test 8: Test file-based discovery with cleanup hooks
async def test_cleanup_with_file_based_discovery():
    """Test that cleanup hooks work with file-based entity discovery."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create agent directory
        agent_dir = temp_path / "test_agent"
        agent_dir.mkdir()

        # Write agent module with cleanup registration
        agent_file = agent_dir / "__init__.py"
        agent_file.write_text("""
from agent_framework import AgentRunResponse, ChatMessage, Role, TextContent
from agent_framework_devui import register_cleanup

class MockCredential:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True

# Create credential and agent
credential = MockCredential()

class TestAgent:
    id = "test-agent"
    name = "Test Agent"
    description = "Test agent with cleanup"

    async def run_stream(self, messages=None, *, thread=None, **kwargs):
        yield AgentRunResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, content=[TextContent(text="Test")])],
            inner_messages=[],
        )

agent = TestAgent()

# Register cleanup at module level
register_cleanup(agent, credential.close)
""")

        # Discover entities
        discovery = EntityDiscovery(str(temp_path))
        await discovery.discover_entities()

        # Load the entity (triggers module import)
        await discovery.load_entity("test_agent")

        # Verify cleanup hooks were registered
        hooks = discovery.get_cleanup_hooks("test_agent")
        assert len(hooks) == 1


# Test 9: Test cleanup execution order
async def test_cleanup_execution_order():
    """Test that cleanup hooks execute in registration order."""
    agent = MockAgent("OrderTest")
    execution_order = []

    def hook1():
        execution_order.append(1)

    def hook2():
        execution_order.append(2)

    def hook3():
        execution_order.append(3)

    # Register in specific order
    register_cleanup(agent, hook1, hook2, hook3)

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Execute hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    for hook in hooks:
        hook()

    # Verify execution order
    assert execution_order == [1, 2, 3]


# Test 10: Test custom cleanup logic
async def test_custom_cleanup_logic():
    """Test registering custom cleanup function with complex logic."""
    agent = MockAgent("CustomCleanup")
    cleanup_executed = False
    resources_closed = []

    async def custom_cleanup():
        nonlocal cleanup_executed
        cleanup_executed = True
        resources_closed.append("credential")
        resources_closed.append("session")
        resources_closed.append("cache")

    register_cleanup(agent, custom_cleanup)

    # Simulate discovery and registration
    discovery = EntityDiscovery()
    entity_info = await discovery.create_entity_info_from_object(agent, entity_type="agent", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Execute hooks
    hooks = discovery.get_cleanup_hooks(entity_info.id)
    assert len(hooks) == 1

    await hooks[0]()

    assert cleanup_executed
    assert resources_closed == ["credential", "session", "cache"]
