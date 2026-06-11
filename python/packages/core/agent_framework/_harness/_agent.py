# Copyright (c) Microsoft. All rights reserved.

"""Harness agent factory: a pre-configured bundled agent with batteries included.

This module provides :func:`create_harness_agent`, a factory function that assembles
the full agent pipeline from a chat client, wiring up function invocation,
per-service-call history persistence, compaction, and a rich set of default
context providers (todo, mode, memory, skills).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from .._agents import Agent, SupportsAgentRun
from .._clients import SupportsWebSearchTool
from .._compaction import CompactionProvider, ContextWindowCompactionStrategy, ToolResultCompactionStrategy
from .._feature_stage import ExperimentalFeature, experimental
from .._sessions import ContextProvider, HistoryProvider, InMemoryHistoryProvider
from .._skills import SkillsProvider
from ._background_agents import BackgroundAgentsProvider
from ._memory import MemoryContextProvider, MemoryStore
from ._mode import AgentModeProvider
from ._todo import TodoProvider

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .._clients import SupportsChatGetResponse
    from .._compaction import CompactionStrategy, TokenizerProtocol
    from .._middleware import MiddlewareTypes
    from .._tools import ToolTypes

logger = logging.getLogger(__name__)

DEFAULT_HARNESS_INSTRUCTIONS = """\
You are a helpful AI assistant that uses tools to complete tasks.

## General guidelines

- Think through the task before acting. Break complex work into clear steps.
- Use the tools available to you to gather information, perform actions, and verify results.
- Explain your reasoning and thought process as you work through tasks.
- Explain what you learned and what you are going to do next between tool calls, \
so the user can follow along with your thought process.
- Avoid making more than 4 tool calls in a row without explaining what you are doing.
- If a tool call fails or returns unexpected results, adapt your approach rather than \
repeating the same call.
- When you have completed the task, present a clear and concise summary of what you did \
and what you found.
"""


def _assemble_instructions(
    harness_instructions: str | None,
    agent_instructions: str | None,
) -> str | None:
    """Assemble final instructions from harness + agent instructions."""
    harness = harness_instructions if harness_instructions is not None else DEFAULT_HARNESS_INSTRUCTIONS

    return f"{harness}\n\n{agent_instructions or ''}".strip() or None


def _assemble_compaction_provider(
    *,
    disable_compaction: bool,
    max_context_window_tokens: int | None,
    max_output_tokens: int | None,
    history_source_id: str,
    before_compaction_strategy: CompactionStrategy | None,
    after_compaction_strategy: CompactionStrategy | None,
    tokenizer: TokenizerProtocol | None,
) -> CompactionProvider | None:
    """Build the compaction provider from parameters or defaults.

    The token-budget defaults (``ContextWindowCompactionStrategy`` for the before phase and
    ``ToolResultCompactionStrategy`` for the after phase) are only applied when the token
    params are provided. Caller-supplied strategies are always honored. Either phase may end
    up ``None``, which ``CompactionProvider`` interprets as "skip that phase".

    Returns None when compaction is explicitly disabled, or when neither phase has a strategy
    (no custom strategies and no token budget to build the defaults).
    """
    if disable_compaction:
        return None

    # Resolve the before-strategy: custom strategy wins; otherwise fall back to the
    # token-budget-aware default when token params are available.
    before_strategy = before_compaction_strategy
    if before_strategy is None and max_context_window_tokens is not None and max_output_tokens is not None:
        before_strategy = ContextWindowCompactionStrategy(
            max_context_window_tokens=max_context_window_tokens,
            max_output_tokens=max_output_tokens,
            tokenizer=tokenizer,
        )

    # Resolve the after-strategy: custom strategy wins; otherwise fall back to the default
    # when token params are available.
    after_strategy = after_compaction_strategy
    if after_strategy is None and max_context_window_tokens is not None and max_output_tokens is not None:
        after_strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=2)

    # Nothing to compact in either phase: skip the provider entirely.
    if before_strategy is None and after_strategy is None:
        return None

    return CompactionProvider(
        before_strategy=before_strategy,
        after_strategy=after_strategy,
        tokenizer=tokenizer,
        history_source_id=history_source_id,
    )


def _assemble_context_providers(
    *,
    history_provider: HistoryProvider,
    compaction_provider: CompactionProvider | None,
    disable_todo: bool,
    todo_provider: TodoProvider | None,
    disable_mode: bool,
    mode_provider: AgentModeProvider | None,
    disable_memory: bool,
    memory_store: MemoryStore | None,
    skills_provider: SkillsProvider | None,
    skills_paths: Sequence[str] | None,
    background_agents: Sequence[SupportsAgentRun] | None,
    background_agents_instructions: str | None,
    extra_context_providers: Sequence[ContextProvider] | None,
) -> list[ContextProvider]:
    """Assemble the ordered list of context providers."""
    providers: list[ContextProvider] = []

    # History first so other providers can access loaded messages.
    providers.append(history_provider)

    # Compaction runs after history loads messages.
    if compaction_provider is not None:
        providers.append(compaction_provider)

    if not disable_todo:
        providers.append(todo_provider or TodoProvider())

    if not disable_mode:
        providers.append(mode_provider or AgentModeProvider())

    if not disable_memory and memory_store is not None:
        providers.append(MemoryContextProvider(store=memory_store))

    # Skills are opt-in: only added when skills_provider or skills_paths is provided.
    if skills_provider:
        providers.append(skills_provider)
    if skills_paths:
        providers.append(SkillsProvider.from_paths(*skills_paths))

    # Background agents are opt-in: only added when agents are provided.
    if background_agents:
        providers.append(BackgroundAgentsProvider(background_agents, instructions=background_agents_instructions))

    # Append any user-supplied additional providers.
    if extra_context_providers:
        providers.extend(extra_context_providers)

    return providers


HARNESS_AGENT_PROVIDER_NAME = "microsoft.agent_framework.harness"


@experimental(feature_id=ExperimentalFeature.HARNESS)
def create_harness_agent(
    client: SupportsChatGetResponse[Any],
    *,
    id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    harness_instructions: str | None = None,
    agent_instructions: str | None = None,
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
    max_context_window_tokens: int | None = None,
    max_output_tokens: int | None = None,
    history_provider: HistoryProvider | None = None,
    disable_compaction: bool = False,
    before_compaction_strategy: CompactionStrategy | None = None,
    after_compaction_strategy: CompactionStrategy | None = None,
    tokenizer: TokenizerProtocol | None = None,
    disable_todo: bool = False,
    todo_provider: TodoProvider | None = None,
    disable_mode: bool = False,
    mode_provider: AgentModeProvider | None = None,
    disable_memory: bool = False,
    memory_store: MemoryStore | None = None,
    skills_provider: SkillsProvider | None = None,
    skills_paths: Sequence[str] | None = None,
    background_agents: Sequence[SupportsAgentRun] | None = None,
    background_agents_instructions: str | None = None,
    disable_web_search: bool = False,
    otel_provider_name: str | None = None,
    context_providers: Sequence[ContextProvider] | None = None,
    middleware: Sequence[MiddlewareTypes] | None = None,
    default_options: Mapping[str, Any] | None = None,
) -> Agent[Any]:
    """Create a pre-configured agent with batteries included.

    Assembles an :class:`~agent_framework.Agent` from a chat client, automatically wiring:

    - **Function invocation** — automatic tool calling loop
    - **Per-service-call history persistence** — persists history after every model call
    - **Compaction** — context-window compaction before/after each run
    - **TodoProvider** — todo list management
    - **AgentModeProvider** — plan/execute mode tracking
    - **MemoryContextProvider** — file-based durable memory (when ``memory_store`` provided)
    - **SkillsProvider** — skill discovery and progressive loading
    - **BackgroundAgentsProvider** — delegate work to background sub-agents
    - **OpenTelemetry** — observability via ``AgentTelemetryLayer``

    Each feature can be disabled or customized via keyword arguments.

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import create_harness_agent
            from agent_framework.openai import OpenAIChatClient

            agent = create_harness_agent(
                OpenAIChatClient(model="gpt-4o"),
            )
            session = agent.create_session()
            response = await agent.run("Plan a weekend trip to Seattle", session=session)

        With customization:

        .. code-block:: python

            agent = create_harness_agent(
                client=client,
                max_context_window_tokens=200_000,
                max_output_tokens=32_000,
                name="research-agent",
                agent_instructions="Focus on academic sources.",
                disable_todo=True,
                skills_paths=["./skills", "./custom-skills"],
            )

    Args:
        client: The chat client providing access to the underlying AI model.

    Keyword Args:
        id: Optional agent ID (auto-generated UUID if omitted).
        name: Optional agent name.
        description: Optional agent description.
        harness_instructions: Override the default harness-level system instructions that
            govern agent behavior (how to use tools, report progress, structure responses).
            These provide general "operating guidelines" independent of any specific task.
            When None, ``DEFAULT_HARNESS_INSTRUCTIONS`` is used. Set to empty string ``""``
            to omit harness instructions entirely.
        agent_instructions: Domain or task-specific instructions appended after harness
            instructions. Use this for the agent's purpose, persona, or specialization
            (e.g., "You are a research assistant focused on academic sources.").
        tools: Additional tools to include in the agent's toolset.
        max_context_window_tokens: Maximum tokens the model's context window supports.
            Used to construct the default token-budget-aware compaction strategies. When None
            (default) and no custom ``before_compaction_strategy`` / ``after_compaction_strategy``
            is provided, compaction is automatically disabled.
        max_output_tokens: Maximum output tokens per response.
            Used to construct the default compaction strategies and sets a default max_tokens
            chat option. When None (default), no default max_tokens option is set, and unless a
            custom compaction strategy is provided, compaction is automatically disabled.
        history_provider: Custom history provider. When None, an InMemoryHistoryProvider is used.
        disable_compaction: When True, skip compaction provider setup.
        before_compaction_strategy: Custom before-run compaction strategy. When provided,
            compaction runs even if token params are omitted. Defaults to
            ContextWindowCompactionStrategy (token-budget aware) when token params are provided.
        after_compaction_strategy: Custom after-run compaction strategy. When provided,
            compaction runs even if token params are omitted. Defaults to
            ToolResultCompactionStrategy when token params are provided.
        tokenizer: Custom tokenizer for compaction strategies.
        disable_todo: When True, skip the TodoProvider.
        todo_provider: Custom TodoProvider instance. Ignored when disable_todo is True.
        disable_mode: When True, skip the AgentModeProvider.
        mode_provider: Custom AgentModeProvider instance. Ignored when disable_mode is True.
        disable_memory: When True, skip the MemoryContextProvider.
        memory_store: Memory store instance. When provided (and disable_memory is False),
            a MemoryContextProvider is added.
        skills_provider: Custom SkillsProvider instance for code-defined skills.
            Can be combined with ``skills_paths`` to aggregate file and code-based skills.
        skills_paths: Paths for file-based skill discovery (looks for SKILL.md files).
            Can be combined with ``skills_provider``. When neither ``skills_provider``
            nor ``skills_paths`` is provided, no SkillsProvider is added.
        background_agents: Collection of agents available for background task delegation.
            When provided, a ``BackgroundAgentsProvider`` is automatically included,
            enabling the agent to start, monitor, and retrieve results from background tasks.
            Each agent must have a non-empty, unique name (case-insensitive).
        background_agents_instructions: Optional instruction override for the
            ``BackgroundAgentsProvider``. May include ``{background_agents}`` placeholder
            which will be replaced with the agent listing.
        disable_web_search: When True, skip automatic web search tool inclusion.
            When False (default), the web search tool is automatically added if the
            client implements SupportsWebSearchTool. A warning is logged if the client
            does not support web search.
        otel_provider_name: Custom OpenTelemetry provider/source name for telemetry.
        context_providers: Additional context providers to include after the built-in ones.
        middleware: Additional middleware to include.
        default_options: Provider-specific chat options (temperature, max_tokens, etc.).

    Returns:
        A fully configured :class:`~agent_framework.Agent` instance.

    Raises:
        ValueError: If max_context_window_tokens is provided and <= 0, or
            max_output_tokens is provided and <= 0, or max_output_tokens >=
            max_context_window_tokens when both are provided.
    """
    if max_context_window_tokens is not None and max_context_window_tokens <= 0:
        raise ValueError("max_context_window_tokens must be positive.")
    if max_output_tokens is not None and max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be positive.")
    if (
        max_context_window_tokens is not None
        and max_output_tokens is not None
        and max_output_tokens >= max_context_window_tokens
    ):
        raise ValueError("max_output_tokens must be less than max_context_window_tokens.")

    # Build history provider.
    resolved_history = history_provider or InMemoryHistoryProvider()

    # Build compaction provider.
    compaction_provider = _assemble_compaction_provider(
        disable_compaction=disable_compaction,
        max_context_window_tokens=max_context_window_tokens,
        max_output_tokens=max_output_tokens,
        history_source_id=resolved_history.source_id,
        before_compaction_strategy=before_compaction_strategy,
        after_compaction_strategy=after_compaction_strategy,
        tokenizer=tokenizer,
    )

    # Build context providers.
    assembled_providers = _assemble_context_providers(
        history_provider=resolved_history,
        compaction_provider=compaction_provider,
        disable_todo=disable_todo,
        todo_provider=todo_provider,
        disable_mode=disable_mode,
        mode_provider=mode_provider,
        disable_memory=disable_memory,
        memory_store=memory_store,
        skills_provider=skills_provider,
        skills_paths=skills_paths,
        background_agents=background_agents,
        background_agents_instructions=background_agents_instructions,
        extra_context_providers=context_providers,
    )

    # Build instructions.
    instructions = _assemble_instructions(harness_instructions, agent_instructions)

    # Assemble tools, auto-adding web search if supported.
    assembled_tools: list[ToolTypes | Callable[..., Any]] = []
    if not disable_web_search:
        if isinstance(client, SupportsWebSearchTool):
            assembled_tools.append(client.get_web_search_tool())
        else:
            logger.warning(
                "Web search tool not available: client %r does not implement SupportsWebSearchTool. "
                "Set disable_web_search=True to suppress this warning.",
                type(client).__name__,
            )
    if tools is not None:
        if isinstance(tools, Sequence):
            assembled_tools.extend(tools)  # pyright: ignore[reportUnknownArgumentType]
        else:
            assembled_tools.append(tools)
    final_tools: list[ToolTypes | Callable[..., Any]] | None = assembled_tools or None

    # Build default options dict.
    default_opts: dict[str, Any] = dict(default_options) if default_options else {}
    if max_output_tokens is not None:
        default_opts.setdefault("max_tokens", max_output_tokens)

    agent = Agent(
        client,
        instructions,
        id=id,
        name=name,
        description=description,
        tools=final_tools,
        default_options=default_opts,  # type: ignore[arg-type]
        context_providers=assembled_providers,
        middleware=list(middleware) if middleware else None,
        require_per_service_call_history_persistence=True,
    )

    # Set the telemetry provider name after construction.
    agent.otel_provider_name = otel_provider_name or HARNESS_AGENT_PROVIDER_NAME

    return agent
