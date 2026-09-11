# Copyright (c) Microsoft. All rights reserved.

import logging
from dataclasses import dataclass
from typing import Any, cast

logger = logging.getLogger(__name__)

# Default maximum iterations for workflow execution.
DEFAULT_MAX_ITERATIONS = 100

# Key used to store executor state in state.
EXECUTOR_STATE_KEY = "_executor_state"

# Key used to store edge runner delivery state (for example, fan-in buffers) in state.
EDGE_STATE_KEY = "_edge_state"

# Source identifier for internal workflow messages.
INTERNAL_SOURCE_PREFIX = "internal"

# State key for storing run kwargs that should be passed to agent invocations.
# Used by all orchestration patterns (Sequential, Concurrent, GroupChat, Handoff, Magentic)
# to pass kwargs from workflow.run() through to agent.run() and @tool functions.
WORKFLOW_RUN_KWARGS_KEY = "_workflow_run_kwargs"

# State keys used to preserve caller-provided kwargs for nested workflow routing.
RAW_FUNCTION_INVOCATION_KWARGS_KEY = "_raw_function_invocation_kwargs"
RAW_CLIENT_KWARGS_KEY = "_raw_client_kwargs"

# Legacy sentinel for global kwargs in pre-structured run state and compatible plain input.
GLOBAL_KWARGS_KEY = "__global__"


@dataclass(frozen=True)
class ResolvedWorkflowInvocationKwargs:
    """Keep resolved global and executor-specific kwargs in separate namespaces."""

    global_kwargs: dict[str, Any] | None = None
    executor_kwargs: dict[str, Any] | None = None

    def for_executor(self, executor_id: str) -> dict[str, Any] | None:
        """Resolve ordinary kwargs for one executor, with specific values taking precedence."""
        global_kwargs = self.global_kwargs
        executor_kwargs: Any = self.executor_kwargs.get(executor_id) if self.executor_kwargs is not None else None

        if global_kwargs is None and executor_kwargs is None:
            return None
        if global_kwargs is not None and not isinstance(global_kwargs, dict):
            logger.warning(
                "Executor %s expected a dict for global kwargs, but got %s. Ignoring.",
                executor_id,
                cast(type[Any], type(global_kwargs)),
            )
            return None
        if executor_kwargs is not None and not isinstance(executor_kwargs, dict):
            logger.warning(
                "Executor %s expected a dict for its kwargs, but got %s. Ignoring.",
                executor_id,
                cast(type[Any], type(executor_kwargs)),
            )
            return None

        return {**(global_kwargs or {}), **(executor_kwargs or {})}


def INTERNAL_SOURCE_ID(executor_id: str) -> str:
    """Generate an internal source ID for a given executor."""
    return f"{INTERNAL_SOURCE_PREFIX}:{executor_id}"
