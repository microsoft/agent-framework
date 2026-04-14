# Copyright (c) Microsoft. All rights reserved.

"""Deterministic tool-driven AG-UI state updates.

Tools wired into the :mod:`agent_framework_ag_ui` endpoint can push a
deterministic state update by returning :func:`state_update`. Unlike
``predict_state_config`` — which emits ``StateDeltaEvent``s optimistically from
LLM-predicted tool call arguments — ``state_update`` runs *after* the tool
executes, so the AG-UI state always reflects the tool's actual return value.

See issue https://github.com/microsoft/agent-framework/issues/3167 for the
motivating discussion.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_framework import Content

__all__ = ["TOOL_RESULT_STATE_KEY", "state_update"]


TOOL_RESULT_STATE_KEY = "__ag_ui_tool_result_state__"
"""Reserved ``Content.additional_properties`` key used to carry a tool-driven
state snapshot from a tool return value through to the AG-UI emitter."""


def state_update(
    text: str = "",
    *,
    state: Mapping[str, Any],
) -> Content:
    """Build a tool return value that deterministically updates AG-UI shared state.

    Return the result of this helper from an agent tool to push a state update
    to AG-UI clients using the actual tool output, rather than LLM-predicted
    tool arguments.

    When the AG-UI endpoint emits the tool result, it will:

    * Forward ``text`` to the LLM as the normal ``function_result`` content.
    * Merge ``state`` into ``FlowState.current_state``.
    * Emit a deterministic ``StateSnapshotEvent`` after the ``ToolCallResult``
      event so frontends observe the updated state deterministically. If
      predictive state is enabled, a predictive snapshot may be emitted first.

    Example:
        .. code-block:: python

            from agent_framework import tool
            from agent_framework_ag_ui import state_update


            @tool
            async def get_weather(city: str) -> Content:
                data = await _fetch_weather(city)
                return state_update(
                    text=f"Weather in {city}: {data['temp']}°C {data['conditions']}",
                    state={"weather": {"city": city, **data}},
                )

    Args:
        text: Text passed back to the LLM as the ``function_result`` content.
            Defaults to an empty string for tools whose only output is a state
            update.
        state: A mapping merged into the AG-UI shared state via JSON-compatible
            ``dict.update`` semantics. Nested dicts are replaced, not deep-merged.

    Returns:
        A ``Content`` object with ``type="text"``. The state payload rides in
        ``additional_properties`` under :data:`TOOL_RESULT_STATE_KEY` and is
        extracted by the AG-UI emitter.

    Raises:
        TypeError: If ``state`` is not a ``Mapping``.
    """
    if not isinstance(state, Mapping):
        raise TypeError(f"state_update() 'state' must be a Mapping, got {type(state).__name__}")
    return Content.from_text(
        text,
        additional_properties={TOOL_RESULT_STATE_KEY: dict(state)},
    )
