# Copyright (c) Microsoft. All rights reserved.

"""High-level builder for conversational handoff workflows.

The handoff pattern models a group of agents that can intelligently route
control to other agents based on the conversation context.

The flow is typically:

    user input -> Agent A -> Agent B -> Agent C -> Agent A -> ... -> output

Depending of wether request info is enabled, the flow may include user input (except when an agent hands off):

    user input -> [Agent A -> Request info] -> [Agent B -> Request info] -> [Agent C -> ... -> output

The difference between a group chat workflow and a handoff workflow is that in group chat there is
always a orchestrator that decides who to speak next, while in handoff the agents themselves decide
who to handoff to next by invoking a tool call that names the target agent.

Group Chat: centralized orchestration of multiple agents
Handoff: decentralized routing by agents themselves

Key properties:
- The entire conversation is maintained and reused on every hop
- Agents signal handoffs by invoking a tool call that names the other agents
- In human_in_loop mode (default), the workflow requests user input after each agent response
  that doesn't trigger a handoff
- In autonomous mode, agents continue responding until they invoke a handoff tool or reach
  a termination condition or turn limit
"""

import inspect
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from typing_extensions import Never

from .._agents import AgentProtocol, ChatAgent
from .._middleware import FunctionInvocationContext, FunctionMiddleware
from .._threads import AgentThread
from .._tools import FunctionTool, tool
from .._types import AgentResponse, ChatMessage, Role
from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._agent_utils import resolve_agent_id
from ._base_group_chat_orchestrator import TerminationCondition
from ._checkpoint import CheckpointStorage
from ._events import WorkflowEvent
from ._orchestrator_helpers import clean_conversation_for_handoff
from ._request_info_mixin import response_handler
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover


logger = logging.getLogger(__name__)


# region Handoff events
class HandoffSentEvent(WorkflowEvent):
    """Base class for handoff workflow events."""

    def __init__(self, source: str, target: str, data: Any | None = None) -> None:
        """Initialize handoff sent event.

        Args:
            source: Identifier of the source agent initiating the handoff
            target: Identifier of the target agent receiving the handoff
            data: Optional event-specific data
        """
        super().__init__(data)
        self.source = source
        self.target = target


# endregion


@dataclass
class HandoffConfiguration:
    """Configuration for handoff routing between agents.

    Attributes:
        target_id: Identifier of the target agent to hand off to
        description: Optional human-readable description of the handoff
    """

    target_id: str
    description: str | None = None

    def __init__(self, *, target: str | AgentProtocol, description: str | None = None) -> None:
        """Initialize HandoffConfiguration.

        Args:
            target: Target agent identifier or AgentProtocol instance
            description: Optional human-readable description of the handoff
        """
        self.target_id = resolve_agent_id(target) if isinstance(target, AgentProtocol) else target
        self.description = description

    def __eq__(self, other: Any) -> bool:
        """Determine equality based on source_id and target_id."""
        if not isinstance(other, HandoffConfiguration):
            return False

        return self.target_id == other.target_id

    def __hash__(self) -> int:
        """Compute hash based on source_id and target_id."""
        return hash(self.target_id)


def get_handoff_tool_name(target_id: str) -> str:
    """Get the standardized handoff tool name for a given target agent ID."""
    return f"handoff_to_{target_id}"


HANDOFF_FUNCTION_RESULT_KEY = "handoff_to"


class _AutoHandoffMiddleware(FunctionMiddleware):
    """Intercept handoff tool invocations and short-circuit execution with synthetic results."""

    def __init__(self, handoffs: Sequence[HandoffConfiguration]) -> None:
        """Initialise middleware with the mapping from tool name to specialist id."""
        self._handoff_functions = {get_handoff_tool_name(handoff.target_id): handoff.target_id for handoff in handoffs}

    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Intercept matching handoff tool calls and inject synthetic results."""
        if context.function.name not in self._handoff_functions:
            await next(context)
            return

        # Short-circuit execution and provide deterministic response payload for the tool call.
        context.result = {HANDOFF_FUNCTION_RESULT_KEY: self._handoff_functions[context.function.name]}
        context.terminate = True


@dataclass
class HandoffAgentUserRequest:
    """Request issued to the user after an agent run in a handoff workflow.

    Attributes:
        agent_response: The response generated by the agent at the most recent turn
    """

    agent_response: AgentResponse

    @staticmethod
    def create_response(response: str | list[str] | ChatMessage | list[ChatMessage]) -> list[ChatMessage]:
        """Create a HandoffAgentUserRequest from a simple text response."""
        messages: list[ChatMessage] = []
        if isinstance(response, str):
            messages.append(ChatMessage(role=Role.USER, text=response))
        elif isinstance(response, ChatMessage):
            messages.append(response)
        elif isinstance(response, list):
            for item in response:
                if isinstance(item, ChatMessage):
                    messages.append(item)
                elif isinstance(item, str):
                    messages.append(ChatMessage(role=Role.USER, text=item))
                else:
                    raise TypeError("List items must be either str or ChatMessage instances")
        else:
            raise TypeError("Response must be str, list of str, ChatMessage, or list of ChatMessage")

        return messages

    @staticmethod
    def terminate() -> list[ChatMessage]:
        """Create a termination response for the handoff workflow."""
        return []


# In autonomous mode, the agent continues responding until it requests a handoff
# or reaches a turn limit, after which it requests user input to continue.
_AUTONOMOUS_MODE_DEFAULT_PROMPT = "User did not respond. Continue assisting autonomously."
_DEFAULT_AUTONOMOUS_TURN_LIMIT = 50

# region Handoff Agent Executor


class HandoffAgentExecutor(AgentExecutor):
    """Specialized AgentExecutor that supports handoff tool interception."""

    def __init__(
        self,
        agent: AgentProtocol,
        handoffs: Sequence[HandoffConfiguration],
        *,
        agent_thread: AgentThread | None = None,
        is_start_agent: bool = False,
        termination_condition: TerminationCondition | None = None,
        autonomous_mode: bool = False,
        autonomous_mode_prompt: str | None = None,
        autonomous_mode_turn_limit: int | None = None,
    ) -> None:
        """Initialize the HandoffAgentExecutor.

        Args:
            agent: The agent to execute
            handoffs: Sequence of handoff configurations defining target agents
            agent_thread: Optional AgentThread that manages the agent's execution context
            is_start_agent: Whether this agent is the starting agent in the handoff workflow.
                            There can only be one starting agent in a handoff workflow.
            termination_condition: Optional callable that determines when to terminate the workflow
            autonomous_mode: Whether the agent should operate involve external systems after
                             a response that does not trigger a handoff or before the turn
                             limit is reached. This allows the agent to perform long-running
                             tasks (e.g., research, coding, analysis) without prematurely returning
                             control to the coordinator or user.
            autonomous_mode_prompt: Prompt to provide to the agent when continuing in autonomous mode.
                                    This will guide the agent in the absence of user input.
            autonomous_mode_turn_limit: Maximum number of autonomous turns before requesting user input.
        """
        cloned_agent = self._prepare_agent_with_handoffs(agent, handoffs)
        super().__init__(cloned_agent, agent_thread=agent_thread)

        self._handoff_targets = {handoff.target_id for handoff in handoffs}
        self._termination_condition = termination_condition
        self._is_start_agent = is_start_agent

        # Autonomous mode members
        self._autonomous_mode = autonomous_mode
        self._autonomous_mode_prompt = autonomous_mode_prompt or _AUTONOMOUS_MODE_DEFAULT_PROMPT
        self._autonomous_mode_turn_limit = autonomous_mode_turn_limit or _DEFAULT_AUTONOMOUS_TURN_LIMIT
        self._autonomous_mode_turns = 0

    def _prepare_agent_with_handoffs(
        self,
        agent: AgentProtocol,
        handoffs: Sequence[HandoffConfiguration],
    ) -> AgentProtocol:
        """Prepare an agent by adding handoff tools for the specified target agents.

        Args:
            agent: The agent to prepare
            handoffs: Sequence of handoff configurations defining target agents

        Returns:
            A new AgentExecutor instance with handoff tools added
        """
        if not isinstance(agent, ChatAgent):
            raise TypeError(
                "Handoff can only be applied to ChatAgent. Please ensure the agent is a ChatAgent instance."
            )

        # Clone the agent to avoid mutating the original
        cloned_agent = self._clone_chat_agent(agent)  # type: ignore
        # Add handoff tools to the cloned agent
        self._apply_auto_tools(cloned_agent, handoffs)
        # Add middleware to handle handoff tool invocations
        middleware = _AutoHandoffMiddleware(handoffs)
        existing_middleware = list(cloned_agent.middleware or [])
        existing_middleware.append(middleware)
        cloned_agent.middleware = existing_middleware

        return cloned_agent

    def _clone_chat_agent(self, agent: ChatAgent) -> ChatAgent:
        """Produce a deep copy of the ChatAgent while preserving runtime configuration."""
        options = agent.default_options
        middleware = list(agent.middleware or [])

        # Reconstruct the original tools list by combining regular tools with MCP tools.
        # ChatAgent.__init__ separates MCP tools during initialization,
        # so we need to recombine them here to pass the complete tools list to the constructor.
        # This makes sure MCP tools are preserved when cloning agents for handoff workflows.
        tools_from_options = options.get("tools")
        all_tools = list(tools_from_options) if tools_from_options else []
        if agent.mcp_tools:
            all_tools.extend(agent.mcp_tools)

        logit_bias = options.get("logit_bias")
        metadata = options.get("metadata")

        # Disable parallel tool calls to prevent the agent from invoking multiple handoff tools at once.
        cloned_options: dict[str, Any] = {
            "allow_multiple_tool_calls": False,
            "frequency_penalty": options.get("frequency_penalty"),
            "instructions": options.get("instructions"),
            "logit_bias": dict(logit_bias) if logit_bias else None,
            "max_tokens": options.get("max_tokens"),
            "metadata": dict(metadata) if metadata else None,
            "model_id": options.get("model_id"),
            "presence_penalty": options.get("presence_penalty"),
            "response_format": options.get("response_format"),
            "seed": options.get("seed"),
            "stop": options.get("stop"),
            "store": options.get("store"),
            "temperature": options.get("temperature"),
            "tool_choice": options.get("tool_choice"),
            "tools": all_tools if all_tools else None,
            "top_p": options.get("top_p"),
            "user": options.get("user"),
        }

        return ChatAgent(
            chat_client=agent.chat_client,
            id=agent.id,
            name=agent.name,
            description=agent.description,
            chat_message_store_factory=agent.chat_message_store_factory,
            context_providers=agent.context_provider,
            middleware=middleware,
            default_options=cloned_options,  # type: ignore[arg-type]
        )

    def _apply_auto_tools(self, agent: ChatAgent, targets: Sequence[HandoffConfiguration]) -> None:
        """Attach synthetic handoff tools to a chat agent and return the target lookup table.

        Creates handoff tools for each specialist agent that this agent can route to.

        Args:
            agent: The ChatAgent to add handoff tools to
            targets: Sequence of handoff configurations defining target agents
        """
        default_options = agent.default_options
        existing_tools = list(default_options.get("tools") or [])
        existing_names = {getattr(tool, "name", "") for tool in existing_tools if hasattr(tool, "name")}

        new_tools: list[FunctionTool[Any, Any]] = []
        for target in targets:
            tool = self._create_handoff_tool(target.target_id, target.description)
            if tool.name in existing_names:
                raise ValueError(
                    f"Agent '{resolve_agent_id(agent)}' already has a tool named '{tool.name}'. "
                    f"Handoff tool name '{tool.name}' conflicts with existing tool."
                    "Please rename the existing tool or modify the target agent ID to avoid conflicts."
                )
            new_tools.append(tool)

        if new_tools:
            default_options["tools"] = existing_tools + new_tools  # type: ignore[operator]
        else:
            default_options["tools"] = existing_tools

    def _create_handoff_tool(self, target_id: str, description: str | None = None) -> FunctionTool[Any, Any]:
        """Construct the synthetic handoff tool that signals routing to `target_id`."""
        tool_name = get_handoff_tool_name(target_id)
        doc = description or f"Handoff to the {target_id} agent."
        # Note: approval_mode is set to "never_require" for handoff tools because
        # they are framework-internal signals that trigger routing logic, not
        # actual function executions. They are automatically intercepted by
        # _AutoHandoffMiddleware which short-circuits execution and provides synthetic
        # results, so the function body never actually runs in practice.

        @tool(name=tool_name, description=doc, approval_mode="never_require")
        def _handoff_tool(context: str | None = None) -> str:
            """Return a deterministic acknowledgement that encodes the target alias."""
            return f"Handoff to {target_id}"

        return _handoff_tool

    @override
    async def _run_agent_and_emit(self, ctx: WorkflowContext[AgentExecutorResponse, AgentResponse]) -> None:
        """Override to support handoff."""
        # When the full conversation is empty, it means this is the first run.
        # Broadcast the initial cache to all other agents. Subsequent runs won't
        # need this since responses are broadcast after each agent run and user input.
        if self._is_start_agent and not self._full_conversation:
            await self._broadcast_messages(self._cache.copy(), cast(WorkflowContext[AgentExecutorRequest], ctx))

        # Append the cache to the full conversation history
        self._full_conversation.extend(self._cache)

        # Check termination condition before running the agent
        if await self._check_terminate_and_yield(cast(WorkflowContext[Never, list[ChatMessage]], ctx)):
            return

        # Run the agent
        if ctx.is_streaming():
            # Streaming mode: emit incremental updates
            response = await self._run_agent_streaming(cast(WorkflowContext, ctx))
        else:
            # Non-streaming mode: use run() and emit single event
            response = await self._run_agent(cast(WorkflowContext, ctx))

        # Clear the cache after running the agent
        self._cache.clear()

        # A function approval request is issued by the base AgentExecutor
        if response is None:
            # Agent did not complete (e.g., waiting for user input); do not emit response
            logger.debug("AgentExecutor %s: Agent did not complete, awaiting user input", self.id)
            return

        # Remove function call related content from the agent response for full conversation history
        cleaned_response = clean_conversation_for_handoff(response.messages)
        # Append the agent response to the full conversation history. This list removes
        # function call related content such that the result stays consistent regardless
        # of which agent yields the final output.
        self._full_conversation.extend(cleaned_response)
        # Broadcast the cleaned response to all other agents
        await self._broadcast_messages(cleaned_response, cast(WorkflowContext[AgentExecutorRequest], ctx))

        # Check if a handoff was requested
        if handoff_target := self._is_handoff_requested(response):
            if handoff_target not in self._handoff_targets:
                raise ValueError(
                    f"Agent '{resolve_agent_id(self._agent)}' attempted to handoff to unknown "
                    f"target '{handoff_target}'. Valid targets are: {', '.join(self._handoff_targets)}"
                )

            await cast(WorkflowContext[AgentExecutorRequest], ctx).send_message(
                AgentExecutorRequest(messages=[], should_respond=True), target_id=handoff_target
            )
            await ctx.add_event(HandoffSentEvent(source=self.id, target=handoff_target))
            self._autonomous_mode_turns = 0  # Reset autonomous mode turn counter on handoff
            return

        # Handle case where no handoff was requested
        if self._autonomous_mode and self._autonomous_mode_turns < self._autonomous_mode_turn_limit:
            # In autonomous mode, continue running the agent until a handoff is requested
            # or a termination condition is met.
            # This allows the agent to perform long-running tasks without returning control
            # to the coordinator or user prematurely.
            self._cache.extend([ChatMessage(role=Role.USER, text=self._autonomous_mode_prompt)])
            self._autonomous_mode_turns += 1
            await self._run_agent_and_emit(ctx)
        else:
            # The response is handled via `handle_response`
            self._autonomous_mode_turns = 0  # Reset autonomous mode turn counter on handoff
            await ctx.request_info(HandoffAgentUserRequest(response), list[ChatMessage])

    @response_handler
    async def handle_response(
        self,
        original_request: HandoffAgentUserRequest,
        response: list[ChatMessage],
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse],
    ) -> None:
        """Handle user response for a request that is issued after agent runs.

        The request only occurs when the agent did not request a handoff and
        autonomous mode is disabled.

        Note that this is different that the `handle_user_input_response` method
        in the base AgentExecutor, which handles function approval responses.

        Args:
            original_request: The original HandoffAgentUserRequest issued to the user
            response: The user's response messages
            ctx: The workflow context

        If the response is empty, it indicates termination of the handoff workflow.
        """
        if not response:
            await cast(WorkflowContext[Never, list[ChatMessage]], ctx).yield_output(self._full_conversation)
            return

        # Broadcast the user response to all other agents
        await self._broadcast_messages(response, cast(WorkflowContext[AgentExecutorRequest], ctx))

        # Append the user response messages to the cache
        self._cache.extend(response)
        await self._run_agent_and_emit(ctx)

    async def _broadcast_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Broadcast the workflow cache to the agent before running."""
        agent_executor_request = AgentExecutorRequest(
            messages=messages,
            should_respond=False,  # Other agents do not need to respond yet
        )
        # Since all agents are connected via fan-out, we can directly send the message
        await ctx.send_message(agent_executor_request)

    def _is_handoff_requested(self, response: AgentResponse) -> str | None:
        """Determine if the agent response includes a handoff request.

        If a handoff tool is invoked, the middleware will short-circuit execution
        and provide a synthetic result that includes the target agent ID. The message
        that contains the function result will be the last message in the response.
        """
        if not response.messages:
            return None

        last_message = response.messages[-1]
        for content in last_message.contents:
            if content.type == "function_result":
                # Use string comparison instead of isinstance to improve performance
                if content.result and isinstance(content.result, dict):
                    handoff_target = content.result.get(HANDOFF_FUNCTION_RESULT_KEY)  # type: ignore
                    if isinstance(handoff_target, str):
                        return handoff_target
            else:
                continue

        return None

    async def _check_terminate_and_yield(self, ctx: WorkflowContext[Never, list[ChatMessage]]) -> bool:
        """Check termination conditions and yield completion if met.

        Args:
            ctx: Workflow context for yielding output

        Returns:
            True if termination condition met and output yielded, False otherwise
        """
        if self._termination_condition is None:
            return False

        terminated = self._termination_condition(self._full_conversation)
        if inspect.isawaitable(terminated):
            terminated = await terminated

        if terminated:
            await ctx.yield_output(self._full_conversation)
            return True

        return False

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Serialize the executor state for checkpointing."""
        state = await super().on_checkpoint_save()
        state["_autonomous_mode_turns"] = self._autonomous_mode_turns
        return state

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the executor state from a checkpoint."""
        await super().on_checkpoint_restore(state)
        if "_autonomous_mode_turns" in state:
            self._autonomous_mode_turns = state["_autonomous_mode_turns"]


# endregion Handoff Agent Executor

# region Handoff workflow builder


class HandoffBuilder:
    r"""Fluent builder for conversational handoff workflows with multiple agents.

    The handoff pattern enables a group of agents to route control among themselves.

    Routing Pattern:
    Agents can hand off to other agents using `.add_handoff()`. This provides a decentralized
    approach to multi-agent collaboration. Handoffs can be configured using `.add_handoff`. If
    none are specified, all agents can hand off to all others by default (making a mesh topology).

    Participants must be agents. Support for custom executors is not available in handoff workflows.

    Outputs:
    The final conversation history as a list of ChatMessage once the group chat completes.

    Note:
    Agents in handoff workflows must be ChatAgent instances and support local tool calls.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        participants: Sequence[AgentProtocol] | None = None,
        participant_factories: Mapping[str, Callable[[], AgentProtocol]] | None = None,
        description: str | None = None,
    ) -> None:
        r"""Initialize a HandoffBuilder for creating conversational handoff workflows.

        The builder starts in an unconfigured state and requires you to call:
        1. `.participants([...])` - Register agents
        2. or `.participant_factories({...})` - Register agent factories
        3. `.build()` - Construct the final Workflow

        Optional configuration methods allow you to customize context management,
        termination logic, and persistence.

        Args:
            name: Optional workflow identifier used in logging and debugging.
                  If not provided, a default name will be generated.
            participants: Optional list of agents that will participate in the handoff workflow.
                          You can also call `.participants([...])` later. Each participant must have a
                          unique identifier (`.name` is preferred if set, otherwise `.id` is used).
            participant_factories: Optional mapping of factory names to callables that produce agents when invoked.
                                   This allows for lazy instantiation and state isolation per workflow instance
                                   created by this builder.
            description: Optional human-readable description explaining the workflow's
                         purpose. Useful for documentation and observability.
        """
        self._name = name
        self._description = description

        # Participant related members
        self._participants: dict[str, AgentProtocol] = {}
        self._participant_factories: dict[str, Callable[[], AgentProtocol]] = {}
        self._start_id: str | None = None
        if participant_factories:
            self.register_participants(participant_factories)

        if participants:
            self.participants(participants)

        # Handoff related members
        self._handoff_config: dict[str, set[HandoffConfiguration]] = {}

        # Checkpoint related members
        self._checkpoint_storage: CheckpointStorage | None = None

        # Autonomous mode related
        self._autonomous_mode: bool = False
        self._autonomous_mode_prompts: dict[str, str] = {}
        self._autonomous_mode_turn_limits: dict[str, int] = {}
        self._autonomous_mode_enabled_agents: list[str] = []

        # Termination related members
        self._termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] | None = None

    def register_participants(
        self, participant_factories: Mapping[str, Callable[[], AgentProtocol]]
    ) -> "HandoffBuilder":
        """Register factories that produce agents for the handoff workflow.

        Each factory is a callable that returns an AgentProtocol instance.
        Factories are invoked when building the workflow, allowing for lazy instantiation
        and state isolation per workflow instance.

        Args:
            participant_factories: Mapping of factory names to callables that return AgentProtocol
                                   instances. Each produced participant must have a unique identifier
                                   (`.name` is preferred if set, otherwise `.id` is used).

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participant_factories is empty or `.participants(...)`  or `.register_participants(...)`
                        has already been called.

        Example:
        .. code-block:: python

            from agent_framework import ChatAgent, HandoffBuilder


            def create_triage() -> ChatAgent:
                return ...


            def create_refund_agent() -> ChatAgent:
                return ...


            def create_billing_agent() -> ChatAgent:
                return ...


            factories = {
                "triage": create_triage,
                "refund": create_refund_agent,
                "billing": create_billing_agent,
            }

            # Handoff will be created automatically unless specified otherwise
            # The default creates a mesh topology where all agents can handoff to all others
            builder = HandoffBuilder().register_participants(factories)
            builder.with_start_agent("triage")
        """
        if self._participants:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participant_factories:
            raise ValueError("register_participants() has already been called on this builder instance.")
        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = dict(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol]) -> "HandoffBuilder":
        """Register the agents that will participate in the handoff workflow.

        Args:
            participants: Sequence of AgentProtocol instances. Each must have a unique identifier.
                (`.name` is preferred if set, otherwise `.id` is used).

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participants is empty, contains duplicates, or `.participants()` or
                        `.register_participants()` has already been called.
            TypeError: If participants are not AgentProtocol instances.

        Example:

        .. code-block:: python

            from agent_framework import HandoffBuilder
            from agent_framework.openai import OpenAIChatClient

            client = OpenAIChatClient()
            triage = client.as_agent(instructions="...", name="triage_agent")
            refund = client.as_agent(instructions="...", name="refund_agent")
            billing = client.as_agent(instructions="...", name="billing_agent")

            builder = HandoffBuilder().participants([triage, refund, billing])
            builder.with_start_agent(triage)
        """
        if self._participant_factories:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participants:
            raise ValueError("participants have already been assigned")

        if not participants:
            raise ValueError("participants cannot be empty")

        named: dict[str, AgentProtocol] = {}
        for participant in participants:
            if isinstance(participant, AgentProtocol):
                resolved_id = self._resolve_to_id(participant)
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

            if resolved_id in named:
                raise ValueError(f"Duplicate participant name '{resolved_id}' detected")
            named[resolved_id] = participant

        self._participants = named

        return self

    def add_handoff(
        self,
        source: str | AgentProtocol,
        targets: Sequence[str] | Sequence[AgentProtocol],
        *,
        description: str | None = None,
    ) -> "HandoffBuilder":
        """Add handoff routing from a source agent to one or more target agents.

        This method enables agent-to-agent handoffs by configuring which agents
        can hand off to which others. Call this method multiple times to build a
        complete routing graph. If no handoffs are specified, all agents can hand off
        to all others by default (mesh topology).

        Args:
            source: The agent that can initiate the handoff. Can be:
                   - Factory name (str): If using participant factories
                   - AgentProtocol instance: The actual agent object
                   - Cannot mix factory names and instances across source and targets
            targets: One or more target agents that the source can hand off to. Can be:
                    - Factory name (str): If using participant factories
                    - AgentProtocol instance: The actual agent object
                    - Single target: ["billing_agent"] or [agent_instance]
                    - Multiple targets: ["billing_agent", "support_agent"] or [agent1, agent2]
                    - Cannot mix factory names and instances across source and targets
            description: Optional custom description for the handoff. If not provided, the description
                         of the target agent(s) will be used. If the target agent has no description,
                         no description will be set for the handoff tool, which is not recommended.
                         If multiple targets are provided, description will be shared among all handoff
                         tools. To configure distinct descriptions for multiple targets, call add_handoff()
                         separately for each target.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: 1) If source or targets are not in the participants list, or if
                           participants(...) hasn't been called yet.
                        2) If source or targets are factory names (str) but participant_factories(...)
                           hasn't been called yet, or if they are not in the participant_factories list.
            TypeError: If mixing factory names (str) and AgentProtocol/Executor instances

        Examples:
            Single target (using factory name):

            .. code-block:: python

                builder.add_handoff("triage_agent", "billing_agent")

            Multiple targets (using factory names):

            .. code-block:: python

                builder.add_handoff("triage_agent", ["billing_agent", "support_agent", "escalation_agent"])

            Multiple targets (using agent instances):

            .. code-block:: python

                builder.add_handoff(triage, [billing, support, escalation])

            Chain multiple configurations:

            .. code-block:: python

                workflow = (
                    HandoffBuilder(participants=[triage, replacement, delivery, billing])
                    .add_handoff(triage, [replacement, delivery, billing])
                    .add_handoff(replacement, [delivery, billing])
                    .add_handoff(delivery, [billing])
                    .build()
                )

        Note:
            - Handoff tools are automatically registered for each source agent
            - If a source agent is configured multiple times via add_handoff, targets are merged
        """
        if isinstance(source, str) and all(isinstance(t, str) for t in targets):
            # Both source and targets are factory names
            if not self._participant_factories:
                raise ValueError("Call participant_factories(...) before add_handoff(...)")

            if source not in self._participant_factories:
                raise ValueError(f"Source factory name '{source}' is not in the participant_factories list")

            for target in targets:
                if target not in self._participant_factories:
                    raise ValueError(f"Target factory name '{target}' is not in the participant_factories list")

            # Merge with existing handoff configuration for this source
            if source in self._handoff_config:
                # Add new targets to existing list, avoiding duplicates
                for t in targets:
                    if t in self._handoff_config[source]:
                        logger.warning(f"Handoff from '{source}' to '{t}' is already configured; overwriting.")
                    self._handoff_config[source].add(HandoffConfiguration(target=t, description=description))
            else:
                self._handoff_config[source] = set()
                for t in targets:
                    self._handoff_config[source].add(HandoffConfiguration(target=t, description=description))
            return self

        if isinstance(source, (AgentProtocol)) and all(isinstance(t, AgentProtocol) for t in targets):
            # Both source and targets are instances
            if not self._participants:
                raise ValueError("Call participants(...) before add_handoff(...)")

            # Resolve source agent ID
            source_id = self._resolve_to_id(source)
            if source_id not in self._participants:
                raise ValueError(f"Source agent '{source}' is not in the participants list")

            # Resolve all target IDs
            target_ids: list[str] = []
            for target in targets:
                target_id = self._resolve_to_id(target)
                if target_id not in self._participants:
                    raise ValueError(f"Target agent '{target}' is not in the participants list")
                target_ids.append(target_id)

            # Merge with existing handoff configuration for this source
            if source_id in self._handoff_config:
                # Add new targets to existing list, avoiding duplicates
                for t in target_ids:
                    if t in self._handoff_config[source_id]:
                        logger.warning(f"Handoff from '{source_id}' to '{t}' is already configured; overwriting.")
                    self._handoff_config[source_id].add(HandoffConfiguration(target=t, description=description))
            else:
                self._handoff_config[source_id] = set()
                for t in target_ids:
                    self._handoff_config[source_id].add(HandoffConfiguration(target=t, description=description))

            return self

        raise TypeError(
            "Cannot mix factory names (str) and AgentProtocol instances across source and targets in add_handoff()"
        )

    def with_start_agent(self, agent: str | AgentProtocol) -> "HandoffBuilder":
        """Set the agent that will initiate the handoff workflow.

        If not specified, the first registered participant will be used as the starting agent.

        Args:
            agent: The agent that will start the workflow. Can be:
                   - Factory name (str): If using participant factories
                   - AgentProtocol instance: The actual agent object
        Returns:
            Self for method chaining.
        """
        if isinstance(agent, str):
            if self._participant_factories:
                if agent not in self._participant_factories:
                    raise ValueError(f"Start agent factory name '{agent}' is not in the participant_factories list")
            else:
                raise ValueError("Call register_participants(...) before with_start_agent(...)")
            self._start_id = agent
        elif isinstance(agent, AgentProtocol):
            resolved_id = self._resolve_to_id(agent)
            if self._participants:
                if resolved_id not in self._participants:
                    raise ValueError(f"Start agent '{resolved_id}' is not in the participants list")
            else:
                raise ValueError("Call participants(...) before with_start_agent(...)")
            self._start_id = resolved_id
        else:
            raise TypeError("Start agent must be a factory name (str) or an AgentProtocol instance")

        return self

    def with_autonomous_mode(
        self,
        *,
        agents: Sequence[AgentProtocol] | Sequence[str] | None = None,
        prompts: dict[str, str] | None = None,
        turn_limits: dict[str, int] | None = None,
    ) -> "HandoffBuilder":
        """Enable autonomous mode for the handoff workflow.

        Autonomous mode allows agents to continue responding without user input.
        The default behavior when autonomous mode is disabled is to return control to the user
        after each agent response that does not trigger a handoff. With autonomous mode enabled,
        agents can continue the conversation until they request a handoff or the turn limit is reached.

        Args:
            agents: Optional list of agents to enable autonomous mode for. Can be:
                    - Factory names (str): If using participant factories
                    - AgentProtocol instances: The actual agent objects
                    - If not provided, all agents will operate in autonomous mode.
            prompts: Optional mapping of agent identifiers/factory names to custom prompts to use when continuing
                     in autonomous mode. If not provided, a default prompt will be used.
            turn_limits: Optional mapping of agent identifiers/factory names to maximum number of autonomous turns
                         before returning control to the user. If not provided, a default turn limit will be used.
        """
        self._autonomous_mode = True
        self._autonomous_mode_prompts = prompts or {}
        self._autonomous_mode_turn_limits = turn_limits or {}
        self._autonomous_mode_enabled_agents = [self._resolve_to_id(agent) for agent in agents] if agents else []

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
            workflow = HandoffBuilder(participants=[triage, refund, billing]).with_checkpointing(storage).build()

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

    def with_termination_condition(self, termination_condition: TerminationCondition) -> "HandoffBuilder":
        """Set a custom termination condition for the handoff workflow.

        The condition can be either synchronous or asynchronous.

        Args:
            termination_condition: Function that receives the full conversation and returns True
                (or awaitable True) if the workflow should terminate.

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
        self._termination_condition = termination_condition
        return self

    def build(self) -> Workflow:
        """Construct the final Workflow instance from the configured builder.

        This method validates the configuration and assembles all internal components:
        - Starting agent executor
        - Specialist agent executors
        - Request/response handling

        Returns:
            A fully configured Workflow ready to execute via `.run()` or `.run_stream()`.

        Raises:
            ValueError: If participants or coordinator were not configured, or if
                       required configuration is invalid.
        """
        # Resolve agents (either from instances or factories)
        # The returned map keys are either executor IDs or factory names, which is need to resolve handoff configs
        resolved_agents = self._resolve_agents()
        # Resolve handoff configurations to use agent display names
        # The returned map keys are executor IDs
        resolved_handoffs = self._resolve_handoffs(resolved_agents)
        # Resolve agents into executors
        executors = self._resolve_executors(resolved_agents, resolved_handoffs)

        # Build the workflow graph
        if self._start_id is None:
            raise ValueError("Must call with_start_agent(...) before building the workflow.")
        start_executor = executors[self._resolve_to_id(resolved_agents[self._start_id])]
        builder = WorkflowBuilder(
            name=self._name,
            description=self._description,
        ).set_start_executor(start_executor)

        # Add the appropriate edges
        # In handoff workflows, all executors are connected, making a fully connected graph.
        # This is because for all agents to stay synchronized, the active agent must be able to
        # broadcast updates to all others via edges. Handoffs are controlled internally by the
        # `HandoffAgentExecutor` instances using handoff tools and middleware.
        for executor in executors.values():
            targets = [e for e in executors.values() if e.id != executor.id]
            # Fan-out requires at least 2 targets. Just in case there are only 2 agents total,
            # we add a direct edge if there's only 1 target.
            if len(targets) > 1:
                builder = builder.add_fan_out_edges(executor, targets)
            elif len(targets) == 1:
                builder = builder.add_edge(executor, targets[0])

        # Configure checkpointing if enabled
        if self._checkpoint_storage:
            builder.with_checkpointing(self._checkpoint_storage)

        return builder.build()

    # region Internal Helper Methods

    def _resolve_agents(self) -> dict[str, AgentProtocol]:
        """Resolve participant factories into agent instances.

        If agent instances were provided directly via participants(...), those are
        returned as-is. If participant factories were provided via participant_factories(...),
        those are invoked to create the agent instances.

        Returns:
            Map of executor IDs or factory names to `AgentProtocol` instances
        """
        if not self._participants and not self._participant_factories:
            raise ValueError("No participants provided. Call .participants() or .register_participants() first.")
        # We don't need to check if both are set since that is handled in the respective methods

        if self._participants:
            return self._participants

        if self._participant_factories:
            # Invoke each factory to create participant instances
            factory_names_to_agents: dict[str, AgentProtocol] = {}
            for factory_name, factory in self._participant_factories.items():
                instance = factory()
                if isinstance(instance, AgentProtocol):
                    resolved_id = self._resolve_to_id(instance)
                else:
                    raise TypeError(f"Participants must be AgentProtocol instances. Got {type(instance).__name__}.")

                if resolved_id in factory_names_to_agents:
                    raise ValueError(f"Duplicate participant name '{resolved_id}' detected")

                # Map executors by factory name (not executor.id) because handoff configs reference factory names
                # This allows users to configure handoffs using the factory names they provided
                factory_names_to_agents[factory_name] = instance

            return factory_names_to_agents

        raise ValueError("No executors or participant_factories have been configured")

    def _resolve_handoffs(self, agents: Mapping[str, AgentProtocol]) -> dict[str, list[HandoffConfiguration]]:
        """Handoffs may be specified using factory names or instances; resolve to executor IDs.

        Args:
            agents: Map of agent IDs or factory names to `AgentProtocol` instances

        Returns:
            Map of executor IDs to list of HandoffConfiguration instances
        """
        # Updated map that used agent resolved IDs as keys
        updated_handoff_configurations: dict[str, list[HandoffConfiguration]] = {}
        if self._handoff_config:
            # Use explicit handoff configuration from add_handoff() calls
            for source_id, handoff_configurations in self._handoff_config.items():
                source_agent = agents.get(source_id)
                if not source_agent:
                    raise ValueError(
                        f"Handoff source agent '{source_id}' not found. "
                        "Please make sure source has been added as either a participant or participant_factory."
                    )
                for handoff_config in handoff_configurations:
                    target_agent = agents.get(handoff_config.target_id)
                    if not target_agent:
                        raise ValueError(
                            f"Handoff target agent '{handoff_config.target_id}' not found for source '{source_id}'. "
                            "Please make sure target has been added as either a participant or participant_factory."
                        )

                    updated_handoff_configurations.setdefault(self._resolve_to_id(source_agent), []).append(
                        HandoffConfiguration(
                            target=self._resolve_to_id(target_agent),
                            description=handoff_config.description or target_agent.description,
                        )
                    )
        else:
            # Use default handoff configuration: all agents can hand off to all others (mesh topology)
            for source_id, source_agent in agents.items():
                for target_id, target_agent in agents.items():
                    if source_id == target_id:
                        continue  # Skip self-handoff
                    updated_handoff_configurations.setdefault(self._resolve_to_id(source_agent), []).append(
                        HandoffConfiguration(
                            target=self._resolve_to_id(target_agent),
                            description=target_agent.description,
                        )
                    )

        return updated_handoff_configurations

    def _resolve_executors(
        self,
        agents: dict[str, AgentProtocol],
        handoffs: dict[str, list[HandoffConfiguration]],
    ) -> dict[str, HandoffAgentExecutor]:
        """Resolve agents into HandoffAgentExecutors.

        Args:
            agents: Map of agent IDs or factory names to `AgentProtocol` instances
            handoffs: Map of executor IDs to list of HandoffConfiguration instances

        Returns:
            Tuple of (starting executor ID, list of HandoffAgentExecutor instances)
        """
        executors: dict[str, HandoffAgentExecutor] = {}

        for id, agent in agents.items():
            # Note that here `id` may be either factory name or agent resolved ID
            resolved_id = self._resolve_to_id(agent)
            if resolved_id not in handoffs or not handoffs.get(resolved_id):
                logger.warning(
                    f"No handoff configuration found for agent '{resolved_id}'. "
                    "This agent will not be able to hand off to any other agents and your workflow may get stuck."
                )

            # Autonomous mode is enabled only for specified agents (or all if none specified)
            autonomous_mode = self._autonomous_mode and (
                not self._autonomous_mode_enabled_agents or id in self._autonomous_mode_enabled_agents
            )

            executors[resolved_id] = HandoffAgentExecutor(
                agent=agent,
                handoffs=handoffs.get(resolved_id, []),
                is_start_agent=(id == self._start_id),
                termination_condition=self._termination_condition,
                autonomous_mode=autonomous_mode,
                autonomous_mode_prompt=self._autonomous_mode_prompts.get(id, None),
                autonomous_mode_turn_limit=self._autonomous_mode_turn_limits.get(id, None),
            )

        return executors

    def _resolve_to_id(self, candidate: str | AgentProtocol) -> str:
        """Resolve a participant reference into a concrete executor identifier."""
        if isinstance(candidate, AgentProtocol):
            return resolve_agent_id(candidate)
        if isinstance(candidate, str):
            return candidate

        raise TypeError(f"Invalid starting agent reference: {type(candidate).__name__}")

    # endregion Internal Helper Methods


# endregion Handoff workflow builder
