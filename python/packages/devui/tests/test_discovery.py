# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for entity discovery functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui._discovery import EntityDiscovery


@pytest.fixture
def test_entities_dir():
    """Use the samples directory which has proper entity structure."""
    # Get the samples directory from the main python samples folder
    current_dir = Path(__file__).parent
    # Navigate to python/samples/getting_started/devui
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"
    return str(samples_dir.resolve())


async def test_discover_agents(test_entities_dir):
    """Test that agent discovery works and returns valid agent entities."""
    discovery = EntityDiscovery(test_entities_dir)
    entities = await discovery.discover_entities()

    agents = [e for e in entities if e.type == "agent"]

    # Test that we can discover agents (not specific count)
    assert len(agents) > 0, "Should discover at least one agent"

    # Test agent structure/properties
    for agent in agents:
        assert agent.id, "Agent should have an ID"
        assert agent.name, "Agent should have a name"
        assert agent.type == "agent", "Should be identified as agent type"
        assert hasattr(agent, "description"), "Agent should have description attribute"


async def test_discover_workflows(test_entities_dir):
    """Test that workflow discovery works and returns valid workflow entities."""
    discovery = EntityDiscovery(test_entities_dir)
    entities = await discovery.discover_entities()

    workflows = [e for e in entities if e.type == "workflow"]

    # Test that we can discover workflows (not specific count)
    assert len(workflows) > 0, "Should discover at least one workflow"

    # Test workflow structure/properties
    for workflow in workflows:
        assert workflow.id, "Workflow should have an ID"
        assert workflow.name, "Workflow should have a name"
        assert workflow.type == "workflow", "Should be identified as workflow type"
        assert hasattr(workflow, "description"), "Workflow should have description attribute"


async def test_empty_directory():
    """Test discovery with empty directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        discovery = EntityDiscovery(temp_dir)
        entities = await discovery.discover_entities()

        assert len(entities) == 0


async def test_discovery_accepts_agents_with_only_run():
    """Test that discovery accepts agents with only run() method.

    With lazy loading, entities with only __init__.py are discovered
    but marked as "unknown" type until loaded.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create agent with only run() method
        agent_dir = temp_path / "non_streaming_agent"
        agent_dir.mkdir()

        init_file = agent_dir / "__init__.py"
        init_file.write_text("""
from agent_framework import AgentRunResponse, AgentThread, ChatMessage, Role, TextContent

class NonStreamingAgent:
    id = "non_streaming"
    name = "Non-Streaming Agent"
    description = "Agent without run_stream"

    @property
    def display_name(self):
        return self.name

    async def run(self, messages=None, *, thread=None, **kwargs):
        return AgentRunResponse(
            messages=[ChatMessage(
                role=Role.ASSISTANT,
                contents=[TextContent(text="response")]
            )],
            response_id="test"
        )

    def get_new_thread(self, **kwargs):
        return AgentThread()

agent = NonStreamingAgent()
""")

        discovery = EntityDiscovery(str(temp_path))
        entities = await discovery.discover_entities()

        # With lazy loading, entity is discovered but type is "unknown"
        # (no agent.py or workflow.py to detect type from)
        assert len(entities) == 1
        entity = entities[0]
        assert entity.id == "non_streaming_agent"
        assert entity.type == "unknown"  # Type not yet determined
        assert entity.tools == []  # Sparse metadata

        # Trigger lazy loading to get full metadata
        agent_obj = await discovery.load_entity(entity.id)
        assert agent_obj is not None

        # Now check enriched metadata after loading
        enriched = discovery.get_entity_info(entity.id)
        assert enriched.type == "agent"  # Now correctly identified
        assert enriched.name == "Non-Streaming Agent"
        assert not enriched.metadata.get("has_run_stream")


async def test_lazy_loading():
    """Test that entities are loaded on-demand, not at discovery time."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test workflow
        workflow_dir = temp_path / "test_workflow"
        workflow_dir.mkdir()
        (workflow_dir / "workflow.py").write_text("""
from agent_framework import WorkflowBuilder, FunctionExecutor

# Create a simple workflow with a start executor
def test_func(input: str) -> str:
    return f"Processed: {input}"

builder = WorkflowBuilder()
executor = FunctionExecutor(id="test_executor", func=test_func)
builder.set_start_executor(executor)
workflow = builder.build()
""")

        discovery = EntityDiscovery(str(temp_path))

        # Discovery should NOT import module
        entities = await discovery.discover_entities()
        assert len(entities) == 1
        assert entities[0].id == "test_workflow"
        assert entities[0].type == "workflow"  # Type detected from filename
        assert entities[0].tools == []  # Sparse metadata (not loaded yet)

        # Entity should NOT be in loaded_objects yet
        assert discovery.get_entity_object("test_workflow") is None

        # Trigger lazy load
        workflow_obj = await discovery.load_entity("test_workflow")
        assert workflow_obj is not None

        # Now in cache
        assert discovery.get_entity_object("test_workflow") is workflow_obj

        # Second load is instant (from cache)
        workflow_obj2 = await discovery.load_entity("test_workflow")
        assert workflow_obj2 is workflow_obj  # Same object


async def test_type_detection():
    """Test that entity types are detected from filenames."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create workflow with workflow.py
        workflow_dir = temp_path / "my_workflow"
        workflow_dir.mkdir()
        (workflow_dir / "workflow.py").write_text("""
from agent_framework import WorkflowBuilder, FunctionExecutor

def test_func(input: str) -> str:
    return f"Processed: {input}"

builder = WorkflowBuilder()
executor = FunctionExecutor(id="test_executor", func=test_func)
builder.set_start_executor(executor)
workflow = builder.build()
""")

        # Create agent with agent.py
        agent_dir = temp_path / "my_agent"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("""
from agent_framework import AgentRunResponse, AgentThread, ChatMessage, Role, TextContent

class TestAgent:
    name = "Test Agent"

    async def run(self, messages=None, *, thread=None, **kwargs):
        return AgentRunResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="test")])],
            response_id="test"
        )

    def get_new_thread(self, **kwargs):
        return AgentThread()

agent = TestAgent()
""")

        # Create ambiguous entity with __init__.py only
        unknown_dir = temp_path / "my_thing"
        unknown_dir.mkdir()
        (unknown_dir / "__init__.py").write_text("# thing")

        discovery = EntityDiscovery(str(temp_path))
        entities = await discovery.discover_entities()

        # Check types detected correctly
        by_id = {e.id: e for e in entities}

        assert by_id["my_workflow"].type == "workflow"
        assert by_id["my_agent"].type == "agent"
        assert by_id["my_thing"].type == "unknown"


async def test_hot_reload():
    """Test that invalidate_entity() enables hot reload."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create workflow
        workflow_dir = temp_path / "test_workflow"
        workflow_dir.mkdir()
        workflow_file = workflow_dir / "workflow.py"
        workflow_file.write_text("""
from agent_framework import WorkflowBuilder, FunctionExecutor

def test_func(input: str) -> str:
    return "v1"

builder = WorkflowBuilder()
executor = FunctionExecutor(id="test_executor", func=test_func)
builder.set_start_executor(executor)
workflow = builder.build()
""")

        discovery = EntityDiscovery(str(temp_path))
        await discovery.discover_entities()

        # Load entity
        workflow1 = await discovery.load_entity("test_workflow")
        assert workflow1 is not None

        # Modify file to create a different workflow
        workflow_file.write_text("""
from agent_framework import WorkflowBuilder, FunctionExecutor

def test_func(input: str) -> str:
    return "v2"

def test_func2(input: str) -> str:
    return "v2_extra"

builder = WorkflowBuilder()
executor1 = FunctionExecutor(id="test_executor", func=test_func)
executor2 = FunctionExecutor(id="test_executor2", func=test_func2)
builder.set_start_executor(executor1)
builder.add_edge(executor1, executor2)
workflow = builder.build()
""")

        # Without invalidation, gets cached version
        workflow2 = await discovery.load_entity("test_workflow")
        assert workflow2 is workflow1  # Same object (cached)
        # Old workflow has 1 executor
        assert len(workflow2.get_executors_list()) == 1

        # Invalidate cache
        discovery.invalidate_entity("test_workflow")

        # Now reloads from disk
        workflow3 = await discovery.load_entity("test_workflow")
        assert workflow3 is not workflow1  # Different object
        # New workflow has 2 executors
        assert len(workflow3.get_executors_list()) == 2


async def test_in_memory_entities_bypass_lazy_loading():
    """Test that in-memory entities work as before (no lazy loading needed)."""
    from agent_framework import FunctionExecutor, WorkflowBuilder

    # Create in-memory workflow
    def test_func(input: str) -> str:
        return f"Processed: {input}"

    builder = WorkflowBuilder()
    executor = FunctionExecutor(id="test_executor", func=test_func)
    builder.set_start_executor(executor)
    workflow = builder.build()

    discovery = EntityDiscovery()

    # Register in-memory entity
    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="in_memory")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    # Should be immediately available (no lazy loading)
    loaded = discovery.get_entity_object(entity_info.id)
    assert loaded is workflow

    # load_entity() should return immediately from cache
    loaded2 = await discovery.load_entity(entity_info.id)
    assert loaded2 is workflow  # Same object (cache hit)


if __name__ == "__main__":
    # Simple test runner
    async def run_tests():
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            agent_file = temp_path / "test_agent.py"
            agent_file.write_text("""
class WeatherAgent:
    name = "Weather Agent"
    description = "Gets weather information"

    def run_stream(self, input_str):
        return f"Weather in {input_str}"
""")

            workflow_file = temp_path / "test_workflow.py"
            workflow_file.write_text("""
class DataWorkflow:
    name = "Data Processing Workflow"
    description = "Processes data"

    def run(self, data):
        return f"Processed {data}"
""")

            discovery = EntityDiscovery(str(temp_path))
            await discovery.discover_entities()

    asyncio.run(run_tests())
