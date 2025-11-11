# Copyright (c) Microsoft. All rights reserved.

"""High-level builder for conversational handoff workflows.

The handoff pattern models a coordinator agent that optionally routes
control to specialist agents before handing the conversation back to the user.
The flow is intentionally cyclical:

    user input -> coordinator -> optional specialist -> request user input -> ...

Key properties:
- The entire conversation is maintained and reused on every hop
- The coordinator signals a handoff by invoking a tool call that names the specialist
- After a specialist responds, the workflow immediately requests new user input
"""

import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AIFunction,
    ChatMessage,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    ai_function,
)

from .._agents import ChatAgent
from .._middleware import FunctionInvocationContext, FunctionMiddleware
from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._base_group_chat_orchestrator import BaseGroupChatOrchestrator
from ._checkpoint import CheckpointStorage
from ._executor import Executor, handler
from ._group_chat import (
    _default_participant_factory,  # type: ignore[reportPrivateUsage]
    _GroupChatConfig,  # type: ignore[reportPrivateUsage]
    assemble_group_chat_workflow,
)
from ._orchestrator_helpers import clean_conversation_for_handoff
from ._participant_utils import GroupChatParticipantSpec, prepare_participant_metadata, sanitize_identifier
from ._request_info_mixin import response_handler
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


_HANDOFF_TOOL_PATTERN = re.compile(r"(?:handoff|transfer)[_\s-]*to[_\s-]*(?P<target>[\w-]+)", re.IGNORECASE)


def _create_handoff_tool(alias: str, description: str | None = None) -> AIFunction[Any, Any]:
    """Construct the synthetic handoff tool that signals routing to `alias`."""
    sanitized = sanitize_identifier(alias)
    tool_name = f"handoff_to_{sanitized}"
    doc = description or f"Handoff to the {alias} agent."

    # Note: approval_mode is intentionally NOT set for handoff tools.
    # Handoff tools are framework-internal signals that trigger routing logic,
    # not actual function executions. They are automatically intercepted and
    # never actually execute, so approval is unnecessary and causes issues
    # with tool_calls/responses pairing when cleaning conversations.
    @ai_function(name=tool_name, description=doc)
    def _handoff_tool(context: str | None = None) -> str:
        """Return a deterministic acknowledgement that encodes the target alias."""
        return f"Handoff to {alias}"

    return _handoff_tool


def _clone_chat_agent(agent: ChatAgent) -> ChatAgent:
    """Produce a deep copy of the ChatAgent while preserving runtime configuration."""
    options = agent.chat_options
    middleware = list(agent.middleware or [])

    # Reconstruct the original tools list by combining regular tools with MCP tools.
    # ChatAgent.__init__ separates MCP tools into _local_mcp_tools during initialization,
    # so we need to recombine them here to pass the complete tools list to the constructor.
    # This makes sure MCP tools are preserved when cloning agents for handoff workflows.
    all_tools = list(options.tools) if options.tools else []
    if agent._local_mcp_tools:  # type: ignore
        all_tools.extend(agent._local_mcp_tools)  # type: ignore

    return ChatAgent(
        chat_client=agent.chat_client,
        instructions=options.instructions,
        id=agent.id,
        name=agent.name,
        description=agent.description,
        chat_message_store_factory=agent.chat_message_store_factory,
        context_providers=agent.context_provider,
        middleware=middleware,
        frequency_penalty=options.frequency_penalty,
        logit_bias=dict(options.logit_bias) if options.logit_bias else None,
        max_tokens=options.max_tokens,
        metadata=dict(options.metadata) if options.metadata else None,
        model_id=options.model_id,
        presence_penalty=options.presence_penalty,
        response_format=options.response_format,
        seed=options.seed,
        stop=options.stop,
        store=options.store,
        temperature=options.temperature,
        tool_choice=options.tool_choice,  # type: ignore[arg-type]
        tools=all_tools if all_tools else None,
        top_p=options.top_p,
        user=options.user,
        additional_chat_options=dict(options.additional_properties),
    )


@dataclass
class HandoffUserInputRequest:
    """Request message emitted when the workflow needs fresh user input."""

    conversation: list[ChatMessage]
    awaiting_agent_id: str
    prompt: str
    source_executor_id: str


@dataclass
class _ConversationWithUserInput:
    """Internal message carrying full conversation + new user messages from gateway to coordinator."""

    full_conversation: list[ChatMessage] = field(default_factory=lambda: [])  # type: ignore[misc]


@dataclass
class _ConversationForUserInput:
    """Internal message from coordinator to gateway specifying which agent will receive the response."""

    conversation: list[ChatMessage]
    next_agent_id: str


class _AutoHandoffMiddleware(FunctionMiddleware):
    """Intercept handoff tool invocations and short-circuit execution with synthetic results."""

    def __init__(self, handoff_targets: Mapping[str, str]) -> None:
        """Initialise middleware with the mapping from tool name to specialist id."""
        self._targets = {name.lower(): target for name, target in handoff_targets.items()}

    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Intercept matching handoff tool calls and inject synthetic results."""
        name = getattr(context.function, "name", "")
        normalized = name.lower() if name else ""
        target = self._targets.get(normalized)
        if target is None:
            await next(context)
            return

        # Short-circuit execution and provide deterministic response payload for the tool call.
        context.result = {"handoff_to": target}
        context.terminate = True


class _InputToConversation(Executor):
    """Normalises initial workflow input into a list[ChatMessage]."""

    @handler
    async def from_str(self, prompt: str, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        """Convert a raw user prompt into a conversation containing a single user message."""
        await ctx.send_message([ChatMessage(Role.USER, text=prompt)])

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[list[ChatMessage]]) -> None:  # type: ignore[name-defined]
        """Pass through an existing chat message as the initial conversation."""
        await ctx.send_message([message])

    @handler
    async def from_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[list[ChatMessage]],
    ) -> None:  # type: ignore[name-defined]
        """Forward a list of chat messages as the starting conversation history."""
        await ctx.send_message(list(messages))


@dataclass
class _HandoffResolution:
    """Result of handoff detection containing the target alias and originating call."""

    target: str
    function_call: FunctionCallContent | None = None


def _resolve_handoff_target(agent_response: AgentRunResponse) -> _HandoffResolution | None:
    """Detect handoff intent from tool call metadata."""
    for message in agent_response.messages:
        resolution = _resolution_from_message(message)
        if resolution:
            return resolution

    for request in agent_response.user_input_requests:
        if isinstance(request, FunctionApprovalRequestContent):
            resolution = _resolution_from_function_call(request.function_call)
            if resolution:
                return resolution

    return None


def _resolution_from_message(message: ChatMessage) -> _HandoffResolution | None:
    """Inspect an assistant message for embedded handoff tool metadata."""
    for content in getattr(message, "contents", ()):
        if isinstance(content, FunctionApprovalRequestContent):
            resolution = _resolution_from_function_call(content.function_call)
            if resolution:
                return resolution
        elif isinstance(content, FunctionCallContent):
            resolution = _resolution_from_function_call(content)
            if resolution:
                return resolution
    return None


def _resolution_from_function_call(function_call: FunctionCallContent | None) -> _HandoffResolution | None:
    """Wrap the target resolved from a function call in a `_HandoffResolution`."""
    if function_call is None:
        return None
    target = _target_from_function_call(function_call)
    if not target:
        return None
    return _HandoffResolution(target=target, function_call=function_call)


def _target_from_function_call(function_call: FunctionCallContent) -> str | None:
    """Extract the handoff target from the tool name or structured arguments."""
    name_candidate = _target_from_tool_name(function_call.name)
    if name_candidate:
        return name_candidate

    arguments = function_call.parse_arguments()
    if isinstance(arguments, Mapping):
        value = arguments.get("handoff_to")
        if isinstance(value, str) and value.strip():
            return value.strip()
    elif isinstance(arguments, str):
        stripped = arguments.strip()
        if stripped:
            name_candidate = _target_from_tool_name(stripped)
            if name_candidate:
                return name_candidate
            return stripped

    return None


def _target_from_tool_name(name: str | None) -> str | None:
    """Parse the specialist alias encoded in a handoff tool's name."""
    if not name:
        return None
    match = _HANDOFF_TOOL_PATTERN.search(name)
    if match:
        parsed = match.group("target").strip()
        if parsed:
            return parsed
    return None


class _HandoffCoordinator(BaseGroupChatOrchestrator):
    """Coordinates agent-to-agent transfers and user turn requests."""

    def __init__(
        self,
        *,
        starting_agent_id: str,
        specialist_ids: Mapping[str, str],
        input_gateway_id: str,
        termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]],
        id: str,
        handoff_tool_targets: Mapping[str, str] | None = None,
        return_to_previous: bool = False,
    ) -> None:
        """Create a coordinator that manages routing between specialists and the user."""
        super().__init__(id)
        self._starting_agent_id = starting_agent_id
        self._specialist_by_alias = dict(specialist_ids)
        self._specialist_ids = set(specialist_ids.values())
        self._input_gateway_id = input_gateway_id
        self._termination_condition = termination_condition
        self._handoff_tool_targets = {k.lower(): v for k, v in (handoff_tool_targets or {}).items()}
        self._return_to_previous = return_to_previous
        self._current_agent_id: str | None = None  # Track the current agent handling conversation

    def _get_author_name(self) -> str:
        """Get the coordinator name for orchestrator-generated messages."""
        return "handoff_coordinator"

    @handler
    async def handle_agent_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest | list[ChatMessage], list[ChatMessage] | _ConversationForUserInput],
    ) -> None:
        """Process an agent's response and determine whether to route, request input, or terminate."""
        # Hydrate coordinator state (and detect new run) using checkpointable executor state
        state = await ctx.get_executor_state()
        if not state:
            self._clear_conversation()
        elif not self._get_conversation():
            restored = self._restore_conversation_from_state(state)
            if restored:
                self._conversation = list(restored)

        source = ctx.get_source_executor_id()
        is_starting_agent = source == self._starting_agent_id

        # On first turn of a run, conversation is empty
        # Track new messages only, build authoritative history incrementally
        conversation_msgs = self._get_conversation()
        if not conversation_msgs:
            # First response from starting agent - initialize with authoritative conversation snapshot
            # Keep the FULL conversation including tool calls (OpenAI SDK default behavior)
            full_conv = self._conversation_from_response(response)
            self._conversation = list(full_conv)
        else:
            # Subsequent responses - append only new messages from this agent
            # Keep ALL messages including tool calls to maintain complete history
            new_messages = response.agent_run_response.messages or []
            self._conversation.extend(new_messages)

        self._apply_response_metadata(self._conversation, response.agent_run_response)

        conversation = list(self._conversation)

        # Check for handoff from ANY agent (starting agent or specialist)
        target = self._resolve_specialist(response.agent_run_response, conversation)
        if target is not None:
            # Update current agent when handoff occurs
            self._current_agent_id = target
            logger.info(f"Handoff detected: {source} -> {target}. Routing control to specialist '{target}'.")
            await self._persist_state(ctx)
            # Clean tool-related content before sending to next agent
            cleaned = clean_conversation_for_handoff(conversation)
            request = AgentExecutorRequest(messages=cleaned, should_respond=True)
            await ctx.send_message(request, target_id=target)
            return

        # No handoff detected - response must come from starting agent or known specialist
        if not is_starting_agent and source not in self._specialist_ids:
            raise RuntimeError(f"HandoffCoordinator received response from unknown executor '{source}'.")

        # Update current agent when they respond without handoff
        self._current_agent_id = source
        logger.info(
            f"Agent '{source}' responded without handoff. "
            f"Requesting user input. Return-to-previous: {self._return_to_previous}"
        )
        await self._persist_state(ctx)

        if await self._check_termination():
            # Clean the output conversation for display
            cleaned_output = clean_conversation_for_handoff(conversation)
            await ctx.yield_output(cleaned_output)
            return

        # Clean conversation before sending to gateway for user input request
        # This removes tool messages that shouldn't be shown to users
        cleaned_for_display = clean_conversation_for_handoff(conversation)

        # The awaiting_agent_id is the agent that just responded and is awaiting user input
        # This is the source of the current response
        next_agent_id = source

        message_to_gateway = _ConversationForUserInput(conversation=cleaned_for_display, next_agent_id=next_agent_id)
        await ctx.send_message(message_to_gateway, target_id=self._input_gateway_id)  # type: ignore[arg-type]

    @handler
    async def handle_user_input(
        self,
        message: _ConversationWithUserInput,
        ctx: WorkflowContext[AgentExecutorRequest, list[ChatMessage]],
    ) -> None:
        """Receive full conversation with new user input from gateway, update history, trim for agent."""
        # Update authoritative conversation
        self._conversation = list(message.full_conversation)
        await self._persist_state(ctx)

        # Check termination before sending to agent
        if await self._check_termination():
            await ctx.yield_output(list(self._conversation))
            return

        # Determine routing target based on return-to-previous setting
        target_agent_id = self._starting_agent_id
        if self._return_to_previous and self._current_agent_id:
            # Route back to the current agent that's handling the conversation
            target_agent_id = self._current_agent_id
            logger.info(
                f"Return-to-previous enabled: routing user input to current agent '{target_agent_id}' "
                f"(bypassing coordinator '{self._starting_agent_id}')"
            )
        else:
            logger.info(f"Routing user input to coordinator '{target_agent_id}'")
        # Note: Stack is only used for specialist-to-specialist handoffs, not user input routing

        # Clean before sending to target agent
        cleaned = clean_conversation_for_handoff(self._conversation)
        request = AgentExecutorRequest(messages=cleaned, should_respond=True)
        await ctx.send_message(request, target_id=target_agent_id)

    def _resolve_specialist(self, agent_response: AgentRunResponse, conversation: list[ChatMessage]) -> str | None:
        """Resolve the specialist executor id requested by the agent response, if any."""
        resolution = _resolve_handoff_target(agent_response)
        if not resolution:
            return None

        candidate = resolution.target
        normalized = candidate.lower()
        resolved_id: str | None
        if normalized in self._handoff_tool_targets:
            resolved_id = self._handoff_tool_targets[normalized]
        else:
            resolved_id = self._specialist_by_alias.get(candidate)

        if resolved_id:
            if resolution.function_call:
                self._append_tool_acknowledgement(conversation, resolution.function_call, resolved_id)
            return resolved_id

        lowered = candidate.lower()
        for alias, exec_id in self._specialist_by_alias.items():
            if alias.lower() == lowered:
                if resolution.function_call:
                    self._append_tool_acknowledgement(conversation, resolution.function_call, exec_id)
                return exec_id

        logger.warning("Handoff requested unknown specialist '%s'.", candidate)
        return None

    def _append_tool_acknowledgement(
        self,
        conversation: list[ChatMessage],
        function_call: FunctionCallContent,
        resolved_id: str,
    ) -> None:
        """Append a synthetic tool result acknowledging the resolved specialist id."""
        call_id = getattr(function_call, "call_id", None)
        if not call_id:
            return

        result_payload: Any = {"handoff_to": resolved_id}
        result_content = FunctionResultContent(call_id=call_id, result=result_payload)
        tool_message = ChatMessage(
            role=Role.TOOL,
            contents=[result_content],
            author_name=function_call.name,
        )
        # Add tool acknowledgement to both the conversation being sent and the full history
        conversation.extend((tool_message,))
        self._append_messages((tool_message,))

    def _conversation_from_response(self, response: AgentExecutorResponse) -> list[ChatMessage]:
        """Return the authoritative conversation snapshot from an executor response."""
        conversation = response.full_conversation
        if conversation is None:
            raise RuntimeError(
                "AgentExecutorResponse.full_conversation missing; AgentExecutor must populate it in handoff workflows."
            )
        return list(conversation)

    async def _persist_state(self, ctx: WorkflowContext[Any, Any]) -> None:
        """Store authoritative conversation snapshot without losing rich metadata."""
        state_payload = self.snapshot_state()
        await ctx.set_executor_state(state_payload)

    def _snapshot_pattern_metadata(self) -> dict[str, Any]:
        """Serialize pattern-specific state.

        Includes the current agent for return-to-previous routing.

        Returns:
            Dict containing current agent if return-to-previous is enabled
        """
        if self._return_to_previous:
            return {
                "current_agent_id": self._current_agent_id,
            }
        return {}

    def _restore_pattern_metadata(self, metadata: dict[str, Any]) -> None:
        """Restore pattern-specific state.

        Restores the current agent for return-to-previous routing.

        Args:
            metadata: Pattern-specific state dict
        """
        if self._return_to_previous and "current_agent_id" in metadata:
            self._current_agent_id = metadata["current_agent_id"]

    def _restore_conversation_from_state(self, state: Mapping[str, Any]) -> list[ChatMessage]:
        """Rehydrate the coordinator's conversation history from checkpointed state.

        DEPRECATED: Use restore_state() instead. Kept for backward compatibility.
        """
        from ._orchestration_state import OrchestrationState

        orch_state_dict = {"conversation": state.get("full_conversation", state.get("conversation", []))}
        temp_state = OrchestrationState.from_dict(orch_state_dict)
        return list(temp_state.conversation)

    def _apply_response_metadata(self, conversation: list[ChatMessage], agent_response: AgentRunResponse) -> None:
        """Merge top-level response metadata into the latest assistant message."""
        if not agent_response.additional_properties:
            return

        # Find the most recent assistant message contributed by this response
        for message in reversed(conversation):
            if message.role == Role.ASSISTANT:
                metadata = agent_response.additional_properties or {}
                if not metadata:
                    return
                # Merge metadata without mutating shared dict from agent response
                merged = dict(message.additional_properties or {})
                for key, value in metadata.items():
                    merged.setdefault(key, value)
                message.additional_properties = merged
                break


class _UserInputGateway(Executor):
    """Bridges conversation context with the request & response cycle and re-enters the loop."""

    def __init__(
        self,
        *,
        starting_agent_id: str,
        prompt: str | None,
        id: str,
    ) -> None:
        """Initialise the gateway that requests user input and forwards responses."""
        super().__init__(id)
        self._starting_agent_id = starting_agent_id
        self._prompt = prompt or "Provide your next input for the conversation."

    @handler
    async def request_input(self, message: _ConversationForUserInput, ctx: WorkflowContext) -> None:
        """Emit a `HandoffUserInputRequest` capturing the conversation snapshot."""
        if not message.conversation:
            raise ValueError("Handoff workflow requires non-empty conversation before requesting user input.")
        request = HandoffUserInputRequest(
            conversation=list(message.conversation),
            awaiting_agent_id=message.next_agent_id,
            prompt=self._prompt,
            source_executor_id=self.id,
        )
        await ctx.request_info(request, object)

    @handler
    async def request_input_legacy(self, conversation: list[ChatMessage], ctx: WorkflowContext) -> None:
        """Legacy handler for backward compatibility - emit user input request with starting agent."""
        if not conversation:
            raise ValueError("Handoff workflow requires non-empty conversation before requesting user input.")
        request = HandoffUserInputRequest(
            conversation=list(conversation),
            awaiting_agent_id=self._starting_agent_id,
            prompt=self._prompt,
            source_executor_id=self.id,
        )
        await ctx.request_info(request, object)

    @response_handler
    async def resume_from_user(
        self,
        original_request: HandoffUserInputRequest,
        response: object,
        ctx: WorkflowContext[_ConversationWithUserInput],
    ) -> None:
        """Convert user input responses back into chat messages and resume the workflow."""
        # Reconstruct full conversation with new user input
        conversation = list(original_request.conversation)
        user_messages = _as_user_messages(response)
        conversation.extend(user_messages)

        # Send full conversation back to coordinator (not trimmed)
        # Coordinator will update its authoritative history and trim for agent
        message = _ConversationWithUserInput(full_conversation=conversation)
        await ctx.send_message(message, target_id="handoff-coordinator")


def _as_user_messages(payload: Any) -> list[ChatMessage]:
    """Normalise arbitrary payloads into user-authored chat messages."""
    if isinstance(payload, ChatMessage):
        if payload.role == Role.USER:
            return [payload]
        return [ChatMessage(Role.USER, text=payload.text)]
    if isinstance(payload, list):
        # Check if all items are ChatMessage instances
        all_chat_messages = all(isinstance(msg, ChatMessage) for msg in payload)  # type: ignore[arg-type]
        if all_chat_messages:
            messages: list[ChatMessage] = payload  # type: ignore[assignment]
            return [msg if msg.role == Role.USER else ChatMessage(Role.USER, text=msg.text) for msg in messages]
    if isinstance(payload, Mapping):  # User supplied structured data
        text = payload.get("text") or payload.get("content")  # type: ignore[union-attr]
        if isinstance(text, str) and text.strip():
            return [ChatMessage(Role.USER, text=text.strip())]
    return [ChatMessage(Role.USER, text=str(payload))]  # type: ignore[arg-type]


def _default_termination_condition(conversation: list[ChatMessage]) -> bool:
    """Default termination: stop after 10 user messages."""
    user_message_count = sum(1 for msg in conversation if msg.role == Role.USER)
    return user_message_count >= 10


class HandoffBuilder:
    r"""Fluent builder for conversational handoff workflows with coordinator and specialist agents.

    The handoff pattern enables a coordinator agent to route requests to specialist agents.
    A termination condition determines when the workflow should stop requesting input and complete.

    Routing Patterns:

    **Single-Tier (Default):** Only the coordinator can hand off to specialists. After any specialist
    responds, control returns to the user for more input. This creates a cyclical flow:
    user -> coordinator -> [optional specialist] -> user -> coordinator -> ...

    **Multi-Tier (Advanced):** Specialists can hand off to other specialists using `.add_handoff()`.
    This provides more flexibility for complex workflows but is less controllable than the single-tier
    pattern. Users lose real-time visibility into intermediate steps during specialist-to-specialist
    handoffs (though the full conversation history including all handoffs is preserved and can be
    inspected afterward).


    Key Features:
    - **Automatic handoff detection**: The coordinator invokes a handoff tool whose
      arguments (for example ``{"handoff_to": "shipping_agent"}``) identify the specialist to receive control.
    - **Auto-generated tools**: By default the builder synthesizes `handoff_to_<agent>` tools for the coordinator,
      so you don't manually define placeholder functions.
    - **Full conversation history**: The entire conversation (including any
      `ChatMessage.additional_properties`) is preserved and passed to each agent.
    - **Termination control**: By default, terminates after 10 user messages. Override with
      `.with_termination_condition(lambda conv: ...)` for custom logic (e.g., detect "goodbye").
    - **Checkpointing**: Optional persistence for resumable workflows.

    Usage (Single-Tier):

    .. code-block:: python

        from agent_framework import HandoffBuilder
        from agent_framework.openai import OpenAIChatClient

        chat_client = OpenAIChatClient()

        # Create coordinator and specialist agents
        coordinator = chat_client.create_agent(
            instructions=(
                "You are a frontline support agent. Assess the user's issue and decide "
                "whether to hand off to 'refund_agent' or 'shipping_agent'. When delegation is "
                "required, call the matching handoff tool (for example `handoff_to_refund_agent`)."
            ),
            name="coordinator_agent",
        )

        refund = chat_client.create_agent(
            instructions="You handle refund requests. Ask for order details and process refunds.",
            name="refund_agent",
        )

        shipping = chat_client.create_agent(
            instructions="You resolve shipping issues. Track packages and update delivery status.",
            name="shipping_agent",
        )

        # Build the handoff workflow - default single-tier routing
        workflow = (
            HandoffBuilder(
                name="customer_support",
                participants=[coordinator, refund, shipping],
            )
            .set_coordinator("coordinator_agent")
            .build()
        )

        # Run the workflow
        events = await workflow.run_stream("My package hasn't arrived yet")
        async for event in events:
            if isinstance(event, RequestInfoEvent):
                # Request user input
                user_response = input("You: ")
                await workflow.send_response(event.data.request_id, user_response)

    **Multi-Tier Routing with .add_handoff():**

    .. code-block:: python

        # Enable specialist-to-specialist handoffs with fluent API
        workflow = (
            HandoffBuilder(participants=[coordinator, replacement, delivery, billing])
            .set_coordinator("coordinator_agent")
            .add_handoff(coordinator, [replacement, delivery, billing])  # Coordinator routes to all
            .add_handoff(replacement, [delivery, billing])  # Replacement delegates to delivery/billing
            .add_handoff(delivery, billing)  # Delivery escalates to billing
            .build()
        )

        # Flow: User → Coordinator → Replacement → Delivery → Back to User
        # (Replacement hands off to Delivery without returning to user)

    **Custom Termination Condition:**

    .. code-block:: python

        # Terminate when user says goodbye or after 5 exchanges
        workflow = (
            HandoffBuilder(participants=[coordinator, refund, shipping])
            .set_coordinator("coordinator_agent")
            .with_termination_condition(
                lambda conv: sum(1 for msg in conv if msg.role.value == "user") >= 5
                or any("goodbye" in msg.text.lower() for msg in conv[-2:])
            )
            .build()
        )

    **Checkpointing:**

    .. code-block:: python

        from agent_framework import InMemoryCheckpointStorage

        storage = InMemoryCheckpointStorage()
        workflow = (
            HandoffBuilder(participants=[coordinator, refund, shipping])
            .set_coordinator("coordinator_agent")
            .with_checkpointing(storage)
            .build()
        )

    Args:
        name: Optional workflow name for identification and logging.
        participants: List of agents (AgentProtocol) or executors to participate in the handoff.
                     The first agent you specify as coordinator becomes the orchestrating agent.
        description: Optional human-readable description of the workflow.

    Raises:
        ValueError: If participants list is empty, contains duplicates, or coordinator not specified.
        TypeError: If participants are not AgentProtocol or Executor instances.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        participants: Sequence[AgentProtocol | Executor] | None = None,
        description: str | None = None,
    ) -> None:
        r"""Initialize a HandoffBuilder for creating conversational handoff workflows.

        The builder starts in an unconfigured state and requires you to call:
        1. `.participants([...])` - Register agents
        2. `.set_coordinator(...)` - Designate which agent receives initial user input
        3. `.build()` - Construct the final Workflow

        Optional configuration methods allow you to customize context management,
        termination logic, and persistence.

        Args:
            name: Optional workflow identifier used in logging and debugging.
                 If not provided, a default name will be generated.
            participants: Optional list of agents (AgentProtocol) or executors that will
                         participate in the handoff workflow. You can also call
                         `.participants([...])` later. Each participant must have a
                         unique identifier (name for agents, id for executors).
            description: Optional human-readable description explaining the workflow's
                        purpose. Useful for documentation and observability.

        Note:
            Participants must have stable names/ids because the workflow maps the
            handoff tool arguments to these identifiers. Agent names should match
            the strings emitted by the coordinator's handoff tool (e.g., a tool that
            outputs ``{\"handoff_to\": \"billing\"}`` requires an agent named ``billing``).
        """
        self._name = name
        self._description = description
        self._executors: dict[str, Executor] = {}
        self._aliases: dict[str, str] = {}
        self._starting_agent_id: str | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._request_prompt: str | None = None
        # Termination condition
        self._termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] = (
            _default_termination_condition
        )
        self._auto_register_handoff_tools: bool = True
        self._handoff_config: dict[str, list[str]] = {}  # Maps agent_id -> [target_agent_ids]
        self._return_to_previous: bool = False

        if participants:
            self.participants(participants)

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "HandoffBuilder":
        """Register the agents or executors that will participate in the handoff workflow.

        Each participant must have a unique identifier (name for agents, id for executors).
        The workflow will automatically create an alias map so agents can be referenced by
        their name, display_name, or executor id when routing.

        Args:
            participants: Sequence of AgentProtocol or Executor instances. Each must have
                         a unique identifier. For agents, the name attribute is used as the
                         primary identifier and must match handoff target strings.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participants is empty or contains duplicates.
            TypeError: If participants are not AgentProtocol or Executor instances.

        Example:

        .. code-block:: python

            from agent_framework import HandoffBuilder
            from agent_framework.openai import OpenAIChatClient

            client = OpenAIChatClient()
            coordinator = client.create_agent(instructions="...", name="coordinator")
            refund = client.create_agent(instructions="...", name="refund_agent")
            billing = client.create_agent(instructions="...", name="billing_agent")

            builder = HandoffBuilder().participants([coordinator, refund, billing])
            # Now you can call .set_coordinator() to designate the entry point

        Note:
            This method resets any previously configured coordinator, so you must call
            `.set_coordinator(...)` again after changing participants.
        """
        if not participants:
            raise ValueError("participants cannot be empty")

        named: dict[str, AgentProtocol | Executor] = {}
        for participant in participants:
            identifier: str
            if isinstance(participant, Executor):
                identifier = participant.id
            elif isinstance(participant, AgentProtocol):
                name_attr = getattr(participant, "name", None)
                if not name_attr:
                    raise ValueError(
                        "Agents used in handoff workflows must have a stable name "
                        "so they can be addressed during routing."
                    )
                identifier = str(name_attr)
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )
            if identifier in named:
                raise ValueError(f"Duplicate participant name '{identifier}' detected")
            named[identifier] = participant

        metadata = prepare_participant_metadata(
            named,
            description_factory=lambda name, participant: getattr(participant, "description", None) or name,
        )

        wrapped = metadata["executors"]
        seen_ids: set[str] = set()
        for executor in wrapped.values():
            if executor.id in seen_ids:
                raise ValueError(f"Duplicate participant with id '{executor.id}' detected")
            seen_ids.add(executor.id)

        self._executors = {executor.id: executor for executor in wrapped.values()}
        self._aliases = metadata["aliases"]
        self._starting_agent_id = None
        return self

    def set_coordinator(self, agent: str | AgentProtocol | Executor) -> "HandoffBuilder":
        r"""Designate which agent receives initial user input and orchestrates specialist routing.

        The coordinator agent is responsible for analyzing user requests and deciding whether to:
        1. Handle the request directly and respond to the user, OR
        2. Hand off to a specialist agent by including handoff metadata in the response

        After a specialist responds, the workflow automatically returns control to the user,
        creating a cyclical flow: user -> coordinator -> [specialist] -> user -> ...

        Args:
            agent: The agent to use as the coordinator. Can be:
                  - Agent name (str): e.g., "coordinator_agent"
                  - AgentProtocol instance: The actual agent object
                  - Executor instance: A custom executor wrapping an agent

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participants(...) hasn't been called yet, or if the specified
                       agent is not in the participants list.

        Example:

        .. code-block:: python

            # Use agent name
            builder = HandoffBuilder().participants([coordinator, refund, billing]).set_coordinator("coordinator")

            # Or pass the agent object directly
            builder = HandoffBuilder().participants([coordinator, refund, billing]).set_coordinator(coordinator)

        Note:
            The coordinator determines routing by invoking a handoff tool call whose
            arguments identify the target specialist (for example ``{\"handoff_to\": \"billing\"}``).
            Decorate the tool with ``approval_mode="always_require"`` to ensure the workflow
            intercepts the call before execution and can make the transition.
        """
        if not self._executors:
            raise ValueError("Call participants(...) before coordinator(...)")
        resolved = self._resolve_to_id(agent)
        if resolved not in self._executors:
            raise ValueError(f"coordinator '{resolved}' is not part of the participants list")
        self._starting_agent_id = resolved
        return self

    def add_handoff(
        self,
        source: str | AgentProtocol | Executor,
        targets: str | AgentProtocol | Executor | Sequence[str | AgentProtocol | Executor],
        *,
        tool_name: str | None = None,
        tool_description: str | None = None,
    ) -> "HandoffBuilder":
        """Add handoff routing from a source agent to one or more target agents.

        This method enables specialist-to-specialist handoffs by configuring which agents
        can hand off to which others. Call this method multiple times to build a complete
        routing graph. By default, only the starting agent can hand off to all other participants;
        use this method to enable additional routing paths.

        Args:
            source: The agent that can initiate the handoff. Can be:
                   - Agent name (str): e.g., "triage_agent"
                   - AgentProtocol instance: The actual agent object
                   - Executor instance: A custom executor wrapping an agent
            targets: One or more target agents that the source can hand off to. Can be:
                    - Single agent: "billing_agent" or agent_instance
                    - Multiple agents: ["billing_agent", "support_agent"] or [agent1, agent2]
            tool_name: Optional custom name for the handoff tool. If not provided, generates
                      "handoff_to_<target>" for single targets or "handoff_to_<target>_agent"
                      for multiple targets based on target names.
            tool_description: Optional custom description for the handoff tool. If not provided,
                             generates "Handoff to the <target> agent."

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If source or targets are not in the participants list, or if
                       participants(...) hasn't been called yet.

        Examples:
            Single target:

            .. code-block:: python

                builder.add_handoff("triage_agent", "billing_agent")

            Multiple targets (using agent names):

            .. code-block:: python

                builder.add_handoff("triage_agent", ["billing_agent", "support_agent", "escalation_agent"])

            Multiple targets (using agent instances):

            .. code-block:: python

                builder.add_handoff(triage, [billing, support, escalation])

            Chain multiple configurations:

            .. code-block:: python

                workflow = (
                    HandoffBuilder(participants=[triage, replacement, delivery, billing])
                    .set_coordinator(triage)
                    .add_handoff(triage, [replacement, delivery, billing])
                    .add_handoff(replacement, [delivery, billing])
                    .add_handoff(delivery, billing)
                    .build()
                )

            Custom tool names and descriptions:

            .. code-block:: python

                builder.add_handoff(
                    "support_agent",
                    "escalation_agent",
                    tool_name="escalate_to_l2",
                    tool_description="Escalate this issue to Level 2 support",
                )

        Note:
            - Handoff tools are automatically registered for each source agent
            - If a source agent is configured multiple times via add_handoff, targets are merged
        """
        if not self._executors:
            raise ValueError("Call participants(...) before add_handoff(...)")

        # Resolve source agent ID
        source_id = self._resolve_to_id(source)
        if source_id not in self._executors:
            raise ValueError(f"Source agent '{source}' is not in the participants list")

        # Normalize targets to list
        target_list = [targets] if isinstance(targets, (str, AgentProtocol, Executor)) else list(targets)

        # Resolve all target IDs
        target_ids: list[str] = []
        for target in target_list:
            target_id = self._resolve_to_id(target)
            if target_id not in self._executors:
                raise ValueError(f"Target agent '{target}' is not in the participants list")
            target_ids.append(target_id)

        # Merge with existing handoff configuration for this source
        if source_id in self._handoff_config:
            # Add new targets to existing list, avoiding duplicates
            existing = self._handoff_config[source_id]
            for target_id in target_ids:
                if target_id not in existing:
                    existing.append(target_id)
        else:
            self._handoff_config[source_id] = target_ids

        return self

    def auto_register_handoff_tools(self, enabled: bool) -> "HandoffBuilder":
        """Configure whether the builder should synthesize handoff tools for the starting agent."""
        self._auto_register_handoff_tools = enabled
        return self

    def _apply_auto_tools(self, agent: ChatAgent, specialists: Mapping[str, Executor]) -> dict[str, str]:
        """Attach synthetic handoff tools to a chat agent and return the target lookup table."""
        chat_options = agent.chat_options
        existing_tools = list(chat_options.tools or [])
        existing_names = {getattr(tool, "name", "") for tool in existing_tools if hasattr(tool, "name")}

        tool_targets: dict[str, str] = {}
        new_tools: list[Any] = []
        for exec_id in specialists:
            alias = exec_id
            sanitized = sanitize_identifier(alias)
            tool = _create_handoff_tool(alias)
            if tool.name not in existing_names:
                new_tools.append(tool)
            tool_targets[tool.name.lower()] = exec_id
            tool_targets[sanitized] = exec_id
            tool_targets[alias.lower()] = exec_id

        if new_tools:
            chat_options.tools = existing_tools + new_tools
        else:
            chat_options.tools = existing_tools

        return tool_targets

    def _resolve_agent_id(self, agent_identifier: str) -> str:
        """Resolve an agent identifier to an executor ID.

        Args:
            agent_identifier: Can be agent name, display name, or executor ID

        Returns:
            The executor ID

        Raises:
            ValueError: If the identifier cannot be resolved
        """
        # Check if it's already an executor ID
        if agent_identifier in self._executors:
            return agent_identifier

        # Check if it's an alias
        if agent_identifier in self._aliases:
            return self._aliases[agent_identifier]

        # Not found
        raise ValueError(f"Agent identifier '{agent_identifier}' not found in participants")

    def _prepare_agent_with_handoffs(
        self,
        executor: AgentExecutor,
        target_agents: Mapping[str, Executor],
    ) -> tuple[AgentExecutor, dict[str, str]]:
        """Prepare an agent by adding handoff tools for the specified target agents.

        Args:
            executor: The agent executor to prepare
            target_agents: Map of executor IDs to target executors this agent can hand off to

        Returns:
            Tuple of (updated executor, tool_targets map)
        """
        agent = getattr(executor, "_agent", None)
        if not isinstance(agent, ChatAgent):
            return executor, {}

        cloned_agent = _clone_chat_agent(agent)
        tool_targets = self._apply_auto_tools(cloned_agent, target_agents)
        if tool_targets:
            middleware = _AutoHandoffMiddleware(tool_targets)
            existing_middleware = list(cloned_agent.middleware or [])
            existing_middleware.append(middleware)
            cloned_agent.middleware = existing_middleware

        new_executor = AgentExecutor(
            cloned_agent,
            agent_thread=getattr(executor, "_agent_thread", None),
            output_response=getattr(executor, "_output_response", False),
            id=executor.id,
        )
        return new_executor, tool_targets

    def request_prompt(self, prompt: str | None) -> "HandoffBuilder":
        """Set a custom prompt message displayed when requesting user input.

        By default, the workflow uses a generic prompt: "Provide your next input for the
        conversation." Use this method to customize the message shown to users when the
        workflow needs their response.

        Args:
            prompt: Custom prompt text to display, or None to use the default prompt.

        Returns:
            Self for method chaining.

        Example:

        .. code-block:: python

            workflow = (
                HandoffBuilder(participants=[triage, refund, billing])
                .set_coordinator("triage")
                .request_prompt("How can we help you today?")
                .build()
            )

            # For more context-aware prompts, you can access the prompt via
            # RequestInfoEvent.data.prompt in your event handling loop

        Note:
            The prompt is static and set once during workflow construction. If you need
            dynamic prompts based on conversation state, you'll need to handle that in
            your application's event processing logic.
        """
        self._request_prompt = prompt
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "HandoffBuilder":
        """Enable workflow state persistence for resumable conversations.

        Checkpointing allows the workflow to save its state at key points, enabling you to:
        - Resume conversations after application restarts
        - Implement long-running support tickets that span multiple sessions
        - Recover from failures without losing conversation context
        - Audit and replay conversation history

        Args:
            checkpoint_storage: Storage backend implementing CheckpointStorage interface.
                               Common implementations: InMemoryCheckpointStorage (testing),
                               database-backed storage (production).

        Returns:
            Self for method chaining.

        Example (In-Memory):

        .. code-block:: python

            from agent_framework import InMemoryCheckpointStorage

            storage = InMemoryCheckpointStorage()
            workflow = (
                HandoffBuilder(participants=[triage, refund, billing])
                .set_coordinator("triage")
                .with_checkpointing(storage)
                .build()
            )

            # Run workflow with a session ID for resumption
            async for event in workflow.run_stream("Help me", session_id="user_123"):
                # Process events...
                pass

            # Later, resume the same conversation
            async for event in workflow.run_stream("I need a refund", session_id="user_123"):
                # Conversation continues from where it left off
                pass

        Use Cases:
            - Customer support systems with persistent ticket history
            - Multi-day conversations that need to survive server restarts
            - Compliance requirements for conversation auditing
            - A/B testing different agent configurations on same conversation

        Note:
            Checkpointing adds overhead for serialization and storage I/O. Use it when
            persistence is required, not for simple stateless request-response patterns.
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_termination_condition(
        self, condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]]
    ) -> "HandoffBuilder":
        """Set a custom termination condition for the handoff workflow.

        The condition can be either synchronous or asynchronous.

        Args:
            condition: Function that receives the full conversation and returns True
                      (or awaitable True) if the workflow should terminate (not request further user input).

        Returns:
            Self for chaining.

        Example:

        .. code-block:: python

            # Synchronous condition
            builder.with_termination_condition(
                lambda conv: len(conv) > 20 or any("goodbye" in msg.text.lower() for msg in conv[-2:])
            )


            # Asynchronous condition
            async def check_termination(conv: list[ChatMessage]) -> bool:
                # Can perform async operations
                return len(conv) > 20


            builder.with_termination_condition(check_termination)
        """
        self._termination_condition = condition
        return self

    def enable_return_to_previous(self, enabled: bool = True) -> "HandoffBuilder":
        """Enable direct return to the current agent after user input, bypassing the coordinator.

        When enabled, after a specialist responds without requesting another handoff, user input
        routes directly back to that same specialist instead of always routing back to the
        coordinator agent for re-evaluation.

        This is useful when a specialist needs multiple turns with the user to gather information
        or resolve an issue, avoiding unnecessary coordinator involvement while maintaining context.

        Flow Comparison:

        **Default (disabled):**
            User -> Coordinator -> Specialist -> User -> Coordinator -> Specialist -> ...

        **With return_to_previous (enabled):**
            User -> Coordinator -> Specialist -> User -> Specialist -> ...

        Args:
            enabled: Whether to enable return-to-previous routing. Default is True.

        Returns:
            Self for method chaining.

        Example:

        .. code-block:: python

            workflow = (
                HandoffBuilder(participants=[triage, technical_support, billing])
                .set_coordinator("triage")
                .add_handoff(triage, [technical_support, billing])
                .enable_return_to_previous()  # Enable direct return routing
                .build()
            )

            # Flow: User asks question
            # -> Triage routes to Technical Support
            # -> Technical Support asks clarifying question
            # -> User provides more info
            # -> Routes back to Technical Support (not Triage)
            # -> Technical Support continues helping

        Multi-tier handoff example:

        .. code-block:: python

            workflow = (
                HandoffBuilder(participants=[triage, specialist_a, specialist_b])
                .set_coordinator("triage")
                .add_handoff(triage, [specialist_a, specialist_b])
                .add_handoff(specialist_a, specialist_b)
                .enable_return_to_previous()
                .build()
            )

            # Flow: User asks question
            # -> Triage routes to Specialist A
            # -> Specialist A hands off to Specialist B
            # -> Specialist B asks clarifying question
            # -> User provides more info
            # -> Routes back to Specialist B (who is currently handling the conversation)

        Note:
            This feature routes to whichever agent most recently responded, whether that's
            the coordinator or a specialist. The conversation continues with that agent until
            they either hand off to another agent or the termination condition is met.
        """
        self._return_to_previous = enabled
        return self

    def build(self) -> Workflow:
        """Construct the final Workflow instance from the configured builder.

        This method validates the configuration and assembles all internal components:
        - Input normalization executor
        - Starting agent executor
        - Handoff coordinator
        - Specialist agent executors
        - User input gateway
        - Request/response handling

        Returns:
            A fully configured Workflow ready to execute via `.run()` or `.run_stream()`.

        Raises:
            ValueError: If participants or coordinator were not configured, or if
                       required configuration is invalid.

        Example (Minimal):

        .. code-block:: python

            workflow = (
                HandoffBuilder(participants=[coordinator, refund, billing]).set_coordinator("coordinator").build()
            )

            # Run the workflow
            async for event in workflow.run_stream("I need help"):
                # Handle events...
                pass

        Example (Full Configuration):

        .. code-block:: python

            from agent_framework import InMemoryCheckpointStorage

            storage = InMemoryCheckpointStorage()
            workflow = (
                HandoffBuilder(
                    name="support_workflow",
                    participants=[coordinator, refund, billing],
                    description="Customer support with specialist routing",
                )
                .set_coordinator("coordinator")
                .with_termination_condition(lambda conv: len(conv) > 20)
                .request_prompt("How can we help?")
                .with_checkpointing(storage)
                .build()
            )

        Note:
            After calling build(), the builder instance should not be reused. Create a
            new builder if you need to construct another workflow with different configuration.
        """
        if not self._executors:
            raise ValueError("No participants provided. Call participants([...]) first.")
        if self._starting_agent_id is None:
            raise ValueError("coordinator must be defined before build().")

        starting_executor = self._executors[self._starting_agent_id]
        specialists = {
            exec_id: executor for exec_id, executor in self._executors.items() if exec_id != self._starting_agent_id
        }

        # Build handoff tool registry for all agents that need them
        handoff_tool_targets: dict[str, str] = {}
        if self._auto_register_handoff_tools:
            # Determine which agents should have handoff tools
            if self._handoff_config:
                # Use explicit handoff configuration from add_handoff() calls
                for source_exec_id, target_exec_ids in self._handoff_config.items():
                    executor = self._executors.get(source_exec_id)
                    if not executor:
                        raise ValueError(f"Handoff source agent '{source_exec_id}' not found in participants")

                    if isinstance(executor, AgentExecutor):
                        # Build targets map for this source agent
                        targets_map: dict[str, Executor] = {}
                        for target_exec_id in target_exec_ids:
                            target_executor = self._executors.get(target_exec_id)
                            if not target_executor:
                                raise ValueError(f"Handoff target agent '{target_exec_id}' not found in participants")
                            targets_map[target_exec_id] = target_executor

                        # Register handoff tools for this agent
                        updated_executor, tool_targets = self._prepare_agent_with_handoffs(executor, targets_map)
                        self._executors[source_exec_id] = updated_executor
                        handoff_tool_targets.update(tool_targets)
            else:
                # Default behavior: only coordinator gets handoff tools to all specialists
                if isinstance(starting_executor, AgentExecutor) and specialists:
                    starting_executor, tool_targets = self._prepare_agent_with_handoffs(starting_executor, specialists)
                    self._executors[self._starting_agent_id] = starting_executor
                    handoff_tool_targets.update(tool_targets)  # Update references after potential agent modifications
        starting_executor = self._executors[self._starting_agent_id]
        specialists = {
            exec_id: executor for exec_id, executor in self._executors.items() if exec_id != self._starting_agent_id
        }

        if not specialists:
            logger.warning("Handoff workflow has no specialist agents; the coordinator will loop with the user.")

        descriptions = {
            exec_id: getattr(executor, "description", None) or exec_id for exec_id, executor in self._executors.items()
        }
        participant_specs = {
            exec_id: GroupChatParticipantSpec(name=exec_id, participant=executor, description=descriptions[exec_id])
            for exec_id, executor in self._executors.items()
        }

        input_node = _InputToConversation(id="input-conversation")
        user_gateway = _UserInputGateway(
            starting_agent_id=starting_executor.id,
            prompt=self._request_prompt,
            id="handoff-user-input",
        )

        specialist_aliases = {alias: exec_id for alias, exec_id in self._aliases.items() if exec_id in specialists}

        def _handoff_orchestrator_factory(_: _GroupChatConfig) -> Executor:
            return _HandoffCoordinator(
                starting_agent_id=starting_executor.id,
                specialist_ids=specialist_aliases,
                input_gateway_id=user_gateway.id,
                termination_condition=self._termination_condition,
                id="handoff-coordinator",
                handoff_tool_targets=handoff_tool_targets,
                return_to_previous=self._return_to_previous,
            )

        wiring = _GroupChatConfig(
            manager=None,
            manager_name=self._starting_agent_id,
            participants=participant_specs,
            max_rounds=None,
            participant_aliases=self._aliases,
            participant_executors=self._executors,
        )

        result = assemble_group_chat_workflow(
            wiring=wiring,
            participant_factory=_default_participant_factory,
            orchestrator_factory=_handoff_orchestrator_factory,
            interceptors=(),
            checkpoint_storage=self._checkpoint_storage,
            builder=WorkflowBuilder(name=self._name, description=self._description),
            return_builder=True,
        )
        if not isinstance(result, tuple):
            raise TypeError("Expected tuple from assemble_group_chat_workflow with return_builder=True")
        builder, coordinator = result

        builder = builder.set_start_executor(input_node)
        builder = builder.add_edge(input_node, starting_executor)
        builder = builder.add_edge(coordinator, user_gateway)
        builder = builder.add_edge(user_gateway, coordinator)

        return builder.build()

    def _resolve_to_id(self, candidate: str | AgentProtocol | Executor) -> str:
        """Resolve a participant reference into a concrete executor identifier."""
        if isinstance(candidate, Executor):
            return candidate.id
        if isinstance(candidate, AgentProtocol):
            name: str | None = getattr(candidate, "name", None)
            if not name:
                raise ValueError("AgentProtocol without a name cannot be resolved to an executor id.")
            return self._aliases.get(name, name)
        if isinstance(candidate, str):
            if candidate in self._aliases:
                return self._aliases[candidate]
            return candidate
        raise TypeError(f"Invalid starting agent reference: {type(candidate).__name__}")
