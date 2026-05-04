# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Literal

from agent_framework._agents import SupportsAgentRun
from agent_framework._types import AgentResponse, Message
from agent_framework._workflows._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from agent_framework._workflows._agent_utils import resolve_agent_id
from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._request_info_mixin import response_handler
from agent_framework._workflows._workflow import Workflow
from agent_framework._workflows._workflow_builder import WorkflowBuilder
from agent_framework._workflows._workflow_context import WorkflowContext
from agent_framework._workflows._workflow_executor import WorkflowExecutor


def resolve_request_info_filter(agents: list[str | SupportsAgentRun] | None) -> set[str]:
    """Resolve a list of agent/executor references to a set of IDs for filtering.

    Args:
        agents: List of agent names (str), SupportsAgentRun instances, or Executor instances.
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
        elif isinstance(agent, SupportsAgentRun):
            result.add(resolve_agent_id(agent))
        else:
            raise TypeError(f"Unsupported type for request_info filter: {type(agent).__name__}")

    return result


@dataclass
class AgentRequestInfoResponse:
    """Response containing additional information requested from users for agents.

    Attributes:
        messages: list[Message]: Additional messages provided by users. If empty,
            the agent response is approved as-is.
    """

    messages: list[Message]

    @staticmethod
    def from_messages(messages: list[Message]) -> "AgentRequestInfoResponse":
        """Create an AgentRequestInfoResponse from a list of ChatMessages.

        Args:
            messages: List of Message instances provided by users.

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
        return AgentRequestInfoResponse(messages=[Message(role="user", contents=[text]) for text in texts])

    @staticmethod
    def approve() -> "AgentRequestInfoResponse":
        """Create an AgentRequestInfoResponse that approves the original agent response.

        Returns:
            AgentRequestInfoResponse instance with no additional messages.
        """
        return AgentRequestInfoResponse(messages=[])


class AgentRequestInfoExecutor(Executor):
    """Executor for gathering request info from users to assist agents.

    On approval (caller returned no follow-up messages), yields the original
    ``AgentExecutorResponse`` so downstream ``AgentExecutor`` participants can consume it
    via their ``from_response`` handler — i.e., the inner workflow's output type matches the
    chain currency used between Sequential participants.
    """

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


class _TerminalAgentRequestInfoExecutor(Executor):
    """Sibling of ``AgentRequestInfoExecutor`` used when ``AgentApprovalExecutor`` is the workflow's terminator.

    This exists because:
    - The orchestration contract established is that every orchestration's terminal
      ``output`` event carries an ``AgentResponse``. That is the user-facing promise — e.g.,
      ``workflow.as_agent().run(prompt)`` returns an ``AgentResponse``.
    - ``AgentRequestInfoExecutor`` yields ``AgentExecutorResponse`` because that is the chain
      currency between Sequential participants: the next ``AgentExecutor`` consumes
      ``AgentExecutorResponse`` via its ``from_response`` handler. That is correct when
      ``AgentApprovalExecutor`` is *intermediate*.
    - When ``AgentApprovalExecutor`` is the *terminator* (``allow_direct_output=True``), the
      inner yield flows straight through ``WorkflowExecutor`` to the outer workflow's terminal
      output. Yielding ``AgentExecutorResponse`` there would surface ``AgentExecutorResponse``
      as the workflow's terminal output — violating the orchestration contract.

    Used in place of ``AgentRequestInfoExecutor`` inside the terminator-mode inner workflow
    built by ``AgentApprovalExecutor._build_workflow`` when ``allow_direct_output=True``.

    Translation belongs here — at the source of the yield in the orchestrations package —
    rather than at the ``WorkflowExecutor`` boundary in core, because core has no opinion
    about the orchestration's ``AgentResponse`` contract.

    Note: not a subclass of ``AgentRequestInfoExecutor``. The two classes have different
    terminal yield contracts (``AgentExecutorResponse`` vs. ``AgentResponse``), and
    ``WorkflowContext``'s output type parameter is invariant — so a subclass override would
    be type-incompatible. They are siblings sharing only a small ``request_info`` handler.
    """

    @handler
    async def request_info(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
        """Handle the agent's response and gather additional info from users."""
        await ctx.request_info(agent_response, AgentRequestInfoResponse)

    @response_handler
    async def handle_request_info_response(
        self,
        original_request: AgentExecutorResponse,
        response: AgentRequestInfoResponse,
        ctx: WorkflowContext[AgentExecutorRequest, AgentResponse],
    ) -> None:
        """Process the additional info provided by users; yield ``AgentResponse`` on approval."""
        if response.messages:
            # User provided additional messages, further iterate on agent response
            await ctx.send_message(AgentExecutorRequest(messages=response.messages, should_respond=True))
        else:
            # No additional info, approve and surface the wrapped AgentResponse to the parent.
            await ctx.yield_output(original_request.agent_response)


class AgentApprovalExecutor(WorkflowExecutor):
    """Executor for enabling scenarios requiring agent approval in an orchestration.

    This executor wraps a sub workflow that contains two executors: an agent executor
    and an request info executor. The agent executor provides intelligence generation,
    while the request info executor gathers input from users to further iterate on the
    agent's output or send the final response to down stream executors in the orchestration.
    """

    def __init__(
        self,
        agent: SupportsAgentRun,
        context_mode: Literal["full", "last_agent", "custom"] | None = None,
        *,
        allow_direct_output: bool = False,
    ) -> None:
        """Initialize the AgentApprovalExecutor.

        Args:
            agent: The agent protocol to use for generating responses.
            context_mode: The mode for providing context to the agent.
            allow_direct_output: When True, the inner agent's response is yielded as the
                wrapping workflow's output (rather than forwarded as a message to a
                downstream participant). Set this when this executor is the workflow's
                terminator — so the user-approved final response surfaces as a workflow
                ``output`` event.
        """
        self._context_mode: Literal["full", "last_agent", "custom"] | None = context_mode
        self._description = agent.description

        super().__init__(
            workflow=self._build_workflow(agent, terminal=allow_direct_output),
            id=resolve_agent_id(agent),
            propagate_request=True,
            allow_direct_output=allow_direct_output,
        )

    def _build_workflow(self, agent: SupportsAgentRun, *, terminal: bool) -> Workflow:
        """Build the internal workflow for the AgentApprovalExecutor.

        Picks the right ``AgentRequestInfoExecutor`` variant for the role this approval flow
        plays in the outer workflow:

        - Intermediate (``terminal=False``): inner workflow yields ``AgentExecutorResponse``
          so the next outer ``AgentExecutor`` participant can consume it via ``from_response``.
        - Terminator (``terminal=True``): inner workflow yields ``AgentResponse`` so the outer
          workflow's terminal output matches the orchestration contract.
        """
        agent_executor = AgentExecutor(
            agent,
            context_mode=self._context_mode,
        )
        request_info_cls = _TerminalAgentRequestInfoExecutor if terminal else AgentRequestInfoExecutor
        request_info_executor = request_info_cls(id="agent_request_info_executor")

        return (
            WorkflowBuilder(start_executor=agent_executor)
            # Create a loop between agent executor and request info executor
            .add_edge(agent_executor, request_info_executor)
            .add_edge(request_info_executor, agent_executor)
            .build()
        )

    @property
    def description(self) -> str | None:
        """Get a description of the underlying agent."""
        return self._description
