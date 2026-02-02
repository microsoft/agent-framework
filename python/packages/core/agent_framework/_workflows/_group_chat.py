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
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast, overload

from pydantic import BaseModel, Field
from typing_extensions import Never

from .._agents import AgentProtocol, ChatAgent
from .._threads import AgentThread
from .._types import ChatMessage, Role
from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._agent_utils import resolve_agent_id
from ._base_group_chat_orchestrator import (
    BaseGroupChatOrchestrator,
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
    GroupChatWorkflowContext_T_Out,
    ParticipantRegistry,
    TerminationCondition,
)
from ._checkpoint import CheckpointStorage
from ._conversation_state import decode_chat_messages, encode_chat_messages
from ._executor import Executor
from ._orchestration_request_info import AgentApprovalExecutor
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

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
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
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
                # We don't need the full conversation since the thread should maintain history
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

    def __init__(self) -> None:
        """Initialize the GroupChatBuilder."""
        self._participants: dict[str, AgentProtocol | Executor] = {}
        self._participant_factories: list[Callable[[], AgentProtocol | Executor]] = []

        # Orchestrator related members
        self._orchestrator: BaseGroupChatOrchestrator | None = None
        self._orchestrator_factory: Callable[[], ChatAgent | BaseGroupChatOrchestrator] | None = None
        self._selection_func: GroupChatSelectionFunction | None = None
        self._agent_orchestrator: ChatAgent | None = None
        self._termination_condition: TerminationCondition | None = None
        self._max_rounds: int | None = None
        self._orchestrator_name: str | None = None

        # Checkpoint related members
        self._checkpoint_storage: CheckpointStorage | None = None

        # Request info related members
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] = set()

    @overload
    def with_orchestrator(self, *, agent: ChatAgent | Callable[[], ChatAgent]) -> "GroupChatBuilder":
        """Set the orchestrator for this group chat workflow using a ChatAgent.

        Args:
            agent: An instance of ChatAgent or a callable that produces one to manage the group chat.

        Returns:
            Self for fluent chaining.
        """
        ...

    @overload
    def with_orchestrator(
        self, *, orchestrator: BaseGroupChatOrchestrator | Callable[[], BaseGroupChatOrchestrator]
    ) -> "GroupChatBuilder":
        """Set the orchestrator for this group chat workflow using a custom orchestrator.

        Args:
            orchestrator: An instance of BaseGroupChatOrchestrator or a callable that produces one to
                          manage the group chat.

        Returns:
            Self for fluent chaining.

        Note:
            When using a custom orchestrator that implements `BaseGroupChatOrchestrator`, setting
            `termination_condition` and `max_rounds` on the builder will have no effect since the
            orchestrator is already fully defined.
        """
        ...

    @overload
    def with_orchestrator(
        self,
        *,
        selection_func: GroupChatSelectionFunction,
        orchestrator_name: str | None = None,
    ) -> "GroupChatBuilder":
        """Set the orchestrator for this group chat workflow using a selection function.

        Args:
            selection_func: Callable that receives the current GroupChatState and returns
                            the name of the next participant to speak, or None to finish.
            orchestrator_name: Optional display name for the orchestrator in the workflow.
                               If not provided, defaults to `GroupChatBuilder.DEFAULT_ORCHESTRATOR_ID`.

        Returns:
            Self for fluent chaining.
        """
        ...

    def with_orchestrator(
        self,
        *,
        agent: ChatAgent | Callable[[], ChatAgent] | None = None,
        orchestrator: BaseGroupChatOrchestrator | Callable[[], BaseGroupChatOrchestrator] | None = None,
        selection_func: GroupChatSelectionFunction | None = None,
        orchestrator_name: str | None = None,
    ) -> "GroupChatBuilder":
        """Set the orchestrator for this group chat workflow.

        An group chat orchestrator is responsible for managing the flow of conversation, making
        sure all participants are synced and picking the next speaker according to the defined logic
        until the termination conditions are met.

        There are a few ways to configure the orchestrator:
        1. Provide a ChatAgent instance or a factory function that produces one to use an agent-based orchestrator
        2. Provide a BaseGroupChatOrchestrator instance or a factory function that produces one to use a custom
           orchestrator
        3. Provide a selection function to use that picks the next speaker based on the function logic

        You can only use one of the above methods to configure the orchestrator.

        Args:
            agent: An instance of ChatAgent or a callable that produces one to manage the group chat.
            orchestrator: An instance of BaseGroupChatOrchestrator or a callable that produces one to manage the group
                          chat.
            selection_func: Callable that receives the current GroupChatState and returns
                            the name of the next participant to speak, or None to finish.
            orchestrator_name: Optional display name for the orchestrator in the workflow if
                               using a selection function. If not provided, defaults to
                               `GroupChatBuilder.DEFAULT_ORCHESTRATOR_ID`. This parameter is
                               ignored if using an agent or custom orchestrator.

        Returns:
            Self for fluent chaining.

        Raises:
            ValueError: If an orchestrator has already been set or if none or multiple
                        of the parameters are provided.

        Note:
            When using a custom orchestrator that implements `BaseGroupChatOrchestrator`, either
            via the `orchestrator` or `orchestrator_factory` parameters, setting `termination_condition`
            and `max_rounds` on the builder will have no effect since the orchestrator is already
            fully defined.

        Example:
        .. code-block:: python

            from agent_framework import GroupChatBuilder


            orchestrator = CustomGroupChatOrchestrator(...)
            workflow = GroupChatBuilder().with_orchestrator(orchestrator).participants([agent1, agent2]).build()
        """
        if self._agent_orchestrator is not None:
            raise ValueError(
                "An agent orchestrator has already been configured. Call with_orchestrator(...) once only."
            )

        if self._orchestrator is not None:
            raise ValueError("An orchestrator has already been configured. Call with_orchestrator(...) once only.")

        if self._orchestrator_factory is not None:
            raise ValueError("A factory has already been configured. Call with_orchestrator(...) once only.")

        if self._selection_func is not None:
            raise ValueError("A selection function has already been configured. Call with_orchestrator(...) once only.")

        if sum(x is not None for x in [agent, orchestrator, selection_func]) != 1:
            raise ValueError("Exactly one of agent, orchestrator, or selection_func must be provided.")

        if agent is not None and isinstance(agent, ChatAgent):
            self._agent_orchestrator = agent
        elif orchestrator is not None and isinstance(orchestrator, BaseGroupChatOrchestrator):
            self._orchestrator = orchestrator
        elif selection_func is not None:
            self._selection_func = selection_func
            self._orchestrator_name = orchestrator_name
        else:
            self._orchestrator_factory = agent or orchestrator

        return self

    def register_participants(
        self,
        participant_factories: Sequence[Callable[[], AgentProtocol | Executor]],
    ) -> "GroupChatBuilder":
        """Register participant factories for this group chat workflow.

        Args:
            participant_factories: Sequence of callables that produce participant definitions
                when invoked. Each callable should return either an AgentProtocol instance
                (auto-wrapped as AgentExecutor) or an Executor instance.

        Returns:
            Self for fluent chaining

        Raises:
            ValueError: If participant_factories is empty, or participants
                or participant factories are already set
        """
        if self._participants:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participant_factories:
            raise ValueError("register_participants() has already been called on this builder instance.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = list(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "GroupChatBuilder":
        """Define participants for this group chat workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.

        Args:
            participants: Sequence of participant definitions

        Returns:
            Self for fluent chaining

        Raises:
            ValueError: If participants are empty, names are duplicated, or participants
                or participant factories are already set
            TypeError: If any participant is not AgentProtocol or Executor instance

        Example:

        .. code-block:: python

            from agent_framework import GroupChatBuilder

            workflow = (
                GroupChatBuilder()
                .with_orchestrator(selection_func=my_selection_function)
                .participants([agent1, agent2, custom_executor])
                .build()
            )
        """
        if self._participant_factories:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participants:
            raise ValueError("participants have already been set. Call participants() at most once.")

        if not participants:
            raise ValueError("participants cannot be empty.")

        # Name of the executor mapped to participant instance
        named: dict[str, AgentProtocol | Executor] = {}
        for participant in participants:
            if isinstance(participant, Executor):
                identifier = participant.id
            elif isinstance(participant, AgentProtocol):
                if not participant.name:
                    raise ValueError("AgentProtocol participants must have a non-empty name.")
                identifier = participant.name
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
                .with_orchestrator(selection_func=my_selection_function)
                .participants([agent1, specialist_agent])
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

    def with_max_rounds(self, max_rounds: int | None) -> "GroupChatBuilder":
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
                .with_orchestrator(selection_func=my_selection_function)
                .participants([agent1, agent2])
                .with_checkpointing(storage)
                .build()
            )
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_info(self, *, agents: Sequence[str | AgentProtocol] | None = None) -> "GroupChatBuilder":
        """Enable request info after agent participant responses.

        This enables human-in-the-loop (HIL) scenarios for the group chat orchestration.
        When enabled, the workflow pauses after each agent participant runs, emitting
        a RequestInfoEvent that allows the caller to review the conversation and optionally
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
            raise ValueError("No orchestrator has been configured. Call with_orchestrator() to set one.")
        # We don't need to check if multiple are set since that is handled in with_orchestrator()

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
        raise RuntimeError("Orchestrator could not be resolved. Please provide one via with_orchestrator()")

    def _resolve_participants(self) -> list[Executor]:
        """Resolve participant instances into Executor objects."""
        if not self._participants and not self._participant_factories:
            raise ValueError("No participants provided. Call .participants() or .register_participants() first.")
        # We don't need to check if both are set since that is handled in the respective methods

        participants: list[Executor | AgentProtocol] = []
        if self._participant_factories:
            for factory in self._participant_factories:
                participant = factory()
                participants.append(participant)
        else:
            participants = list(self._participants.values())

        executors: list[Executor] = []
        for participant in participants:
            if isinstance(participant, Executor):
                executors.append(participant)
            elif isinstance(participant, AgentProtocol):
                if self._request_info_enabled and (
                    not self._request_info_filter or resolve_agent_id(participant) in self._request_info_filter
                ):
                    # Handle request info enabled agents
                    executors.append(AgentApprovalExecutor(participant))
                else:
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
        """
        # Resolve orchestrator and participants to executors
        participants: list[Executor] = self._resolve_participants()
        orchestrator: Executor = self._resolve_orchestrator(participants)

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
