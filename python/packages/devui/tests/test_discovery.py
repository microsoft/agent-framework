#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for entity discovery functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui.executors.agent_framework._discovery import AgentFrameworkEntityDiscovery


@pytest.fixture
def test_entities_dir():
    """Use the examples directory which has proper entity structure."""
    # Get the examples directory relative to the current test file
    current_dir = Path(__file__).parent
    examples_dir = current_dir.parent / "examples"
    return str(examples_dir.resolve())


@pytest.mark.asyncio
async def test_discover_agents(test_entities_dir):
    """Test agent discovery."""
    discovery = AgentFrameworkEntityDiscovery("agent_framework", test_entities_dir)
    entities = await discovery.discover_entities()

    agents = [e for e in entities if e.type == "agent"]
    assert len(agents) == 1
    assert agents[0].name == "WeatherAgent"
    assert agents[0].description and "weather" in agents[0].description.lower()


@pytest.mark.asyncio
async def test_discover_workflows(test_entities_dir):
    """Test workflow discovery."""
    discovery = AgentFrameworkEntityDiscovery("agent_framework", test_entities_dir)
    entities = await discovery.discover_entities()

    workflows = [e for e in entities if e.type == "workflow"]
    # Should find at least 1 workflow from examples (spam_workflow)
    assert len(workflows) >= 1
    workflow_names = [w.name for w in workflows]
    # At least one workflow should be found
    assert len(workflow_names) > 0


@pytest.mark.asyncio
async def test_empty_directory():
    """Test discovery with empty directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        discovery = AgentFrameworkEntityDiscovery("agent_framework", temp_dir)
        entities = await discovery.discover_entities()

        assert len(entities) == 0


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

            print("🔍 Testing entity discovery...")

            discovery = AgentFrameworkEntityDiscovery("agent_framework", str(temp_path))
            entities = await discovery.discover_entities()

            print(f"✅ Discovered {len(entities)} entities")
            for entity in entities:
                print(f"  - {entity.id} ({entity.type}): {entity.name}")

    asyncio.run(run_tests())
