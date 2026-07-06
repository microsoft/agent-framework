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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._agents import Agent, SupportsAgentRun
from .._clients import SupportsShellTool, SupportsWebSearchTool
from .._compaction import CompactionProvider, ContextWindowCompactionStrategy, ToolResultCompactionStrategy
from .._feature_stage import ExperimentalFeature, experimental
from .._sessions import ContextProvider, HistoryProvider, InMemoryHistoryProvider
from .._skills import SkillsProvider
from ._background_agents import BackgroundAgentsProvider
from ._file_access import AgentFileStore, FileAccessProvider, FileSystemAgentFileStore
from ._file_memory import FileMemoryProvider
from ._loop import DEFAULT_MAX_ITERATIONS, AgentLoopMiddleware
from ._mode import AgentModeProvider
from ._todo import TodoProvider
from ._tool_approval import ToolApprovalMiddleware

if TYPE_CHECKING:
    from collections.abc import Mapping

    from agent_framework_tools.shell import ShellEnvironmentProviderOptions, ShellExecutor

    from .._clients import SupportsChatGetResponse
    from .._compaction import CompactionStrategy, TokenizerProtocol
    from .._middleware import MiddlewareTypes
    from .._tools import ToolTypes
    from ._loop import NextMessageCallable, ShouldContinueCallable
    from ._tool_approval import ToolApprovalRuleCallback

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
    disable_file_memory: bool,
    file_memory_store: AgentFileStore | None,
    disable_file_access: bool,
    file_access_store: AgentFileStore | None,
    file_access_disable_write_tools: bool,
    file_access_disable_readonly_tool_approval: bool,
    file_access_disable_write_tool_approval: bool,
    skills_provider: SkillsProvider | None,
    skills_paths: str | Path | Sequence[str | Path] | None,
    background_agents: Sequence[SupportsAgentRun] | None,
    background_agents_instructions: str | None,
    shell_context_provider: ContextProvider | None,
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

    # File-based session memory (on by default). Default store is rooted at
    # ``{cwd}/agent-file-memory``; the provider isolates memories per session
    # via its default ``scope=session_id``.
    if not disable_file_memory:
        memory_store = file_memory_store or FileSystemAgentFileStore(Path.cwd() / "agent-file-memory")
        providers.append(FileMemoryProvider(memory_store))

    # Shared file access (on by default). Default store is rooted at ``{cwd}/working``.
    if not disable_file_access:
        access_store = file_access_store or FileSystemAgentFileStore(Path.cwd() / "working")
        providers.append(
            FileAccessProvider(
                access_store,
                disable_write_tools=file_access_disable_write_tools,
                disable_readonly_tool_approval=file_access_disable_readonly_tool_approval,
                disable_write_tool_approval=file_access_disable_write_tool_approval,
            )
        )

    # Skills are opt-in: only added when skills_provider or skills_paths is provided.
    if skills_provider:
        providers.append(skills_provider)
    if skills_paths:
        providers.append(SkillsProvider.from_paths(skills_paths))

    # Background agents are opt-in: only added when agents are provided.
    if background_agents:
        providers.append(BackgroundAgentsProvider(background_agents, instructions=background_agents_instructions))

    # Shell environment provider is opt-in: only added when a shell tool was wired.
    if shell_context_provider is not None:
        providers.append(shell_context_provider)

    # Append any user-supplied additional providers.
    if extra_context_providers:
        providers.extend(extra_context_providers)

    return providers


def _assemble_shell(
    client: SupportsChatGetResponse[Any],
    shell_executor: ShellExecutor | None,
    shell_environment_provider_options: ShellEnvironmentProviderOptions | None,
) -> tuple[ToolTypes | None, ContextProvider | None]:
    """Build the shell tool and environment provider when a shell executor is supplied.

    Returns a ``(tool, provider)`` tuple. Both are ``None`` when no shell executor is
    provided, or when the client does not support shell tools (a warning is logged in the
    latter case, since the environment provider is not useful without an execution path).

    Raises:
        TypeError: If ``shell_executor`` does not expose a callable ``as_function()`` method.
    """
    if shell_executor is None:
        return None, None

    # ShellExecutor is a protocol without ``as_function()``, so the
    # contract is validated at runtime: a shell tool such as LocalShellTool/DockerShellTool exposes it.
    as_function = getattr(shell_executor, "as_function", None)
    if not callable(as_function):
        raise TypeError(
            f"shell_executor must expose a callable 'as_function()' method "
            f"(e.g. a LocalShellTool or DockerShellTool from agent-framework-tools), "
            f"but got {type(shell_executor).__name__}."
        )

    if not isinstance(client, SupportsShellTool):
        logger.warning(
            "Shell tool not available: client %r does not implement SupportsShellTool. "
            "Skipping the shell tool and environment provider.",
            type(client).__name__,
        )
        return None, None

    # Imported lazily: the shell types live in the separate agent-framework-tools package,
    # which depends on core, so core cannot import them at module load time.
    from agent_framework_tools.shell import ShellEnvironmentProvider

    shell_tool = client.get_shell_tool(func=as_function())
    shell_provider = ShellEnvironmentProvider(shell_executor, shell_environment_provider_options)
    return shell_tool, shell_provider


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
    disable_file_memory: bool = False,
    file_memory_store: AgentFileStore | None = None,
    disable_file_access: bool = False,
    file_access_store: AgentFileStore | None = None,
    file_access_disable_write_tools: bool = False,
    file_access_disable_readonly_tool_approval: bool = False,
    file_access_disable_write_tool_approval: bool = False,
    skills_provider: SkillsProvider | None = None,
    skills_paths: str | Path | Sequence[str | Path] | None = None,
    background_agents: Sequence[SupportsAgentRun] | None = None,
    background_agents_instructions: str | None = None,
    shell_executor: ShellExecutor | None = None,
    shell_environment_provider_options: ShellEnvironmentProviderOptions | None = None,
    disable_web_search: bool = False,
    disable_tool_auto_approval: bool = False,
    auto_approval_rules: Sequence[ToolApprovalRuleCallback] | None = None,
    loop_should_continue: ShouldContinueCallable | None = None,
    loop_next_message: NextMessageCallable | None = None,
    loop_max_iterations: int | None = DEFAULT_MAX_ITERATIONS,
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
    - **FileMemoryProvider** — file-based session memory (on by default)
    - **FileAccessProvider** — shared file read/write tools (on by default)
    - **SkillsProvider** — skill discovery and progressive loading
    - **BackgroundAgentsProvider** — delegate work to background sub-agents
    - **Tool approval** — "don't ask again" standing approval rules plus heuristic
      auto-approval callbacks
    - **Looping** — re-run the agent until a ``should_continue`` predicate is satisfied
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
        disable_file_memory: When True, skip the FileMemoryProvider. When False (default),
            a FileMemoryProvider is added, giving the agent session-scoped, file-based memory.
        file_memory_store: Custom AgentFileStore backing the FileMemoryProvider. When None
            (and disable_file_memory is False), a FileSystemAgentFileStore rooted at
            ``{cwd}/agent-file-memory`` is created. Ignored when disable_file_memory is True.
        disable_file_access: When True, skip the FileAccessProvider. When False (default),
            a FileAccessProvider is added, giving the agent shared read/write file tools.
        file_access_store: Custom AgentFileStore backing the FileAccessProvider. When None
            (and disable_file_access is False), a FileSystemAgentFileStore rooted at
            ``{cwd}/working`` is created. Ignored when disable_file_access is True.
        file_access_disable_write_tools: When True, the FileAccessProvider advertises only its
            read-only tools (read, ls, grep); the write tools (write, delete, replace,
            replace_lines) are hidden. When False (default), all tools are advertised. Ignored
            when disable_file_access is True.
        file_access_disable_readonly_tool_approval: When True, the FileAccessProvider's read-only
            tools (read, ls, grep) are registered with ``approval_mode="never_require"`` so they
            run without host approval. When False (default), they require approval. Ignored when
            disable_file_access is True.
        file_access_disable_write_tool_approval: When True, the FileAccessProvider's write tools
            (write, delete, replace, replace_lines) are registered with
            ``approval_mode="never_require"`` so they run without host approval. When False
            (default), they require approval. Ignored when disable_file_access is True.
        skills_provider: Custom SkillsProvider instance for code-defined skills.
            Can be combined with ``skills_paths`` to aggregate file and code-based skills.
        skills_paths: Paths for file-based skill discovery (looks for SKILL.md files).
            Accepts a single ``str`` or :class:`~pathlib.Path`, or a sequence of
            ``str | Path``. Can be combined with ``skills_provider``. When neither
            ``skills_provider`` nor ``skills_paths`` is provided, no SkillsProvider
            is added.
        background_agents: Collection of agents available for background task delegation.
            When provided, a ``BackgroundAgentsProvider`` is automatically included,
            enabling the agent to start, monitor, and retrieve results from background tasks.
            Each agent must have a non-empty, unique name (case-insensitive).
        background_agents_instructions: Optional instruction override for the
            ``BackgroundAgentsProvider``. May include ``{background_agents}`` placeholder
            which will be replaced with the agent listing.
        shell_executor: Optional shell tool that enables shell command execution. When
            provided, the shell tool and a ``ShellEnvironmentProvider`` are automatically
            added (provided the client supports shell tools; otherwise a warning is logged
            and both are skipped). The object must expose ``as_function()`` and satisfy the
            ``ShellExecutor`` protocol -- e.g. a ``LocalShellTool`` or ``DockerShellTool`` from
            the ``agent-framework-tools`` package. The caller owns the executor's lifecycle.
        shell_environment_provider_options: Optional ``ShellEnvironmentProviderOptions``
            (from ``agent-framework-tools``) used to customize the ``ShellEnvironmentProvider``
            environment probing and instructions. Only used when ``shell_executor`` is provided.
        disable_web_search: When True, skip automatic web search tool inclusion.
            When False (default), the web search tool is automatically added if the
            client implements SupportsWebSearchTool. A warning is logged if the client
            does not support web search.
        disable_tool_auto_approval: When True, do not wire the tool auto-approval middleware.
            When False (default), a :class:`~agent_framework.ToolApprovalMiddleware` is added
            (outermost) to coordinate "don't ask again" standing approval rules and queued
            approval prompts; callers must pass an :class:`~agent_framework.AgentSession` to
            :meth:`~agent_framework.Agent.run` when enabled.
        auto_approval_rules: Optional heuristic callbacks that can auto-approve a function call
            that would otherwise require approval. Each callback receives the ``function_call``
            content and returns ``True`` to approve it. Rules are evaluated after standing rules
            (derived from prior user approvals) but before prompting the user. Only used when
            ``disable_tool_auto_approval`` is False.
        loop_should_continue: Optional predicate that enables the looping middleware. When provided, the
            agent is re-run in a loop (via :class:`~agent_framework.AgentLoopMiddleware`, wired as
            the outermost middleware so each iteration is a full agent run including tool approval)
            for as long as the predicate returns ``True``, up to ``loop_max_iterations``. If an
            iteration returns a pending tool-approval request, the loop stops and returns it so the
            caller can approve before continuing. When None (default), no loop is added.
        loop_next_message: Optional callable controlling the input for the next loop iteration.
            Only takes effect when ``loop_should_continue`` is set (otherwise no loop is added and
            this is ignored).
        loop_max_iterations: Safety cap on the number of loop iterations. ``None`` means unbounded;
            a positive integer caps the loop (defaults to the loop middleware's default cap). Only
            takes effect when ``loop_should_continue`` is set (otherwise no loop is added and this
            is ignored).
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

    # Build the shell tool and environment provider (opt-in via shell_executor).
    shell_tool, shell_provider = _assemble_shell(
        client,
        shell_executor,
        shell_environment_provider_options,
    )

    # Build context providers.
    assembled_providers = _assemble_context_providers(
        history_provider=resolved_history,
        compaction_provider=compaction_provider,
        disable_todo=disable_todo,
        todo_provider=todo_provider,
        disable_mode=disable_mode,
        mode_provider=mode_provider,
        disable_file_memory=disable_file_memory,
        file_memory_store=file_memory_store,
        disable_file_access=disable_file_access,
        file_access_store=file_access_store,
        file_access_disable_write_tools=file_access_disable_write_tools,
        file_access_disable_readonly_tool_approval=file_access_disable_readonly_tool_approval,
        file_access_disable_write_tool_approval=file_access_disable_write_tool_approval,
        skills_provider=skills_provider,
        skills_paths=skills_paths,
        background_agents=background_agents,
        background_agents_instructions=background_agents_instructions,
        shell_context_provider=shell_provider,
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
    if shell_tool is not None:
        assembled_tools.append(shell_tool)
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

    # Assemble middleware. Tool approval is enabled by default (like the .NET harness) and is
    # placed first so it sits outermost: it intercepts inbound "always approve" responses and
    # outbound approval requests at the caller boundary, and its re-invocation loop re-runs any
    # user-supplied middleware. ToolApprovalMiddleware requires an AgentSession at run time.
    # When should_continue is supplied, the loop is prepended ahead of tool approval so it sits
    # outermost of all: each loop iteration is a full agent run (including tool approval), and the
    # loop's approval escape hatch returns any pending approval request to the caller.
    assembled_middleware: list[MiddlewareTypes] = []
    if not disable_tool_auto_approval:
        assembled_middleware.append(ToolApprovalMiddleware(auto_approval_rules=auto_approval_rules))
    if loop_should_continue is not None:
        assembled_middleware.insert(
            0,
            AgentLoopMiddleware(
                loop_should_continue,
                max_iterations=loop_max_iterations,
                next_message=loop_next_message,
            ),
        )
    if middleware:
        assembled_middleware.extend(middleware)

    agent = Agent(
        client,
        instructions,
        id=id,
        name=name,
        description=description,
        tools=final_tools,
        default_options=default_opts,  # type: ignore[arg-type]
        context_providers=assembled_providers,
        middleware=assembled_middleware or None,
        require_per_service_call_history_persistence=True,
    )

    # Set the telemetry provider name after construction.
    agent.otel_provider_name = otel_provider_name or HARNESS_AGENT_PROVIDER_NAME

    return agent
