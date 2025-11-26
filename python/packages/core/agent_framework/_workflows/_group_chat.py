# Copyright (c) Microsoft. All rights reserved.

"""Group chat orchestration primitives.

This module introduces a reusable orchestration surface for manager-directed
multi-agent conversations. The key components are:

- GroupChatRequestMessage / GroupChatResponseMessage: canonical envelopes used
  between the orchestrator and participants.
- Group chat managers: minimal asynchronous callables for pluggable coordination logic.
- GroupChatOrchestratorExecutor: runtime state machine that delegates to a
  manager to select the next participant or complete the task.
- GroupChatBuilder: high-level builder that wires managers and participants
  into a workflow graph. It mirrors the ergonomics of SequentialBuilder and
  ConcurrentBuilder while allowing Magentic to reuse the same infrastructure.

The default wiring uses AgentExecutor under the hood for agent participants so
existing observability and streaming semantics continue to apply.
"""

import inspect
import itertools
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias, cast
from uuid import uuid4

from pydantic import BaseModel, Field

from .._agents import AgentProtocol, ChatAgent
from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutorRequest, AgentExecutorResponse
from ._base_group_chat_orchestrator import BaseGroupChatOrchestrator
from ._checkpoint import CheckpointStorage
from ._conversation_history import ensure_author, latest_user_message
from ._executor import Executor, handler
from ._participant_utils import GroupChatParticipantSpec, prepare_participant_metadata, wrap_participant
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


# region Message primitives


@dataclass
class _GroupChatRequestMessage:
    """Internal: Request envelope sent from the orchestrator to a participant."""

    agent_name: str
    conversation: list[ChatMessage] = field(default_factory=list)  # type: ignore
    instruction: str = ""
    task: ChatMessage | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class _GroupChatResponseMessage:
    """Internal: Response envelope emitted by participants back to the orchestrator."""

    agent_name: str
    message: ChatMessage


@dataclass
class _GroupChatTurn:
    """Internal: Represents a single turn in the manager-participant conversation."""

    speaker: str
    role: str
    message: ChatMessage


@dataclass
class GroupChatDirective:
    """Instruction emitted by a group chat manager implementation."""

    agent_name: str | None = None
    instruction: str | None = None
    metadata: dict[str, Any] | None = None
    finish: bool = False
    final_message: ChatMessage | None = None


@dataclass
class ManagerSelectionRequest:
    """Request sent to manager agent for next speaker selection.

    This dataclass packages the full conversation state and task context
    for the manager agent to analyze and make a speaker selection decision.

    Attributes:
        task: Original user task message
        participants: Mapping of participant names to their descriptions
        conversation: Full conversation history including all messages
        round_index: Number of manager selection rounds completed so far
        metadata: Optional metadata for extensibility
    """

    task: ChatMessage
    participants: dict[str, str]  # type: ignore
    conversation: list[ChatMessage]  # type: ignore
    round_index: int
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task": self.task.to_dict(),
            "participants": dict(self.participants),
            "conversation": [msg.to_dict() for msg in self.conversation],
            "round_index": self.round_index,
            "metadata": self.metadata,
        }


class ManagerSelectionResponse(BaseModel):
    """Response from manager agent with speaker selection decision.

    The manager agent must produce this structure (or compatible dict/JSON)
    to communicate its decision back to the orchestrator.

    Attributes:
        selected_participant: Name of participant to speak next (None = finish conversation)
        instruction: Optional instruction to provide to the selected participant
        finish: Whether the conversation should be completed
        final_message: Optional final message string when finishing conversation (will be converted to ChatMessage)
    """

    model_config = {"extra": "forbid"}

    selected_participant: str | None = None
    instruction: str | None = None
    finish: bool = False
    final_message: str | None = Field(default=None, description="Optional text content for final message")

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ManagerSelectionResponse":
        """Create from dictionary representation."""
        return ManagerSelectionResponse(
            selected_participant=data.get("selected_participant"),
            instruction=data.get("instruction"),
            finish=data.get("finish", False),
            final_message=data.get("final_message"),
        )

    def get_final_message_as_chat_message(self) -> ChatMessage | None:
        """Convert final_message string to ChatMessage if present."""
        if self.final_message:
            return ChatMessage(role=Role.ASSISTANT, text=self.final_message)
        return None


# endregion


# region Manager callable


GroupChatStateSnapshot = Mapping[str, Any]
_GroupChatManagerFn = Callable[[GroupChatStateSnapshot], Awaitable[GroupChatDirective]]


async def _maybe_await(value: Any) -> Any:
    """Await value if it is awaitable; otherwise return as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


_GroupChatParticipantPipeline: TypeAlias = Sequence[Executor]


@dataclass
class _GroupChatConfig:
    """Internal: Configuration passed to factories during workflow assembly.

    Attributes:
        manager: Manager callable for orchestration decisions (used by set_select_speakers_func)
        manager_participant: Manager agent/executor instance (used by set_manager)
        manager_name: Display name for the manager in conversation history
        participants: Mapping of participant names to their specifications
        max_rounds: Optional limit on manager selection rounds to prevent infinite loops
        termination_condition: Optional callable that halts the conversation when it returns True
        orchestrator: Orchestrator executor instance (populated during build)
        participant_aliases: Mapping of aliases to executor IDs
        participant_executors: Mapping of participant names to their executor instances
    """

    manager: _GroupChatManagerFn | None
    manager_participant: AgentProtocol | Executor | None
    manager_name: str
    participants: Mapping[str, GroupChatParticipantSpec]
    max_rounds: int | None = None
    termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] | None = None
    orchestrator: Executor | None = None
    participant_aliases: dict[str, str] = field(default_factory=dict)  # type: ignore[type-arg]
    participant_executors: dict[str, Executor] = field(default_factory=dict)  # type: ignore[type-arg]


# endregion


# region Default participant factory

_GroupChatOrchestratorFactory: TypeAlias = Callable[[_GroupChatConfig], Executor]
_InterceptorSpec: TypeAlias = tuple[Callable[[_GroupChatConfig], Executor], Callable[[Any], bool]]


def _default_participant_factory(
    spec: GroupChatParticipantSpec,
    wiring: _GroupChatConfig,
) -> _GroupChatParticipantPipeline:
    """Default factory for constructing participant pipeline nodes in the workflow graph.

    Creates a single AgentExecutor node for AgentProtocol participants or a passthrough executor
    for custom participants. Translation between group-chat envelopes and the agent runtime is now
    handled inside the orchestrator, removing the need for dedicated ingress/egress adapters.

    Args:
        spec: Participant specification containing name, instance, and description
        wiring: GroupChatWiring configuration for accessing cached executors

    Returns:
        Sequence of executors representing the participant pipeline in execution order

    Behavior:
        - AgentProtocol participants are wrapped in AgentExecutor with deterministic IDs
        - Executor participants are wired directly without additional adapters
    """
    participant = spec.participant
    if isinstance(participant, Executor):
        return (participant,)

    cached = wiring.participant_executors.get(spec.name)
    if cached is not None:
        return (cached,)

    agent_executor = wrap_participant(participant, executor_id=f"groupchat_agent:{spec.name}")
    return (agent_executor,)


# endregion


# region Default orchestrator


class GroupChatOrchestratorExecutor(BaseGroupChatOrchestrator):
    """Executor that orchestrates a group chat between multiple participants using a manager.

    This is the central runtime state machine that drives multi-agent conversations. It
    maintains conversation state, delegates speaker selection to a manager, routes messages
    to participants, and collects responses in a loop until the manager signals completion.

    Core responsibilities:
    - Accept initial input as str, ChatMessage, or list[ChatMessage]
    - Maintain conversation history and turn tracking
    - Query manager for next action (select participant or finish)
    - Route requests to selected participants using AgentExecutorRequest or GroupChatRequestMessage
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
    The orchestrator builds immutable state snapshots and passes them to the manager
    callable. The manager returns a GroupChatDirective indicating either:
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
        manager: Callable that selects the next participant or finishes based on state snapshot
        participants: Mapping of participant names to descriptions (for manager context)
        manager_name: Display name for manager in conversation history
        max_rounds: Optional limit on manager selection rounds (None = unlimited)
        termination_condition: Optional callable that halts the conversation when it returns True
        executor_id: Optional custom ID for observability (auto-generated if not provided)
    """

    def __init__(
        self,
        manager: _GroupChatManagerFn,
        *,
        participants: Mapping[str, str],
        manager_name: str,
        max_rounds: int | None = None,
        termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] | None = None,
        executor_id: str | None = None,
    ) -> None:
        super().__init__(executor_id or f"groupchat_orchestrator_{uuid4().hex[:8]}")
        self._manager = manager
        self._participants = dict(participants)
        self._manager_name = manager_name
        self._max_rounds = max_rounds
        self._termination_condition = termination_condition
        self._history: list[_GroupChatTurn] = []
        self._task_message: ChatMessage | None = None
        self._pending_agent: str | None = None
        self._pending_finalization: bool = False
        # Stashes the initial conversation list until _handle_task_message normalizes it into _conversation.
        self._pending_initial_conversation: list[ChatMessage] | None = None

    def _get_author_name(self) -> str:
        """Get the manager name for orchestrator-generated messages."""
        return self._manager_name

    def _build_state(self) -> GroupChatStateSnapshot:
        """Build a snapshot of current orchestration state for the manager.

        Packages conversation history, participant metadata, and round tracking into
        an immutable mapping that the manager uses to make speaker selection decisions.

        Returns:
            Mapping containing all context needed for manager decision-making

        Raises:
            RuntimeError: If called before task message initialization (defensive check)

        When this is called:
            - After initial input is processed (first manager query)
            - After each participant response (subsequent manager queries)
        """
        if self._task_message is None:
            raise RuntimeError("GroupChatOrchestratorExecutor state not initialized with task message.")
        snapshot: dict[str, Any] = {
            "task": self._task_message,
            "participants": dict(self._participants),
            "conversation": tuple(self._conversation),
            "history": tuple(self._history),
            "pending_agent": self._pending_agent,
            "round_index": self._round_index,
        }
        return MappingProxyType(snapshot)

    def _snapshot_pattern_metadata(self) -> dict[str, Any]:
        """Serialize GroupChat-specific state for checkpointing.

        Returns:
            Dict with participants, manager name, history, and pending agent
        """
        return {
            "participants": dict(self._participants),
            "manager_name": self._manager_name,
            "pending_agent": self._pending_agent,
            "task_message": self._task_message.to_dict() if self._task_message else None,
            "history": [
                {"speaker": turn.speaker, "role": turn.role, "message": turn.message.to_dict()}
                for turn in self._history
            ],
        }

    def _restore_pattern_metadata(self, metadata: dict[str, Any]) -> None:
        """Restore GroupChat-specific state from checkpoint.

        Args:
            metadata: Pattern-specific state dict
        """
        if "participants" in metadata:
            self._participants = dict(metadata["participants"])
        if "manager_name" in metadata:
            self._manager_name = metadata["manager_name"]
        if "pending_agent" in metadata:
            self._pending_agent = metadata["pending_agent"]
        task_msg = metadata.get("task_message")
        if task_msg:
            self._task_message = ChatMessage.from_dict(task_msg)
        if "history" in metadata:
            self._history = [
                _GroupChatTurn(
                    speaker=turn["speaker"],
                    role=turn["role"],
                    message=ChatMessage.from_dict(turn["message"]),
                )
                for turn in metadata["history"]
            ]

    async def _complete_on_termination(
        self,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> bool:
        """Finish the conversation early when the termination condition is met."""
        if not await self._check_termination():
            return False

        if self._is_manager_agent():
            if self._pending_finalization:
                return True

            self._pending_finalization = True
            termination_prompt = ChatMessage(
                role=Role.SYSTEM,
                text="Termination condition met. Provide a final manager summary and finish the conversation.",
            )
            manager_conversation = [
                self._build_manager_context_message(),
                termination_prompt,
                *list(self._conversation),
            ]
            self._pending_agent = self._manager_name
            await self._route_to_participant(
                participant_name=self._manager_name,
                conversation=manager_conversation,
                ctx=ctx,
                instruction="",
                task=self._task_message,
                metadata={"termination_condition": True},
            )
            return True

        final_message: ChatMessage | None = None
        if self._manager is not None and not self._is_manager_agent():
            try:
                directive = await self._manager(self._build_state())
            except Exception:
                logger.warning("Manager finalization failed during termination; using default termination message.")
            else:
                if directive.final_message is not None:
                    final_message = ensure_author(directive.final_message, self._manager_name)
                elif directive.finish:
                    final_message = ensure_author(
                        self._create_completion_message(
                            text="Conversation completed.",
                            reason="termination_condition_manager_finish",
                        ),
                        self._manager_name,
                    )

        if final_message is None:
            final_message = ensure_author(
                self._create_completion_message(
                    text="Conversation halted after termination condition was met.",
                    reason="termination_condition",
                ),
                self._manager_name,
            )
        self._conversation.append(final_message)
        self._history.append(_GroupChatTurn(self._manager_name, "manager", final_message))
        self._pending_agent = None
        await ctx.yield_output(list(self._conversation))
        return True

    async def _apply_directive(
        self,
        directive: GroupChatDirective,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
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
            - Prepares full conversation context for the participant
            - Routes request directly to the participant entry executor
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
                final_message = self._create_completion_message(
                    text="Completed without final summary.",
                    reason="no summary provided",
                )
            final_message = ensure_author(final_message, self._manager_name)

            self._conversation.extend((final_message,))
            self._history.append(_GroupChatTurn(self._manager_name, "manager", final_message))
            self._pending_agent = None
            await ctx.yield_output(list(self._conversation))
            return

        agent_name = directive.agent_name
        if not agent_name:
            raise ValueError("Directive must include agent_name when finish is False.")
        if agent_name not in self._participants:
            raise ValueError(f"Manager selected unknown participant '{agent_name}'.")

        instruction = directive.instruction or ""
        conversation = list(self._conversation)
        if instruction:
            manager_message = ensure_author(
                self._create_completion_message(text=instruction, reason="instruction"),
                self._manager_name,
            )
            conversation.extend((manager_message,))
            self._conversation.extend((manager_message,))
            self._history.append(_GroupChatTurn(self._manager_name, "manager", manager_message))

        if await self._complete_on_termination(ctx):
            return

        self._pending_agent = agent_name
        self._increment_round()

        # Use inherited routing method from BaseGroupChatOrchestrator
        await self._route_to_participant(
            participant_name=agent_name,
            conversation=conversation,
            ctx=ctx,
            instruction=instruction,
            task=self._task_message,
            metadata=directive.metadata,
        )

        if self._check_round_limit():
            await self._apply_directive(
                GroupChatDirective(
                    finish=True,
                    final_message=self._create_completion_message(
                        text="Conversation halted after reaching manager round limit.",
                        reason="max_rounds reached",
                    ),
                ),
                ctx,
            )

    async def _ingest_participant_message(
        self,
        participant_name: str,
        message: ChatMessage,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> None:
        """Common response ingestion logic shared by agent and custom participants."""
        if participant_name not in self._participants:
            raise ValueError(f"Received response from unknown participant '{participant_name}'.")

        message = ensure_author(message, participant_name)
        self._conversation.extend((message,))
        self._history.append(_GroupChatTurn(participant_name, "agent", message))
        self._pending_agent = None

        if await self._complete_on_termination(ctx):
            return

        if self._check_round_limit():
            final_message = self._create_completion_message(
                text="Conversation halted after reaching manager round limit.",
                reason="max_rounds reached after response",
            )
            self._conversation.extend((final_message,))
            self._history.append(_GroupChatTurn(self._manager_name, "manager", final_message))
            await ctx.yield_output(list(self._conversation))
            return

        # Query manager for next speaker selection
        if self._is_manager_agent():
            # Agent-based manager: route request through workflow graph
            # Prepend system message with participant context
            manager_conversation = [self._build_manager_context_message(), *list(self._conversation)]
            await self._route_to_participant(
                participant_name=self._manager_name,
                conversation=manager_conversation,
                ctx=ctx,
                instruction="",
                task=self._task_message,
                metadata=None,
            )
        else:
            # Callable manager: invoke directly
            directive = await self._manager(self._build_state())
            await self._apply_directive(directive, ctx)

    def _is_manager_agent(self) -> bool:
        """Check if orchestrator is using an agent-based manager (vs callable manager)."""
        return self._registry.is_participant_registered(self._manager_name)

    def _build_manager_context_message(self) -> ChatMessage:
        """Build system message with participant context for manager agent.

        This message is prepended to the conversation when querying the manager
        to provide up-to-date participant information for selection decisions.

        Returns:
            System message with participant names and descriptions
        """
        participant_list = "\n".join(f"- {name}: {desc}" for name, desc in self._participants.items())
        context_text = (
            "Available participants:\n"
            f"{participant_list}\n\n"
            "IMPORTANT: Choose only from these exact participant names (case-sensitive)."
        )
        return ChatMessage(role=Role.SYSTEM, text=context_text)

    def _parse_manager_selection(self, response: AgentExecutorResponse) -> ManagerSelectionResponse:
        """Extract manager selection decision from agent response.

        Attempts to parse structured output from the manager agent using multiple strategies:
        1. response.value (structured output from response_format)
        2. JSON parsing from message text
        3. Fallback error handling

        Args:
            response: AgentExecutor response from manager agent

        Returns:
            Parsed ManagerSelectionResponse with speaker selection

        Raises:
            RuntimeError: If manager response cannot be parsed into valid selection
        """
        import json

        # Strategy 1: agent_run_response.value (structured output)
        agent_value = response.agent_run_response.value
        if agent_value is not None:
            if isinstance(agent_value, ManagerSelectionResponse):
                return agent_value
            if isinstance(agent_value, dict):
                return ManagerSelectionResponse.from_dict(cast(dict[str, Any], agent_value))
            if isinstance(agent_value, str):
                try:
                    data = json.loads(agent_value)
                    return ManagerSelectionResponse.from_dict(data)
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    raise RuntimeError(f"Manager response.value contains invalid JSON: {e}") from e

        # Strategy 2: Parse from message text
        messages = response.agent_run_response.messages or []
        if messages:
            last_msg = messages[-1]
            text = last_msg.text or ""
            try:
                return ManagerSelectionResponse.model_validate_json(text)
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # Fallback: Cannot parse manager decision
        raise RuntimeError(
            "Manager response did not contain valid selection data. "
            "Ensure manager agent uses response_format=ManagerSelectionResponse "
            "or returns compatible JSON structure."
        )

    async def _handle_manager_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> None:
        """Process manager agent's speaker selection decision.

        Parses the manager's response and either finishes the conversation or routes
        to the selected participant. This method implements the core orchestration
        logic for agent-based managers.

        Args:
            response: AgentExecutor response from manager agent
            ctx: Workflow context for routing and output

        Behavior:
            - Parses manager selection from response
            - If finish=True: yields final message and completes workflow
            - If participant selected: routes request to that participant
            - Validates selected participant exists
            - Enforces round limits if configured

        Raises:
            ValueError: If manager selects invalid/unknown participant
            RuntimeError: If manager response cannot be parsed
        """
        selection = self._parse_manager_selection(response)

        if self._pending_finalization:
            self._pending_finalization = False
            final_message_obj = selection.get_final_message_as_chat_message()
            if final_message_obj is None:
                final_message_obj = self._create_completion_message(
                    text="Conversation halted after termination condition was met.",
                    reason="termination_condition_manager",
                )
            final_message_obj = ensure_author(final_message_obj, self._manager_name)

            self._conversation.append(final_message_obj)
            self._history.append(_GroupChatTurn(self._manager_name, "manager", final_message_obj))
            self._pending_agent = None
            await ctx.yield_output(list(self._conversation))
            return

        if selection.finish:
            # Manager decided to complete conversation
            final_message_obj = selection.get_final_message_as_chat_message()
            if final_message_obj is None:
                final_message_obj = self._create_completion_message(
                    text="Conversation completed.",
                    reason="manager_finish",
                )
            final_message_obj = ensure_author(final_message_obj, self._manager_name)

            self._conversation.append(final_message_obj)
            self._history.append(_GroupChatTurn(self._manager_name, "manager", final_message_obj))
            self._pending_agent = None
            await ctx.yield_output(list(self._conversation))
            return

        # Manager selected next participant
        selected = selection.selected_participant
        if not selected:
            raise ValueError("Manager selection missing selected_participant when finish=False.")
        if selected not in self._participants:
            raise ValueError(f"Manager selected unknown participant: '{selected}'")

        # Route to selected participant
        instruction = selection.instruction or ""
        conversation = list(self._conversation)
        if instruction:
            manager_message = ensure_author(
                self._create_completion_message(text=instruction, reason="manager_instruction"),
                self._manager_name,
            )
            conversation.append(manager_message)
            self._conversation.append(manager_message)
            self._history.append(_GroupChatTurn(self._manager_name, "manager", manager_message))

        if await self._complete_on_termination(ctx):
            return

        self._pending_agent = selected
        self._increment_round()

        await self._route_to_participant(
            participant_name=selected,
            conversation=conversation,
            ctx=ctx,
            instruction=instruction,
            task=self._task_message,
            metadata=None,
        )

        if self._check_round_limit():
            await self._apply_directive(
                GroupChatDirective(
                    finish=True,
                    final_message=self._create_completion_message(
                        text="Conversation halted after reaching manager round limit.",
                        reason="max_rounds reached after manager selection",
                    ),
                ),
                ctx,
            )

    @staticmethod
    def _extract_agent_message(response: AgentExecutorResponse, participant_name: str) -> ChatMessage:
        """Select the final assistant message from an AgentExecutor response."""
        from ._orchestrator_helpers import create_completion_message

        final_message: ChatMessage | None = None
        candidate_sequences: tuple[Sequence[ChatMessage] | None, ...] = (
            response.agent_run_response.messages,
            response.full_conversation,
        )
        for sequence in candidate_sequences:
            if not sequence:
                continue
            for candidate in reversed(sequence):
                if candidate.role == Role.ASSISTANT:
                    final_message = candidate
                    break
            if final_message is not None:
                break

        if final_message is None:
            final_message = create_completion_message(
                text="",
                author_name=participant_name,
                reason="empty response",
            )
        return ensure_author(final_message, participant_name)

    async def _handle_task_message(
        self,
        task_message: ChatMessage,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
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
            The handle_conversation handler supplies an explicit task (the first message in
            the list) but still forwards the entire conversation for context. The full list is
            stashed in _pending_initial_conversation to preserve all context when initializing state.
        """
        self._task_message = task_message
        if self._pending_initial_conversation:
            initial_conversation = list(self._pending_initial_conversation)
            self._pending_initial_conversation = None
            self._conversation = initial_conversation
            self._history = [
                _GroupChatTurn(
                    msg.author_name or msg.role.value,
                    msg.role.value,
                    msg,
                )
                for msg in initial_conversation
            ]
        else:
            self._conversation = [task_message]
            self._history = [_GroupChatTurn("user", "user", task_message)]
        self._pending_agent = None
        self._round_index = 0

        if await self._complete_on_termination(ctx):
            return

        # Query manager for first speaker selection
        if self._is_manager_agent():
            # Agent-based manager: route request through workflow graph
            # Prepend system message with participant context
            manager_conversation = [self._build_manager_context_message(), *list(self._conversation)]
            await self._route_to_participant(
                participant_name=self._manager_name,
                conversation=manager_conversation,
                ctx=ctx,
                instruction="",
                task=self._task_message,
                metadata=None,
            )
        else:
            # Callable manager: invoke directly
            directive = await self._manager(self._build_state())
            await self._apply_directive(directive, ctx)

    @handler
    async def handle_str(
        self,
        task: str,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
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
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
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
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> None:
        """Handler for conversation history as workflow entry point.

        Accepts a pre-existing conversation and uses the first message in the list as the task.
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
        task_message = latest_user_message(conversation)
        await self._handle_task_message(task_message, ctx)

    @handler
    async def handle_agent_response(
        self,
        response: _GroupChatResponseMessage,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> None:
        """Handle responses from custom participant executors."""
        await self._ingest_participant_message(response.agent_name, response.message, ctx)

    @handler
    async def handle_agent_executor_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest | _GroupChatRequestMessage, list[ChatMessage]],
    ) -> None:
        """Handle responses from both manager agent and regular participants.

        Routes responses based on whether they come from the manager or a participant:
        - Manager responses: parsed for speaker selection decisions
        - Participant responses: ingested as conversation messages
        """
        participant_name = self._registry.get_participant_name(response.executor_id)
        if participant_name is None:
            logger.debug(
                "Ignoring response from unregistered agent executor '%s'.",
                response.executor_id,
            )
            return

        # Check if response is from manager agent
        if participant_name == self._manager_name and self._is_manager_agent():
            await self._handle_manager_response(response, ctx)
        else:
            # Regular participant response
            message = self._extract_agent_message(response, participant_name)
            await self._ingest_participant_message(participant_name, message, ctx)


def _default_orchestrator_factory(wiring: _GroupChatConfig) -> Executor:
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
        - Forwards manager instance, manager name, max_rounds, and termination_condition settings
        - Allows orchestrator to auto-generate its executor ID
        - Supports both callable managers (set_select_speakers_func) and agent-based managers (set_manager)

    Why descriptions are extracted:
        The manager needs participant descriptions (not full specs) to make informed
        selection decisions. The orchestrator doesn't need participant instances directly
        since routing is handled by the workflow graph.

    Raises:
        RuntimeError: If neither manager nor manager_participant is configured
    """
    if wiring.manager is None and wiring.manager_participant is None:
        raise RuntimeError(
            "Default orchestrator factory requires a manager to be configured. "
            "Call set_manager(...) or set_select_speakers_func(...) before build()."
        )

    manager_callable = wiring.manager
    if manager_callable is None:
        # Keep orchestrator signature satisfied; agent managers are routed via the workflow graph
        async def _agent_manager_placeholder(_: GroupChatStateSnapshot) -> GroupChatDirective:  # noqa: RUF029
            raise RuntimeError(
                "Manager callable invoked unexpectedly. Agent-based managers should route through the workflow graph."
            )

        manager_callable = _agent_manager_placeholder

    return GroupChatOrchestratorExecutor(
        manager=manager_callable,
        participants={name: spec.description for name, spec in wiring.participants.items()},
        manager_name=wiring.manager_name,
        max_rounds=wiring.max_rounds,
        termination_condition=wiring.termination_condition,
    )


def group_chat_orchestrator(factory: _GroupChatOrchestratorFactory | None = None) -> _GroupChatOrchestratorFactory:
    """Return a callable orchestrator factory, defaulting to the built-in implementation."""
    return factory or _default_orchestrator_factory


def assemble_group_chat_workflow(
    *,
    wiring: _GroupChatConfig,
    participant_factory: Callable[[GroupChatParticipantSpec, _GroupChatConfig], _GroupChatParticipantPipeline],
    orchestrator_factory: _GroupChatOrchestratorFactory = _default_orchestrator_factory,
    interceptors: Sequence[_InterceptorSpec] | None = None,
    checkpoint_storage: CheckpointStorage | None = None,
    builder: WorkflowBuilder | None = None,
    return_builder: bool = False,
) -> Workflow | tuple[WorkflowBuilder, Executor]:
    """Build the workflow graph shared by group-chat style orchestrators."""
    interceptor_specs = interceptors or ()

    orchestrator = wiring.orchestrator or orchestrator_factory(wiring)
    wiring.orchestrator = orchestrator

    workflow_builder = builder or WorkflowBuilder()
    start_executor = getattr(workflow_builder, "_start_executor", None)
    if start_executor is None:
        workflow_builder = workflow_builder.set_start_executor(orchestrator)

    # Wire manager as participant if agent-based manager is configured
    if wiring.manager_participant is not None:
        manager_spec = GroupChatParticipantSpec(
            name=wiring.manager_name,
            participant=wiring.manager_participant,
            description="Coordination manager",
        )
        manager_pipeline = list(participant_factory(manager_spec, wiring))
        if not manager_pipeline:
            raise ValueError("Participant factory returned empty pipeline for manager.")

        manager_entry = manager_pipeline[0]
        manager_exit = manager_pipeline[-1]

        # Register manager with orchestrator
        register_entry = getattr(orchestrator, "register_participant_entry", None)
        if callable(register_entry):
            register_entry(
                wiring.manager_name,
                entry_id=manager_entry.id,
                is_agent=not isinstance(wiring.manager_participant, Executor),
            )

        # Wire manager edges: Orchestrator ↔ Manager
        workflow_builder = workflow_builder.add_edge(orchestrator, manager_entry)
        for upstream, downstream in itertools.pairwise(manager_pipeline):
            workflow_builder = workflow_builder.add_edge(upstream, downstream)
        if manager_exit is not orchestrator:
            workflow_builder = workflow_builder.add_edge(manager_exit, orchestrator)

    # Wire regular participants
    for name, spec in wiring.participants.items():
        pipeline = list(participant_factory(spec, wiring))
        if not pipeline:
            raise ValueError(
                f"Participant factory returned an empty pipeline for '{name}'. "
                "Provide at least one executor per participant."
            )
        entry_executor = pipeline[0]
        exit_executor = pipeline[-1]

        register_entry = getattr(orchestrator, "register_participant_entry", None)
        if callable(register_entry):
            register_entry(
                name,
                entry_id=entry_executor.id,
                is_agent=not isinstance(spec.participant, Executor),
            )

        workflow_builder = workflow_builder.add_edge(orchestrator, entry_executor)
        for upstream, downstream in itertools.pairwise(pipeline):
            workflow_builder = workflow_builder.add_edge(upstream, downstream)
        if exit_executor is not orchestrator:
            workflow_builder = workflow_builder.add_edge(exit_executor, orchestrator)

    for factory, condition in interceptor_specs:
        interceptor_executor = factory(wiring)
        workflow_builder = workflow_builder.add_edge(orchestrator, interceptor_executor, condition=condition)
        workflow_builder = workflow_builder.add_edge(interceptor_executor, orchestrator)

    if checkpoint_storage is not None:
        workflow_builder = workflow_builder.with_checkpointing(checkpoint_storage)

    if return_builder:
        return workflow_builder, orchestrator
    return workflow_builder.build()


# endregion


# region Builder


class GroupChatBuilder:
    r"""High-level builder for manager-directed group chat workflows with dynamic orchestration.

    GroupChat coordinates multi-agent conversations using a manager that selects which participant
    speaks next. The manager can be a simple Python function (:py:meth:`GroupChatBuilder.set_select_speakers_func`)
    or an agent-based selector via :py:meth:`GroupChatBuilder.set_manager`. These two approaches are
    mutually exclusive.

    **Core Workflow:**
    1. Define participants: list of agents (uses their .name) or dict mapping names to agents
    2. Configure speaker selection: :py:meth:`GroupChatBuilder.set_select_speakers_func` OR
       :py:meth:`GroupChatBuilder.set_manager` (not both)
    3. Optional: set round limits, checkpointing, termination conditions
    4. Build and run the workflow

    **Speaker Selection Patterns:**

    *Pattern 1: Simple function-based selection (recommended)*

    .. code-block:: python

        from agent_framework import GroupChatBuilder, GroupChatStateSnapshot


        def select_next_speaker(state: GroupChatStateSnapshot) -> str | None:
            # state contains: task, participants, conversation, history, round_index
            if state["round_index"] >= 5:
                return None  # Finish
            last_speaker = state["history"][-1].speaker if state["history"] else None
            if last_speaker == "researcher":
                return "writer"
            return "researcher"


        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(select_next_speaker)
            .participants([researcher_agent, writer_agent])  # Uses agent.name
            .build()
        )

    *Pattern 2: LLM-based selection*

    .. code-block:: python

        from agent_framework import ChatAgent
        from agent_framework.azure import AzureOpenAIChatClient

        manager_agent = AzureOpenAIChatClient().create_agent(
            instructions="Coordinate the conversation and pick the next speaker.",
            name="Coordinator",
            temperature=0.3,
            seed=42,
            max_tokens=500,
        )

        workflow = (
            GroupChatBuilder()
            .set_manager(manager_agent, display_name="Coordinator")
            .participants([researcher, writer])  # Or use dict: researcher=r, writer=w
            .with_max_rounds(10)
            .build()
        )

    **Participant Specification:**

    Two ways to specify participants:
    - List form: `[agent1, agent2]` - uses `agent.name` attribute for participant names
    - Dict form: `{name1: agent1, name2: agent2}` - explicit name control
    - Keyword form: `participants(name1=agent1, name2=agent2)` - explicit name control

    **State Snapshot Structure:**

    The GroupChatStateSnapshot passed to set_select_speakers_func contains:
    - `task`: ChatMessage - Original user task
    - `participants`: dict[str, str] - Mapping of participant names to descriptions
    - `conversation`: tuple[ChatMessage, ...] - Full conversation history
    - `history`: tuple[GroupChatTurn, ...] - Turn-by-turn record with speaker attribution
    - `round_index`: int - Number of manager selection rounds so far
    - `pending_agent`: str | None - Name of agent currently processing (if any)

    **Important Constraints:**
    - Cannot combine :py:meth:`GroupChatBuilder.set_select_speakers_func` and :py:meth:`GroupChatBuilder.set_manager`
    - Participant names must be unique
    - When using list form, agents must have a non-empty `name` attribute
    """

    def __init__(
        self,
        *,
        _orchestrator_factory: _GroupChatOrchestratorFactory | None = None,
        _participant_factory: Callable[[GroupChatParticipantSpec, _GroupChatConfig], _GroupChatParticipantPipeline]
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
        self._participant_metadata: dict[str, Any] | None = None
        self._manager: _GroupChatManagerFn | None = None
        self._manager_participant: AgentProtocol | Executor | None = None
        self._manager_name: str = "manager"
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_rounds: int | None = None
        self._termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] | None = None
        self._interceptors: list[_InterceptorSpec] = []
        self._orchestrator_factory = group_chat_orchestrator(_orchestrator_factory)
        self._participant_factory = _participant_factory or _default_participant_factory

    def _set_manager_function(
        self,
        manager: _GroupChatManagerFn,
        display_name: str | None,
    ) -> "GroupChatBuilder":
        if self._manager is not None or self._manager_participant is not None:
            raise ValueError(
                "GroupChatBuilder already has a manager configured. "
                "Call set_select_speakers_func(...) or set_manager(...) at most once."
            )
        resolved_name = display_name or getattr(manager, "name", None) or "manager"
        self._manager = manager
        self._manager_name = resolved_name
        return self

    def set_manager(
        self,
        manager: AgentProtocol | Executor,
        *,
        display_name: str | None = None,
    ) -> "GroupChatBuilder":
        """Configure the manager/coordinator agent for group chat orchestration.

        The manager coordinates participants by selecting who speaks next based on
        conversation state and task requirements. The manager is a full workflow
        participant with access to all agent infrastructure (tools, context, observability).

        The manager agent must produce structured output compatible with ManagerSelectionResponse
        to communicate its speaker selection decisions. Use response_format for reliable parsing.
        GroupChatBuilder enforces this when the manager is a ChatAgent and rejects incompatible
        response formats.

        Args:
            manager: Agent or executor responsible for speaker selection and coordination.
                Must return ManagerSelectionResponse or compatible dict/JSON structure.
            display_name: Optional name for manager messages in conversation history.
                If not provided, uses manager.name for AgentProtocol or manager.id for Executor.

        Returns:
            Self for fluent chaining.

        Raises:
            ValueError: If manager is already configured via :py:meth:`GroupChatBuilder.set_select_speakers_func`
            TypeError: If manager is not AgentProtocol or Executor instance

        Example:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, ChatAgent
            from agent_framework.openai import OpenAIChatClient

            # Coordinator agent - response_format is enforced to ManagerSelectionResponse
            coordinator = ChatAgent(
                name="Coordinator",
                description="Coordinates multi-agent collaboration",
                instructions='''
                You coordinate a team conversation. Review the conversation history
                and select the next participant to speak.

                When ready to finish, set finish=True and provide a summary in final_message.
                ''',
                chat_client=OpenAIChatClient(),
            )

            workflow = (
                GroupChatBuilder()
                .set_manager(coordinator, display_name="Orchestrator")
                .participants([researcher, writer])
                .build()
            )

        Note:
            The manager agent's response_format must be ManagerSelectionResponse for structured output.
            Custom response formats raise ValueError instead of being overridden.
        """
        if self._manager is not None or self._manager_participant is not None:
            raise ValueError(
                "GroupChatBuilder already has a manager configured. "
                "Call set_select_speakers_func(...) or set_manager(...) at most once."
            )

        if not isinstance(manager, (AgentProtocol, Executor)):
            raise TypeError(f"Manager must be AgentProtocol or Executor instance. Got {type(manager).__name__}.")

        # Infer display name from manager if not provided
        if display_name is None:
            display_name = manager.id if isinstance(manager, Executor) else manager.name or "manager"

        # Enforce ManagerSelectionResponse for ChatAgent managers
        if isinstance(manager, ChatAgent):
            configured_format = manager.chat_options.response_format
            if configured_format is None:
                manager.chat_options.response_format = ManagerSelectionResponse
            elif configured_format is not ManagerSelectionResponse:
                configured_format_name = getattr(configured_format, "__name__", str(configured_format))
                raise ValueError(
                    "Manager ChatAgent response_format must be ManagerSelectionResponse. "
                    f"Received '{configured_format_name}' for manager '{display_name}'."
                )

        self._manager_participant = manager
        self._manager_name = display_name
        return self

    def set_select_speakers_func(
        self,
        selector: (
            Callable[[GroupChatStateSnapshot], Awaitable[str | None]] | Callable[[GroupChatStateSnapshot], str | None]
        ),
        *,
        display_name: str | None = None,
        final_message: ChatMessage | str | Callable[[GroupChatStateSnapshot], Any] | None = None,
    ) -> "GroupChatBuilder":
        """Configure speaker selection using a pure function that examines group chat state.

        This is the primary way to control orchestration flow in a GroupChat. Your selector
        function receives an immutable snapshot of the current conversation state and returns
        the name of the next participant to speak, or None to finish the conversation.

        The selector function can implement any logic including:
        - Simple round-robin or rule-based selection
        - LLM-based decision making with custom prompts
        - Conversation summarization before routing to the next agent
        - Custom metadata or context passing

        For advanced scenarios, return a GroupChatDirective instead of a string to include
        custom instructions or metadata for the next participant.

        The selector function signature:
            def select_next_speaker(state: GroupChatStateSnapshot) -> str | None:
                # state contains: task, participants, conversation, history, round_index
                # Return participant name to continue, or None to finish
                ...

        Args:
            selector: Function that takes GroupChatStateSnapshot and returns the next speaker's
                name (str) to continue the conversation, or None to finish. May be sync or async.
                Can also return GroupChatDirective for advanced control (instruction, metadata).
            display_name: Optional name shown in conversation history for orchestrator messages
                (defaults to "manager").
            final_message: Optional final message (or factory) emitted when selector returns None
                (defaults to "Conversation completed." authored by the manager).

        Returns:
            Self for fluent chaining.

        Example (simple):

        .. code-block:: python

            def select_next_speaker(state: GroupChatStateSnapshot) -> str | None:
                if state["round_index"] >= 3:
                    return None  # Finish after 3 rounds
                last_speaker = state["history"][-1].speaker if state["history"] else None
                if last_speaker == "researcher":
                    return "writer"
                return "researcher"


            workflow = (
                GroupChatBuilder()
                .set_select_speakers_func(select_next_speaker)
                .participants(researcher=researcher_agent, writer=writer_agent)
                .build()
            )

        Example (with LLM and custom instructions):

        .. code-block:: python

            from agent_framework import GroupChatDirective


            async def llm_based_selector(state: GroupChatStateSnapshot) -> GroupChatDirective | None:
                if state["round_index"] >= 5:
                    return GroupChatDirective(finish=True)

                # Use LLM to decide next speaker and summarize conversation
                conversation_summary = await summarize_with_llm(state["conversation"])
                next_agent = await pick_agent_with_llm(state["participants"], state["task"])

                # Pass custom instruction to the selected agent
                return GroupChatDirective(
                    agent_name=next_agent,
                    instruction=f"Context summary: {conversation_summary}",
                )


            workflow = GroupChatBuilder().set_select_speakers_func(llm_based_selector).participants(...).build()

        Note:
            Cannot be combined with :py:meth:`GroupChatBuilder.set_manager`. Choose one orchestration strategy.
        """
        manager_name = display_name or "manager"
        adapter = _SpeakerSelectorAdapter(
            selector,
            manager_name=manager_name,
            final_message=final_message,
        )
        return self._set_manager_function(adapter, display_name)

    def participants(
        self,
        participants: Mapping[str, AgentProtocol | Executor] | Sequence[AgentProtocol | Executor] | None = None,
        /,
        **named_participants: AgentProtocol | Executor,
    ) -> "GroupChatBuilder":
        """Define participants for this group chat workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.
        Provide a mapping of name → participant for explicit control, or pass a sequence and
        names will be inferred from the agent's name attribute (or executor id).

        Args:
            participants: Optional mapping or sequence of participant definitions
            **named_participants: Keyword arguments mapping names to agent/executor instances

        Returns:
            Self for fluent chaining

        Raises:
            ValueError: If participants are empty, names are duplicated, or names are empty strings

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            workflow = (
                GroupChatBuilder().set_manager(manager_agent).participants([writer_agent, reviewer_agent]).build()
            )
        """
        combined: dict[str, AgentProtocol | Executor] = {}

        def _add(name: str, participant: AgentProtocol | Executor) -> None:
            if not name:
                raise ValueError("participant names must be non-empty strings")
            if name in combined or name in self._participants:
                raise ValueError(f"Duplicate participant name '{name}' supplied.")
            if name == self._manager_name:
                raise ValueError(
                    f"Participant name '{name}' conflicts with manager name. "
                    "Manager is automatically registered as a participant."
                )
            combined[name] = participant

        if participants:
            if isinstance(participants, Mapping):
                for name, participant in participants.items():
                    _add(name, participant)
            else:
                for participant in participants:
                    inferred_name: str
                    if isinstance(participant, Executor):
                        inferred_name = participant.id
                    else:
                        name_attr = getattr(participant, "name", None)
                        if not name_attr:
                            raise ValueError(
                                "Agent participants supplied via sequence must define a non-empty 'name' attribute."
                            )
                        inferred_name = str(name_attr)
                    _add(inferred_name, participant)

        for name, participant in named_participants.items():
            _add(name, participant)

        if not combined:
            raise ValueError("participants cannot be empty")

        for name, participant in combined.items():
            self._participants[name] = participant
        self._participant_metadata = None
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
                .set_manager(manager_agent)
                .participants(agent1=agent1, agent2=agent2)
                .with_checkpointing(storage)
                .build()
            )
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_handler(
        self,
        handler: Callable[[_GroupChatConfig], Executor] | Executor,
        *,
        condition: Callable[[Any], bool],
    ) -> "GroupChatBuilder":
        """Register an interceptor factory that creates executors for special requests.

        Args:
            handler: Callable that receives the wiring and returns an executor, or a pre-built executor
            condition: Filter determining which orchestrator messages the interceptor should process

        Returns:
            Self for fluent chaining
        """
        factory: Callable[[_GroupChatConfig], Executor]
        if isinstance(handler, Executor):
            executor = handler

            def _factory(_: _GroupChatConfig) -> Executor:
                return executor

            factory = _factory
        else:
            factory = handler

        self._interceptors.append((factory, condition))
        return self

    def with_termination_condition(
        self,
        condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]],
    ) -> "GroupChatBuilder":
        """Define a custom termination condition for the group chat workflow.

        The condition receives the full conversation (including manager and agent messages) and may be async.
        When it returns True, the orchestrator halts the conversation and emits a completion message authored
        by the manager.

        Example:

        .. code-block:: python

            from agent_framework import ChatMessage, GroupChatBuilder, Role


            def stop_after_two_calls(conversation: list[ChatMessage]) -> bool:
                calls = sum(1 for msg in conversation if msg.role == Role.ASSISTANT and msg.author_name == "specialist")
                return calls >= 2


            specialist_agent = ...
            workflow = (
                GroupChatBuilder()
                .set_select_speakers_func(lambda _: "specialist")
                .participants(specialist=specialist_agent)
                .with_termination_condition(stop_after_two_calls)
                .build()
            )
        """
        self._termination_condition = condition
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
                .set_manager(manager_agent)
                .participants(agent1=agent1, agent2=agent2)
                .with_max_rounds(15)
                .build()
            )

            # Unlimited rounds
            workflow = (
                GroupChatBuilder().set_manager(manager_agent).participants(agent1=agent1).with_max_rounds(None).build()
            )
        """
        self._max_rounds = max_rounds
        return self

    def _get_participant_metadata(self) -> dict[str, Any]:
        if self._participant_metadata is None:
            self._participant_metadata = prepare_participant_metadata(
                self._participants,
                executor_id_factory=lambda name, participant: (
                    participant.id if isinstance(participant, Executor) else f"groupchat_agent:{name}"
                ),
                description_factory=lambda name, participant: (
                    participant.id if isinstance(participant, Executor) else participant.__class__.__name__
                ),
            )
        return self._participant_metadata

    def _build_participant_specs(self) -> dict[str, GroupChatParticipantSpec]:
        metadata = self._get_participant_metadata()
        descriptions: Mapping[str, str] = metadata["descriptions"]
        specs: dict[str, GroupChatParticipantSpec] = {}
        for name, participant in self._participants.items():
            specs[name] = GroupChatParticipantSpec(
                name=name,
                participant=participant,
                description=descriptions[name],
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
        - If participant selected: request routed directly to participant entry node
        - Participant pipeline: AgentExecutor for agents or custom executor chains
        - Participant response flows back to orchestrator
        - Orchestrator updates state and queries manager again
        - When manager returns finish directive: orchestrator yields final message and becomes idle

        Usage:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            # Execute the workflow
            workflow = GroupChatBuilder().set_manager(manager_agent).participants(agent1=agent1, agent2=agent2).build()
            async for message in workflow.run("Solve this problem collaboratively"):
                print(message.text)
        """
        # Manager is only required when using the default orchestrator factory
        # Custom factories (e.g., MagenticBuilder) provide their own orchestrator with embedded manager
        if (
            self._manager is None
            and self._manager_participant is None
            and self._orchestrator_factory == _default_orchestrator_factory
        ):
            raise ValueError(
                "manager must be configured before build() when using default orchestrator. "
                "Call set_manager(...) or set_select_speakers_func(...) before build()."
            )
        if not self._participants:
            raise ValueError("participants must be configured before build()")

        metadata = self._get_participant_metadata()
        participant_specs = self._build_participant_specs()
        wiring = _GroupChatConfig(
            manager=self._manager,
            manager_participant=self._manager_participant,
            manager_name=self._manager_name,
            participants=participant_specs,
            max_rounds=self._max_rounds,
            termination_condition=self._termination_condition,
            participant_aliases=metadata["aliases"],
            participant_executors=metadata["executors"],
        )

        result = assemble_group_chat_workflow(
            wiring=wiring,
            participant_factory=self._participant_factory,
            orchestrator_factory=self._orchestrator_factory,
            interceptors=self._interceptors,
            checkpoint_storage=self._checkpoint_storage,
        )
        if not isinstance(result, Workflow):
            raise TypeError("Expected Workflow from assemble_group_chat_workflow")
        return result


# endregion


# region Default manager implementation


DEFAULT_MANAGER_INSTRUCTIONS = """You are coordinating a team conversation to solve the user's task.
Your role is to orchestrate collaboration between multiple participants by selecting who speaks next.
Leverage each participant's unique expertise as described in their descriptions.
Have participants build on each other's contributions - earlier participants gather information,
later ones refine and synthesize.
Only finish the task after multiple relevant participants have contributed their expertise."""

DEFAULT_MANAGER_STRUCTURED_OUTPUT_PROMPT = """Return your decision using the following structure:
- next_agent: name of the participant who should act next (use null when finish is true)
- message: instruction for that participant (empty string if not needed)
- finish: boolean indicating if the task is complete
- final_response: when finish is true, provide the final answer to the user"""


class ManagerDirectiveModel(BaseModel):
    """Pydantic model for structured manager directive output."""

    next_agent: str | None = Field(
        default=None,
        description="Name of the participant who should act next (null when finish is true)",
    )
    message: str = Field(
        default="",
        description="Instruction for the selected participant",
    )
    finish: bool = Field(
        default=False,
        description="Whether the task is complete",
    )
    final_response: str | None = Field(
        default=None,
        description="Final answer to the user when finish is true",
    )


class _SpeakerSelectorAdapter:
    """Adapter that turns a simple speaker selector into a full manager directive."""

    def __init__(
        self,
        selector: Callable[[GroupChatStateSnapshot], Awaitable[Any]] | Callable[[GroupChatStateSnapshot], Any],
        *,
        manager_name: str,
        final_message: ChatMessage | str | Callable[[GroupChatStateSnapshot], Any] | None = None,
    ) -> None:
        self._selector = selector
        self._manager_name = manager_name
        self._final_message = final_message
        self.name = manager_name

    async def __call__(self, state: GroupChatStateSnapshot) -> GroupChatDirective:
        result = await _maybe_await(self._selector(state))
        if result is None:
            message = await self._resolve_final_message(state)
            return GroupChatDirective(finish=True, final_message=message)

        if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
            if not result:
                message = await self._resolve_final_message(state)
                return GroupChatDirective(finish=True, final_message=message)
            if len(result) != 1:  # type: ignore[arg-type]
                raise ValueError("Speaker selector must return a single participant name or None.")
            first_item = result[0]  # type: ignore[index]
            if not isinstance(first_item, str):
                raise TypeError("Speaker selector must return a participant name (str) or None.")
            result = first_item

        if not isinstance(result, str):
            raise TypeError("Speaker selector must return a participant name (str) or None.")

        return GroupChatDirective(agent_name=result)

    async def _resolve_final_message(self, state: GroupChatStateSnapshot) -> ChatMessage:
        final_message = self._final_message
        if callable(final_message):
            value = await _maybe_await(final_message(state))
        else:
            value = final_message

        if value is None:
            message = ChatMessage(
                role=Role.ASSISTANT,
                text="Conversation completed.",
                author_name=self._manager_name,
            )
        elif isinstance(value, ChatMessage):
            message = value
        else:
            message = ChatMessage(
                role=Role.ASSISTANT,
                text=str(value),
                author_name=self._manager_name,
            )

        if not message.author_name:
            patch = message.to_dict()
            patch["author_name"] = self._manager_name
            message = ChatMessage.from_dict(patch)
        return message


# endregion
