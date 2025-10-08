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


@pytest.mark.skip("Skipping while we fix discovery")
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
    """Test that discovery accepts agents with only run() method."""
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

        # Should discover the non-streaming agent
        agents = [e for e in entities if e.type == "agent"]
        assert len(agents) == 1
        # ID is auto-generated, just check it exists and starts with agent_
        assert agents[0].id.startswith("agent_")
        assert agents[0].name == "Non-Streaming Agent"
        assert not agents[0].metadata.get("has_run_stream")


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
