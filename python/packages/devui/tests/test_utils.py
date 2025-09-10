"""Shared test utilities for devui tests."""

from collections.abc import AsyncIterable
from typing import List
from unittest.mock import Mock

from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, AgentThread
from agent_framework_workflow import Executor, WorkflowBuilder, WorkflowContext, handler


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


class MockExecutor(Executor):
    """Mock executor for testing."""

    def __init__(self, exec_id: str):
        # Properly initialize via parent constructor
        super().__init__(id=exec_id)

    @handler
    async def mock_handler(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Mock handler that accepts string input."""
        pass


def create_mock_workflow(name: str = "TestWorkflow"):
    """Create a real workflow for testing instead of trying to mock the complex Workflow class."""
    executor1 = MockExecutor("executor1")
    executor2 = MockExecutor("executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    # Real workflows don't have name/description fields in the Pydantic model
    # The registry will get None for these, which is expected behavior

    return workflow


def mock_tool_function():
    """Mock tool function for testing."""
    pass
