# Copyright (c) Microsoft. All rights reserved.

"""AG-UI context plumbing for A2UI.

The AG-UI A2UI middleware injects the component catalog and usage guidelines as
``RunAgentInput.context`` entries, and the ``injectA2UITool`` flag via
``forwardedProps``. MAF's AG-UI hosting (``run_agent_stream``) does not forward
``context`` to the agent by default, so this module builds the ``ag-ui`` state slice
the toolkit expects (:func:`build_ag_ui_context_slice`) and reads the enablement flag
(:func:`read_inject_a2ui_flag`).

The slice is handed to the A2UI runner (``A2UIAgent``) directly per run — NOT stamped
onto run-option
``additional_properties``. The wrappers feed it to the toolkit's
``build_context_prompt`` / ``prepare_a2ui_request``. (The old ``ChatOptions``
``additional_properties`` channel leaked the slice to the provider SDK on any run that
carried AG-UI context; passing it in directly keeps it off the wire.)
"""

from __future__ import annotations

import json
from typing import Any

# MUST stay byte-identical to the A2UI middleware's exported
# A2UI_SCHEMA_CONTEXT_DESCRIPTION (middlewares/a2ui-middleware/src/index.ts) and to
# the langgraph-python adapter's copy. The match below is exact-equality; any drift
# silently routes the schema into the generic context section instead of
# ``a2ui_schema``, defeating the catalog-aware validation path.
A2UI_SCHEMA_CONTEXT_DESCRIPTION = (
    "A2UI Component Schema — available components for generating UI surfaces. "
    "Use these component names and properties when creating A2UI operations."
)


def _entry_desc_value(entry: Any) -> tuple[str, Any]:
    """Read (description, value) from a context entry that may be a dict or object."""
    if isinstance(entry, dict):
        return entry.get("description", "") or "", entry.get("value")
    return getattr(entry, "description", "") or "", getattr(entry, "value", None)


def build_ag_ui_context_slice(context: list[Any] | None) -> dict[str, Any]:
    """Build the ``ag-ui`` context slice from AG-UI ``context`` entries.

    Splits the A2UI schema context entry (matched by exact description) into
    ``a2ui_schema`` and routes the remaining entries to ``context``, mirroring the
    langgraph-python adapter. This slice is catalog/guidelines ONLY — it is what the
    toolkit's ``build_context_prompt`` consumes.

    The auto-inject ENABLEMENT flag is deliberately NOT part of this slice: enablement
    is sourced from ``forwardedProps`` (see :func:`read_inject_a2ui_flag`), a separate
    concern from the catalog context. Returns an empty dict when there is no A2UI
    context, so callers can skip stamping for non-A2UI runs.
    """
    schema_value: Any = None
    regular_context: list[Any] = []
    for entry in context or []:
        desc, value = _entry_desc_value(entry)
        if desc == A2UI_SCHEMA_CONTEXT_DESCRIPTION:
            schema_value = value
        else:
            regular_context.append(entry)

    slice_: dict[str, Any] = {}
    if regular_context:
        slice_["context"] = regular_context
    if schema_value is not None:
        slice_["a2ui_schema"] = schema_value
    return slice_


def read_inject_a2ui_flag(forwarded_props: dict[str, Any] | None) -> Any:
    """Read the A2UI auto-inject enablement flag from ``forwardedProps``.

    Enablement comes from ``forwardedProps.injectA2UITool`` (set by the AG-UI
    a2ui-middleware), NOT from ``context``. Returns the RAW value — ``True``/``False``,
    or a string naming the injected render tool to drop (Strands-parity) — or ``None``
    when unset so a backend opt-in can take over with nullish fallback. Callers gate on
    truthiness; auto-injection preserves a string value as the render-tool name. MAF
    does not snake-mangle ``forwardedProps`` keys (unlike langgraph), so the camelCase
    form is canonical; the snake form is accepted for safety.
    """
    forwarded = forwarded_props if isinstance(forwarded_props, dict) else {}
    if "injectA2UITool" in forwarded:
        return forwarded["injectA2UITool"]
    if "inject_a2ui_tool" in forwarded:
        return forwarded["inject_a2ui_tool"]
    return None


def _role_value(msg: Any) -> str | None:
    role = getattr(msg, "role", None)
    return getattr(role, "value", role) if role is not None else None


def to_history_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Map MAF ``Message`` objects onto the toolkit's history shape.

    The toolkit's ``find_prior_surface`` / ``prepare_a2ui_request`` walk a list of
    ``{"role", "content"}`` entries, where a tool message's content is the JSON
    string of its function-result payload (the A2UI operations envelope for prior
    renders). Duck-typed (no agent_framework import) so this module stays
    dependency-light.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = _role_value(msg)
        content: Any = getattr(msg, "text", None)
        if not content and role == "tool":
            # A tool message carries its payload as function_result content; the
            # prior-surface walker needs the raw JSON string.
            for c in getattr(msg, "contents", None) or []:
                if getattr(c, "type", None) == "function_result":
                    result = getattr(c, "result", None)
                    content = result if isinstance(result, str) else _safe_json(result)
                    if content:
                        break
        out.append({"role": role, "content": content})
    return out


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)
