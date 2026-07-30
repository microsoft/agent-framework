# Copyright (c) Microsoft. All rights reserved.

"""AG-UI context plumbing for A2UI.

The AG-UI A2UI middleware injects the component catalog and usage guidelines as
``RunAgentInput.context`` entries, and the ``injectA2UITool`` flag via
``forwardedProps``. MAF's AG-UI hosting (``run_agent_stream``) does not forward
``context`` to the agent by default, so this module builds the ``ag-ui`` state
slice the toolkit expects and stamps it onto the run's
``options.additional_properties`` under :data:`A2UI_CONTEXT_KEY` — the analog of
.NET ``MapAGUI`` stamping ``ag_ui_context`` onto ``ChatOptions.AdditionalProperties``.

Wrapper agents (:class:`~.._context_agent.AGUIContextAgent`, ``A2UIAgent``) read it
back with :func:`read_agent_state` and feed it to the toolkit's
``build_context_prompt`` / ``prepare_a2ui_request``.
"""

from __future__ import annotations

import json
from typing import Any

# Additional-properties key under which the ag-ui context slice is stamped onto the
# run options. Mirrors .NET's "ag_ui_context" AdditionalProperties key.
A2UI_CONTEXT_KEY = "ag_ui_context"

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
    renders). Mirrors .NET ``ToHistoryMessage``. Duck-typed (no agent_framework
    import) so this module stays dependency-light.
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


def _additional_properties(options: Any) -> dict[str, Any] | None:
    """Read ``additional_properties`` from a ChatOptions object or a plain dict."""
    if options is None:
        return None
    if isinstance(options, dict):
        ap = options.get("additional_properties")
        return ap if isinstance(ap, dict) else None
    ap = getattr(options, "additional_properties", None)
    return ap if isinstance(ap, dict) else None


def read_agent_state(options: Any) -> dict[str, Any]:
    """Read the ag-ui context slice stamped on the run options.

    Accepts a ChatOptions object or a plain options dict (the shape
    ``run_agent_stream`` passes). Returns the slice, or an empty dict when absent.
    """
    ap = _additional_properties(options)
    if not ap:
        return {}
    slice_ = ap.get(A2UI_CONTEXT_KEY)
    return slice_ if isinstance(slice_, dict) else {}


def stamp_context_slice(options: Any, slice_: dict[str, Any]) -> dict[str, Any]:
    """Stamp the ag-ui context slice onto run options' additional_properties.

    Normalizes ``options`` to a dict (creating one if needed) and returns it, so the
    caller can assign it back into ``run_kwargs["options"]``. No-op-safe: an empty
    slice still returns valid options.
    """
    opts: dict[str, Any] = dict(options) if isinstance(options, dict) else {}
    ap = opts.get("additional_properties")
    ap = dict(ap) if isinstance(ap, dict) else {}
    ap[A2UI_CONTEXT_KEY] = slice_
    opts["additional_properties"] = ap
    return opts


def strip_context_slice(options: Any) -> Any:
    """Return ``options`` with the ag-ui context slice removed from
    ``additional_properties``.

    The slice is adapter-private run state; ``additional_properties`` is forwarded to
    the provider SDK by the underlying chat client, which rejects the unknown key.
    Wrapper agents therefore read the slice with :func:`read_agent_state` and then
    strip it via this helper BEFORE delegating to the inner planner agent, so it never
    reaches ``responses.create`` / ``chat.completions.create``. If removing the slice
    empties ``additional_properties``, the key is dropped entirely. Non-dict options are
    returned unchanged (best effort — only the dict shape the hosting loop passes carries
    the stamped slice).
    """
    if not isinstance(options, dict):
        return options
    ap = options.get("additional_properties")
    if not isinstance(ap, dict) or A2UI_CONTEXT_KEY not in ap:
        return options
    opts = dict(options)
    new_ap = {k: v for k, v in ap.items() if k != A2UI_CONTEXT_KEY}
    if new_ap:
        opts["additional_properties"] = new_ap
    else:
        opts.pop("additional_properties", None)
    return opts
