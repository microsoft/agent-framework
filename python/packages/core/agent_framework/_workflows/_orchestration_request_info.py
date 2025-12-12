# Copyright (c) Microsoft. All rights reserved.

"""Request info support for high-level builder APIs.

This module provides a mechanism for pausing workflows to request external input
before agent turns in `SequentialBuilder`, `ConcurrentBuilder`, `GroupChatBuilder`,
and `HandoffBuilder`.

The design follows the standard `request_info` pattern used throughout the
workflow system, keeping the API consistent and predictable.

Key components:
- AgentInputRequest: Request type emitted via RequestInfoEvent for pre-agent steering
- RequestInfoInterceptor: Internal executor that pauses workflow before agent runs
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from .._agents import AgentProtocol
from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutorRequest
from ._executor import Executor, handler
from ._request_info_mixin import response_handler
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


def resolve_request_info_filter(
    agents: list[str | AgentProtocol | Executor] | None,
) -> set[str] | None:
    """Resolve a list of agent/executor references to a set of IDs for filtering.

    Args:
        agents: List of agent names (str), AgentProtocol instances, or Executor instances.
                If None, returns None (meaning no filtering - pause for all).

    Returns:
        Set of executor/agent IDs to filter on, or None if no filtering.
    """
    if agents is None:
        return None

    result: set[str] = set()
    for agent in agents:
        if isinstance(agent, str):
            result.add(agent)
        elif isinstance(agent, Executor):
            result.add(agent.id)
        elif isinstance(agent, AgentProtocol):
            name = getattr(agent, "name", None)
            if name:
                result.add(name)
            else:
                logger.warning("AgentProtocol without name cannot be used for request_info filtering")
        else:
            logger.warning(f"Unsupported type for request_info filter: {type(agent).__name__}")

    return result if result else None


@dataclass
class AgentInputRequest:
    """Request for human input before an agent runs in high-level builder workflows.

    Emitted via RequestInfoEvent when a workflow pauses before an agent executes.
    The response is injected into the conversation as a user message to steer
    the agent's behavior.

    This is the standard request type used by `.with_request_info()` on
    SequentialBuilder, ConcurrentBuilder, GroupChatBuilder, and HandoffBuilder.

    Attributes:
        target_agent_id: ID of the agent that is about to run
        conversation: Current conversation history the agent will receive
        instruction: Optional instruction from the orchestrator (e.g., manager in GroupChat)
        metadata: Builder-specific context (stores internal state for resume)
    """

    target_agent_id: str | None
    conversation: list[ChatMessage] = field(default_factory=lambda: [])
    instruction: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: {})


# Keep legacy name as alias for backward compatibility
AgentResponseReviewRequest = AgentInputRequest


DEFAULT_REQUEST_INFO_ID = "request_info_interceptor"


class RequestInfoInterceptor(Executor):
    """Internal executor that pauses workflow for human input before agent runs.

    This executor is inserted into the workflow graph by builders when
    `.with_request_info()` is called. It intercepts AgentExecutorRequest messages
    BEFORE the agent runs and pauses the workflow via `ctx.request_info()` with
    an AgentInputRequest.

    When a response is received, the response handler injects the input
    as a user message into the conversation and forwards the request to the agent.

    The optional `agent_filter` parameter allows limiting which agents trigger the pause.
    If the target agent's ID is not in the filter set, the request is forwarded
    without pausing.
    """

    def __init__(
        self,
        executor_id: str | None = None,
        agent_filter: set[str] | None = None,
    ) -> None:
        """Initialize the request info interceptor executor.

        Args:
            executor_id: ID for this executor. If None, generates a unique ID
                        using the format "request_info_interceptor-<uuid4>".
            agent_filter: Optional set of agent/executor IDs to filter on.
                         If provided, only requests to these agents trigger a pause.
                         If None (default), all requests trigger a pause.
        """
        if executor_id is None:
            executor_id = f"{DEFAULT_REQUEST_INFO_ID}-{uuid.uuid4().hex[:8]}"
        super().__init__(executor_id)
        self._agent_filter = agent_filter

    def _should_pause_for_agent(self, agent_id: str | None) -> bool:
        """Check if we should pause for the given agent ID."""
        if self._agent_filter is None:
            return True
        if agent_id is None:
            return False
        # Check both the full ID and any name portion after a prefix
        # e.g., "groupchat_agent:writer" should match filter "writer"
        if agent_id in self._agent_filter:
            return True
        # Extract name from prefixed IDs like "groupchat_agent:writer" or "request_info:writer"
        if ":" in agent_id:
            name_part = agent_id.split(":", 1)[1]
            if name_part in self._agent_filter:
                return True
        return False

    def _extract_agent_name_from_executor_id(self) -> str | None:
        """Extract the agent name from this interceptor's executor ID.

        The interceptor ID is typically "request_info:<agent_name>", so we
        extract the agent name to determine which agent we're intercepting for.
        """
        if ":" in self.id:
            return self.id.split(":", 1)[1]
        return None

    @handler
    async def intercept_agent_request(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorRequest, Any],
    ) -> None:
        """Intercept request before agent runs and pause for human input.

        Pauses the workflow and emits a RequestInfoEvent with the current
        conversation for steering. If an agent filter is configured and this
        agent is not in the filter, the request is forwarded without pausing.

        Args:
            request: The request about to be sent to the agent
            ctx: Workflow context for requesting info
        """
        # Determine the target agent from our executor ID
        target_agent = self._extract_agent_name_from_executor_id()

        # Check if we should pause for this agent
        if not self._should_pause_for_agent(target_agent):
            logger.debug(f"Skipping request_info pause for agent {target_agent} (not in filter)")
            await ctx.send_message(request)
            return

        conversation = list(request.messages or [])

        input_request = AgentInputRequest(
            target_agent_id=target_agent,
            conversation=conversation,
            instruction=None,  # Could be extended to include manager instruction
            metadata={"_original_request": request, "_input_type": "AgentExecutorRequest"},
        )
        await ctx.request_info(input_request, str)

    @handler
    async def intercept_conversation(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[list[ChatMessage], Any],
    ) -> None:
        """Intercept conversation before agent runs (used by SequentialBuilder).

        SequentialBuilder passes list[ChatMessage] directly to agents. This handler
        intercepts that flow and pauses for human input.

        Args:
            messages: The conversation about to be sent to the agent
            ctx: Workflow context for requesting info
        """
        # Determine the target agent from our executor ID
        target_agent = self._extract_agent_name_from_executor_id()

        # Check if we should pause for this agent
        if not self._should_pause_for_agent(target_agent):
            logger.debug(f"Skipping request_info pause for agent {target_agent} (not in filter)")
            await ctx.send_message(messages)
            return

        input_request = AgentInputRequest(
            target_agent_id=target_agent,
            conversation=list(messages),
            instruction=None,
            metadata={"_original_messages": messages, "_input_type": "list[ChatMessage]"},
        )
        await ctx.request_info(input_request, str)

    @handler
    async def intercept_concurrent_requests(
        self,
        requests: list[AgentExecutorRequest],
        ctx: WorkflowContext[list[AgentExecutorRequest], Any],
    ) -> None:
        """Intercept requests before concurrent agents run.

        This handler is used by ConcurrentBuilder to get human input before
        all parallel agents execute.

        Args:
            requests: List of requests for all concurrent agents
            ctx: Workflow context for requesting info
        """
        # Combine conversations for display
        combined_conversation: list[ChatMessage] = []
        if requests:
            combined_conversation = list(requests[0].messages or [])

        input_request = AgentInputRequest(
            target_agent_id=None,  # Multiple agents
            conversation=combined_conversation,
            instruction=None,
            metadata={"_original_requests": requests},
        )
        await ctx.request_info(input_request, str)

    @response_handler
    async def handle_input_response(
        self,
        original_request: AgentInputRequest,
        # TODO(@moonbox3): Extend to support other content types
        response: str,
        ctx: WorkflowContext[AgentExecutorRequest | list[ChatMessage], Any],
    ) -> None:
        """Handle the human input and forward the modified request to the agent.

        Injects the response as a user message into the conversation
        and forwards the modified request to the agent.

        Args:
            original_request: The AgentInputRequest that triggered the pause
            response: The human input text
            ctx: Workflow context for continuing the workflow

        TODO: Consider having each orchestration implement its own response handler
              for more specialized behavior.
        """
        human_message = ChatMessage(role=Role.USER, text=response)

        # Handle concurrent case (list of AgentExecutorRequest)
        original_requests: list[AgentExecutorRequest] | None = original_request.metadata.get("_original_requests")
        if original_requests is not None:
            updated_requests: list[AgentExecutorRequest] = []
            for orig_req in original_requests:
                messages = list(orig_req.messages or [])
                messages.append(human_message)
                updated_requests.append(
                    AgentExecutorRequest(
                        messages=messages,
                        should_respond=orig_req.should_respond,
                    )
                )

            logger.debug(
                f"Human input received for concurrent workflow, "
                f"continuing with {len(updated_requests)} updated requests"
            )
            await ctx.send_message(updated_requests)  # type: ignore[arg-type]
            return

        # Handle list[ChatMessage] case (SequentialBuilder)
        original_messages: list[ChatMessage] | None = original_request.metadata.get("_original_messages")
        if original_messages is not None:
            messages = list(original_messages)
            messages.append(human_message)

            logger.debug(
                f"Human input received for agent {original_request.target_agent_id}, "
                f"forwarding conversation with steering context"
            )
            await ctx.send_message(messages)
            return

        # Handle AgentExecutorRequest case (GroupChatBuilder)
        orig_request: AgentExecutorRequest | None = original_request.metadata.get("_original_request")
        if orig_request is not None:
            messages = list(orig_request.messages or [])
            messages.append(human_message)

            updated_request = AgentExecutorRequest(
                messages=messages,
                should_respond=orig_request.should_respond,
            )

            logger.debug(
                f"Human input received for agent {original_request.target_agent_id}, "
                f"forwarding request with steering context"
            )
            await ctx.send_message(updated_request)
            return

        logger.error("Input response handler missing original request/messages in metadata")
        raise RuntimeError("Missing original request or messages in AgentInputRequest metadata")
