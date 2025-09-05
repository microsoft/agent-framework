"""Tests for AgentRegistry functionality."""

import pytest
from typing import List, Any
from unittest.mock import Mock, patch
from collections.abc import AsyncIterable

from agent_framework import AgentProtocol, AgentThread, AgentRunResponse, AgentRunResponseUpdate
from agent_framework.workflow import Workflow, Executor

from devui.registry import AgentRegistry
from devui.models import AgentInfo


class MockAgent(AgentProtocol):
    """Mock agent implementing AgentProtocol for testing."""
    
    def __init__(self, name: str = "TestAgent", tools: List | None = None, agent_id: str = "test_agent"):
        self._name = name
        self._description = f"Test agent: {name}"
        self._id = agent_id
        self.tools = tools if tools is not None else []
        self.chat_options = Mock()
        self.chat_options.tools = self.tools
    
    @property
    def id(self) -> str:
        return self._id
        
    @property
    def name(self) -> str | None:
        return self._name
        
    @property
    def display_name(self) -> str:
        return self._name
        
    @property 
    def description(self) -> str | None:
        return self._description
        
    async def run(self, messages=None, *, thread=None, **kwargs) -> AgentRunResponse:
        return AgentRunResponse(messages=[])
        
    async def run_stream(self, messages=None, *, thread=None, **kwargs) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[])
        
    def get_new_thread(self) -> AgentThread:
        return Mock()


class MockWorkflow(Workflow):
    """Mock workflow implementing Workflow for testing."""
    
    def __init__(self, name: str = "TestWorkflow"):
        self._name = name
        self._description = f"Test workflow: {name}"
    
    @property
    def name(self) -> str | None:
        return self._name
        
    @property
    def description(self) -> str | None:
        return self._description
        
    def get_graph(self):
        return {}
        
    def get_executors_list(self) -> List[Executor]:
        executor1 = Mock(spec=Executor)
        executor1.id = "executor1"
        executor2 = Mock(spec=Executor) 
        executor2.id = "executor2"
        return [executor1, executor2]


def mock_tool_function():
    """Mock tool function for testing."""
    pass


@pytest.mark.asyncio
async def test_register_agent():
    """Test registering an in-memory agent."""
    registry = AgentRegistry()
    agent = MockAgent("TestAgent")
    
    # Should register successfully
    registry.register_agent("test_agent", agent)
    
    # Should be retrievable
    retrieved = registry.get_agent("test_agent")
    assert retrieved is agent  # Use identity check instead of equality
    
    # Should appear in listings
    agents = registry.list_agents()
    assert len(agents) == 1
    assert agents[0].id == "test_agent"
    assert agents[0].name == "TestAgent"
    assert agents[0].type == "agent"
    assert agents[0].source == "in_memory"


@pytest.mark.asyncio 
async def test_register_workflow():
    """Test registering an in-memory workflow."""
    registry = AgentRegistry()
    workflow = MockWorkflow("TestWorkflow")
    
    # Should register successfully
    registry.register_workflow("test_workflow", workflow)
    
    # Should be retrievable
    retrieved = registry.get_workflow("test_workflow")
    assert retrieved is workflow  # Use identity check instead of equality
    
    # Should appear in listings
    workflows = registry.list_workflows()
    assert len(workflows) == 1
    assert workflows[0].id == "test_workflow"
    assert workflows[0].name == "TestWorkflow"
    assert workflows[0].type == "workflow"
    assert workflows[0].source == "in_memory"


@pytest.mark.asyncio
async def test_type_validation():
    """Test that registration validates types."""
    registry = AgentRegistry()
    
    # Create invalid objects that don't implement the protocols
    invalid_agent = "not_an_agent"
    invalid_workflow = "not_a_workflow"
    
    # Should reject non-agent for agent registration
    with pytest.raises(TypeError):
        registry.register_agent("invalid", invalid_agent)  # type: ignore
    
    # Should reject non-workflow for workflow registration  
    with pytest.raises(TypeError):
        registry.register_workflow("invalid", invalid_workflow)  # type: ignore


@pytest.mark.asyncio
async def test_agent_tool_extraction():
    """Test extracting tool names from agents."""
    registry = AgentRegistry()
    
    # Create agent with named tools
    tools = [mock_tool_function]
    mock_tool_function.__name__ = "mock_tool_function"
    agent = MockAgent("ToolAgent", tools)
    
    registry.register_agent("tool_agent", agent)
    
    # Check tools are extracted
    agents = registry.list_agents()
    assert len(agents) == 1
    assert "mock_tool_function" in agents[0].tools


@pytest.mark.asyncio
async def test_workflow_executor_extraction():
    """Test extracting executor names from workflows."""
    registry = AgentRegistry()
    workflow = MockWorkflow("ExecutorWorkflow")
    
    registry.register_workflow("executor_workflow", workflow)
    
    # Check executors are extracted
    workflows = registry.list_workflows()
    assert len(workflows) == 1
    assert "executor1" in workflows[0].tools
    assert "executor2" in workflows[0].tools


@pytest.mark.asyncio
async def test_get_nonexistent_items():
    """Test retrieving non-existent agents/workflows."""
    registry = AgentRegistry()
    
    # Should return None for missing items
    assert registry.get_agent("missing") is None
    assert registry.get_workflow("missing") is None


@pytest.mark.asyncio
async def test_remove_items():
    """Test removing in-memory agents and workflows."""
    registry = AgentRegistry()
    
    # Add items
    agent = MockAgent()
    workflow = MockWorkflow()
    registry.register_agent("agent1", agent)
    registry.register_workflow("workflow1", workflow)
    
    # Remove items
    assert registry.remove_agent("agent1") is True
    assert registry.remove_workflow("workflow1") is True
    
    # Should not be retrievable anymore
    assert registry.get_agent("agent1") is None
    assert registry.get_workflow("workflow1") is None
    
    # Remove non-existent should return False
    assert registry.remove_agent("missing") is False
    assert registry.remove_workflow("missing") is False


@pytest.mark.asyncio
async def test_mixed_sources():
    """Test registry with both in-memory and directory sources."""
    with patch('devui.discovery.DirectoryScanner') as mock_scanner_class:
        # Setup mock directory scanner
        mock_scanner = Mock()
        mock_scanner.discover_agents.return_value = [
            AgentInfo(
                id="dir_agent",
                name="DirectoryAgent", 
                type="agent",
                source="directory",
                tools=["dir_tool"],
                has_env=True,
                module_path="/path/to/dir_agent"
            )
        ]
        mock_scanner_class.return_value = mock_scanner
        
        # Create registry with directory support
        registry = AgentRegistry(agents_dir="/fake/dir")
        
        # Add in-memory agent
        memory_agent = MockAgent("MemoryAgent")
        registry.register_agent("memory_agent", memory_agent)
        
        # Should list both sources
        all_agents = registry.list_agents()
        assert len(all_agents) == 2
        
        # Check we have one from each source
        sources = [agent.source for agent in all_agents]
        assert "directory" in sources
        assert "in_memory" in sources


@pytest.mark.asyncio
async def test_cache_clearing():
    """Test cache clearing functionality."""
    with patch('devui.discovery.DirectoryScanner') as mock_scanner_class:
        mock_scanner = Mock()
        mock_scanner_class.return_value = mock_scanner
        
        registry = AgentRegistry(agents_dir="/fake/dir")
        
        # Should call scanner's clear_cache
        registry.clear_cache()
        mock_scanner.clear_cache.assert_called_once()


@pytest.mark.asyncio
async def test_tool_extraction_edge_cases():
    """Test tool extraction handles various edge cases.""" 
    registry = AgentRegistry()
    
    # Agent with no tools
    agent_no_tools = MockAgent("NoToolsAgent", [])
    registry.register_agent("no_tools", agent_no_tools)
    
    # Agent with tools having different name attributes
    tool_with_name = Mock()
    tool_with_name.name = "named_tool"
    
    agent_mixed_tools = MockAgent("MixedAgent", [tool_with_name, "string_tool"])
    registry.register_agent("mixed_tools", agent_mixed_tools)
    
    agents = registry.list_agents()
    
    # No tools agent should have empty tools list
    no_tools_agent = next(a for a in agents if a.id == "no_tools")
    assert no_tools_agent.tools == []
    
    # Mixed tools agent should extract names properly
    mixed_agent = next(a for a in agents if a.id == "mixed_tools")
    assert "named_tool" in mixed_agent.tools
    assert "string_tool" in mixed_agent.tools