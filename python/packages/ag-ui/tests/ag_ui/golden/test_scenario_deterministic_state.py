# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the deterministic tool-driven state scenario.

Covers issue https://github.com/microsoft/agent-framework/issues/3167 — a tool
returning :func:`agent_framework_ag_ui.state_update` must push a deterministic
``StateSnapshotEvent`` derived from its actual return value, orthogonal to the
optimistic ``predict_state_config`` path. These golden tests pin the user-visible
event stream so additive changes cannot silently regress it.
"""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream

from agent_framework_ag_ui import AgentFrameworkAgent, state_update

STATE_SCHEMA = {
    "weather": {"type": "object", "description": "Last fetched weather"},
}


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(updates=updates)
    kwargs.setdefault("state_schema", STATE_SCHEMA)
    return AgentFrameworkAgent(agent=stub, **kwargs)


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-det-state",
    "run_id": "run-det-state",
    "messages": [{"role": "user", "content": "What's the weather in SF?"}],
    "state": {"weather": {}},
}


def _tool_call(call_id: str, name: str, arguments: str) -> AgentResponseUpdate:
    return AgentResponseUpdate(
        contents=[Content.from_function_call(name=name, call_id=call_id, arguments=arguments)],
        role="assistant",
    )


def _tool_result_with_state(call_id: str, text: str, state: dict[str, Any]) -> AgentResponseUpdate:
    """Build a function_result update whose inner item carries a state marker.

    This mirrors what the core framework produces when a real ``@tool`` returns
    :func:`state_update`: ``parse_result`` keeps the ``Content`` as-is, and
    ``Content.from_function_result`` preserves its ``additional_properties``
    inside ``items``.
    """
    return AgentResponseUpdate(
        contents=[
            Content.from_function_result(
                call_id=call_id,
                result=[state_update(text=text, state=state)],
            )
        ],
        role="assistant",
    )


# ── Golden stream tests ──


async def test_deterministic_state_emits_snapshot_after_tool_result() -> None:
    """The happy path: STATE_SNAPSHOT follows TOOL_CALL_RESULT in order."""
    updates = [
        _tool_call("call-1", "get_weather", '{"city": "SF"}'),
        _tool_result_with_state(
            "call-1",
            text="Weather in SF: 14°C foggy",
            state={"weather": {"city": "SF", "temp": 14, "conditions": "foggy"}},
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's 14°C and foggy in SF.")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_tool_calls_balanced()
    stream.assert_text_messages_balanced()

    # Ordered subsequence: the deterministic STATE_SNAPSHOT must follow the
    # TOOL_CALL_RESULT. This is the central contract for #3167.
    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            "STATE_SNAPSHOT",
            "RUN_FINISHED",
        ]
    )

    # The final STATE_SNAPSHOT must carry the tool-driven state.
    snapshot = stream.snapshot()
    assert snapshot["weather"] == {"city": "SF", "temp": 14, "conditions": "foggy"}


async def test_deterministic_state_does_not_fire_for_plain_tool_result() -> None:
    """Regression guard: tools returning plain strings must NOT emit a new STATE_SNAPSHOT.

    The initial STATE_SNAPSHOT fires once from the schema + initial payload
    state. A plain (non-state_update) tool result must not add another one.
    """
    updates = [
        _tool_call("call-1", "get_weather", '{"city": "SF"}'),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="14°C foggy")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's 14°C and foggy.")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()

    snapshots = stream.get("STATE_SNAPSHOT")
    # Only the initial snapshot (from state_schema + payload state) should exist.
    # No deterministic snapshot should have been added by the plain tool result.
    assert len(snapshots) == 1, (
        f"Expected exactly 1 STATE_SNAPSHOT (initial only) for plain tool result; "
        f"got {len(snapshots)}. Snapshots: {[s.snapshot for s in snapshots]}"
    )


async def test_deterministic_state_merges_into_initial_state() -> None:
    """The tool-driven snapshot must merge into, not replace, pre-existing state keys."""
    payload = dict(PAYLOAD)
    payload["state"] = {"weather": {}, "user_preferences": {"unit": "C"}}

    updates = [
        _tool_call("call-1", "get_weather", '{"city": "SF"}'),
        _tool_result_with_state(
            "call-1",
            text="Weather: 14°C",
            state={"weather": {"city": "SF", "temp": 14}},
        ),
    ]
    agent = _build_agent(updates, state_schema={**STATE_SCHEMA, "user_preferences": {"type": "object"}})
    stream = await _run(agent, payload)

    stream.assert_bookends()
    stream.assert_no_run_error()

    final_snapshot = stream.snapshot()
    assert final_snapshot["weather"] == {"city": "SF", "temp": 14}
    assert final_snapshot["user_preferences"] == {"unit": "C"}, (
        "Pre-existing state keys must survive the deterministic merge"
    )


async def test_deterministic_state_llm_visible_text_is_clean() -> None:
    """The LLM-visible TOOL_CALL_RESULT content must not leak the state marker key."""
    updates = [
        _tool_call("call-1", "get_weather", '{"city": "SF"}'),
        _tool_result_with_state(
            "call-1",
            text="Weather in SF: 14°C foggy",
            state={"weather": {"city": "SF", "temp": 14}},
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    result = stream.first("TOOL_CALL_RESULT")
    assert result.content == "Weather in SF: 14°C foggy"
    # The marker key must never appear in the content sent back to the LLM.
    assert "__ag_ui_tool_result_state__" not in result.content
    assert "weather" not in result.content  # not as a raw state dump


async def test_deterministic_state_multiple_tools_merge_in_order() -> None:
    """Two state-updating tools in one run merge in order; later wins on key collisions."""
    updates = [
        _tool_call("call-a", "get_weather", '{"city": "SF"}'),
        _tool_result_with_state(
            "call-a",
            text="First result",
            state={"weather": {"city": "SF", "temp": 14}, "source": "primary"},
        ),
        _tool_call("call-b", "get_weather_refined", '{"city": "SF"}'),
        _tool_result_with_state(
            "call-b",
            text="Refined result",
            state={"source": "refined"},
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="Here you go.")],
            role="assistant",
        ),
    ]
    agent = _build_agent(
        updates,
        state_schema={**STATE_SCHEMA, "source": {"type": "string"}},
    )
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_tool_calls_balanced()
    stream.assert_no_run_error()

    # Two tool-driven snapshots emitted (one per tool) plus the initial snapshot.
    snapshots = stream.get("STATE_SNAPSHOT")
    assert len(snapshots) >= 2, f"Expected at least 2 STATE_SNAPSHOTs; got {len(snapshots)}"

    final = stream.snapshot()
    assert final["weather"] == {"city": "SF", "temp": 14}
    # Later tool must override earlier tool on the shared key.
    assert final["source"] == "refined"


async def test_deterministic_state_coexists_with_predict_state_config() -> None:
    """Predictive state and deterministic state must coexist without clobbering each other."""
    predict_config = {
        "draft": {
            "tool": "write_draft",
            "tool_argument": "body",
        }
    }
    updates = [
        # Predictive tool: its argument "body" populates state.draft optimistically.
        _tool_call("call-1", "write_draft", '{"body": "Hello world"}'),
        # Then a deterministic tool result landing a different key.
        _tool_result_with_state(
            "call-1",
            text="Draft saved",
            state={"weather": {"city": "SF", "temp": 14}},
        ),
    ]
    agent = _build_agent(
        updates,
        state_schema={**STATE_SCHEMA, "draft": {"type": "string"}},
        predict_state_config=predict_config,
        require_confirmation=False,
    )
    payload = dict(PAYLOAD)
    payload["state"] = {"weather": {}, "draft": ""}
    stream = await _run(agent, payload)

    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_tool_calls_balanced()

    # The final observed state must contain both the deterministic and predictive contributions.
    final = stream.snapshot()
    assert final["weather"] == {"city": "SF", "temp": 14}, f"Deterministic state missing from final snapshot: {final}"
