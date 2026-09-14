# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import Any, cast

from .._agents import SupportsAgentRun
from ._const import GLOBAL_KWARGS_KEY

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


def resolve_executor_kwargs(executor_id: str, resolved: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract one executor's kwargs from a resolved invocation kwargs dict.

    Args:
        executor_id: The id of the executor whose kwargs are wanted.
        resolved: The resolved dict produced by ``Workflow._resolve_invocation_kwargs``,
            containing either a ``__global__`` key (global kwargs) or executor-ID keys
            (per-executor kwargs). May also be ``None``.

    Returns:
        The kwargs for that executor, or ``None`` if not applicable.
    """
    if not isinstance(resolved, dict):
        return None
    global_kwargs: Any = resolved.get(GLOBAL_KWARGS_KEY)
    executor_kwargs: Any = resolved.get(executor_id)
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


def prepare_agent_run_args(
    executor_id: str,
    raw_run_kwargs: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Prepare function_invocation_kwargs and client_kwargs for agent.run().

    Extracts ``function_invocation_kwargs`` and ``client_kwargs`` from the workflow state
    dict, resolving per-executor entries using ``executor_id``. The ``__global__`` sentinel
    key (set by ``Workflow._resolve_invocation_kwargs``) denotes global kwargs that apply to
    all executors. Per-executor dicts use executor IDs as keys; only the entry for
    ``executor_id`` is extracted.

    Args:
        executor_id: The id of the executor about to invoke the agent.
        raw_run_kwargs: The workflow state dict stored under ``WORKFLOW_RUN_KWARGS_KEY``.

    Returns:
        A 2-tuple of (function_invocation_kwargs, client_kwargs).
    """
    function_invocation_kwargs = resolve_executor_kwargs(executor_id, raw_run_kwargs.get("function_invocation_kwargs"))
    client_kwargs = resolve_executor_kwargs(executor_id, raw_run_kwargs.get("client_kwargs"))

    return function_invocation_kwargs, client_kwargs
