# Copyright (c) Microsoft. All rights reserved.

"""Deterministic tool-driven AG-UI state updates and display payloads.

Tools wired into the :mod:`agent_framework_ag_ui` endpoint can push a
deterministic state update or a per-call tool result display payload by
returning :func:`state_update`. Unlike ``predict_state_config`` — which emits
``StateDeltaEvent``s optimistically from LLM-predicted tool call arguments —
``state_update`` runs *after* the tool executes, so AG-UI state and display
content always reflect the tool's actual return value.

See issue https://github.com/microsoft/agent-framework/issues/3167 for the
motivating discussion.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agent_framework import Content

from ._utils import make_json_safe

__all__ = ["TOOL_RESULT_DISPLAY_KEY", "TOOL_RESULT_STATE_KEY", "state_update"]


TOOL_RESULT_STATE_KEY = "__ag_ui_tool_result_state__"
"""Reserved ``Content.additional_properties`` key used to carry a tool-driven
state snapshot from a tool return value through to the AG-UI emitter."""

TOOL_RESULT_DISPLAY_KEY = "__ag_ui_tool_result_display__"
"""Reserved ``Content.additional_properties`` key used to carry UI-only tool result display content from a tool return value through to the AG-UI emitter."""

_UNSET = object()


def _serialize_tool_result(value: Any) -> str:  # noqa: ANN401
    return value if isinstance(value, str) else json.dumps(make_json_safe(value))


def state_update(
    text: str = "",
    *,
    state: Mapping[str, Any] | None = None,
    tool_result: Any = _UNSET,  # noqa: ANN401
) -> Content:
    """Build a tool return value that updates AG-UI shared state or display content.

    Return the result of this helper from an agent tool to push a state update
    or UI-only display payload to AG-UI clients using the actual tool output,
    rather than LLM-predicted tool arguments.

    When the AG-UI endpoint emits the tool result, it will:

    * Forward ``text`` to the LLM as the normal ``function_result`` content.
    * Use ``tool_result`` as the ``ToolCallResultEvent.content`` payload shown
      to AG-UI clients, falling back to ``text`` when no display payload is set.
    * Merge ``state`` into ``FlowState.current_state``.
    * Emit a deterministic ``StateSnapshotEvent`` after the ``ToolCallResult``
      event so frontends observe the updated state deterministically. If
      predictive state is enabled, a predictive snapshot may be emitted first.

    Example:
        .. code-block:: python

            from agent_framework import Content, tool
            from agent_framework_ag_ui import state_update


            @tool
            async def get_weather(city: str) -> Content:
                data = await _fetch_weather(city)
                return state_update(
                    text=f"Weather in {city}: {data['temp']}°C {data['conditions']}",
                    state={"weather": {"city": city, **data}},
                )

    Example:
        .. code-block:: python

            from agent_framework import Content, tool
            from agent_framework_ag_ui import state_update


            @tool
            async def get_weather(city: str) -> Content:
                data = await _fetch_weather(city)
                return state_update(
                    text=f"{city}: {data['temp']}°C and {data['conditions']}",
                    tool_result={
                        "component": "weather-card",
                        "city": city,
                        "temperature": data["temp"],
                        "conditions": data["conditions"],
                        "humidity": data["humidity"],
                    },
                    state={"weather": {"city": city, **data}},
                )

    Args:
        text: Text passed back to the LLM as the ``function_result`` content.
            Defaults to an empty string for tools whose only output is a state
            update.
        state: A mapping merged into the AG-UI shared state via JSON-compatible
            ``dict.update`` semantics. Nested dicts are replaced, not deep-merged.
        tool_result: JSON-safe payload emitted to AG-UI clients as
            ``ToolCallResultEvent.content`` for frontend rendering. The LLM
            still receives ``text``. If ``text`` is empty, the serialized
            display payload is also used as the LLM-bound text fallback.

    Returns:
        A ``Content`` object with ``type="text"``. The state payload rides in
        ``additional_properties`` under :data:`TOOL_RESULT_STATE_KEY`
        (``"__ag_ui_tool_result_state__"``), and the display payload rides
        under :data:`TOOL_RESULT_DISPLAY_KEY`
        (``"__ag_ui_tool_result_display__"``). Both reserved keys are extracted
        by the AG-UI emitter.

    Raises:
        TypeError: If ``state`` is not a ``Mapping``.
    """
    if state is not None and not isinstance(state, Mapping):
        raise TypeError(f"state_update() 'state' must be a Mapping, got {type(state).__name__}")
    additional_properties: dict[str, Any] = {}
    if state is not None:
        additional_properties[TOOL_RESULT_STATE_KEY] = dict(state)
    if tool_result is not _UNSET:
        display_content = _serialize_tool_result(tool_result)
        additional_properties[TOOL_RESULT_DISPLAY_KEY] = display_content
        if not text:
            text = display_content
    return Content.from_text(
        text,
        additional_properties=additional_properties,
    )
