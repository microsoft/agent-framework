# Copyright (c) Microsoft. All rights reserved.

"""Group chat orchestration primitives.

This module introduces a reusable orchestration surface for orchestrator-directed
multi-agent conversations. The key components are:

- GroupChatRequestMessage / GroupChatResponseMessage: canonical envelopes used
  between the orchestrator and participants.
- GroupChatSelectionFunction: asynchronous callable for pluggable speaker selection logic.
- GroupChatOrchestrator: runtime state machine that delegates to a
  selection function to select the next participant or complete the task.
- GroupChatBuilder: high-level builder that wires orchestrators and participants
  into a workflow graph. It mirrors the ergonomics of SequentialBuilder and
  ConcurrentBuilder while allowing Magentic to reuse the same infrastructure.

The default wiring uses AgentExecutor under the hood for agent participants so
existing observability and streaming semantics continue to apply.
"""

from __future__ import annotations

import inspect
import logging
import sys
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from agent_framework import ChatAgent, SupportsAgentRun
from agent_framework._threads import AgentThread
from agent_framework._types import ChatMessage
from agent_framework._workflows._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from agent_framework._workflows._agent_utils import resolve_agent_id
from agent_framework._workflows._checkpoint import CheckpointStorage
from agent_framework._workflows._conversation_state import decode_chat_messages, encode_chat_messages
from agent_framework._workflows._executor import Executor
from agent_framework._workflows._workflow import Workflow
from agent_framework._workflows._workflow_builder import WorkflowBuilder
from agent_framework._workflows._workflow_context import WorkflowContext
from pydantic import BaseModel, Field
from typing_extensions import Never

from ._base_group_chat_orchestrator import (
    BaseGroupChatOrchestrator,
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
    GroupChatWorkflowContextOutT,
    ParticipantRegistry,
    TerminationCondition,
)
from ._orchestration_request_info import AgentApprovalExecutor
from ._orchestrator_helpers import clean_conversation_for_handoff

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupChatState:
    """Immutable state of the group chat for the selection function to determine the next speaker.

    Attributes:
        current_round: The current round index of the group chat, starting from 0.
        participants: A mapping of participant names to their descriptions in the group chat.
        conversation: The full conversation history up to this point as a list of ChatMessage.
    """

    # Round index, starting from 0
    current_round: int
    # participant name to description mapping as a ordered dict
    participants: OrderedDict[str, str]
    # Full conversation history up to this point
    conversation: list[ChatMessage]


# region Default orchestrator


# Type alias for the selection function used by the orchestrator to choose the next speaker.
GroupChatSelectionFunction = Callable[[GroupChatState], Awaitable[str] | str]


class GroupChatOrchestrator(BaseGroupChatOrchestrator):
    """Orchestrator that manages a group chat between multiple participants.

    This group chat orchestrator operates under the direction of a selection function
    provided at initialization. The selection function receives the current state of
    the group chat and returns the name of the next participant to speak.

    This orchestrator drives the conversation loop as follows:
    1. Receives initial messages, saves to history, and broadcasts to all participants
    2. Invokes the selection function to determine the next speaker based on the most recent state
    3. Sends a request to the selected participant to generate a response
    4. Receives the participant's response, saves to history, and broadcasts to all participants
       except the one that just spoke
    5. Repeats steps 2-4 until the termination conditions are met

    This is the most basic orchestrator, great for getting started with multi-agent
    conversations. More advanced orchestrators can be built by extending BaseGroupChatOrchestrator
    and implementing custom logic in the message and response handlers.
    """

    def __init__(
        self,
        id: str,
        participant_registry: ParticipantRegistry,
        selection_func: GroupChatSelectionFunction,
        *,
        name: str | None = None,
        max_rounds: int | None = None,
        termination_condition: TerminationCondition | None = None,
    ) -> None:
        """Initialize the GroupChatOrchestrator.

        Args:
            id: Unique executor ID for the orchestrator. The ID must be unique within the workflow.
            participant_registry: Registry of participants in the group chat that track executor types
                (agents vs. executors) and provide resolution utilities.
            selection_func: Function to select the next speaker based on conversation state
            name: Optional display name for the orchestrator in the messages, defaults to executor ID.
                A more descriptive name that is not an ID could help models better understand the role
                of the orchestrator in multi-agent conversations. If the ID is not human-friendly,
                providing a name can improve context for the agents.
            max_rounds: Optional limit on selection rounds to prevent infinite loops.
            termination_condition: Optional callable that halts the conversation when it returns True

        Note: If neither `max_rounds` nor `termination_condition` is provided, the conversation
        will continue indefinitely. It is recommended to always set one of these to ensure proper termination.

        Example:
        .. code-block:: python

            from agent_framework_orchestrations import GroupChatOrchestrator


            async def round_robin_selector(state: GroupChatState) -> str:
                # Simple round-robin selection among participants
                return state.participants[state.current_round % len(state.participants)]


            orchestrator = GroupChatOrchestrator(
                id="group_chat_orchestrator_1",
                selection_func=round_robin_selector,
                participants=["researcher", "writer"],
                name="Coordinator",
                max_rounds=10,
            )
        """
        super().__init__(
            id,
            participant_registry,
            name=name,
            max_rounds=max_rounds,
            termination_condition=termination_condition,
        )
        self._selection_func = selection_func

    @override
    async def _handle_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[GroupChatWorkflowContextOutT, list[ChatMessage]],
    ) -> None:
        """Initialize orchestrator state and start the conversation loop."""
        self._append_messages(messages)
        # Termination condition will also be applied to the input messages
        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        next_speaker = await self._get_next_speaker()

        # Broadcast messages to all participants for context
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            next_speaker,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )
        self._increment_round()

    @override
    async def _handle_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContextOutT, list[ChatMessage]],
    ) -> None:
        """Handle a participant response."""
        messages = self._process_participant_response(response)
        # Remove tool-related content to prevent API errors from empty messages
        messages = clean_conversation_for_handoff(messages)
        self._append_messages(messages)

        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return
        if await self._check_round_limit_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        next_speaker = await self._get_next_speaker()

        # Broadcast participant messages to all participants for context, except
        # the participant that just responded
        participant = ctx.get_source_executor_id()
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
            participants=[p for p in self._participant_registry.participants if p != participant],
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            next_speaker,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )
        self._increment_round()

    async def _get_next_speaker(self) -> str:
        """Determine the next speaker using the selection function."""
        group_chat_state = GroupChatState(
            current_round=self._round_index,
            participants=self._participant_registry.participants,
            conversation=self._get_conversation(),
        )

        next_speaker = self._selection_func(group_chat_state)
        if inspect.isawaitable(next_speaker):
            next_speaker = await next_speaker

        if next_speaker not in self._participant_registry.participants:
            raise RuntimeError(f"Selection function returned unknown participant '{next_speaker}'.")

        return next_speaker


# endregion

# region Agent-based orchestrator


class AgentOrchestrationOutput(BaseModel):
    """Structured output type for the agent in AgentBasedGroupChatOrchestrator."""

    model_config = {
        "extra": "forbid",
        # OpenAI strict mode requires all properties to be in required array
        "json_schema_extra": {"required": ["terminate", "reason", "next_speaker", "final_message"]},
    }

    # Whether to terminate the conversation
    terminate: bool
    # An explanation for the decision made
    reason: str
    # Next speaker to select if not terminating
    next_speaker: str | None = Field(
        default=None,
        description="Name of the next participant to speak (if not terminating)",
    )
    # Optional final message to send if terminating
    final_message: str | None = Field(default=None, description="Optional final message if terminating")


class AgentBasedGroupChatOrchestrator(BaseGroupChatOrchestrator):
    """Orchestrator that manages a group chat between multiple participants.

    This group chat orchestrator is driven by an agent that can select the next speaker
    intelligently based on the conversation context.

    This orchestrator drives the conversation loop as follows:
    1. Receives initial messages, saves to history, and broadcasts to all participants
    2. Invokes the agent to determine the next speaker based on the most recent state
    3. Sends a request to the selected participant to generate a response
    4. Receives the participant's response, saves to history, and broadcasts to all participants
       except the one that just spoke
    5. Repeats steps 2-4 until the termination conditions are met

    Note: The agent will be asked to generate a structured output of type `AgentOrchestrationOutput`,
    thus it must be capable of structured output.
    """

    def __init__(
        self,
        agent: ChatAgent,
        participant_registry: ParticipantRegistry,
        *,
        max_rounds: int | None = None,
        termination_condition: TerminationCondition | None = None,
        retry_attempts: int | None = None,
        thread: AgentThread | None = None,
    ) -> None:
        """Initialize the GroupChatOrchestrator.

        Args:
            agent: Agent that selects the next speaker based on conversation state
            participant_registry: Registry of participants in the group chat that track executor types
                (agents vs. executors) and provide resolution utilities.
            max_rounds: Optional limit on selection rounds to prevent infinite loops.
            termination_condition: Optional callable that halts the conversation when it returns True
            retry_attempts: Optional number of retry attempts for the agent in case of failure.
            thread: Optional agent thread to use for the orchestrator agent.
        """
        super().__init__(
            resolve_agent_id(agent),
            participant_registry,
            name=agent.name,
            max_rounds=max_rounds,
            termination_condition=termination_condition,
        )
        self._agent = agent
        self._retry_attempts = retry_attempts
        self._thread = thread or agent.get_new_thread()
        # Cache for messages since last agent invocation
        # This is different from the full conversation history maintained by the base orchestrator
        self._cache: list[ChatMessage] = []

    @override
    def _append_messages(self, messages: Sequence[ChatMessage]) -> None:
        self._cache.extend(messages)
        return super()._append_messages(messages)

    @override
    async def _handle_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[GroupChatWorkflowContextOutT, list[ChatMessage]],
    ) -> None:
        """Initialize orchestrator state and start the conversation loop."""
        self._append_messages(messages)
        # Termination condition will also be applied to the input messages
        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        agent_orchestration_output = await self._invoke_agent()
        if await self._check_agent_terminate_and_yield(
            agent_orchestration_output,
            cast(WorkflowContext[Never, list[ChatMessage]], ctx),
        ):
            return

        # Broadcast messages to all participants for context
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            # If not terminating, next_speaker must be provided thus will not be None
            agent_orchestration_output.next_speaker,  # type: ignore[arg-type]
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )
        self._increment_round()

    @override
    async def _handle_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContextOutT, list[ChatMessage]],
    ) -> None:
        """Handle a participant response."""
        messages = self._process_participant_response(response)
        # Remove tool-related content to prevent API errors from empty messages
        messages = clean_conversation_for_handoff(messages)
        self._append_messages(messages)
        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return
        if await self._check_round_limit_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        agent_orchestration_output = await self._invoke_agent()
        if await self._check_agent_terminate_and_yield(
            agent_orchestration_output,
            cast(WorkflowContext[Never, list[ChatMessage]], ctx),
        ):
            return

        # Broadcast participant messages to all participants for context, except
        # the participant that just responded
        participant = ctx.get_source_executor_id()
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
            participants=[p for p in self._participant_registry.participants if p != participant],
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            # If not terminating, next_speaker must be provided thus will not be None
            agent_orchestration_output.next_speaker,  # type: ignore[arg-type]
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )
        self._increment_round()

    async def _invoke_agent(self) -> AgentOrchestrationOutput:
        """Invoke the orchestrator agent to determine the next speaker and termination."""

        async def _invoke_agent_helper(conversation: list[ChatMessage]) -> AgentOrchestrationOutput:
            # Run the agent in non-streaming mode for simplicity
            agent_response = await self._agent.run(
                messages=conversation,
                thread=self._thread,
                options={"response_format": AgentOrchestrationOutput},
            )
            # Parse and validate the structured output
            agent_orchestration_output = AgentOrchestrationOutput.model_validate_json(agent_response.text)

            if not agent_orchestration_output.terminate and not agent_orchestration_output.next_speaker:
                raise ValueError("next_speaker must be provided if not terminating the conversation.")

            return agent_orchestration_output

        # We only need the last message for context since history is maintained in the thread
        current_conversation = self._cache.copy()
        self._cache.clear()
        instruction = (
            "Decide what to do next. Respond with a JSON object of the following format:\n"
            "{\n"
            '  "terminate": <true|false>,\n'
            '  "reason": "<explanation for the decision>",\n'
            '  "next_speaker": "<name of the next participant to speak (if not terminating)>",\n'
            '  "final_message": "<optional final message if terminating>"\n'
            "}\n"
            "If not terminating, here are the valid participant names (case-sensitive) and their descriptions:\n"
            + "\n".join([
                f"{name}: {description}" for name, description in self._participant_registry.participants.items()
            ])
        )
        # Prepend instruction as system message
        current_conversation.append(ChatMessage(role="user", text=instruction))

        retry_attempts = self._retry_attempts
        while True:
            try:
                return await _invoke_agent_helper(current_conversation)
            except Exception as ex:
                logger.error(f"Agent orchestration invocation failed: {ex}")
                if retry_attempts is None or retry_attempts <= 0:
                    raise
                retry_attempts -= 1
                logger.debug(f"Retrying agent orchestration invocation, attempts left: {retry_attempts}")
                # We don't need the full conversation since the thread should maintain history
                current_conversation = [
                    ChatMessage(
                        role="user",
                        text=f"Your input could not be parsed due to an error: {ex}. Please try again.",
                    )
                ]

    async def _check_agent_terminate_and_yield(
        self,
        agent_orchestration_output: AgentOrchestrationOutput,
        ctx: WorkflowContext[Never, list[ChatMessage]],
    ) -> bool:
        """Check if the agent requested termination and yield completion if so.

        Args:
            agent_orchestration_output: Output from the orchestrator agent
            ctx: Workflow context for yielding output
        Returns:
            True if termination was requested and output was yielded, False otherwise
        """
        if agent_orchestration_output.terminate:
            final_message = (
                agent_orchestration_output.final_message or "The conversation has been terminated by the agent."
            )
            self._append_messages([self._create_completion_message(final_message)])
            await ctx.yield_output(self._full_conversation)
            return True

        return False

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture current orchestrator state for checkpointing."""
        state = await super().on_checkpoint_save()
        state["cache"] = encode_chat_messages(self._cache)
        serialized_thread = await self._thread.serialize()
        state["thread"] = serialized_thread

        return state

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore executor state from checkpoint."""
        await super().on_checkpoint_restore(state)
        self._cache = decode_chat_messages(state.get("cache", []))
        serialized_thread = state.get("thread")
        if serialized_thread:
            self._thread = await self._agent.deserialize_thread(serialized_thread)


# endregion

# region Builder


class GroupChatBuilder:
    r"""High-level builder for group chat workflows.

    GroupChat coordinates multi-agent conversations using an orchestrator that can dynamically
    select participants to speak at each turn based on the conversation state.

    Routing Pattern:
    Agents respond in turns as directed by the orchestrator until termination conditions are met.
    This provides a centralized approach to multi-agent collaboration, similar to a star topology.

    Participants can be a combination of agents and executors. If they are executors, they
    must implement the expected handlers for receiving GroupChat messages and returning responses
    (Read our official documentation for details on implementing custom participant executors).

    The orchestrator can be provided directly, or a simple selection function can be defined
    to choose the next speaker based on the current state. The builder wires everything together
    into a complete workflow graph that can be executed.

    Outputs:
    The final conversation history as a list of ChatMessage once the group chat completes.
    """

    DEFAULT_ORCHESTRATOR_ID: ClassVar[str] = "group_chat_orchestrator"

    def __init__(
        self,
        *,
        participants: Sequence[SupportsAgentRun | Executor],
        # Orchestrator config (exactly one required)
        orchestrator_agent: ChatAgent | Callable[[], ChatAgent] | None = None,
        orchestrator: BaseGroupChatOrchestrator | Callable[[], BaseGroupChatOrchestrator] | None = None,
        selection_func: GroupChatSelectionFunction | None = None,
        orchestrator_name: str | None = None,
        # Existing params
        termination_condition: TerminationCondition | None = None,
        max_rounds: int | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        intermediate_outputs: bool = False,
    ) -> None:
        """Initialize the GroupChatBuilder.

        Args:
            participants: Sequence of agent or executor instances for the group chat.
            orchestrator_agent: An instance of ChatAgent or a callable that produces one to manage the group chat.
            orchestrator: An instance of BaseGroupChatOrchestrator or a callable that produces one to manage the
                group chat.
            selection_func: Callable that receives the current GroupChatState and returns the name of the next
                participant to speak.
            orchestrator_name: Optional display name for the orchestrator when using a selection function.
            termination_condition: Optional callable that receives the conversation history and returns
                True to terminate the conversation, False to continue.
            max_rounds: Optional maximum number of orchestrator rounds to prevent infinite conversations.
            checkpoint_storage: Optional checkpoint storage for enabling workflow state persistence.
            intermediate_outputs: If True, enables intermediate outputs from agent participants.
        """
        self._participants: dict[str, SupportsAgentRun | Executor] = {}

        # Orchestrator related members
        self._orchestrator: BaseGroupChatOrchestrator | None = None
        self._orchestrator_factory: Callable[[], ChatAgent | BaseGroupChatOrchestrator] | None = None
        self._selection_func: GroupChatSelectionFunction | None = None
        self._agent_orchestrator: ChatAgent | None = None
        self._termination_condition: TerminationCondition | None = termination_condition
        self._max_rounds: int | None = max_rounds
        self._orchestrator_name: str | None = None

        # Checkpoint related members
        self._checkpoint_storage: CheckpointStorage | None = checkpoint_storage

        # Request info related members
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] = set()

        # Intermediate outputs
        self._intermediate_outputs = intermediate_outputs

        self._set_participants(participants)

        # Set orchestrator if provided
        if any(x is not None for x in [orchestrator_agent, orchestrator, selection_func]):
            self._set_orchestrator(
                orchestrator_agent=orchestrator_agent,
                orchestrator=orchestrator,
                selection_func=selection_func,
                orchestrator_name=orchestrator_name,
            )

    def _set_orchestrator(
        self,
        *,
        orchestrator_agent: ChatAgent | Callable[[], ChatAgent] | None = None,
        orchestrator: BaseGroupChatOrchestrator | Callable[[], BaseGroupChatOrchestrator] | None = None,
        selection_func: GroupChatSelectionFunction | None = None,
        orchestrator_name: str | None = None,
    ) -> None:
        """Set the orchestrator for this group chat workflow (internal).

        Args:
            orchestrator_agent: An instance of ChatAgent or a callable that produces one to manage the group chat.
            orchestrator: An instance of BaseGroupChatOrchestrator or a callable that produces one to manage the group
                          chat.
            selection_func: Callable that receives the current GroupChatState and returns
                            the name of the next participant to speak, or None to finish.
            orchestrator_name: Optional display name for the orchestrator in the workflow if
                               using a selection function. If not provided, defaults to
                               `GroupChatBuilder.DEFAULT_ORCHESTRATOR_ID`. This parameter is
                               ignored if using an agent or custom orchestrator.

        Raises:
            ValueError: If an orchestrator has already been set or if none or multiple
                        of the parameters are provided.
        """
        if self._agent_orchestrator is not None:
            raise ValueError("An agent orchestrator has already been configured. Set orchestrator config once only.")

        if self._orchestrator is not None:
            raise ValueError("An orchestrator has already been configured. Set orchestrator config once only.")

        if self._orchestrator_factory is not None:
            raise ValueError("A factory has already been configured. Set orchestrator config once only.")

        if self._selection_func is not None:
            raise ValueError("A selection function has already been configured. Set orchestrator config once only.")

        if sum(x is not None for x in [orchestrator_agent, orchestrator, selection_func]) != 1:
            raise ValueError("Exactly one of orchestrator_agent, orchestrator, or selection_func must be provided.")

        if orchestrator_agent is not None and isinstance(orchestrator_agent, ChatAgent):
            self._agent_orchestrator = orchestrator_agent
        elif orchestrator is not None and isinstance(orchestrator, BaseGroupChatOrchestrator):
            self._orchestrator = orchestrator
        elif selection_func is not None:
            self._selection_func = selection_func
            self._orchestrator_name = orchestrator_name
        else:
            self._orchestrator_factory = orchestrator_agent or orchestrator

    def _set_participants(self, participants: Sequence[SupportsAgentRun | Executor]) -> None:
        """Set participants (internal)."""
        if self._participants:
            raise ValueError("participants already set.")

        if not participants:
            raise ValueError("participants cannot be empty.")

        # Name of the executor mapped to participant instance
        named: dict[str, SupportsAgentRun | Executor] = {}
        for participant in participants:
            if isinstance(participant, Executor):
                identifier = participant.id
            elif isinstance(participant, SupportsAgentRun):
                if not participant.name:
                    raise ValueError("SupportsAgentRun participants must have a non-empty name.")
                identifier = participant.name
            else:
                raise TypeError(
                    f"Participants must be SupportsAgentRun or Executor instances. Got {type(participant).__name__}."
                )

            if identifier in named:
                raise ValueError(f"Duplicate participant name '{identifier}' detected")

            named[identifier] = participant

        self._participants = named

    def with_termination_condition(self, termination_condition: TerminationCondition) -> GroupChatBuilder:
        """Set a custom termination condition for the group chat workflow.

        Args:
            termination_condition: Callable that receives the conversation history and returns
                                   True to terminate the conversation, False to continue.

        Returns:
            Self for fluent chaining

        Example:

        .. code-block:: python

            from agent_framework import ChatMessage
            from agent_framework_orchestrations import GroupChatBuilder


            def stop_after_two_calls(conversation: list[ChatMessage]) -> bool:
                calls = sum(1 for msg in conversation if msg.role == "assistant" and msg.author_name == "specialist")
                return calls >= 2


            specialist_agent = ...
            workflow = (
                GroupChatBuilder(
                    participants=[agent1, specialist_agent],
                    selection_func=my_selection_function,
                )
                .with_termination_condition(stop_after_two_calls)
                .build()
            )
        """
        if self._orchestrator is not None or self._orchestrator_factory is not None:
            logger.warning(
                "Orchestrator has already been configured; setting termination condition on builder has no effect."
            )

        self._termination_condition = termination_condition
        return self

    def with_max_rounds(self, max_rounds: int | None) -> GroupChatBuilder:
        """Set a maximum number of orchestrator rounds to prevent infinite conversations.

        When the round limit is reached, the workflow automatically completes with
        a default completion message. Setting to None allows unlimited rounds.

        Args:
            max_rounds: Maximum number of orchestrator selection rounds, or None for unlimited

        Returns:
            Self for fluent chaining
        """
        if self._orchestrator is not None or self._orchestrator_factory is not None:
            logger.warning("Orchestrator has already been configured; setting max rounds on builder has no effect.")

        self._max_rounds = max_rounds
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> GroupChatBuilder:
        """Enable checkpointing for the built workflow using the provided storage.

        Checkpointing allows the workflow to persist state and resume from interruption
        points, enabling long-running conversations and failure recovery.

        Args:
            checkpoint_storage: Storage implementation for persisting workflow state

        Returns:
            Self for fluent chaining

        Example:

        .. code-block:: python

            from agent_framework import MemoryCheckpointStorage
            from agent_framework_orchestrations import GroupChatBuilder

            storage = MemoryCheckpointStorage()
            workflow = (
                GroupChatBuilder(
                    participants=[agent1, agent2],
                    selection_func=my_selection_function,
                )
                .with_checkpointing(storage)
                .build()
            )
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_info(self, *, agents: Sequence[str | SupportsAgentRun] | None = None) -> GroupChatBuilder:
        """Enable request info after agent participant responses.

        This enables human-in-the-loop (HIL) scenarios for the group chat orchestration.
        When enabled, the workflow pauses after each agent participant runs, emitting
        a request_info event (type='request_info') that allows the caller to review the conversation and optionally
        inject guidance for the agent participant to iterate. The caller provides input via
        the standard response_handler/request_info pattern.

        Simulated flow with HIL:
        Input -> Orchestrator -> [Participant <-> Request Info] -> Orchestrator -> [Participant <-> Request Info] -> ...

        Note: This is only available for agent participants. Executor participants can incorporate
        request info handling in their own implementation if desired.

        Args:
            agents: Optional list of agents names to enable request info for.
                    If None, enables HIL for all agent participants.

        Returns:
            Self for fluent chaining
        """
        from ._orchestration_request_info import resolve_request_info_filter

        self._request_info_enabled = True
        self._request_info_filter = resolve_request_info_filter(list(agents) if agents else None)

        return self

    def _resolve_orchestrator(self, participants: Sequence[Executor]) -> Executor:
        """Determine the orchestrator to use for the workflow.

        Args:
            participants: List of resolved participant executors
        """
        if all(
            x is None
            for x in [self._agent_orchestrator, self._selection_func, self._orchestrator, self._orchestrator_factory]
        ):
            raise ValueError(
                "No orchestrator has been configured. "
                "Pass orchestrator_agent, orchestrator, or selection_func to the constructor."
            )
        # We don't need to check if multiple are set since that is handled in _set_orchestrator()

        if self._agent_orchestrator:
            return AgentBasedGroupChatOrchestrator(
                agent=self._agent_orchestrator,
                participant_registry=ParticipantRegistry(participants),
                max_rounds=self._max_rounds,
                termination_condition=self._termination_condition,
            )

        if self._selection_func:
            return GroupChatOrchestrator(
                id=self.DEFAULT_ORCHESTRATOR_ID,
                participant_registry=ParticipantRegistry(participants),
                selection_func=self._selection_func,
                name=self._orchestrator_name,
                max_rounds=self._max_rounds,
                termination_condition=self._termination_condition,
            )

        if self._orchestrator:
            return self._orchestrator

        if self._orchestrator_factory:
            orchestrator_instance = self._orchestrator_factory()
            if isinstance(orchestrator_instance, ChatAgent):
                return AgentBasedGroupChatOrchestrator(
                    agent=orchestrator_instance,
                    participant_registry=ParticipantRegistry(participants),
                    max_rounds=self._max_rounds,
                    termination_condition=self._termination_condition,
                )
            if isinstance(orchestrator_instance, BaseGroupChatOrchestrator):
                return orchestrator_instance
            raise TypeError(
                f"Orchestrator factory must return ChatAgent or BaseGroupChatOrchestrator instance. "
                f"Got {type(orchestrator_instance).__name__}."
            )

        # This should never be reached due to the checks above
        raise RuntimeError(
            "Orchestrator could not be resolved. "
            "Pass orchestrator_agent, orchestrator, or selection_func to the constructor."
        )

    def _resolve_participants(self) -> list[Executor]:
        """Resolve participant instances into Executor objects."""
        if not self._participants:
            raise ValueError("No participants provided. Pass participants to the constructor.")

        participants: list[Executor | SupportsAgentRun] = list(self._participants.values())

        executors: list[Executor] = []
        for participant in participants:
            if isinstance(participant, Executor):
                executors.append(participant)
            elif isinstance(participant, SupportsAgentRun):
                if self._request_info_enabled and (
                    not self._request_info_filter or resolve_agent_id(participant) in self._request_info_filter
                ):
                    # Handle request info enabled agents
                    executors.append(AgentApprovalExecutor(participant))
                else:
                    executors.append(AgentExecutor(participant))
            else:
                raise TypeError(
                    f"Participants must be SupportsAgentRun or Executor instances. Got {type(participant).__name__}."
                )

        return executors

    def build(self) -> Workflow:
        """Build and validate the group chat workflow.

        Assembles the orchestrator and participants into a complete workflow graph.
        The workflow graph consists of bi-directional edges between the orchestrator and each participant,
        allowing for message exchanges in both directions.

        Returns:
            Validated Workflow instance ready for execution
        """
        # Resolve orchestrator and participants to executors
        participants: list[Executor] = self._resolve_participants()
        orchestrator: Executor = self._resolve_orchestrator(participants)

        # Build workflow graph
        workflow_builder = WorkflowBuilder(
            start_executor=orchestrator,
            checkpoint_storage=self._checkpoint_storage,
            output_executors=[orchestrator] if not self._intermediate_outputs else None,
        )
        for participant in participants:
            # Orchestrator and participant bi-directional edges
            workflow_builder = workflow_builder.add_edge(orchestrator, participant)
            workflow_builder = workflow_builder.add_edge(participant, orchestrator)

        return workflow_builder.build()


# endregion
