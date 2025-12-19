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

import inspect
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar, Never, cast

from pydantic import BaseModel, Field

from agent_framework import AgentExecutor, AgentExecutorRequest, AgentThread, ChatAgent, Role

from .._agents import AgentProtocol
from .._types import ChatMessage
from ._agent_executor import AgentExecutorResponse
from ._base_group_chat_orchestrator import (
    BaseGroupChatOrchestrator,
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
    GroupChatWorkflowContext_T_Out,
    TerminationCondition,
)
from ._checkpoint import CheckpointStorage
from ._executor import Executor
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupChatState:
    """Immutable state of the group chat for the selection function to determine the next speaker."""

    current_round: int
    participants: list[str]
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

    # TODO (@taochen): HIL
    # Input -> Orchestrator -> Participant A -> HIL -> Orchestrator -> HIL -> Participant B -> HIL -> Orchestrator -> HIL -> Orchestrator -> Output
    # Input -> Orchestrator -> Participant A -> (Orchestrator -> HIL -> Orchestrator) -> Participant B -> (Orchestrator -> HIL -> Orchestrator) -> Output

    def __init__(
        self,
        id: str,
        selection_func: GroupChatSelectionFunction,
        *,
        participants: list[str],
        name: str | None = None,
        max_rounds: int | None = None,
        termination_condition: TerminationCondition | None = None,
    ) -> None:
        """Initialize the GroupChatOrchestrator.

        Args:
            id: Unique executor ID for the orchestrator. The ID must be unique within the workflow.
            selection_func: Function to select the next speaker based on conversation state
            participants: List of participant names in the group chat. This should match the
                executor IDs of the participants.
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

            from agent_framework import GroupChatOrchestrator


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
        super().__init__(id, name=name, max_rounds=max_rounds, termination_condition=termination_condition)
        self._selection_func = selection_func
        self._participants = participants

    @override
    async def _handle_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Initialize orchestrator state and start the conversation loop."""
        self._append_messages(messages)
        # Termination condition will also be applied to the input messages
        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        next_speaker = await self._get_next_speaker()
        self._increment_round()

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

    @override
    async def _handle_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Handle a participant response."""
        messages = self._process_participant_response(response)
        self._append_messages(messages)

        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return
        if await self._check_round_limit_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        next_speaker = await self._get_next_speaker()
        self._increment_round()

        # Broadcast participant messages to all participants for context, except
        # the participant that just responded
        participant = ctx.get_source_executor_id()
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
            participants=[p for p in self._participants if p != participant],
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            next_speaker,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )

    async def _get_next_speaker(self) -> str:
        """Determine the next speaker using the selection function."""
        group_chat_state = GroupChatState(
            current_round=self._round_index,
            participants=self._participants,
            conversation=self._get_conversation(),
        )

        next_speaker = self._selection_func(group_chat_state)
        if inspect.isawaitable(next_speaker):
            next_speaker = await next_speaker

        if next_speaker not in self._participants:
            raise RuntimeError(f"Selection function returned unknown participant '{next_speaker}'.")

        return next_speaker


# endregion

# region Agent-based orchestrator


class AgentOrchestrationOutput(BaseModel):
    """Structured output type for the agent in AgentBasedGroupChatOrchestrator."""

    model_config = {
        "extra": "forbid",
        # OpenAI strict mode requires all properties to be in required array
        "json_schema_extra": {"required": ["terminate", "next_speaker", "final_message"]},
    }

    # Whether to terminate the conversation
    terminate: bool
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
        *,
        participants: list[str],
        max_rounds: int | None = None,
        termination_condition: TerminationCondition | None = None,
        retry_attempts: int | None = None,
        thread: AgentThread | None = None,
    ) -> None:
        """Initialize the GroupChatOrchestrator.

        Args:
            agent: Agent that selects the next speaker based on conversation state
            participants: List of participant names in the group chat. This should match the
                executor IDs of the participants.
            name: Optional display name for the orchestrator in the messages, defaults to executor ID.
                A more descriptive name that is not an ID could help models better understand the role
                of the orchestrator in multi-agent conversations. If the ID is not human-friendly,
                providing a name can improve context for the agents.
            max_rounds: Optional limit on selection rounds to prevent infinite loops.
            termination_condition: Optional callable that halts the conversation when it returns True
            retry_attempts: Optional number of retry attempts for the agent in case of failure.
            thread: Optional agent thread to use for the orchestrator agent.
        """
        super().__init__(agent.id, name=agent.name, max_rounds=max_rounds, termination_condition=termination_condition)
        self._agent = agent
        self._participants = participants
        self._retry_attempts = retry_attempts
        self._thread = thread or agent.get_new_thread()

    @override
    async def _handle_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
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

        self._increment_round()

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

    @override
    async def _handle_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Handle a participant response."""
        messages = self._process_participant_response(response)
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
        self._increment_round()

        # Broadcast participant messages to all participants for context, except
        # the participant that just responded
        participant = ctx.get_source_executor_id()
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
            participants=[p for p in self._participants if p != participant],
        )
        # Send request to selected participant
        await self._send_request_to_participant(
            # If not terminating, next_speaker must be provided thus will not be None
            agent_orchestration_output.next_speaker,  # type: ignore[arg-type]
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
        )

    async def _invoke_agent(self) -> AgentOrchestrationOutput:
        """Invoke the orchestrator agent to determine the next speaker and termination."""

        async def _invoke_agent_helper(conversation: list[ChatMessage]) -> AgentOrchestrationOutput:
            # Run the agent in non-streaming mode for simplicity
            agent_response = await self._agent.run(
                messages=conversation,
                thread=self._thread,
                response_format=AgentOrchestrationOutput,
            )
            # Parse and validate the structured output
            agent_orchestration_output = AgentOrchestrationOutput.model_validate_json(agent_response.text)

            if not agent_orchestration_output.terminate and not agent_orchestration_output.next_speaker:
                raise ValueError("next_speaker must be provided if not terminating the conversation.")

            return agent_orchestration_output

        current_conversation = self._get_conversation()
        instruction = (
            "Based on the current conversation, decide what to do next.\n"
            "Respond with a JSON object of the following format:\n"
            "{\n"
            '  "terminate": <true|false>,\n'
            '  "next_speaker": "<name of the next participant to speak (if not terminating)>",\n'
            '  "final_message": "<optional final message if terminating>"\n'
            "}\n"
            "If not terminating, here are the valid participant names (case-sensitive):\n"
            f"{', '.join(self._participants)}"
        )
        # Prepend instruction as system message
        current_conversation.append(ChatMessage(role=Role.USER, text=instruction))

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
                current_conversation = [
                    ChatMessage(
                        role=Role.USER,
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
            await ctx.yield_output(self._conversation)
            return True

        return False


# endregion

# region Builder


class GroupChatBuilder:
    r"""High-level builder for group chat workflows.

    GroupChat coordinates multi-agent conversations using an orchestrator that can dynamically
    select participants to speak at each turn based on the conversation state.

    All participants can be a combination of agents and executors. If they are executors, they
    must implement the expected handlers for receiving GroupChat messages and returning responses
    (Read our official documentation for details on implementing custom participant executors).

    The orchestrator can be provided directly, or a simple selection function can be defined
    to choose the next speaker based on the current state. The builder wires everything together
    into a complete workflow graph that can be executed.
    """

    DEFAULT_ORCHESTRATOR_ID: ClassVar[str] = "group_chat_orchestrator"

    def __init__(self) -> None:
        """Initialize the GroupChatBuilder."""
        self._participants: dict[str, AgentProtocol | Executor] = {}
        # Orchestrator related members
        self._orchestrator: BaseGroupChatOrchestrator | None = None
        self._selection_func: GroupChatSelectionFunction | None = None
        self._termination_condition: TerminationCondition | None = None
        self._max_rounds: int | None = None
        self._orchestrator_name: str | None = None
        # Checkpoint related members
        self._checkpoint_storage: CheckpointStorage | None = None
        # Request info related members
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] = set()

    def with_orchestrator(self, orchestrator: BaseGroupChatOrchestrator) -> "GroupChatBuilder":
        """Set the orchestrator for this group chat workflow.

        An group chat orchestrator is responsible for managing the flow of conversation, making
        sure all participants are synced and picking the next speaker according to the defined logic
        until the termination conditions are met.

        Args:
            orchestrator: An instance of GroupChatOrchestrator to manage the group chat.

        Returns:
            Self for fluent chaining.

        Example:
        .. code-block:: python

            from agent_framework import GroupChatBuilder, GroupChatOrchestrator


            orchestrator = GroupChatOrchestrator(...)
            workflow = GroupChatBuilder().with_orchestrator(orchestrator).participants([agent1, agent2]).build()
        """
        if self._orchestrator is not None:
            raise ValueError("Orchestrator has already been configured. Call with_orchestrator(...) at most once.")

        if self._selection_func is not None:
            raise ValueError(
                "select_speakers_func has already been configured. Call with_orchestrator(...) or "
                "with_select_speakers_func(...) but not both."
            )

        self._orchestrator = orchestrator
        return self

    def with_select_speaker_func(
        self,
        selection_func: GroupChatSelectionFunction,
        *,
        orchestrator_name: str | None = None,
    ) -> "GroupChatBuilder":
        """Define a custom function to select the next speaker in the group chat.

        This is a quick way to implement simple orchestration logic without needing a full
        GroupChatOrchestrator. The provided function receives the current state of
        the group chat and returns the name of the next participant to speak.

        Args:
            selection_func: Callable that receives the current GroupChatState and returns
                            the name of the next participant to speak, or None to finish.
            orchestrator_name: Optional display name for the orchestrator in the workflow.
                            If not provided, defaults to `GroupChatBuilder.DEFAULT_ORCHESTRATOR_ID`.

        Returns:
            Self for fluent chaining

        Example:
        .. code-block:: python

            from agent_framework import GroupChatBuilder, GroupChatState


            async def round_robin_selector(state: GroupChatState) -> str:
                # Simple round-robin selection among participants
                return state.participants[state.current_round % len(state.participants)]


            workflow = (
                GroupChatBuilder()
                .with_select_speaker_func(round_robin_selector, orchestrator_name="Coordinator")
                .participants([agent1, agent2])
                .build()
            )
        """
        if self._selection_func is not None:
            raise ValueError(
                "select_speakers_func has already been configured. Call with_select_speakers_func(...) at most once."
            )

        if self._orchestrator is not None:
            raise ValueError(
                "Orchestrator has already been configured. Call with_orchestrator(...) or "
                "with_select_speakers_func(...) but not both."
            )

        self._selection_func = selection_func
        self._orchestrator_name = orchestrator_name
        return self

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "GroupChatBuilder":
        """Define participants for this group chat workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.

        Args:
            participants: Sequence of participant definitions

        Returns:
            Self for fluent chaining

        Raises:
            ValueError: If participants are empty, names are duplicated, or already set
            TypeError: If any participant is not AgentProtocol or Executor instance

        Example:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            workflow = (
                GroupChatBuilder()
                .with_select_speaker_func(my_selection_function)
                .participants([agent1, agent2, custom_executor])
                .build()
            )
        """
        if self._participants:
            raise ValueError("participants have already been set. Call participants(...) at most once.")

        if not participants:
            raise ValueError("participants cannot be empty.")

        # Name of the executor mapped to participant instance
        named: dict[str, AgentProtocol | Executor] = {}
        for participant in participants:
            if isinstance(participant, Executor):
                identifier = participant.id
            elif isinstance(participant, AgentProtocol):
                identifier = participant.display_name
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

            if identifier in named:
                raise ValueError(f"Duplicate participant name '{identifier}' detected")

            named[identifier] = participant

        self._participants = named

        return self

    def with_termination_condition(self, termination_condition: TerminationCondition) -> "GroupChatBuilder":
        """Set a custom termination condition for the group chat workflow.

        Args:
            termination_condition: Callable that receives the conversation history and returns
                                   True to terminate the conversation, False to continue.

        Returns:
            Self for fluent chaining

        Example:

        .. code-block:: python

            from agent_framework import ChatMessage, GroupChatBuilder, Role


            def stop_after_two_calls(conversation: list[ChatMessage]) -> bool:
                calls = sum(1 for msg in conversation if msg.role == Role.ASSISTANT and msg.author_name == "specialist")
                return calls >= 2


            specialist_agent = ...
            workflow = (
                GroupChatBuilder()
                .with_select_speaker_func(my_selection_function)
                .participants([agent1, specialist_agent])
                .with_termination_condition(stop_after_two_calls)
                .build()
            )
        """
        if self._orchestrator is not None:
            logger.warning(
                "Orchestrator has already been configured; setting termination condition on builder has no effect."
            )

        self._termination_condition = termination_condition
        return self

    def with_max_rounds(self, max_rounds: int | None) -> "GroupChatBuilder":
        """Set a maximum number of manager rounds to prevent infinite conversations.

        When the round limit is reached, the workflow automatically completes with
        a default completion message. Setting to None allows unlimited rounds.

        Args:
            max_rounds: Maximum number of manager selection rounds, or None for unlimited

        Returns:
            Self for fluent chaining
        """
        self._max_rounds = max_rounds
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "GroupChatBuilder":
        """Enable checkpointing for the built workflow using the provided storage.

        Checkpointing allows the workflow to persist state and resume from interruption
        points, enabling long-running conversations and failure recovery.

        Args:
            checkpoint_storage: Storage implementation for persisting workflow state

        Returns:
            Self for fluent chaining

        Example:

        .. code-block:: python

            from agent_framework import GroupChatBuilder, MemoryCheckpointStorage

            storage = MemoryCheckpointStorage()
            workflow = (
                GroupChatBuilder()
                .with_select_speaker_func(my_selection_function)
                .participants([agent1, agent2])
                .with_checkpointing(storage)
                .build()
            )
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_info(
        self,
        *,
        agents: Sequence[str | AgentProtocol | Executor] | None = None,
    ) -> "GroupChatBuilder":
        """Enable request info before participant responses.

        This enables human-in-the-loop (HIL) scenarios for the group chat orchestration.
        When enabled, the workflow pauses before each participant runs, emitting
        a RequestInfoEvent that allows the caller to review the conversation and
        optionally inject guidance before the participant responds. The caller provides
        input via the standard response_handler/request_info pattern.

        Simulated flow with HIL:
        Input -> Orchestrator -> Request Info -> Participant -> Orchestrator -> Request Info -> Participant -> ...

        Args:
            agents: Optional list of agents or participant names to enable request info for.
                    If None, enables HIL for all participants.

        Returns:
            Self for fluent chaining
        """
        from ._orchestration_request_info import resolve_request_info_filter

        self._request_info_enabled = True
        self._request_info_filter = resolve_request_info_filter(list(agents) if agents else None) or set()

        return self

    def _resolve_orchestrator(self) -> Executor:
        """Determine the orchestrator to use for the workflow."""
        if self._orchestrator is not None:
            return self._orchestrator

        if self._selection_func is not None:
            return GroupChatOrchestrator(
                id=self.DEFAULT_ORCHESTRATOR_ID,
                selection_func=self._selection_func,
                name=self._orchestrator_name,
                max_rounds=self._max_rounds,
                termination_condition=self._termination_condition,
                participants=list(self._participants.keys()),
            )

        raise RuntimeError("Orchestrator could not be resolved. This should not happen.")

    def _resolve_participants(self) -> list[Executor]:
        """Resolve participant instances into Executor objects."""
        executors: list[Executor] = []
        for participant in self._participants.values():
            if isinstance(participant, Executor):
                executors.append(participant)
            elif isinstance(participant, AgentProtocol):
                executors.append(AgentExecutor(participant))
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

        return executors

    def build(self) -> Workflow:
        """Build and validate the group chat workflow.

        Assembles the orchestrator and participants into a complete workflow graph.
        The workflow graph consists of bi-directional edges between the orchestrator and each participant,
        allowing for message exchanges in both directions.

        Returns:
            Validated Workflow instance ready for execution

        Raises:
            ValueError: If orchestrator or participants are not properly configured
        """
        if self._orchestrator is None and self._selection_func is None:
            raise ValueError(
                "Orchestrator must be configured before build(). "
                "Call with_orchestrator(...) or with_select_speakers_func(...)."
            )
        if self._orchestrator and self._selection_func:
            logger.warning(
                "Both orchestrator and selection function are configured; the custom orchestrator will take precedence."
            )

        if not self._participants:
            raise ValueError("participants must be configured before build()")

        # Resolve orchestrator and participants to executors
        orchestrator: Executor = self._resolve_orchestrator()
        participants: list[Executor] = self._resolve_participants()

        # Build workflow graph
        workflow_builder = WorkflowBuilder().set_start_executor(orchestrator)
        for participant in participants:
            # Orchestrator and participant bi-directional edges
            workflow_builder = workflow_builder.add_edge(orchestrator, participant)
            workflow_builder = workflow_builder.add_edge(participant, orchestrator)
        if self._checkpoint_storage is not None:
            workflow_builder = workflow_builder.with_checkpointing(self._checkpoint_storage)

        return workflow_builder.build()


# endregion
