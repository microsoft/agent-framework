# Copyright (c) Microsoft. All rights reserved.

"""Group chat orchestration primitives.

This module introduces a reusable orchestration surface for manager-directed
multi-agent conversations. The key components are:

- GroupChatRequestMessage / GroupChatResponseMessage: canonical envelopes used
  between the orchestrator and participants.
- GroupChatManagerProtocol: minimal contract for pluggable coordination logic.
- GroupChatOrchestratorExecutor: runtime state machine that delegates to a
  manager to select the next participant or complete the task.
- GroupChatBuilder: high-level builder that wires managers and participants
  into a workflow graph. It mirrors the ergonomics of SequentialBuilder and
  ConcurrentBuilder while allowing Magentic to reuse the same infrastructure.

The default wiring uses AgentExecutor under the hood for agent participants so
existing observability and streaming semantics continue to apply.
"""

import itertools
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from .._agents import AgentProtocol
from .._clients import ChatClientProtocol
from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._checkpoint import CheckpointStorage
from ._executor import Executor, handler
from ._workflow import Workflow, WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


# region Message primitives


@dataclass
class GroupChatRequestMessage:
    """Request envelope sent from the orchestrator to a participant."""

    agent_name: str
    conversation: list[ChatMessage] = field(default_factory=list)  # type: ignore
    instruction: str = ""
    task: ChatMessage | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class GroupChatResponseMessage:
    """Response envelope emitted by participants back to the orchestrator."""

    agent_name: str
    message: ChatMessage
    target_agent: str | None = None
    broadcast: bool = False
    metadata: dict[str, Any] | None = None


@dataclass
class GroupChatTurn:
    """Represents a single turn in the manager-participant conversation."""

    speaker: str
    role: str
    message: ChatMessage


@dataclass
class GroupChatState:
    """Snapshot of the current orchestration state provided to managers."""

    task: ChatMessage
    participants: Mapping[str, str]
    conversation: Sequence[ChatMessage]
    history: Sequence[GroupChatTurn]
    pending_agent: str | None
    round_index: int


@dataclass
class GroupChatDirective:
    """Instruction emitted by a GroupChatManagerProtocol implementation."""

    agent_name: str | None = None
    instruction: str | None = None
    metadata: dict[str, Any] | None = None
    finish: bool = False
    final_message: ChatMessage | None = None


# endregion


# region Manager protocol


@runtime_checkable
class GroupChatManagerProtocol(Protocol):
    """Interface for orchestration managers that drive group chat workflows."""

    @property
    def name(self) -> str: ...

    async def next_action(self, state: GroupChatState) -> GroupChatDirective:
        """Return the next directive based on current conversation state."""
        ...


@dataclass
class GroupChatParticipantSpec:
    """Metadata describing a single participant in the orchestration.

    Attributes:
        name: Unique identifier for the participant used by the manager for selection
        participant: AgentProtocol or Executor instance representing the participant
        description: Human-readable description provided to the manager for selection context
    """

    name: str
    participant: AgentProtocol | Executor
    description: str


@dataclass
class GroupChatParticipantNodes:
    """Nodes that implement a participant pipeline in the workflow graph.

    Attributes:
        entry: First executor in the participant pipeline that receives orchestrator requests
        exit: Final executor in the participant pipeline that sends responses back
        intermediates: Optional sequence of executors between entry and exit (e.g., AgentExecutor)
    """

    entry: Executor
    exit: Executor
    intermediates: Sequence[Executor] = field(default_factory=tuple)


@dataclass
class GroupChatWiring:
    """Configuration passed to factories during workflow assembly.

    Attributes:
        manager: Manager instance responsible for orchestration decisions (None when custom factory handles it)
        manager_name: Display name for the manager in conversation history
        participants: Mapping of participant names to their specifications
        max_rounds: Optional limit on manager selection rounds to prevent infinite loops
        orchestrator: Orchestrator executor instance (populated during build)
    """

    manager: GroupChatManagerProtocol | None
    manager_name: str
    participants: Mapping[str, GroupChatParticipantSpec]
    max_rounds: int | None = None
    orchestrator: Executor | None = None


# endregion


# region Default participant adapters


class _GroupChatAgentIngress(Executor):
    """Adapter that converts orchestrator requests into agent-compatible execution requests.

    This internal executor sits at the entry point of each agent participant's pipeline,
    translating GroupChatRequestMessage envelopes from the orchestrator into
    AgentExecutorRequest format that AgentExecutor understands.

    Responsibilities:
    - Filter messages by participant name (ignores requests for other participants)
    - Extract conversation history from the request envelope
    - Append manager instructions as a user message when present
    - Forward the formatted request to AgentExecutor

    Pipeline position: orchestrator -> ingress -> AgentExecutor -> egress -> orchestrator

    Why this adapter exists:
    The orchestrator operates on a broadcast model where all participants receive
    GroupChatRequestMessage envelopes, but each ingress filters for its specific
    agent_name. This keeps routing logic simple and makes the graph structure explicit.

    Args:
        agent_name: Unique name of the participant this ingress serves
    """

    def __init__(self, agent_name: str) -> None:
        super().__init__(f"groupchat_ingress:{agent_name}")
        self._agent_name = agent_name

    @handler
    async def handle_request(
        self,
        message: GroupChatRequestMessage,
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Process GroupChatRequestMessage and forward to AgentExecutor if targeted.

        Args:
            message: Request envelope from the orchestrator
            ctx: Workflow context for sending the transformed request

        Behavior:
            - Silently ignores messages not addressed to this participant
            - Clones conversation to avoid shared state mutation
            - Appends manager instruction as USER message if provided
            - Always sets should_respond=True to ensure agent produces output
        """
        if message.agent_name != self._agent_name:
            return
        conversation = list(message.conversation)
        if message.instruction:
            conversation.append(ChatMessage(role=Role.USER, text=message.instruction))
        await ctx.send_message(AgentExecutorRequest(messages=conversation, should_respond=True))


class _GroupChatAgentEgress(Executor):
    """Adapter that converts agent responses into orchestrator-compatible response envelopes.

    This internal executor sits at the exit point of each agent participant's pipeline,
    translating AgentExecutorResponse into GroupChatResponseMessage format that the
    orchestrator expects.

    Responsibilities:
    - Extract the final assistant message from the agent's response
    - Ensure author_name is populated for conversation tracking
    - Wrap the message in a GroupChatResponseMessage envelope
    - Send the envelope back to the orchestrator

    Pipeline position: orchestrator -> ingress -> AgentExecutor -> egress -> orchestrator

    Why this adapter exists:
    AgentExecutorResponse contains rich metadata (full_conversation, streaming events)
    but the orchestrator only needs the final assistant message. The egress adapter
    normalizes this and ensures consistent author attribution for multi-agent tracking.

    Args:
        agent_name: Unique name of the participant this egress serves
    """

    def __init__(self, agent_name: str) -> None:
        super().__init__(f"groupchat_egress:{agent_name}")
        self._agent_name = agent_name

    @handler
    async def handle_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[GroupChatResponseMessage],
    ) -> None:
        """Extract final assistant message and send to orchestrator as response envelope.

        Args:
            response: Response from AgentExecutor containing agent output
            ctx: Workflow context for sending the response envelope

        Behavior:
            - Searches agent_run_response.messages first, then full_conversation
            - Scans backwards to find the most recent ASSISTANT role message
            - Creates empty assistant message if no output found (defensive)
            - Populates author_name if missing to preserve conversation attribution
            - Wraps message in GroupChatResponseMessage for orchestrator routing
        """
        # Prefer the final assistant message from the agent run.
        final_message: ChatMessage | None = None
        candidate_sequences: tuple[Sequence[ChatMessage] | None, ...] = (
            response.agent_run_response.messages,
            response.full_conversation,
        )
        for sequence in candidate_sequences:
            if not sequence:
                continue
            for candidate in reversed(sequence):
                if getattr(candidate, "role", None) == Role.ASSISTANT:
                    final_message = candidate
                    break
            if final_message is not None:
                break

        if final_message is None:
            final_message = ChatMessage(role=Role.ASSISTANT, text="", author_name=self._agent_name)
        elif not final_message.author_name:
            message_dict = final_message.to_dict()
            message_dict["author_name"] = self._agent_name
            final_message = ChatMessage.from_dict(message_dict)

        await ctx.send_message(
            GroupChatResponseMessage(
                agent_name=self._agent_name,
                message=final_message,
            )
        )


def _default_participant_factory(
    spec: GroupChatParticipantSpec,
    _: GroupChatWiring,
) -> GroupChatParticipantNodes:
    """Default factory for constructing participant pipeline nodes in the workflow graph.

    Creates a three-node pipeline for AgentProtocol participants (ingress -> executor -> egress)
    or a single-node passthrough for Executor participants.

    This is the internal implementation used by GroupChatBuilder when no custom factory
    is provided. It wires agents with the standard adapters that handle protocol translation
    between the orchestrator's envelope format and AgentExecutor's request/response format.

    Args:
        spec: Participant specification containing name, instance, and description
        _: GroupChatWiring configuration (unused by default implementation)

    Returns:
        GroupChatParticipantNodes with entry/exit executors and optional intermediates

    Behavior for AgentProtocol participants:
        - Creates _GroupChatAgentIngress to translate orchestrator requests
        - Wraps agent in AgentExecutor for streaming and observability
        - Creates _GroupChatAgentEgress to translate agent responses
        - Returns three-node pipeline: ingress -> executor -> egress

    Behavior for Executor participants:
        - Assumes executor handles GroupChatRequestMessage directly
        - Returns executor as both entry and exit (single node, no adapters)
        - Expects executor to emit GroupChatResponseMessage

    Pipeline topology (agent case):
        orchestrator --GroupChatRequestMessage--> ingress
        ingress --AgentExecutorRequest--> agent_executor
        agent_executor --AgentExecutorResponse--> egress
        egress --GroupChatResponseMessage--> orchestrator
    """
    participant = spec.participant
    if isinstance(participant, Executor):
        return GroupChatParticipantNodes(entry=participant, exit=participant)

    agent = participant
    ingress = _GroupChatAgentIngress(spec.name)
    agent_executor = AgentExecutor(agent, id=f"groupchat_agent:{spec.name}")
    egress = _GroupChatAgentEgress(spec.name)
    return GroupChatParticipantNodes(entry=ingress, exit=egress, intermediates=[agent_executor])


# endregion


# region Default orchestrator


class GroupChatOrchestratorExecutor(Executor):
    """Default orchestrator executor that implements manager-directed group chat coordination.

    This is the central runtime state machine that drives multi-agent conversations. It
    maintains conversation state, delegates speaker selection to a manager, routes messages
    to participants, and collects responses in a loop until the manager signals completion.

    Core responsibilities:
    - Accept initial input as str, ChatMessage, or list[ChatMessage]
    - Maintain conversation history and turn tracking
    - Query manager for next action (select participant or finish)
    - Route requests to selected participants via GroupChatRequestMessage
    - Collect participant responses and append to conversation
    - Enforce optional round limits to prevent infinite loops
    - Yield final completion message and transition to idle state

    State management:
    - _conversation: Growing list of all messages (user, manager, agents)
    - _history: Turn-by-turn record with speaker attribution and roles
    - _task_message: Original user task extracted from input
    - _pending_agent: Name of agent currently processing a request
    - _round_index: Count of manager selection rounds for limit enforcement

    Manager interaction:
    The orchestrator builds GroupChatState snapshots and passes them to the manager's
    next_action() method. The manager returns a GroupChatDirective indicating either:
    - Next participant to speak (with optional instruction)
    - Finish signal (with optional final message)

    Message flow topology:
        User input -> orchestrator -> manager -> orchestrator -> participant -> orchestrator
        (loops until manager returns finish directive)

    Why this design:
    - Separates orchestration logic (this class) from selection logic (manager)
    - Manager is stateless and testable in isolation
    - Orchestrator handles all state mutations and message routing
    - Broadcast routing to participants keeps graph structure simple

    Args:
        manager: Manager instance implementing next_action() for speaker selection
        participants: Mapping of participant names to descriptions (for manager context)
        manager_name: Display name for manager in conversation history
        max_rounds: Optional limit on manager selection rounds (None = unlimited)
        executor_id: Optional custom ID for observability (auto-generated if not provided)
    """

    def __init__(
        self,
        manager: GroupChatManagerProtocol,
        *,
        participants: Mapping[str, str],
        manager_name: str,
        max_rounds: int | None = None,
        executor_id: str | None = None,
    ) -> None:
        super().__init__(executor_id or f"groupchat_orchestrator_{uuid4().hex[:8]}")
        self._manager = manager
        self._participants = dict(participants)
        self._manager_name = manager_name
        self._conversation: list[ChatMessage] = []
        self._history: list[GroupChatTurn] = []
        self._task_message: ChatMessage | None = None
        self._pending_agent: str | None = None
        self._round_index = 0
        self._max_rounds = max_rounds
        self._pending_initial_conversation: list[ChatMessage] | None = None

    @staticmethod
    def _select_task_message(conversation: Sequence[ChatMessage]) -> ChatMessage:
        """Extract the primary user task message from a conversation history.

        Scans backwards through the conversation to find the most recent USER role message,
        which is treated as the main task description. Falls back to the last message if
        no user message is found.

        Args:
            conversation: Sequence of chat messages (may include system, user, assistant)

        Returns:
            The task message to provide to the manager for context

        Usage:
            Called when workflow receives a list[ChatMessage] as initial input to identify
            which message represents the user's task request.
        """
        for msg in reversed(conversation):
            role_value = getattr(msg.role, "value", None) or str(msg.role)
            if str(role_value).lower() == Role.USER.value:
                return msg
        return conversation[-1]

    @staticmethod
    def _role_value(message: ChatMessage) -> str:
        """Extract string role value from a ChatMessage, handling enum and string cases.

        Args:
            message: Chat message with role attribute (may be enum or string)

        Returns:
            String representation of the role (e.g., "user", "assistant", "system")

        Why this exists:
            Different ChatMessage implementations may use Role enum or plain strings.
            This normalizes access for consistent turn tracking.
        """
        role = getattr(message.role, "value", None) or str(message.role)
        return str(role)

    def _build_state(self) -> GroupChatState:
        """Build a snapshot of current orchestration state for the manager.

        Packages conversation history, participant metadata, and round tracking into
        a GroupChatState that the manager uses to make speaker selection decisions.

        Returns:
            GroupChatState containing all context needed for manager decision-making

        Raises:
            RuntimeError: If called before task message initialization (defensive check)

        When this is called:
            - After initial input is processed (first manager query)
            - After each participant response (subsequent manager queries)
        """
        if self._task_message is None:
            raise RuntimeError("GroupChatOrchestratorExecutor state not initialized with task message.")
        return GroupChatState(
            task=self._task_message,
            participants=self._participants,
            conversation=tuple(self._conversation),
            history=tuple(self._history),
            pending_agent=self._pending_agent,
            round_index=self._round_index,
        )

    async def _apply_directive(
        self,
        directive: GroupChatDirective,
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Execute a manager directive by either finishing the workflow or routing to a participant.

        This is the core routing logic that interprets manager decisions. It handles two cases:
        1. Finish directive: append final message, update state, yield output, become idle
        2. Agent selection: build request envelope, route to participant, increment round counter

        Args:
            directive: Manager's decision (finish or select next participant)
            ctx: Workflow context for sending messages and yielding output

        Behavior for finish directive:
            - Uses provided final_message or creates default completion message
            - Ensures author_name is set to manager for attribution
            - Appends to conversation and history for complete record
            - Yields message as workflow output
            - Orchestrator becomes idle (no further processing)

        Behavior for agent selection:
            - Validates agent_name exists in participants
            - Optionally appends manager instruction as USER message
            - Builds GroupChatRequestMessage with full conversation context
            - Sends request to workflow (participant ingress filters for agent_name)
            - Increments round counter and enforces max_rounds if configured

        Round limit enforcement:
            If max_rounds is reached, recursively calls _apply_directive with a finish
            directive to gracefully terminate the conversation.

        Raises:
            ValueError: If directive lacks agent_name when finish=False, or if
                       agent_name doesn't match any participant
        """
        if directive.finish:
            final_message = directive.final_message
            if final_message is None:
                final_message = ChatMessage(
                    role=Role.ASSISTANT,
                    text="Completed without final summary.",
                    author_name=self._manager_name,
                )
            elif not final_message.author_name:
                message_dict = final_message.to_dict()
                message_dict["author_name"] = self._manager_name
                final_message = ChatMessage.from_dict(message_dict)

            self._conversation.append(final_message)
            self._history.append(GroupChatTurn(self._manager_name, "manager", final_message))
            self._pending_agent = None
            await ctx.yield_output(final_message)
            return

        agent_name = directive.agent_name
        if not agent_name:
            raise ValueError("Directive must include agent_name when finish is False.")
        if agent_name not in self._participants:
            raise ValueError(f"Manager selected unknown participant '{agent_name}'.")

        instruction = directive.instruction or ""
        conversation = list(self._conversation)
        if instruction:
            manager_message = ChatMessage(
                role=Role.USER,
                text=instruction,
                author_name=self._manager_name,
            )
            conversation.append(manager_message)
            self._conversation.append(manager_message)
            self._history.append(GroupChatTurn(self._manager_name, "manager", manager_message))

        request = GroupChatRequestMessage(
            agent_name=agent_name,
            conversation=conversation,
            task=self._task_message,
            metadata=dict(directive.metadata or {}),
        )
        self._pending_agent = agent_name
        self._round_index += 1
        await ctx.send_message(request)

        if self._max_rounds is not None and self._round_index >= self._max_rounds:
            logger.warning(
                "GroupChatOrchestratorExecutor reached max_rounds=%s; forcing completion.",
                self._max_rounds,
            )
            await self._apply_directive(
                GroupChatDirective(
                    finish=True,
                    final_message=ChatMessage(
                        role=Role.ASSISTANT,
                        text="Conversation halted after reaching manager round limit.",
                        author_name=self._manager_name,
                    ),
                ),
                ctx,
            )

    async def _handle_task_message(
        self,
        task_message: ChatMessage,
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Initialize orchestrator state and start the manager-directed conversation loop.

        This internal method is called by all public handlers (str, ChatMessage, list[ChatMessage])
        after normalizing their input. It initializes conversation state, queries the manager
        for the first action, and applies the resulting directive.

        Args:
            task_message: The primary user task message (extracted or provided directly)
            ctx: Workflow context for sending messages and yielding output

        Behavior:
            - Sets task_message for manager context
            - Initializes conversation from pending_initial_conversation if present
            - Otherwise starts fresh with just the task message
            - Builds turn history with speaker attribution
            - Resets pending_agent and round_index
            - Queries manager for first action
            - Applies directive to start the conversation loop

        State initialization:
            - _conversation: Full message list for context
            - _history: Turn-by-turn record with speaker names and roles
            - _pending_agent: None (no active request)
            - _round_index: 0 (first manager query)

        Why pending_initial_conversation exists:
            The handle_conversation handler receives a list[ChatMessage] and needs to
            extract the task message before calling this method. The full list is stashed
            in _pending_initial_conversation to preserve all context when initializing state.
        """
        self._task_message = task_message
        if self._pending_initial_conversation:
            initial_conversation = list(self._pending_initial_conversation)
            self._pending_initial_conversation = None
            self._conversation = initial_conversation
            self._history = [
                GroupChatTurn(
                    msg.author_name or self._role_value(msg),
                    self._role_value(msg),
                    msg,
                )
                for msg in initial_conversation
            ]
        else:
            self._conversation = [task_message]
            self._history = [GroupChatTurn("user", "user", task_message)]
        self._pending_agent = None
        self._round_index = 0
        directive = await self._manager.next_action(self._build_state())
        await self._apply_directive(directive, ctx)

    @handler
    async def handle_str(
        self,
        task: str,
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Handler for string input as workflow entry point.

        Wraps the string in a USER role ChatMessage and delegates to _handle_task_message.

        Args:
            task: Plain text task description from user
            ctx: Workflow context

        Usage:
            workflow.run("Write a blog post about AI agents")
        """
        await self._handle_task_message(ChatMessage(role=Role.USER, text=task), ctx)

    @handler
    async def handle_chat_message(
        self,
        task_message: ChatMessage,
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Handler for ChatMessage input as workflow entry point.

        Directly delegates to _handle_task_message for state initialization.

        Args:
            task_message: Structured chat message from user (may include metadata, role, etc.)
            ctx: Workflow context

        Usage:
            workflow.run(ChatMessage(role=Role.USER, text="Analyze this data"))
        """
        await self._handle_task_message(task_message, ctx)

    @handler
    async def handle_conversation(
        self,
        conversation: list[ChatMessage],
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Handler for conversation history as workflow entry point.

        Accepts a pre-existing conversation and extracts the primary task message.
        Preserves the full conversation for state initialization.

        Args:
            conversation: List of chat messages (system, user, assistant)
            ctx: Workflow context

        Raises:
            ValueError: If conversation list is empty

        Behavior:
            - Validates conversation is non-empty
            - Clones conversation to avoid mutation
            - Extracts task message (most recent USER message)
            - Stashes full conversation in _pending_initial_conversation
            - Delegates to _handle_task_message for initialization

        Usage:
            existing_messages = [
                ChatMessage(role=Role.SYSTEM, text="You are an expert"),
                ChatMessage(role=Role.USER, text="Help me with this task")
            ]
            workflow.run(existing_messages)
        """
        if not conversation:
            raise ValueError("GroupChat workflow requires at least one chat message.")
        self._pending_initial_conversation = list(conversation)
        task_message = self._select_task_message(conversation)
        await self._handle_task_message(task_message, ctx)

    @handler
    async def handle_agent_response(
        self,
        response: GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatRequestMessage, ChatMessage],
    ) -> None:
        """Handler for participant responses returning to the orchestrator.

        This is the completion point of the participant->orchestrator loop. After a
        participant processes a request and returns a response, this handler updates
        orchestrator state and queries the manager for the next action.

        Args:
            response: Response envelope from participant egress
            ctx: Workflow context

        Behavior:
            - Validates agent_name matches a known participant (defensive)
            - Ensures message has author_name for conversation attribution
            - Appends message to conversation history
            - Records turn in history with agent name and role
            - Clears pending_agent (request fulfilled)
            - Checks if max_rounds reached (yields completion if so)
            - Queries manager for next action
            - Applies directive to continue or finish

        Round limit handling:
            If max_rounds is reached after receiving a response, yields a default
            completion message instead of querying the manager. This prevents the
            manager from selecting another participant when the limit is exhausted.

        Defensive behavior:
            Silently ignores responses from unknown participants (shouldn't happen
            in normal operation, but protects against graph misconfiguration).
        """
        agent_name = response.agent_name
        if agent_name not in self._participants:
            logger.debug("Ignoring response from unknown participant '%s'.", agent_name)
            return

        message = response.message
        if not message.author_name:
            message_dict = message.to_dict()
            message_dict["author_name"] = agent_name
            message = ChatMessage.from_dict(message_dict)

        self._conversation.append(message)
        self._history.append(GroupChatTurn(agent_name, "agent", message))
        self._pending_agent = None

        if self._max_rounds is not None and self._round_index >= self._max_rounds:
            logger.warning(
                "GroupChatOrchestratorExecutor reached max_rounds=%s after receiving agent response.",
                self._max_rounds,
            )
            await ctx.yield_output(
                ChatMessage(
                    role=Role.ASSISTANT,
                    text="Conversation halted after reaching manager round limit.",
                    author_name=self._manager_name,
                )
            )
            return

        directive = await self._manager.next_action(self._build_state())
        await self._apply_directive(directive, ctx)


def _default_orchestrator_factory(wiring: GroupChatWiring) -> Executor:
    """Default factory for creating the GroupChatOrchestratorExecutor instance.

    This is the internal implementation used by GroupChatBuilder to instantiate the
    orchestrator. It extracts participant descriptions from the wiring configuration
    and passes them to the orchestrator for manager context.

    Args:
        wiring: Complete workflow configuration assembled by the builder

    Returns:
        Initialized GroupChatOrchestratorExecutor ready to coordinate the conversation

    Behavior:
        - Extracts participant names and descriptions for manager context
        - Forwards manager instance, manager name, and max_rounds settings
        - Allows orchestrator to auto-generate its executor ID

    Why descriptions are extracted:
        The manager needs participant descriptions (not full specs) to make informed
        selection decisions. The orchestrator doesn't need participant instances directly
        since routing is handled by the workflow graph.

    Raises:
        RuntimeError: If manager is None (should not happen when using default factory)
    """
    if wiring.manager is None:
        raise RuntimeError("Default orchestrator factory requires a manager to be set")

    return GroupChatOrchestratorExecutor(
        manager=wiring.manager,
        participants={name: spec.description for name, spec in wiring.participants.items()},
        manager_name=wiring.manager_name,
        max_rounds=wiring.max_rounds,
    )


# endregion


# region Builder


class GroupChatBuilder:
    r"""High-level builder for manager-directed group chat workflows with dynamic orchestration.

    - `set_manager(...)` configures the orchestration manager (required)
    - `participants({...})` accepts a mapping of named AgentProtocol or Executor instances
    - The workflow wires an orchestrator that delegates speaker selection to the manager
    - Agents are automatically wrapped as AgentExecutor for consistent observability
    - The manager receives conversation state and returns directives (next speaker or finish)
    - The final output is the manager's completion message when the task is finished

    Usage:

    .. code-block:: python

        from agent_framework import GroupChatBuilder, StandardGroupChatManager

        manager = StandardGroupChatManager(chat_client)
        workflow = (
            GroupChatBuilder().set_manager(manager).participants(writer=writer_agent, reviewer=reviewer_agent).build()
        )

        # Enable checkpoint persistence
        workflow = (
            GroupChatBuilder()
            .set_manager(manager)
            .participants({"analyst": analyst_agent, "coder": coder_agent})
            .with_checkpointing(storage)
            .build()
        )

        # Limit conversation rounds
        workflow = (
            GroupChatBuilder()
            .set_manager(manager)
            .participants(agent1=agent1, agent2=agent2)
            .with_max_rounds(10)
            .build()
        )
    """

    def __init__(
        self,
        *,
        _orchestrator_factory: Callable[[GroupChatWiring], Executor] | None = None,
        _participant_factory: Callable[[GroupChatParticipantSpec, GroupChatWiring], GroupChatParticipantNodes]
        | None = None,
    ) -> None:
        """Initialize the GroupChatBuilder.

        Args:
            _orchestrator_factory: Internal extension point for custom orchestrator implementations.
                Used by Magentic. Not part of public API - subject to change.
            _participant_factory: Internal extension point for custom participant pipelines.
                Used by Magentic. Not part of public API - subject to change.
        """
        self._participants: dict[str, AgentProtocol | Executor] = {}
        self._participant_descriptions: dict[str, str] = {}
        self._manager: GroupChatManagerProtocol | None = None
        self._manager_name: str = "manager"
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_rounds: int | None = None
        self._request_handler: tuple[Executor, Callable[[Any], bool]] | None = None
        self._orchestrator_factory = _orchestrator_factory or _default_orchestrator_factory
        self._participant_factory = _participant_factory or _default_participant_factory

    def set_manager(self, manager: GroupChatManagerProtocol, *, display_name: str | None = None) -> "GroupChatBuilder":
        """Configure the orchestration manager that selects participants and completes tasks.

        The manager receives conversation state and returns directives indicating which
        participant should speak next or whether the task is complete.

        Args:
            manager: Implementation of GroupChatManagerProtocol for orchestration logic
            display_name: Optional custom name for the manager in conversation history

        Returns:
            Self for fluent chaining

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, StandardGroupChatManager

            manager = StandardGroupChatManager(chat_client, instructions="Custom instructions")
            workflow = GroupChatBuilder().set_manager(manager, display_name="coordinator").build()
        """
        self._manager = manager
        resolved_name = display_name or getattr(manager, "name", None) or "manager"
        self._manager_name = resolved_name
        return self

    def participants(
        self,
        participants: Mapping[str, AgentProtocol | Executor] | None = None,
        /,
        **named_participants: AgentProtocol | Executor,
    ) -> "GroupChatBuilder":
        """Define the named participants for this group chat workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.
        Participant names must be unique and non-empty. The manager uses these names when
        selecting the next speaker.

        Args:
            participants: Optional mapping of participant names to agent/executor instances
            **named_participants: Keyword arguments mapping names to agent/executor instances

        Returns:
            Self for fluent chaining

        Raises:
            ValueError: If participants are empty, names are duplicated, or names are empty strings

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            # Using keyword arguments
            workflow = (
                GroupChatBuilder()
                .set_manager(manager)
                .participants(writer=writer_agent, editor=editor_agent, reviewer=reviewer_agent)
                .build()
            )

            # Using dictionary
            participants_dict = {"analyst": analyst_agent, "coder": coder_agent}
            workflow = GroupChatBuilder().set_manager(manager).participants(participants_dict).build()

            # Combining both approaches
            workflow = (
                GroupChatBuilder()
                .set_manager(manager)
                .participants({"agent1": agent1}, agent2=agent2, agent3=agent3)
                .build()
            )
        """
        combined: dict[str, AgentProtocol | Executor] = {}
        if participants:
            combined.update(participants)
        combined.update(named_participants)

        if not combined:
            raise ValueError("participants cannot be empty")

        for name, participant in combined.items():
            if not name:
                raise ValueError("participant names must be non-empty strings")
            if name in self._participants:
                raise ValueError(f"Duplicate participant name '{name}' supplied.")
            self._participants[name] = participant
            description = ""
            if isinstance(participant, Executor):
                description = participant.id
            else:
                description = getattr(participant, "description", None) or participant.__class__.__name__
            self._participant_descriptions[name] = description
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "GroupChatBuilder":
        """Enable checkpointing for the built workflow using the provided storage.

        Checkpointing allows the workflow to persist state and resume from interruption
        points, enabling long-running conversations and failure recovery.

        Args:
            checkpoint_storage: Storage implementation for persisting workflow state

        Returns:
            Self for fluent chaining

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, MemoryCheckpointStorage

            storage = MemoryCheckpointStorage()
            workflow = (
                GroupChatBuilder()
                .set_manager(manager)
                .participants(agent1=agent1, agent2=agent2)
                .with_checkpointing(storage)
                .build()
            )
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_handler(
        self,
        executor: Executor,
        *,
        condition: Callable[[Any], bool],
    ) -> "GroupChatBuilder":
        """Register an executor that intercepts and handles special orchestrator requests.

        This advanced feature allows custom executors to process specific messages
        emitted by the orchestrator before they reach participants. Useful for
        implementing plan review, validation gates, or custom routing logic.

        Args:
            executor: Executor instance that handles intercepted requests
            condition: Callable that returns True for messages this executor should handle

        Returns:
            Self for fluent chaining

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, Executor


            def is_plan_review(msg: Any) -> bool:
                return isinstance(msg, dict) and msg.get("type") == "plan_review"


            review_executor = PlanReviewExecutor()
            workflow = (
                GroupChatBuilder()
                .set_manager(manager)
                .participants(agent1=agent1)
                .with_request_handler(review_executor, condition=is_plan_review)
                .build()
            )
        """
        self._request_handler = (executor, condition)
        return self

    def with_max_rounds(self, max_rounds: int | None) -> "GroupChatBuilder":
        """Set a maximum number of manager rounds to prevent infinite conversations.

        When the round limit is reached, the workflow automatically completes with
        a default completion message. Setting to None allows unlimited rounds.

        Args:
            max_rounds: Maximum number of manager selection rounds, or None for unlimited

        Returns:
            Self for fluent chaining

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            # Limit to 15 rounds
            workflow = (
                GroupChatBuilder()
                .set_manager(manager)
                .participants(agent1=agent1, agent2=agent2)
                .with_max_rounds(15)
                .build()
            )

            # Unlimited rounds
            workflow = GroupChatBuilder().set_manager(manager).participants(agent1=agent1).with_max_rounds(None).build()
        """
        self._max_rounds = max_rounds
        return self

    def _build_participant_specs(self) -> dict[str, GroupChatParticipantSpec]:
        specs: dict[str, GroupChatParticipantSpec] = {}
        for name, participant in self._participants.items():
            specs[name] = GroupChatParticipantSpec(
                name=name,
                participant=participant,
                description=self._participant_descriptions[name],
            )
        return specs

    def build(self) -> Workflow:
        """Build and validate the group chat workflow.

        Assembles the orchestrator, participants, and their interconnections into
        a complete workflow graph. The orchestrator delegates speaker selection to
        the manager, routes requests to the appropriate participants, and collects
        their responses to continue or complete the conversation.

        Returns:
            Validated Workflow instance ready for execution

        Raises:
            ValueError: If manager or participants are not configured (when using default factory)

        Wiring pattern:
        - Orchestrator receives initial input (str, ChatMessage, or list[ChatMessage])
        - Orchestrator queries manager for next action (participant selection or finish)
        - If participant selected: request routed to participant entry node
        - Participant pipeline: ingress -> (agent executor) -> egress
        - Egress sends response back to orchestrator
        - Orchestrator updates state and queries manager again
        - When manager returns finish directive: orchestrator yields final message and becomes idle

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, StandardGroupChatManager

            manager = StandardGroupChatManager(chat_client)
            workflow = GroupChatBuilder().set_manager(manager).participants(agent1=agent1, agent2=agent2).build()

            # Execute the workflow
            async for message in workflow.run("Solve this problem collaboratively"):
                print(message.text)
        """
        # Manager is only required when using the default orchestrator factory
        # Custom factories (e.g., MagenticBuilder) provide their own orchestrator with embedded manager
        if self._manager is None and self._orchestrator_factory == _default_orchestrator_factory:
            raise ValueError("manager must be configured before build() when using default orchestrator")
        if not self._participants:
            raise ValueError("participants must be configured before build()")

        participant_specs = self._build_participant_specs()
        wiring = GroupChatWiring(
            manager=self._manager,
            manager_name=self._manager_name,
            participants=participant_specs,
            max_rounds=self._max_rounds,
        )

        orchestrator = self._orchestrator_factory(wiring)
        wiring.orchestrator = orchestrator

        workflow_builder = WorkflowBuilder().set_start_executor(orchestrator)

        for name, spec in participant_specs.items():
            nodes = self._participant_factory(spec, wiring)
            chain: list[Executor] = [nodes.entry, *nodes.intermediates, nodes.exit]
            target_name = name

            def _route(msg: Any, expected: str = target_name) -> bool:
                return isinstance(msg, GroupChatRequestMessage) and msg.agent_name == expected

            workflow_builder = workflow_builder.add_edge(orchestrator, nodes.entry, condition=_route)
            for upstream, downstream in itertools.pairwise(chain):
                workflow_builder = workflow_builder.add_edge(upstream, downstream)
            if nodes.exit is not orchestrator:
                workflow_builder = workflow_builder.add_edge(nodes.exit, orchestrator)

        if self._request_handler is not None:
            handler_executor, condition = self._request_handler
            workflow_builder = workflow_builder.add_edge(orchestrator, handler_executor, condition=condition)
            workflow_builder = workflow_builder.add_edge(handler_executor, orchestrator)

        if self._checkpoint_storage is not None:
            workflow_builder = workflow_builder.with_checkpointing(self._checkpoint_storage)

        return workflow_builder.build()


# endregion


# region Default manager implementation


class _ManagerDirectiveModel(BaseModel):
    """Pydantic model for structured output from LLM manager decisions.

    Defines the JSON schema that StandardGroupChatManager expects from the LLM's
    response_format output. This ensures type-safe parsing and validation of manager
    directives.

    Attributes:
        next_agent: Name of participant to speak next (null when finishing)
        message: Optional instruction for the selected participant
        finish: Boolean indicating if the task is complete
        final_response: Final answer to the user (only when finish=True)

    Usage:
        The LLM is prompted to return this exact structure via structured output,
        which is then parsed and converted to GroupChatDirective for orchestrator routing.
    """

    next_agent: str | None = None
    message: str | None = None
    finish: bool = False
    final_response: str | None = None


DEFAULT_MANAGER_INSTRUCTIONS = """You are coordinating a team conversation to solve the user's task.
Select the next participant to respond or finish the task. When selecting an agent you MUST return
the JSON fields:
- next_agent: name of the participant who should act next (use null when finish is true)
- message: instruction for that participant (empty string if not needed)
- finish: boolean indicating if the task is complete
- final_response: when finish is true, provide the final answer to the user
"""


class StandardGroupChatManager(GroupChatManagerProtocol):
    """LLM-backed manager that produces directives via structured output.

    This is the default manager implementation for group chat workflows. It uses an LLM
    to make speaker selection decisions based on conversation state, participant
    descriptions, and custom instructions.

    Coordination strategy:
    - Receives GroupChatState snapshot with full conversation history
    - Formats system prompt with instructions, task, and participant descriptions
    - Appends conversation context and structured output prompt
    - Calls LLM with response_format=_ManagerDirectiveModel for type safety
    - Parses LLM response and converts to GroupChatDirective

    Flexibility:
    - Custom instructions allow domain-specific coordination strategies
    - Participant descriptions guide the LLM's selection logic
    - Structured output ensures reliable parsing (no regex or brittle prompts)

    Example coordination patterns:
    - Round-robin: "Rotate between participants in order"
    - Task-based: "Select the participant best suited for the current sub-task"
    - Dependency-aware: "Only call analyst after researcher provides data"

    Args:
        chat_client: ChatClientProtocol implementation for LLM inference
        instructions: Custom system instructions (defaults to DEFAULT_MANAGER_INSTRUCTIONS)
        name: Display name for the manager in conversation history

    Raises:
        RuntimeError: If LLM response cannot be parsed into _ManagerDirectiveModel
                     If directive is missing next_agent when finish=False
                     If selected agent is not in participants
    """

    def __init__(
        self,
        chat_client: ChatClientProtocol,
        *,
        instructions: str | None = None,
        name: str | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._instructions = instructions or DEFAULT_MANAGER_INSTRUCTIONS
        self._name = name or "GroupChatManager"

    @property
    def name(self) -> str:
        return self._name

    async def next_action(self, state: GroupChatState) -> GroupChatDirective:
        participants_section = "\n".join(
            f"- {agent}: {description}" for agent, description in state.participants.items()
        )

        system_message = ChatMessage(
            role=Role.SYSTEM,
            text=(f"{self._instructions}\n\nTask:\n{state.task.text}\n\nParticipants:\n{participants_section}"),
        )

        messages: list[ChatMessage] = [system_message, *state.conversation]
        messages.append(
            ChatMessage(
                role=Role.USER,
                text=(
                    "Return a JSON object with keys (next_agent, message, finish, final_response). "
                    "If you decide to finish, next_agent must be null."
                ),
            )
        )

        try:
            response = await self._chat_client.get_response(
                messages,
                response_format=_ManagerDirectiveModel,
            )
            directive_obj: _ManagerDirectiveModel
            if response.value is not None:
                directive_obj = _ManagerDirectiveModel.model_validate(response.value)
            elif response.messages:
                payload = response.messages[-1].text or "{}"
                directive_obj = _ManagerDirectiveModel.model_validate_json(payload)
            else:
                raise RuntimeError("LLM response did not contain structured output.")
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse manager directive: %s", exc)
            raise RuntimeError("Unable to parse manager directive from chat client response.") from exc

        if directive_obj.finish:
            final_text = directive_obj.final_response or ""
            return GroupChatDirective(
                finish=True,
                final_message=ChatMessage(
                    role=Role.ASSISTANT,
                    text=final_text,
                    author_name=self._name,
                ),
            )

        next_agent = directive_obj.next_agent
        if not next_agent:
            raise RuntimeError("Manager directive missing next_agent while finish is False.")
        if next_agent not in state.participants:
            raise RuntimeError(f"Manager selected unknown participant '{next_agent}'.")

        return GroupChatDirective(
            agent_name=next_agent,
            instruction=directive_obj.message or "",
        )


# endregion
