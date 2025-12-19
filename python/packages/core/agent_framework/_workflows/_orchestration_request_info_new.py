# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentProtocol,
    ChatMessage,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    response_handler,
)


@dataclass
class AgentRequestInfoResponse:
    """Response containing additional information requested from users for agents.

    Attributes:
        messages: list[ChatMessage]: Additional messages provided by users. If empty,
            the agent response is approved as-is.
    """

    messages: list[ChatMessage]


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
        super().__init__(workflow=self._build_workflow(agent), id=agent.id)

    def _build_workflow(self, agent: AgentProtocol) -> Workflow:
        """Build the internal workflow for the AgentApprovalExecutor."""
        agent_executor = AgentExecutor(agent)
        request_info_executor = AgentRequestInfoExecutor(id="agent_request_info_executor")

        return (
            WorkflowBuilder()
            .add_edge(agent_executor, request_info_executor)
            .add_edge(request_info_executor, agent_executor)
            .set_start_executor(agent_executor)
            .build()
        )
