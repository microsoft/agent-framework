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

import logging
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from .._agents import AgentProtocol, ChatAgent
from .._middleware import FunctionInvocationContext, FunctionMiddleware
from .._threads import AgentThread
from .._tools import AIFunction, ai_function
from .._types import ChatMessage
from ._agent_executor import AgentExecutor, AgentExecutorResponse, AgentRunResponse
from ._checkpoint import CheckpointStorage
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


logger = logging.getLogger(__name__)

_HANDOFF_TOOL_PATTERN = re.compile(r"(?:handoff|transfer)[_\s-]*to[_\s-]*(?P<target>[\w-]+)", re.IGNORECASE)
_DEFAULT_AUTONOMOUS_TURN_LIMIT = 50


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
        self.target_id = target.display_name if isinstance(target, AgentProtocol) else target
        self.description = description

    def __eq__(self, other: Any) -> bool:
        """Determine equality based on source_id and target_id."""
        if not isinstance(other, HandoffConfiguration):
            return False

        return self.target_id == other.target_id


def get_handoff_tool_name(target_id: str) -> str:
    """Get the standardized handoff tool name for a given target agent ID."""
    return f"handoff_to_{target_id}"


class _AutoHandoffMiddleware(FunctionMiddleware):
    """Intercept handoff tool invocations and short-circuit execution with synthetic results."""

    def __init__(self, handoffs: Sequence[HandoffConfiguration]) -> None:
        """Initialise middleware with the mapping from tool name to specialist id."""
        self._handoffs: set[str] = {get_handoff_tool_name(handoff.target_id) for handoff in handoffs}

    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Intercept matching handoff tool calls and inject synthetic results."""
        if context.function.name not in self._handoffs:
            await next(context)
            return

        # Short-circuit execution and provide deterministic response payload for the tool call.
        context.result = {"handoff_to": context.function.name}
        context.terminate = True


class HandoffAgentExecutor(AgentExecutor):
    """Specialized AgentExecutor that supports handoff tool interception."""

    def __init__(
        self,
        agent: AgentProtocol,
        handoffs: Sequence[HandoffConfiguration],
        *,
        agent_thread: AgentThread | None = None,
    ) -> None:
        """Initialize the HandoffAgentExecutor.

        Args:
            agent: The agent to execute
            handoffs: Sequence of handoff configurations defining target agents
            agent_thread: Optional AgentThread that manages the agent's execution context
        """
        cloned_agent = self._prepare_agent_with_handoffs(agent, handoffs)
        super().__init__(cloned_agent, agent_thread=agent_thread)

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
        cloned_agent = self._clone_chat_agent(agent)
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
            # Disable parallel tool calls to prevent the agent from invoking multiple handoff tools at once.
            allow_multiple_tool_calls=False,
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

    def _apply_auto_tools(self, agent: ChatAgent, targets: Sequence[HandoffConfiguration]) -> None:
        """Attach synthetic handoff tools to a chat agent and return the target lookup table.

        Creates handoff tools for each specialist agent that this agent can route to.

        Args:
            agent: The ChatAgent to add handoff tools to
            targets: Sequence of handoff configurations defining target agents
        """
        chat_options = agent.chat_options
        existing_tools = list(chat_options.tools or [])
        existing_names = {getattr(tool, "name", "") for tool in existing_tools if hasattr(tool, "name")}

        new_tools: list[AIFunction[Any, Any]] = []
        for target in targets:
            tool = self._create_handoff_tool(target.target_id, target.description)
            if tool.name in existing_names:
                raise ValueError(
                    f"Agent '{agent.display_name}' already has a tool named '{tool.name}'. "
                    f"Handoff tool name '{tool.name}' conflicts with existing tool."
                    "Please rename the existing tool or modify the target agent ID to avoid conflicts."
                )
            new_tools.append(tool)

        if new_tools:
            chat_options.tools = existing_tools + new_tools
        else:
            chat_options.tools = existing_tools

    def _create_handoff_tool(self, target_id: str, description: str | None = None) -> AIFunction[Any, Any]:
        """Construct the synthetic handoff tool that signals routing to `target_id`."""
        tool_name = get_handoff_tool_name(target_id)
        doc = description or f"Handoff to the {target_id} agent."
        # Note: approval_mode is intentionally NOT set for handoff tools.
        # Handoff tools are framework-internal signals that trigger routing logic,
        # not actual function executions. They are automatically intercepted by
        # _AutoHandoffMiddleware which short-circuits execution and provides synthetic
        # results, so the function body never actually runs in practice.

        @ai_function(name=tool_name, description=doc)
        def _handoff_tool(context: str | None = None) -> str:
            """Return a deterministic acknowledgement that encodes the target alias."""
            return f"Handoff to {target_id}"

        return _handoff_tool

    @override
    async def _run_agent_and_emit(self, ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse]):
        """Override to support handoff."""
        if ctx.is_streaming():
            # Streaming mode: emit incremental updates
            response = await self._run_agent_streaming(cast(WorkflowContext, ctx))
        else:
            # Non-streaming mode: use run() and emit single event
            response = await self._run_agent(cast(WorkflowContext, ctx))

        if response is None:
            # Agent did not complete (e.g., waiting for user input); do not emit response
            logger.debug("AgentExecutor %s: Agent did not complete, awaiting user input", self.id)
            return

        # Check for handoff signal in the response
        pass


class HandoffBuilder:
    r"""Fluent builder for conversational handoff workflows with multiple agents.

    The handoff pattern enables a group of agents to route control among themselves.

    Routing Pattern:

    Agents can hand off to other agents using `.add_handoff()`. This provides a decentralized
    approach to multi-agent collaboration. Handoffs can be configured using `.add_handoff`. If
    none are specified, all agents can hand off to all others by default (making a mesh topology).

    Participants must be agents. Support for custom executors is not available in handoff workflows.
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
                          unique identifier (display_name for agents).
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
            self.participant_factories(participant_factories)

        if participants:
            self.participants(participants)

        # Handoff related members
        self._handoff_config: dict[str, set[HandoffConfiguration]] = {}

        # Checkpoint related members
        self._checkpoint_storage: CheckpointStorage | None = None

        self._request_prompt: str | None = None

        # Termination related members
        self._termination_condition: Callable[[list[ChatMessage]], bool | Awaitable[bool]] | None = None

        # Request info related members
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] | None = None

        # Unknown yet
        self._return_to_previous: bool = False
        self._interaction_mode: Literal["human_in_loop", "autonomous"] = "human_in_loop"
        self._autonomous_turn_limit: int | None = _DEFAULT_AUTONOMOUS_TURN_LIMIT

    # region Fluent Configuration Methods

    def participant_factories(
        self, participant_factories: Mapping[str, Callable[[], AgentProtocol]]
    ) -> "HandoffBuilder":
        """Register factories that produce agents for the handoff workflow.

        Each factory is a callable that returns an AgentProtocol instance.
        Factories are invoked when building the workflow, allowing for lazy instantiation
        and state isolation per workflow instance.

        Args:
            participant_factories: Mapping of factory names to callables that return AgentProtocol
                                   instances. Each produced participant must have a unique identifier
                                   (display_name for agents).

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participant_factories is empty or `.participants(...)`  or `.participant_factories(...)`
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
            builder = HandoffBuilder().participant_factories(factories)
            builder.with_start_agent("triage")
        """
        if self._participants:
            raise ValueError(
                "Cannot mix .participants([...]) and .participant_factories() in the same builder instance."
            )

        if self._participant_factories:
            raise ValueError("participant_factories() has already been called on this builder instance.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = dict(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol]) -> "HandoffBuilder":
        """Register the agents that will participate in the handoff workflow.

        Each participant must have a unique identifier (display_name for agents).
        The workflow will automatically create an alias map so agents can be referenced by
        their display_name when routing.

        Args:
            participants: Sequence of AgentProtocol instances. Each must have a unique identifier.
                          For agents, the display_name attribute is used as the primary identifier
                          and must match handoff target strings.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If participants is empty, contains duplicates, or `.participants(...)` or
                        `.participant_factories(...)` has already been called.
            TypeError: If participants are not AgentProtocol instances.

        Example:

        .. code-block:: python

            from agent_framework import HandoffBuilder
            from agent_framework.openai import OpenAIChatClient

            client = OpenAIChatClient()
            triage = client.create_agent(instructions="...", name="triage_agent")
            refund = client.create_agent(instructions="...", name="refund_agent")
            billing = client.create_agent(instructions="...", name="billing_agent")

            builder = HandoffBuilder().participants([triage, refund, billing])
            builder.with_start_agent(triage)
        """
        if self._participant_factories:
            raise ValueError(
                "Cannot mix .participants([...]) and .participant_factories() in the same builder instance."
            )

        if self._participants:
            raise ValueError("participants have already been assigned")

        if not participants:
            raise ValueError("participants cannot be empty")

        named: dict[str, AgentProtocol] = {}
        for participant in participants:
            if isinstance(participant, AgentProtocol):
                identifier = self._resolve_to_id(participant)
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

            if identifier in named:
                raise ValueError(f"Duplicate participant name '{identifier}' detected")
            named[identifier] = participant

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
                raise ValueError("Call participant_factories(...) before with_start_agent(...)")
            self._start_id = agent
        elif isinstance(agent, AgentProtocol):
            if self._participants:
                if agent.display_name not in self._participants:
                    raise ValueError(f"Start agent '{agent.display_name}' is not in the participants list")
            else:
                raise ValueError("Call participants(...) before with_start_agent(...)")
            self._start_id = agent.display_name
        else:
            raise TypeError("Start agent must be a factory name (str) or an AgentProtocol instance")

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

    def with_request_info(
        self,
        *,
        agents: Sequence[str | AgentProtocol] | None = None,
    ) -> "HandoffBuilder":
        """Enable request info after agent participant responses.

        This enables human-in-the-loop (HIL) scenarios for the handoff orchestration.
        When enabled, the workflow pauses after each agent participant runs, emitting
        a RequestInfoEvent that allows the caller to review the conversation and optionally
        inject guidance for the agent participant to iterate. The caller provides input via
        the standard response_handler/request_info pattern.

        Simulated flow with HIL:
        Input -> [Participant <-> Request Info] -> [Participant <-> Request Info] -> ...

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
        if not self._participants and not self._participant_factories:
            raise ValueError(
                "No participants or participant_factories have been configured. "
                "Call participants(...) or participant_factories(...) first."
            )

        if self._start_id is None:
            raise ValueError("Must call with_start_agent(...) before building the workflow.")

        # Resolve agents (either from instances or factories)
        # The returned map keys are either executor IDs or factory names, which is need to resolve handoff configs
        resolved_agents = self._resolve_agents()
        # Resolve handoff configurations to use agent display names
        # The returned map keys are executor IDs
        resolved_handoffs = self._resolve_handoffs(resolved_agents)
        # Resolve agents into executors
        executors = self._resolve_executors(list(resolved_agents.values()), resolved_handoffs)

        # Build the workflow graph
        start_executor = executors[resolved_agents[self._start_id].display_name]
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
            builder = builder.add_fan_out_edges(executor, [e for e in executors.values() if e.id != executor.id])

        # Configure checkpointing if enabled
        if self._checkpoint_storage:
            builder.with_checkpointing(self._checkpoint_storage)

        # TODO(@taochen): handle termination condition, request info

        return builder.build()

    # endregion Fluent Configuration Methods

    # region Internal Helper Methods

    def _resolve_agents(self) -> dict[str, AgentProtocol]:
        """Resolve participant factories into agent instances.

        If agent instances were provided directly via participants(...), those are
        returned as-is. If participant factories were provided via participant_factories(...),
        those are invoked to create the agent instances.

        Returns:
            Map of executor IDs or factory names to `AgentProtocol` instances
        """
        if self._participants and self._participant_factories:
            raise ValueError("Cannot have both executors and participant_factories configured")

        if self._participants:
            return self._participants

        if self._participant_factories:
            # Invoke each factory to create participant instances
            factory_names_to_agents: dict[str, AgentProtocol] = {}
            for factory_name, factory in self._participant_factories.items():
                instance = factory()
                if isinstance(instance, AgentProtocol):
                    identifier = instance.display_name
                else:
                    raise TypeError(
                        f"Participants must be AgentProtocol or Executor instances. Got {type(instance).__name__}."
                    )

                if identifier in factory_names_to_agents:
                    raise ValueError(f"Duplicate participant name '{identifier}' detected")

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
        # Updated map that used agent display_name as keys
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

                    updated_handoff_configurations.setdefault(source_agent.display_name, []).append(
                        HandoffConfiguration(
                            target=target_agent.display_name,
                            description=handoff_config.description or target_agent.description,
                        )
                    )
        else:
            # Use default handoff configuration: all agents can hand off to all others (mesh topology)
            for source_id, source_agent in agents.items():
                for target_id, target_agent in agents.items():
                    if source_id == target_id:
                        continue  # Skip self-handoff
                    updated_handoff_configurations.setdefault(source_agent.display_name, []).append(
                        HandoffConfiguration(
                            target=target_agent.display_name,
                            description=target_agent.description,
                        )
                    )

        return updated_handoff_configurations

    def _resolve_executors(
        self,
        agents: list[AgentProtocol],
        handoffs: dict[str, list[HandoffConfiguration]],
    ) -> dict[str, HandoffAgentExecutor]:
        """Resolve agents into HandoffAgentExecutors.

        Returns:
            Tuple of (starting executor ID, list of HandoffAgentExecutor instances)
        """
        executors: dict[str, HandoffAgentExecutor] = {}

        for agent in agents:
            if agent.display_name not in handoffs or not handoffs.get(agent.display_name):
                # All agents should have handoff configurations at this point
                raise ValueError(f"No handoff configuration found for agent '{agent.display_name}'")

            executors[agent.display_name] = HandoffAgentExecutor(
                agent=agent,
                handoffs=handoffs.get(agent.display_name),  # type: ignore
            )

        return executors

    def _resolve_to_id(self, candidate: str | AgentProtocol) -> str:
        """Resolve a participant reference into a concrete executor identifier."""
        if isinstance(candidate, AgentProtocol):
            return candidate.display_name
        if isinstance(candidate, str):
            return candidate

        raise TypeError(f"Invalid starting agent reference: {type(candidate).__name__}")

    # endregion Internal Helper Methods
