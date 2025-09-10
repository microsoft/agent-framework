"""Tests for DirectoryScanner discovery functionality."""

import types
from typing import Any, AsyncIterable
from unittest.mock import Mock

from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, AgentThread

from agent_framework_devui._discovery import DirectoryScanner

# Import shared test utilities
from .test_utils import MockAgent


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self, name: str = "TestWorkflow") -> None:
        self._name = name
        self._description = f"Test workflow: {name}"

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def description(self) -> str | None:
        return self._description

    async def run_stream(self, message: Any) -> AsyncIterable[dict[str, str]]:
        """Mock run_stream method."""
        yield {"type": "test_event"}


def test_find_agent_in_module_success() -> None:
    """Test finding agent with correct 'agent' variable name."""
    scanner = DirectoryScanner("/fake/dir")

    # Create mock module with agent variable
    mock_module = types.ModuleType("test_module")
    setattr(mock_module, "agent", MockAgent("TestAgent"))

    # Should find the agent
    result = scanner._find_agent_in_module(mock_module)

    assert result is not None
    assert result.name == "TestAgent"
    assert hasattr(result, "run_stream")


def test_find_workflow_in_module_success() -> None:
    """Test finding workflow with correct 'workflow' variable name."""
    scanner = DirectoryScanner("/fake/dir")

    # Create mock module with workflow variable
    mock_module = types.ModuleType("test_module")
    setattr(mock_module, "workflow", MockWorkflow("TestWorkflow"))

    # Should find the workflow
    result = scanner._find_agent_in_module(mock_module)

    assert result is not None
    assert result.name == "TestWorkflow"
    assert hasattr(result, "run_stream")


def test_find_agent_wrong_variable_name() -> None:
    """Test that wrong variable names are not found."""
    scanner = DirectoryScanner("/fake/dir")

    # Create mock module with wrong variable name
    mock_module = types.ModuleType("test_module")
    setattr(mock_module, "my_agent", MockAgent("TestAgent"))  # Wrong name!
    setattr(mock_module, "some_workflow", MockWorkflow("TestWorkflow"))  # Wrong name!

    # Should not find anything
    result = scanner._find_agent_in_module(mock_module)

    assert result is None


def test_find_agent_missing_methods() -> None:
    """Test that objects without required methods are rejected."""
    scanner = DirectoryScanner("/fake/dir")

    # Create mock module with objects missing required methods
    mock_module = types.ModuleType("test_module")

    # Agent without run_stream method - use plain object
    class BadAgent:
        def __init__(self) -> None:
            self.id = "test_id"
            self.name = "test_name"
            # Missing run_stream method!

    setattr(mock_module, "agent", BadAgent())

    # Should not find it
    result = scanner._find_agent_in_module(mock_module)

    assert result is None

    # Workflow without run_stream method - use plain object
    class BadWorkflow:
        def __init__(self) -> None:
            self.name = "test_workflow"
            # Missing run_stream method!

    setattr(mock_module, "workflow", BadWorkflow())
    setattr(mock_module, "agent", None)  # Clear agent

    # Should not find it
    result = scanner._find_agent_in_module(mock_module)

    assert result is None


def test_extract_tools_from_real_chat_agent() -> None:
    """Test tool extraction from real ChatAgent with actual tools."""
    from agent_framework import ChatAgent

    scanner = DirectoryScanner("/fake/dir")

    # Create real tool functions
    def get_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    def get_forecast(location: str, days: int = 3) -> str:
        return f"Forecast for {location}: sunny for {days} days"

    # Create real ChatAgent with actual OpenAI client and tools
    agent = ChatAgent(
        name="WeatherAgent",
        description="Test weather agent",
        chat_client=Mock(),  # Mock the client since we don't need actual API calls
        tools=[get_weather, get_forecast],
    )

    # Extract tools using discovery logic
    tools = scanner._extract_tools_from_object(agent, "agent")

    # Should extract the actual function names
    assert len(tools) == 2
    assert "get_weather" in tools
    assert "get_forecast" in tools
