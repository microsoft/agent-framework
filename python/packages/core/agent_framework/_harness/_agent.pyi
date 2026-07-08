# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from typing_extensions import TypedDict, TypeVar

from .._agents import Agent, SupportsAgentRun
from .._clients import SupportsChatGetResponse
from .._compaction import CompactionStrategy, TokenizerProtocol
from .._middleware import MiddlewareTypes
from .._sessions import ContextProvider, HistoryProvider
from .._skills import SkillsProvider
from .._tools import ToolTypes
from .._types import ChatOptions
from ._file_access import AgentFileStore
from ._loop import DEFAULT_MAX_ITERATIONS, NextMessageCallable, ShouldContinueCallable
from ._mode import AgentModeProvider
from ._todo import TodoProvider
from ._tool_approval import ToolApprovalRuleCallback

DEFAULT_HARNESS_INSTRUCTIONS: str
HARNESS_AGENT_PROVIDER_NAME: str

OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default=ChatOptions[None],
)

class _ShellExecutorLike(Protocol):
    def as_function(self, *args: Any, **kwargs: Any) -> Any: ...

class _ShellEnvironmentProviderOptionsLike(Protocol):
    @property
    def probe_tools(self) -> Sequence[str]: ...
    @property
    def override_family(self) -> Any | None: ...
    @property
    def probe_timeout(self) -> float: ...
    @property
    def instructions_formatter(self) -> Callable[[Any], str] | None: ...

def _assemble_instructions(
    harness_instructions: str | None,
    agent_instructions: str | None,
) -> str | None: ...
def create_harness_agent(
    client: SupportsChatGetResponse[OptionsCoT],
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
    shell_executor: _ShellExecutorLike | None = None,
    shell_environment_provider_options: _ShellEnvironmentProviderOptionsLike | None = None,
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
) -> Agent[OptionsCoT]: ...
