"""Tests for AgentRegistry functionality."""

from unittest.mock import Mock, patch

import pytest
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowContext, handler

from agent_framework_devui._models import AgentInfo, WorkflowInfo
from agent_framework_devui._registry import AgentRegistry

# Import shared test utilities
from .test_utils import MockAgent, MockExecutor, create_mock_workflow, mock_tool_function


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
    workflow = create_mock_workflow("TestWorkflow")

    # Should register successfully
    registry.register_workflow("test_workflow", workflow)

    # Should be retrievable
    retrieved = registry.get_workflow("test_workflow")
    assert retrieved is workflow  # Use identity check instead of equality

    # Should appear in listings
    workflows = registry.list_workflows()
    assert len(workflows) == 1
    assert workflows[0].id == "test_workflow"
    assert workflows[0].name is None  # Real workflows don't have name field
    assert workflows[0].source == "in_memory"
    # Should have schema extraction working - enhanced schema for string input
    assert workflows[0].input_type_name == "str"
    assert workflows[0].input_schema["type"] == "object"
    assert "properties" in workflows[0].input_schema
    assert "message" in workflows[0].input_schema["properties"]
    assert workflows[0].input_schema["properties"]["message"]["type"] == "string"


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
    workflow = create_mock_workflow("ExecutorWorkflow")

    registry.register_workflow("executor_workflow", workflow)

    # Check that workflow structure is extracted (WorkflowInfo doesn't have tools field)
    workflows = registry.list_workflows()
    assert len(workflows) == 1
    assert workflows[0].workflow_dump is not None
    assert hasattr(workflows[0].workflow_dump, "executors")
    # Check executor IDs in the workflow dump
    executors = workflows[0].workflow_dump.executors
    executor_ids = list(executors.keys())
    assert "executor1" in executor_ids
    assert "executor2" in executor_ids


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
    workflow = create_mock_workflow()
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
    with patch("agent_framework_devui._discovery.DirectoryScanner") as mock_scanner_class:
        # Setup mock directory scanner
        mock_scanner = Mock()
        mock_scanner.discover_entities.return_value = [
            AgentInfo(
                id="dir_agent",
                name="DirectoryAgent",
                type="agent",
                source="directory",
                tools=["dir_tool"],
                has_env=True,
                module_path="/path/to/dir_agent",
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
    with patch("agent_framework_devui._discovery.DirectoryScanner") as mock_scanner_class:
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


# Comprehensive Workflow Input Schema Tests
from dataclasses import dataclass
from typing import Optional

from agent_framework.workflow import WorkflowContext, handler
from agent_framework_devui._models import WorkflowInfo
from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    """A user request with various field types for testing."""

    name: str = Field(..., description="User's name")
    age: int = Field(default=25, ge=0, le=120, description="User's age")
    email: Optional[str] = Field(default=None, description="Optional email address")
    is_premium: bool = Field(default=False, description="Premium user status")
    preferences: dict = Field(default_factory=dict, description="User preferences")


@dataclass
class SimpleDataClass:
    """Simple dataclass for testing."""

    message: str
    count: int = 0


class StringExecutor(Executor):
    """Executor that accepts string input."""

    @handler
    async def handle_string(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"Processed: {message}")


class IntExecutor(Executor):
    """Executor that accepts int input."""

    @handler
    async def handle_int(self, number: int, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"Number squared: {number * number}")


class PydanticExecutor(Executor):
    """Executor that accepts Pydantic model input."""

    @handler
    async def handle_user_request(self, request: UserRequest, ctx: WorkflowContext[str]) -> None:
        response = f"Hello {request.name}, age {request.age}"
        if request.is_premium:
            response += " (Premium user)"
        await ctx.send_message(response)


class DataClassExecutor(Executor):
    """Executor that accepts dataclass input."""

    @handler
    async def handle_dataclass(self, data: SimpleDataClass, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{data.message} (count: {data.count})")


class MultiHandlerExecutor(Executor):
    """Executor with multiple handlers to test our 'first handler' logic."""

    @handler
    async def handle_string(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"String: {message}")

    @handler
    async def handle_int(self, number: int, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"Int: {number}")


@pytest.mark.asyncio
async def test_workflow_multiple_handlers():
    """Test that we handle executors with multiple handlers correctly."""
    registry = AgentRegistry()

    # Create workflow with multi-handler executor
    multi_executor = MultiHandlerExecutor(id="multi_exec")
    workflow = WorkflowBuilder().set_start_executor(multi_executor).build()

    registry.register_workflow("multi_workflow", workflow)
    workflows = registry.list_workflows()

    workflow_info = workflows[0]
    # Should pick one of the handler types (our implementation picks first)
    assert workflow_info.input_type_name in ["str", "int"]
    assert workflow_info.start_executor_id == "multi_exec"


def create_string_workflow():
    """Create workflow that accepts string input."""
    string_executor = StringExecutor(id="string_exec")
    return WorkflowBuilder().set_start_executor(string_executor).build()


def create_pydantic_workflow():
    """Create workflow that accepts Pydantic model input."""
    pydantic_executor = PydanticExecutor(id="pydantic_exec")
    return WorkflowBuilder().set_start_executor(pydantic_executor).build()


@pytest.mark.asyncio
async def test_workflow_string_input_schema():
    """Test workflow with string input type schema extraction."""
    registry = AgentRegistry()
    workflow = create_string_workflow()
    registry.register_workflow("string_workflow", workflow)

    workflows = registry.list_workflows()
    assert len(workflows) == 1

    workflow_info = workflows[0]
    assert isinstance(workflow_info, WorkflowInfo)
    assert workflow_info.id == "string_workflow"
    assert workflow_info.input_type_name == "str"
    assert workflow_info.start_executor_id == "string_exec"
    # Enhanced schema for string input should be an object with message property
    assert workflow_info.input_schema["type"] == "object"
    assert "properties" in workflow_info.input_schema
    assert "message" in workflow_info.input_schema["properties"]
    assert workflow_info.input_schema["properties"]["message"]["type"] == "string"


@pytest.mark.asyncio
async def test_workflow_pydantic_input_schema():
    """Test workflow with Pydantic model input type schema extraction."""
    registry = AgentRegistry()
    workflow = create_pydantic_workflow()
    registry.register_workflow("pydantic_workflow", workflow)

    workflows = registry.list_workflows()
    assert len(workflows) == 1

    workflow_info = workflows[0]
    assert workflow_info.input_type_name == "UserRequest"
    assert workflow_info.start_executor_id == "pydantic_exec"

    # Check rich Pydantic schema with defaults, validation, descriptions
    schema = workflow_info.input_schema
    assert "properties" in schema
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]
    assert "email" in schema["properties"]
    assert "is_premium" in schema["properties"]

    # Check field details
    name_field = schema["properties"]["name"]
    assert name_field["type"] == "string"
    assert "description" in name_field

    age_field = schema["properties"]["age"]
    assert age_field["type"] == "integer"
    assert age_field["default"] == 25
    assert "minimum" in age_field
    assert "maximum" in age_field

    premium_field = schema["properties"]["is_premium"]
    assert premium_field["type"] == "boolean"
    assert premium_field["default"] is False


@pytest.mark.asyncio
async def test_workflow_info_structure():
    """Test that WorkflowInfo has all required fields."""
    registry = AgentRegistry()
    workflow = create_string_workflow()
    registry.register_workflow("test_workflow", workflow)

    workflows = registry.list_workflows()
    workflow_info = workflows[0]

    # Should have workflow dump
    assert workflow_info.workflow_dump is not None
    # With proper typing, workflow_dump is now a Workflow instance that has model_dump() method
    assert hasattr(workflow_info.workflow_dump, "executors")
    assert hasattr(workflow_info.workflow_dump, "start_executor_id")

    # Should have input schema info
    assert workflow_info.input_schema is not None
    assert workflow_info.input_type_name is not None
    assert workflow_info.start_executor_id is not None

    # Mermaid diagram might be None if viz package not available
    if workflow_info.mermaid_diagram is not None:
        assert isinstance(workflow_info.mermaid_diagram, str)
