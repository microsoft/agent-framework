# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import Any, cast

from .._agents import SupportsAgentRun
from ._const import GLOBAL_KWARGS_KEY, RAW_CLIENT_KWARGS_KEY, RAW_FUNCTION_INVOCATION_KWARGS_KEY

logger = logging.getLogger(__name__)


def resolve_agent_id(agent: SupportsAgentRun) -> str:
    """Resolve the unique identifier for an agent.

    Prefers the `.name` attribute if set; otherwise falls back to `.id`.

    Args:
        agent: The agent whose identifier is to be resolved.

    Returns:
        The resolved unique identifier for the agent.
    """
    return agent.name if agent.name else agent.id


def _merge_executor_kwargs(
    executor_id: str,
    global_kwargs: Any,
    executor_kwargs: Any,
) -> dict[str, Any] | None:
    """Merge validated global and executor-specific kwargs for one executor."""
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

    # Specific values override global values for the same function argument.
    return {**(global_kwargs or {}), **(executor_kwargs or {})}


def resolve_executor_kwargs(executor_id: str, resolved: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract one executor's kwargs from a resolved invocation kwargs dict.

    Args:
        executor_id: The id of the executor whose kwargs are wanted.
        resolved: A legacy-compatible resolved dict containing either a ``__global__``
            key (global kwargs) or executor-ID keys (per-executor kwargs). May also be
            ``None``.

    Returns:
        The kwargs for that executor, or ``None`` if not applicable.
    """
    if not isinstance(resolved, dict):
        return None
    return _merge_executor_kwargs(executor_id, resolved.get(GLOBAL_KWARGS_KEY), resolved.get(executor_id))


def _resolve_structured_executor_kwargs(
    executor_id: str,
    resolved: Any,
) -> dict[str, Any] | None:
    """Extract one executor's kwargs from collision-free workflow run state."""
    if not isinstance(resolved, dict):
        raise TypeError("Resolved workflow invocation kwargs state must be a dict.")
    resolved_dict = cast(dict[str, Any], resolved)
    executor_kwargs = resolved_dict.get("executor_kwargs")
    specific_kwargs = (
        cast(dict[str, Any], executor_kwargs).get(executor_id) if isinstance(executor_kwargs, dict) else None
    )
    return _merge_executor_kwargs(executor_id, resolved_dict.get("global_kwargs"), specific_kwargs)


def prepare_executor_run_kwargs(
    executor_id: str,
    raw_run_kwargs: dict[str, Any],
    resolved_run_kwargs: Any = None,
) -> dict[str, Any]:
    """Prepare sanitized, executor-ready kwargs from workflow run state.

    New collision-free state takes precedence when present. Legacy dict state remains
    readable for checkpoint and package-version compatibility. Internal raw-routing
    snapshots are never forwarded to agents.

    Args:
        executor_id: The id of the executor about to invoke an agent.
        raw_run_kwargs: Legacy-compatible state stored under ``WORKFLOW_RUN_KWARGS_KEY``.
        resolved_run_kwargs: Collision-free state stored under the resolved run-state key.

    Returns:
        A copy of the run kwargs containing only values applicable to ``executor_id``.
    """
    run_kwargs = dict(raw_run_kwargs)
    run_kwargs.pop(RAW_FUNCTION_INVOCATION_KWARGS_KEY, None)
    run_kwargs.pop(RAW_CLIENT_KWARGS_KEY, None)

    if resolved_run_kwargs is not None and not isinstance(resolved_run_kwargs, dict):
        raise TypeError("Resolved workflow run kwargs state must be a dict.")

    for key in ("function_invocation_kwargs", "client_kwargs"):
        if resolved_run_kwargs is not None:
            executor_value = (
                _resolve_structured_executor_kwargs(executor_id, resolved_run_kwargs[key])
                if key in resolved_run_kwargs
                else None
            )
        else:
            executor_value = resolve_executor_kwargs(executor_id, raw_run_kwargs.get(key))
        if executor_value is None:
            run_kwargs.pop(key, None)
        else:
            run_kwargs[key] = executor_value

    return run_kwargs


def prepare_agent_run_args(
    executor_id: str,
    raw_run_kwargs: dict[str, Any],
    resolved_run_kwargs: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Prepare function_invocation_kwargs and client_kwargs for agent.run().

    Extracts ``function_invocation_kwargs`` and ``client_kwargs`` from workflow state,
    preferring collision-free state when present and otherwise reading the legacy dict
    representation. Global and executor-specific values are merged for ``executor_id``.

    Args:
        executor_id: The id of the executor about to invoke the agent.
        raw_run_kwargs: The legacy-compatible workflow run-state dict.
        resolved_run_kwargs: Optional collision-free workflow run-state dict.

    Returns:
        A 2-tuple of (function_invocation_kwargs, client_kwargs).
    """
    run_kwargs = prepare_executor_run_kwargs(executor_id, raw_run_kwargs, resolved_run_kwargs)
    function_invocation_kwargs = run_kwargs.get("function_invocation_kwargs")
    client_kwargs = run_kwargs.get("client_kwargs")

    return function_invocation_kwargs, client_kwargs
