# Copyright (c) Microsoft. All rights reserved.

"""Human input hook support for high-level builder APIs.

This module provides infrastructure for requesting arbitrary human feedback
mid-workflow in `SequentialBuilder`, `ConcurrentBuilder`, and `GroupChatBuilder`.

Key components:
- HumanInputRequest: Standard request type emitted via RequestInfoEvent
- HumanInputHook: Callable type alias for hook functions
- HumanInputHookMixin: Mixin class providing `.with_human_input_hook()` method
- _HumanInputInterceptor: Internal executor that intercepts responses and invokes the hook
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias, cast

from typing_extensions import Self

from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutorResponse
from ._executor import Executor, handler
from ._request_info_mixin import response_handler
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class HumanInputRequest:
    """Request for human input in high-level builder workflows.

    Emitted via RequestInfoEvent when a workflow needs human guidance beyond
    binary tool approval. The human's response is injected into the conversation
    as a user message before the workflow continues.

    Attributes:
        prompt: Human-readable prompt explaining what input is needed
        conversation: Full conversation history at the time of the request
        source_agent_id: ID of the agent whose output triggered the request (if known)
        metadata: Optional builder-specific context (round index, agent name, etc.)
    """

    prompt: str
    conversation: list[ChatMessage] = field(default_factory=lambda: [])
    source_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: {})


# Type alias for human input hook result
HumanInputHookResult: TypeAlias = HumanInputRequest | None

# Type alias for the human input hook callback
# Accepts (conversation, agent_id) and returns HumanInputRequest to pause or None to continue
# Supports both sync and async callbacks
HumanInputHook: TypeAlias = Callable[
    [list[ChatMessage], str | None],
    HumanInputHookResult | Awaitable[HumanInputHookResult],
]


class HumanInputHookMixin:
    """Mixin providing human input hook capability for high-level builders.

    Builders that inherit this mixin gain the `.with_human_input_hook()` method
    and internal state management for the hook. The mixin provides a factory
    method to create the interceptor executor when the hook is configured.
    """

    _human_input_hook: HumanInputHook | None = None

    def with_human_input_hook(
        self: Self,
        hook: HumanInputHook,
    ) -> Self:
        """Add a hook that can request human input between agent turns.

        The hook is called after each agent completes. If it returns a
        HumanInputRequest, the workflow pauses and emits a RequestInfoEvent.
        The human's response is injected into the conversation as a user
        message before the next agent runs.

        The hook can be either sync or async. Async hooks are awaited internally.

        Args:
            hook: Callback that receives (conversation, agent_id) and returns
                  HumanInputRequest to pause, or None to continue. Can be
                  sync or async.

        Returns:
            Self for method chaining.

        Example:

        .. code-block:: python

            # Sync hook - simple inspection
            def review_on_keyword(
                conversation: list[ChatMessage],
                agent_id: str | None,
            ) -> HumanInputRequest | None:
                if conversation and "review" in conversation[-1].text.lower():
                    return HumanInputRequest(
                        prompt="Please review and provide feedback:",
                        conversation=conversation,
                        source_agent_id=agent_id,
                    )
                return None


            # Async hook - checks external service
            async def check_policy_service(
                conversation: list[ChatMessage],
                agent_id: str | None,
            ) -> HumanInputRequest | None:
                requires_review = await policy_api.check_content(conversation[-1].text)
                if requires_review:
                    return HumanInputRequest(
                        prompt="Content flagged for review:",
                        conversation=conversation,
                        source_agent_id=agent_id,
                    )
                return None


            # Both work the same way
            workflow = (
                SequentialBuilder().participants([agent1, agent2]).with_human_input_hook(check_policy_service).build()
            )
        """
        self._human_input_hook = hook
        return self

    def _create_human_input_executor(
        self,
        executor_id: str = "human_input_interceptor",
    ) -> "_HumanInputInterceptor | None":
        """Factory method for builders to create the interceptor executor if hook is set.

        Args:
            executor_id: ID for the interceptor executor (default: "human_input_interceptor")

        Returns:
            _HumanInputInterceptor instance if hook is configured, None otherwise.
        """
        if self._human_input_hook is None:
            return None
        return _HumanInputInterceptor(self._human_input_hook, executor_id=executor_id)


class _HumanInputInterceptor(Executor):
    """Internal executor that intercepts agent responses and invokes the human input hook.

    This executor is inserted into the workflow graph by builders that use
    the HumanInputHookMixin. It intercepts AgentExecutorResponse messages,
    invokes the configured hook, and either:
    - Passes through the response unchanged (hook returns None)
    - Pauses the workflow via ctx.request_info() (hook returns HumanInputRequest)

    When the human responds, the response handler injects the human's input
    as a user message into the conversation and continues the workflow.

    For ConcurrentBuilder, this executor also handles list[AgentExecutorResponse]
    from fan-in aggregation. In that case, all conversations are merged before
    invoking the hook with agent_id=None.
    """

    def __init__(
        self,
        hook: HumanInputHook,
        executor_id: str = "human_input_interceptor",
    ) -> None:
        """Initialize the interceptor executor.

        Args:
            hook: The human input hook callback
            executor_id: ID for this executor (default: "human_input_interceptor")
        """
        super().__init__(executor_id)
        self._hook = hook

    async def _invoke_hook(
        self,
        conversation: list[ChatMessage],
        agent_id: str | None,
    ) -> HumanInputRequest | None:
        """Invoke the hook, handling both sync and async callbacks.

        Args:
            conversation: Current conversation history
            agent_id: ID of the agent that produced the last response

        Returns:
            HumanInputRequest if human input is needed, None otherwise
        """
        result = self._hook(conversation, agent_id)
        if inspect.iscoroutine(result):
            return cast("HumanInputRequest | None", await result)
        return cast("HumanInputRequest | None", result)

    @handler
    async def check_for_input(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorResponse, Any],
    ) -> None:
        """Check if human input is needed after an agent response.

        If the hook returns a HumanInputRequest, the workflow pauses and emits
        a RequestInfoEvent. Otherwise, the response passes through unchanged.

        Args:
            response: The agent's response to check
            ctx: Workflow context for sending messages or requesting info
        """
        conversation = list(response.full_conversation or [])
        agent_id = response.executor_id

        request = await self._invoke_hook(conversation, agent_id)
        if request is not None:
            # Store the original response so we can continue after human input
            request.metadata["_original_response"] = response
            await ctx.request_info(request, str)
        else:
            # No human input needed, pass through the response
            await ctx.send_message(response)

    @handler
    async def check_for_input_concurrent(
        self,
        responses: list[AgentExecutorResponse],
        ctx: WorkflowContext[list[AgentExecutorResponse], Any],
    ) -> None:
        """Check if human input is needed after concurrent agents complete.

        This handler is used by ConcurrentBuilder to check all parallel agent
        outputs before aggregation. The hook is called with a merged view of
        all agent conversations and agent_id=None.

        Args:
            responses: List of responses from all concurrent agents
            ctx: Workflow context for sending messages or requesting info
        """
        # Merge all conversations into a combined view for the hook
        # Take the first response's conversation as base (they share user prompt)
        # then append each agent's final assistant messages
        combined_conversation: list[ChatMessage] = []
        if responses:
            # Use the first response's full conversation as the base
            first_conv = responses[0].full_conversation or []
            combined_conversation = list(first_conv)

            # For subsequent responses, just add their assistant messages to avoid
            # duplicating the user prompt. Note: this is a simplified merge.
            for resp in responses[1:]:
                if resp.agent_run_response and resp.agent_run_response.messages:
                    combined_conversation.extend(resp.agent_run_response.messages)

        request = await self._invoke_hook(combined_conversation, None)
        if request is not None:
            # Store the original responses so we can continue after human input
            request.metadata["_original_responses"] = responses
            await ctx.request_info(request, str)
        else:
            # No human input needed, pass through the responses
            await ctx.send_message(responses)

    @response_handler
    async def handle_human_response(
        self,
        original_request: HumanInputRequest,
        response: str,
        ctx: WorkflowContext[AgentExecutorResponse, Any],
    ) -> None:
        """Handle the human's response and continue the workflow.

        Injects the human's response as a user message into the conversation
        and forwards the modified AgentExecutorResponse to continue the workflow.

        Args:
            original_request: The HumanInputRequest that triggered the pause
            response: The human's response text
            ctx: Workflow context for continuing the workflow
        """
        # Check if this is from concurrent (list) or sequential (single) response
        original_responses: list[AgentExecutorResponse] | None = original_request.metadata.get("_original_responses")
        if original_responses is not None:
            # Concurrent case: inject human response and forward list
            human_message = ChatMessage(role=Role.USER, text=response)

            # Add the human message to all responses' conversations
            updated_responses: list[AgentExecutorResponse] = []
            for orig_resp in original_responses:
                conversation = list(orig_resp.full_conversation or [])
                conversation.append(human_message)
                updated_responses.append(
                    AgentExecutorResponse(
                        executor_id=orig_resp.executor_id,
                        agent_run_response=orig_resp.agent_run_response,
                        full_conversation=conversation,
                    )
                )

            logger.debug(
                f"Human input received for concurrent workflow, "
                f"continuing with {len(updated_responses)} updated responses"
            )
            await ctx.send_message(updated_responses)  # type: ignore[arg-type]
            return

        # Sequential case: single response
        original_response: AgentExecutorResponse | None = original_request.metadata.get("_original_response")
        if original_response is None:
            logger.error("Human input response handler missing original response in request metadata")
            raise RuntimeError("Missing original response in HumanInputRequest metadata")

        # Inject human response into the conversation
        human_message = ChatMessage(role=Role.USER, text=response)
        conversation = list(original_response.full_conversation or [])
        conversation.append(human_message)

        # Create updated response with the human input included
        updated_response = AgentExecutorResponse(
            executor_id=original_response.executor_id,
            agent_run_response=original_response.agent_run_response,
            full_conversation=conversation,
        )

        logger.debug(
            f"Human input received for agent {original_response.executor_id}, "
            f"continuing workflow with updated conversation"
        )
        await ctx.send_message(updated_response)
