# Copyright (c) Microsoft. All rights reserved.

"""Convenience wiring for A2UI on MAF-python.

Auto-injection of ``render_a2ui`` happens CLIENT-side via the AG-UI a2ui-middleware
(``injectA2UITool`` puts ``render_a2ui`` into ``input.tools``). The server-side opt-in
is explicit: the developer wraps their agent. This module provides that wrapping as a
one-liner.

Progressive-paint note: surface generation must run at the AGENT level
(:class:`~._agent.A2UIAgent`) so the render sub-agent's argument fragments reach the
wire incrementally. A plain executable ``generate_a2ui`` tool added to an agent's
tool list would invoke the sub-agent hidden inside the tool body, producing the
"5s blank then bulk paint" regression — hence the wrapper, not a bare tool.
"""

from __future__ import annotations

import logging
from typing import Any

from ag_ui_a2ui_toolkit import GENERATE_A2UI_TOOL_NAME, A2UIToolParams

from ._agent import RENDER_A2UI_TOOL_NAME, A2UIAgent
from ._state import read_inject_a2ui_flag

logger = logging.getLogger(__name__)


def is_a2ui_runner(agent: Any) -> bool:
    """True when ``agent`` is an A2UI runner (an :class:`A2UIAgent`).

    Lets the AG-UI host treat a manually ``enable_a2ui()``-wrapped agent the same as an
    auto-injected one (e.g. for terminal-snapshot suppression), so A2UI wiring lives in
    one place instead of the host re-deriving it.
    """
    return isinstance(agent, A2UIAgent)


def enable_a2ui(
    inner_agent: Any,
    subagent_chat_client: Any,
    params: A2UIToolParams | None = None,
    context_slice: dict[str, Any] | None = None,
    drop_tool_names: list[str] | None = None,
) -> A2UIAgent:
    """Wrap ``inner_agent`` with full A2UI support.

    Returns an :class:`A2UIAgent` — the ``generate_a2ui`` streaming loop, which also
    adds the forwarded component catalog + guidelines as untrusted user data. The result
    is a drop-in ``SupportsAgentRun`` to hand to ``AgentFrameworkAgent`` /
    ``add_agent_framework_fastapi_endpoint``.

    Args:
        inner_agent: The planner agent to wrap.
        subagent_chat_client: Raw chat client for the render sub-agent. Prefer a
            Chat-Completions client (``OpenAIChatCompletionClient``) so the balancing
            ``render_a2ui`` tool result replays cleanly on the next turn.
        params: Optional A2UI behaviour knobs (guidelines, recovery, catalog, ...).
        context_slice: Forwarded AG-UI context (component catalog + guidelines) for the
            run, handed in directly instead of via run-option ``additional_properties``.
        drop_tool_names: Render tool name(s) to strip from the planner's tools (set by
            auto-injection; empty for a manual call).

    Returns:
        The A2UI runner.
    """
    return A2UIAgent(inner_agent, subagent_chat_client, params, context_slice, drop_tool_names)


def plan_a2ui_injection(
    *,
    agent: Any,
    forwarded_props: Any,
    existing_tool_names: list[str],
    config: dict[str, Any] | None = None,
    context_slice: dict[str, Any] | None = None,
    log: logging.Logger | None = None,
) -> A2UIAgent | None:
    """Decide whether to auto-inject A2UI for this run (Strands-parity contract).

    CopilotKit's runtime composes ``forwardedProps``; the AG-UI a2ui-middleware sets
    ``injectA2UITool`` there. The backend must first opt in with
    ``config["inject_a2ui_tool"]``; the request flag can then enable, disable, or name the
    injected render tool for that run. Rules:

    1. Off unless the backend enables ``config["inject_a2ui_tool"]``. An explicit runtime
       ``false`` still disables injection for that request.
    2. USER PREVAILS — never double-inject when ``generate_a2ui`` is already wired, or
       when the agent is already A2UI-wrapped.
    3. The render sub-agent client is inferred from the planner agent's ``.client``; if
       none can be inferred, warn and skip (wire ``enable_a2ui`` explicitly instead).

    Returns the :class:`A2UIAgent` runner (which carries the render tool(s) to strip on
    :attr:`~._agent.A2UIAgent.drop_tool_names`) or ``None`` when no injection. The caller
    uses the runner ONLY for the stream call and keeps the original agent bound for
    protected-state, approval, and serialization reads, so those reads still see the real
    agent's ``context_providers`` and ``client``.
    """
    log = log or logger
    config = config or {}

    runtime_flag: Any = read_inject_a2ui_flag(forwarded_props)
    backend_flag: Any = config.get("inject_a2ui_tool")
    if runtime_flag is False or not backend_flag:
        return None
    flag = runtime_flag if runtime_flag is not None else backend_flag
    if not flag:
        return None

    # USER PREVAILS: explicit dev wiring or an already-wrapped agent wins.
    if GENERATE_A2UI_TOOL_NAME in existing_tool_names:
        return None
    if is_a2ui_runner(agent):
        return None

    subagent_client = getattr(agent, "client", None)
    if subagent_client is None:
        log.warning(
            "injectA2UITool is set but no chat client could be inferred from the agent; "
            "skipping A2UI auto-injection. Wire enable_a2ui() explicitly."
        )
        return None

    render_tool_name = flag if isinstance(flag, str) else RENDER_A2UI_TOOL_NAME
    params: A2UIToolParams = {
        "catalog": config.get("catalog"),
        "guidelines": config.get("guidelines"),
        "recovery": config.get("recovery"),
        "default_catalog_id": config.get("default_catalog_id"),
        "default_surface_id": config.get("default_surface_id"),
    }
    return enable_a2ui(agent, subagent_client, params, context_slice, [render_tool_name])
