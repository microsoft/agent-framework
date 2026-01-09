# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

from .._agents import AgentProtocol
from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._agent_utils import resolve_agent_id
from ._executor import Executor, handler
from ._request_info_mixin import response_handler
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext
from ._workflow_executor import WorkflowExecutor


def resolve_request_info_filter(agents: list[str | AgentProtocol] | None) -> set[str]:
    """Resolve a list of agent/executor references to a set of IDs for filtering.

    Args:
        agents: List of agent names (str), AgentProtocol instances, or Executor instances.
                If None, returns None (meaning no filtering - pause for all).

    Returns:
        Set of executor/agent IDs to filter on, or None if no filtering.
    """
    if agents is None:
        return set()

    result: set[str] = set()
    for agent in agents:
        if isinstance(agent, str):
            result.add(agent)
        elif isinstance(agent, AgentProtocol):
            result.add(resolve_agent_id(agent))
        else:
            raise TypeError(f"Unsupported type for request_info filter: {type(agent).__name__}")

    return result


@dataclass
class AgentRequestInfoResponse:
    """Response containing additional information requested from users for agents.

    Attributes:
        messages: list[ChatMessage]: Additional messages provided by users. If empty,
            the agent response is approved as-is.
    """

    messages: list[ChatMessage]

    @staticmethod
    def from_messages(messages: list[ChatMessage]) -> "AgentRequestInfoResponse":
        """Create an AgentRequestInfoResponse from a list of ChatMessages.

        Args:
            messages: List of ChatMessage instances provided by users.

        Returns:
            AgentRequestInfoResponse instance.
        """
        return AgentRequestInfoResponse(messages=messages)

    @staticmethod
    def from_strings(texts: list[str]) -> "AgentRequestInfoResponse":
        """Create an AgentRequestInfoResponse from a list of string messages.

        Args:
            texts: List of text messages provided by users.

        Returns:
            AgentRequestInfoResponse instance.
        """
        return AgentRequestInfoResponse(messages=[ChatMessage(role=Role.USER, text=text) for text in texts])

    @staticmethod
    def approve() -> "AgentRequestInfoResponse":
        """Create an AgentRequestInfoResponse that approves the original agent response.

        Returns:
            AgentRequestInfoResponse instance with no additional messages.
        """
        return AgentRequestInfoResponse(messages=[])


class AgentRequestInfoExecutor(Executor):
    """Executor for gathering request info from users to assist agents."""

    @handler
    async def request_info(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
        """Handle the agent's response and gather additional info from users."""
        await ctx.request_info(agent_response, AgentRequestInfoResponse)

    @response_handler
    async def handle_request_info_response(
        self,
        original_request: AgentExecutorResponse,
        response: AgentRequestInfoResponse,
        ctx: WorkflowContext[AgentExecutorRequest, AgentExecutorResponse],
    ) -> None:
        """Process the additional info provided by users."""
        if response.messages:
            # User provided additional messages, further iterate on agent response
            await ctx.send_message(AgentExecutorRequest(messages=response.messages, should_respond=True))
        else:
            # No additional info, approve original agent response
            await ctx.yield_output(original_request)


class AgentApprovalExecutor(WorkflowExecutor):
    """Executor for enabling scenarios requiring agent approval in an orchestration.

    This executor wraps a sub workflow that contains two executors: an agent executor
    and an request info executor. The agent executor provides intelligence generation,
    while the request info executor gathers input from users to further iterate on the
    agent's output or send the final response to down stream executors in the orchestration.
    """

    def __init__(self, agent: AgentProtocol) -> None:
        """Initialize the AgentApprovalExecutor.

        Args:
            agent: The agent protocol to use for generating responses.
        """
        super().__init__(workflow=self._build_workflow(agent), id=resolve_agent_id(agent), propagate_request=True)
        self._description = agent.description

    def _build_workflow(self, agent: AgentProtocol) -> Workflow:
        """Build the internal workflow for the AgentApprovalExecutor."""
        agent_executor = AgentExecutor(agent)
        request_info_executor = AgentRequestInfoExecutor(id="agent_request_info_executor")

        return (
            WorkflowBuilder()
            # Create a loop between agent executor and request info executor
            .add_edge(agent_executor, request_info_executor)
            .add_edge(request_info_executor, agent_executor)
            .set_start_executor(agent_executor)
            .build()
        )

    @property
    def description(self) -> str | None:
        """Get a description of the underlying agent."""
        return self._description
