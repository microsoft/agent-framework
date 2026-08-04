# Copyright (c) Microsoft. All rights reserved.

"""Convenience wiring for A2UI on MAF-python.

MAF does not own a tool registry the adapter can mutate per run, and (like the .NET
sibling) auto-injection of ``render_a2ui`` happens CLIENT-side via the AG-UI
a2ui-middleware (``injectA2UITool`` puts ``render_a2ui`` into ``input.tools``). The
server-side opt-in is therefore explicit: the developer wraps their agent. This
module provides that wrapping as a one-liner.

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
from ._context_agent import AGUIContextAgent
from ._state import read_inject_a2ui_flag

logger = logging.getLogger(__name__)


def enable_a2ui(
    inner_agent: Any,
    subagent_chat_client: Any,
    params: A2UIToolParams | None = None,
    context_slice: dict[str, Any] | None = None,
) -> AGUIContextAgent:
    """Wrap ``inner_agent`` with full A2UI support.

    Composes the two wrappers in the order .NET uses: an :class:`A2UIAgent` (the
    ``generate_a2ui`` streaming loop) wrapped by an :class:`AGUIContextAgent` (which
    replays the forwarded component catalog into the prompt). The result is a drop-in
    ``SupportsAgentRun`` to hand to ``AgentFrameworkAgent`` /
    ``add_agent_framework_fastapi_endpoint``.

    Args:
        inner_agent: The planner agent to wrap.
        subagent_chat_client: Raw chat client for the render sub-agent. Prefer a
            Chat-Completions client (``OpenAIChatCompletionClient``) so the balancing
            ``render_a2ui`` tool result replays cleanly on the next turn.
        params: Optional A2UI behaviour knobs (guidelines, recovery, catalog, ...).
        context_slice: Forwarded AG-UI context (component catalog + guidelines) for the
            run, handed to the wrappers directly instead of via run-option
            ``additional_properties``. The wrappers read it and never forward it to the
            provider SDK.

    Returns:
        The wrapped agent.
    """
    return AGUIContextAgent(
        A2UIAgent(inner_agent, subagent_chat_client, params, context_slice),
        context_slice,
    )


def plan_a2ui_injection(
    *,
    agent: Any,
    forwarded_props: Any,
    existing_tool_names: list[str],
    config: dict[str, Any] | None = None,
    context_slice: dict[str, Any] | None = None,
    log: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Decide whether to auto-inject A2UI for this run (Strands-parity contract).

    CopilotKit's runtime composes ``forwardedProps``; the AG-UI a2ui-middleware sets
    ``injectA2UITool`` there. When true (or a string naming the injected render tool to
    drop), the framework auto-wraps the agent with :func:`enable_a2ui`; when false/unset
    the developer wires A2UI themselves. Rules:

    1. Off unless ``forwardedProps.injectA2UITool`` is truthy OR a backend
       ``config["inject_a2ui_tool"]`` override is — nullish fallback, so an explicit
       runtime ``false`` beats a backend opt-in.
    2. USER PREVAILS — never double-inject when ``generate_a2ui`` is already wired, or
       when the agent is already A2UI-wrapped.
    3. The render sub-agent client is inferred from the planner agent's ``.client``; if
       none can be inferred, warn and skip (wire ``enable_a2ui`` explicitly instead).

    Returns ``{"runner", "drop_tool_names"}`` (the A2UI runner to drive the stream call +
    the middleware-injected render tool to strip from the planner's tool list) or
    ``None`` when no injection. The caller uses ``runner`` ONLY for the stream call and
    keeps the original agent bound for protected-state, approval, and serialization
    reads, so those reads still see the real agent's ``context_providers`` and ``client``.
    """
    log = log or logger
    config = config or {}

    flag: Any = read_inject_a2ui_flag(forwarded_props)
    if flag is None:
        flag = config.get("inject_a2ui_tool")
    if not flag:
        return None

    # USER PREVAILS: explicit dev wiring or an already-wrapped agent wins.
    if GENERATE_A2UI_TOOL_NAME in existing_tool_names:
        return None
    if isinstance(agent, (A2UIAgent, AGUIContextAgent)):
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
    return {
        "runner": enable_a2ui(agent, subagent_client, params, context_slice),
        "drop_tool_names": [render_tool_name],
    }
