# Copyright (c) Microsoft. All rights reserved.

"""Tests for A2UI (agent-generated UI) support in the AG-UI adapter.

Covers the context plumbing (_state) and the A2UIAgent streaming/non-streaming loop
including context prepend, recovery, catalog-driven validation, error classification,
and mid-stream render-call balancing.

Skipped wholesale when ag-ui-a2ui-toolkit is not installed (A2UI is an optional
extra; the base package does not require it).
"""

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("ag_ui_a2ui_toolkit")

from agent_framework import AgentResponseUpdate, ChatResponse, ChatResponseUpdate, Content, Message  # noqa: E402

from agent_framework_ag_ui._a2ui import (  # noqa: E402
    A2UI_SCHEMA_CONTEXT_DESCRIPTION,
    A2UIAgent,
    build_ag_ui_context_slice,
    enable_a2ui,
    is_a2ui_runner,
    plan_a2ui_injection,
    read_inject_a2ui_flag,
)
from agent_framework_ag_ui._a2ui._state import to_history_messages  # noqa: E402

# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


def _role(msg):
    r = getattr(msg, "role", None)
    return getattr(r, "value", r)


class _GenerateOnceInner:
    """Planner that requests one generate_a2ui surface, then narrates."""

    id = name = description = "planner"

    def __init__(self):
        self.calls = 0
        self.last_tools: list[Any] | None = None

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        self.last_tools = [getattr(t, "name", None) for t in (tools or [])]
        n = self.calls

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        )
                    ],
                )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


class _RenderSub:
    """Render sub-agent that streams render_a2ui args as fragments."""

    def __init__(self, components=None, fragments=None):
        self._components = components or [{"id": "root", "component": "Card"}]
        self._fragments = fragments

    def get_response(self, messages, *, stream=False, options=None):
        full = {"surfaceId": "s1", "components": self._components}
        text = json.dumps(full)
        frags = self._fragments if self._fragments is not None else [text[:8], text[8:20], text[20:]]

        async def gen():
            for frag in frags:
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="r1", name="render_a2ui", arguments=frag)],
                )

        return gen()


async def _drive(agent, tools=None):
    """Run a streaming A2UIAgent and classify the yielded content.

    The forwarded AG-UI context (when any) is a constructor arg of ``A2UIAgent`` now,
    not a run option, so this helper passes no options. ``tools`` supplies developer
    tools for the mixed-batch (ordinary tool + generate_a2ui) path.
    """
    kinds: list[tuple[Any, ...]] = []
    run_kwargs = {"tools": tools} if tools is not None else {}
    async for update in agent.run("make a card", stream=True, **run_kwargs):
        for c in update.contents:
            t = getattr(c, "type", None)
            if t == "function_call":
                kinds.append(("call", c.name, c.arguments))
            elif t == "function_result":
                kinds.append(("result", getattr(c, "call_id", None), c.result))
            elif t == "text":
                kinds.append(("text", c.text))
    return kinds


def _generate_envelope(kinds) -> Any:
    for kind, call_id, result in (k for k in kinds if k[0] == "result"):
        if call_id == "g1":
            return json.loads(result)
    return None


# --------------------------------------------------------------------------- #
# _state: context slice + enablement flag
# --------------------------------------------------------------------------- #


def test_context_slice_is_catalog_only():
    ctx = [
        {"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": "CAT"},
        {"description": "Generation Guidelines", "value": "be terse"},
    ]
    slice_ = build_ag_ui_context_slice(ctx)
    assert slice_["a2ui_schema"] == "CAT"
    assert slice_["context"] == [{"description": "Generation Guidelines", "value": "be terse"}]
    assert "inject_a2ui_tool" not in slice_  # enablement is NOT bundled into context


def test_inject_flag_sourced_from_forwarded_props_only():
    assert read_inject_a2ui_flag({"injectA2UITool": True}) is True
    assert read_inject_a2ui_flag({"injectA2UITool": False}) is False
    assert read_inject_a2ui_flag({"inject_a2ui_tool": True}) is True  # snake fallback
    assert read_inject_a2ui_flag({}) is None  # unset -> None (nullish)
    assert read_inject_a2ui_flag(None) is None
    # A context entry never enables injection.
    assert read_inject_a2ui_flag({"context": [{"description": "x", "value": "y"}]}) is None


def test_no_a2ui_context_yields_empty_slice():
    assert build_ag_ui_context_slice(None) == {}
    assert build_ag_ui_context_slice([{"description": "x", "value": "y"}]) == {
        "context": [{"description": "x", "value": "y"}]
    }


def test_to_history_messages_extracts_tool_result_payload():
    envelope = '{"a2ui_operations": []}'
    messages = [
        Message(role="user", contents=[Content.from_text(text="hi")]),
        Message(role="tool", contents=[Content.from_function_result(call_id="c", result=envelope)]),
    ]
    history = to_history_messages(messages)
    assert history[0] == {"role": "user", "content": "hi"}
    assert history[1]["role"] == "tool"
    assert history[1]["content"] == envelope


# --------------------------------------------------------------------------- #
# A2UIAgent context prepend (folded in, no separate wrapper)
# --------------------------------------------------------------------------- #


def test_a2ui_agent_prepends_catalog_system_message():
    slice_ = build_ag_ui_context_slice(
        [{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": '{"components":{"Card":{}}}'}]
    )
    agent = A2UIAgent(_GenerateOnceInner(), _RenderSub(), context_slice=slice_)
    msgs = agent._with_context_prompt("hi", slice_)
    assert _role(msgs[0]) == "system"
    assert "Available Components" in msgs[0].text and "Card" in msgs[0].text
    assert _role(msgs[-1]) == "user"


def test_a2ui_agent_passthrough_without_context():
    agent = A2UIAgent(_GenerateOnceInner(), _RenderSub())
    msgs = agent._with_context_prompt("hi", {})
    assert [_role(m) for m in msgs] == ["user"]


# --------------------------------------------------------------------------- #
# A2UIAgent streaming loop
# --------------------------------------------------------------------------- #


def test_streaming_progressive_paint_balancing_and_envelope():
    kinds = asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), _RenderSub())))

    # >= 3 incremental render_a2ui arg fragments forwarded (progressive paint)
    render_frags = [k for k in kinds if k[0] == "call" and k[1] == "render_a2ui"]
    assert len(render_frags) >= 3

    # balancing render result emitted
    assert any(k[0] == "result" and k[1] == "r1" and "rendered" in str(k[2]) for k in kinds)

    # generate_a2ui envelope fed back with operations
    env = _generate_envelope(kinds)
    assert env is not None and "a2ui_operations" in env
    assert any("createSurface" in op for op in env["a2ui_operations"])

    # closing turn narrated
    assert any(k[0] == "text" and "Done" in k[1] for k in kinds)


def test_streaming_loop_ends_when_planner_stops_requesting():
    # Normal termination: planner requests once, then narrates -> loop ends after
    # the planner's no-generate turn (the tool is still advertised on that turn;
    # withholding only applies to the round-cap closing turn, below).
    inner = _GenerateOnceInner()
    asyncio.run(_drive(A2UIAgent(inner, _RenderSub())))
    assert inner.calls == 2


def test_streaming_closing_turn_withholds_generate_tool_at_round_cap():
    from agent_framework_ag_ui._a2ui._agent import MAX_PLANNER_ROUNDS

    class AlwaysGenerateInner:
        id = name = description = "planner"

        def __init__(self):
            self.tools_per_call: list[Any] = []

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.tools_per_call.append([getattr(t, "name", None) for t in (tools or [])])

            async def gen():
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="g", name="generate_a2ui", arguments="{}")],
                )

            return gen()

    inner = AlwaysGenerateInner()
    asyncio.run(_drive(A2UIAgent(inner, _RenderSub())))
    # MAX_PLANNER_ROUNDS planner rounds (tool advertised) + 1 closing turn (withheld).
    assert len(inner.tools_per_call) == MAX_PLANNER_ROUNDS + 1
    assert all("generate_a2ui" in t for t in inner.tools_per_call[:MAX_PLANNER_ROUNDS])
    assert "generate_a2ui" not in inner.tools_per_call[-1]


def test_streaming_recovery_exhaustion():
    # Always-invalid (no root) -> recovery_exhausted after default 3 attempts.
    sub = _RenderSub(components=[{"id": "x", "component": "Card"}])
    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), sub))))
    assert env["code"] == "a2ui_recovery_exhausted"
    assert len(env["attempts"]) == 3


def test_streaming_retry_then_success():
    class RetrySub:
        def __init__(self):
            self.n = 0

        def get_response(self, messages, *, stream=False, options=None):
            self.n += 1
            comps = [{"id": "x", "component": "Card"}] if self.n == 1 else [{"id": "root", "component": "Card"}]

            async def gen():
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id=f"r{self.n}",
                            name="render_a2ui",
                            arguments=json.dumps({"surfaceId": "s", "components": comps}),
                        )
                    ],
                )

            return gen()

    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), RetrySub()))))
    assert "a2ui_operations" in env


# --------------------------------------------------------------------------- #
# P3: catalog-driven validation + error classification
# --------------------------------------------------------------------------- #


def test_forwarded_schema_drives_validation_catalog():
    # Card requires "text"; render omits it -> invalid via the forwarded catalog.
    catalog = {"components": {"Card": {"required": ["text"]}}}
    slice_ = build_ag_ui_context_slice([{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": json.dumps(catalog)}])
    sub = _RenderSub(components=[{"id": "root", "component": "Card"}])
    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), sub, context_slice=slice_))))
    assert env["code"] == "a2ui_recovery_exhausted"
    errors = [e for attempt in env["attempts"] for e in attempt["errors"]]
    assert any(e["code"] == "missing_required_prop" for e in errors)


def test_recoverable_subagent_error_retries():
    class RaisingSub:
        def get_response(self, messages, *, stream=False, options=None):
            async def gen():
                raise ValueError("transient")
                yield  # pragma: no cover

            return gen()

    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), RaisingSub()))))
    assert env["code"] == "a2ui_recovery_exhausted"
    assert all(e["code"] == "subagent_error" for a in env["attempts"] for e in a["errors"])


def test_programmer_error_is_rethrown():
    class TypeErrorSub:
        def get_response(self, messages, *, stream=False, options=None):
            async def gen():
                raise TypeError("bug")
                yield  # pragma: no cover

            return gen()

    with pytest.raises(TypeError):
        asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), TypeErrorSub())))


def test_mid_stream_death_balances_render_call():
    class PartialThenDieSub:
        def get_response(self, messages, *, stream=False, options=None):
            async def gen():
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(call_id="rX", name="render_a2ui", arguments='{"surfaceId":"s","comp')
                    ],
                )
                raise ValueError("died mid-stream")

            return gen()

    kinds = asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), PartialThenDieSub())))
    assert any(k[0] == "result" and k[1] == "rX" and "rendered" in str(k[2]) for k in kinds)


# --------------------------------------------------------------------------- #
# Non-streaming tool body + enable_a2ui
# --------------------------------------------------------------------------- #


def test_non_streaming_tool_body_runs_recovery():
    class NonStreamSub:
        async def get_response(self, messages, *, stream=False, options=None):
            return ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="r",
                                name="render_a2ui",
                                arguments=json.dumps(
                                    {"surfaceId": "s", "components": [{"id": "root", "component": "Card"}]}
                                ),
                            )
                        ],
                    )
                ]
            )

    agent = A2UIAgent(
        inner_agent=type("I", (), {"id": "i", "name": "n", "description": "d"})(), subagent_chat_client=NonStreamSub()
    )
    tool = agent._build_generate_tool([Message(role="user", contents=[Content.from_text(text="card")])], {})
    assert tool.func is not None  # executable on the non-streaming path
    env = json.loads(asyncio.run(tool.func(intent="create")))
    assert "a2ui_operations" in env


def test_enable_a2ui_returns_runner_wrapping_inner():
    inner = type("I", (), {"id": "i", "name": "n", "description": "d"})()
    runner = enable_a2ui(inner, object())
    assert isinstance(runner, A2UIAgent) and is_a2ui_runner(runner)
    assert runner.inner_agent is inner
    assert runner.drop_tool_names == []  # manual path injects nothing to drop


# --------------------------------------------------------------------------- #
# P5: auto-injection (plan_a2ui_injection)
# --------------------------------------------------------------------------- #


class _AgentWithClient:
    id = name = description = "planner"
    client = object()  # inferable render sub-agent client


def test_plan_injection_off_without_flag():
    assert plan_a2ui_injection(agent=_AgentWithClient(), forwarded_props=None, existing_tool_names=[]) is None
    assert plan_a2ui_injection(agent=_AgentWithClient(), forwarded_props={}, existing_tool_names=[]) is None
    assert (
        plan_a2ui_injection(agent=_AgentWithClient(), forwarded_props={"injectA2UITool": False}, existing_tool_names=[])
        is None
    )


def test_plan_injection_wraps_and_drops_render_tool():
    plan = plan_a2ui_injection(
        agent=_AgentWithClient(),
        forwarded_props={"injectA2UITool": True},
        existing_tool_names=["some_other_tool"],
    )
    assert plan is not None
    assert is_a2ui_runner(plan)
    assert plan.drop_tool_names == ["render_a2ui"]


def test_plan_injection_string_flag_names_render_tool_to_drop():
    plan = plan_a2ui_injection(
        agent=_AgentWithClient(),
        forwarded_props={"injectA2UITool": "render_custom"},
        existing_tool_names=[],
    )
    assert plan is not None and plan.drop_tool_names == ["render_custom"]


def test_plan_injection_user_prevails_when_generate_already_wired():
    plan = plan_a2ui_injection(
        agent=_AgentWithClient(),
        forwarded_props={"injectA2UITool": True},
        existing_tool_names=["generate_a2ui"],
    )
    assert plan is None


def test_plan_injection_skips_already_wrapped_agent():
    wrapped = enable_a2ui(_AgentWithClient(), object())
    assert plan_a2ui_injection(agent=wrapped, forwarded_props={"injectA2UITool": True}, existing_tool_names=[]) is None


def test_plan_injection_skips_when_no_client_inferable():
    agent = type("NoClient", (), {"id": "i", "name": "n", "description": "d"})()
    assert plan_a2ui_injection(agent=agent, forwarded_props={"injectA2UITool": True}, existing_tool_names=[]) is None


def test_plan_injection_runtime_false_beats_backend_opt_in():
    # Nullish fallback: explicit runtime false disables even when backend config opts in.
    assert (
        plan_a2ui_injection(
            agent=_AgentWithClient(),
            forwarded_props={"injectA2UITool": False},
            existing_tool_names=[],
            config={"inject_a2ui_tool": True},
        )
        is None
    )
    # Backend opt-in applies when runtime is unset.
    plan = plan_a2ui_injection(
        agent=_AgentWithClient(),
        forwarded_props={},
        existing_tool_names=[],
        config={"inject_a2ui_tool": True},
    )
    assert plan is not None


def test_run_agent_stream_auto_wraps_and_drops_render_tool(stub_agent):
    """Integration: run_agent_stream auto-wraps the agent and strips render_a2ui."""
    from agent_framework_ag_ui._agent import AgentConfig
    from agent_framework_ag_ui._agent_run import run_agent_stream

    # Planner that narrates (no generate call) so the A2UIAgent loop ends after one
    # inner turn — no render sub-agent call needed for this assertion.
    agent = stub_agent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="hi there")], role="assistant")],
        client=object(),  # inferable render sub-agent client
    )

    input_data = {
        "messages": [{"role": "user", "content": "make a card"}],
        # The a2ui-middleware injects render_a2ui into the tool list.
        "tools": [
            {
                "name": "render_a2ui",
                "description": "render",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "context": [{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": '{"components":{}}'}],
        "forwardedProps": {"injectA2UITool": True},
    }

    async def _consume():
        async for _ in run_agent_stream(input_data, agent, AgentConfig()):
            pass

    asyncio.run(_consume())

    received = [getattr(t, "name", None) for t in (getattr(agent, "tools_received", None) or [])]
    assert "generate_a2ui" in received  # auto-injected
    assert "render_a2ui" not in received  # middleware-injected render tool dropped


# --------------------------------------------------------------------------- #
# Regression: real-LLM-only bugs (masked by pre-coalesced test doubles / aimock)
# --------------------------------------------------------------------------- #


class _FragmentedGenerateInner:
    """Planner streaming ONE generate_a2ui call the way MAF's Chat-Completions client
    actually does (verified empirically against gpt-4o):

      1. an OPENING fragment carrying id + name + EMPTY args,
      2. argument-delta fragments with name="" and call_id="" (streaming visibility),
      3. a FINAL COALESCED fragment repeating id + name + the FULL args.

    The coalescer must select the coalesced full args BY NAME. Accumulating every
    fragment name-agnostically would concatenate the deltas AND the coalesced copy,
    doubling the JSON into an unparseable string (the client emits the args twice:
    ``buf_all == 2 * buf_named``). It must also not treat each fragment as its own
    call (that emitted duplicate tool results for one call id -> a 400 on replay).
    """

    id = name = description = "planner"

    def __init__(self):
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls
        # intent=update + a target surface with no prior render. The OUTCOME (an
        # "update target not found" error envelope) depends on BOTH the intent and the
        # target_surface_id being correctly coalesced. If the args are doubled/lost, the
        # tool defaults to intent=create and paints a normal surface instead — so this
        # test fails under the name-agnostic-doubling mutation (mutation-effective).
        full = '{"intent":"update","target_surface_id":"ghost-surface"}'
        deltas = ['{"intent":"upda', 'te","target_surface_id":', '"ghost-surface"}']

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="g1", name="generate_a2ui", arguments="")],
                )
                for piece in deltas:
                    yield AgentResponseUpdate(
                        role="assistant",
                        contents=[Content.from_function_call(call_id="", name="", arguments=piece)],
                    )
                # Final coalesced fragment (MAF re-emits id + name + FULL args).
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="g1", name="generate_a2ui", arguments=full)],
                )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


class _RenderSubMAF:
    """Render sub-agent streaming render_a2ui the way MAF's Chat-Completions client does:
    an opening fragment (id + name + empty args), name="" argument deltas, then a final
    coalesced fragment (id + name + FULL args). Guards ``_extract_render_args`` against a
    name-agnostic rewrite that would double the arguments (deltas + coalesced) into
    invalid JSON."""

    def __init__(self, components=None):
        self._components = components or [{"id": "root", "component": "Card"}]

    def get_response(self, messages, *, stream=False, options=None):
        full = json.dumps({"surfaceId": "s1", "components": self._components})
        mid = len(full) // 2

        async def gen():
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_function_call(call_id="r1", name="render_a2ui", arguments="")],
            )
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_function_call(call_id="", name="", arguments=full[:mid])],
            )
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_function_call(call_id="", name="", arguments=full[mid:])],
            )
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_function_call(call_id="r1", name="render_a2ui", arguments=full)],
            )

        return gen()


def test_streaming_coalesces_fragmented_generate_call():
    kinds = asyncio.run(_drive(A2UIAgent(_FragmentedGenerateInner(), _RenderSub())))
    # Exactly ONE generate_a2ui result despite the call arriving as many fragments +
    # a coalesced copy (no duplicate tool results for one call id).
    gen_results = [k for k in kinds if k[0] == "result" and k[1] == "g1"]
    assert len(gen_results) == 1
    env = _generate_envelope(kinds)
    assert env is not None
    # The coalesced args (intent=update, target_surface_id=ghost-surface) drive an
    # "update target not found" error envelope. This assertion depends on the args
    # being correctly coalesced: doubling/losing them defaults to create + a painted
    # surface (no error), which fails here.
    assert "error" in env
    assert "ghost-surface" in env["error"]
    assert "a2ui_operations" not in env


def test_streaming_render_selects_coalesced_args_not_doubled():
    # MAF emits render args as deltas + a coalesced copy; _extract_render_args must
    # select the coalesced full args by name. Name-agnostic accumulation would join
    # deltas + coalesced into doubled, unparseable JSON -> None -> no surface.
    kinds = asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), _RenderSubMAF())))
    env = _generate_envelope(kinds)
    assert env is not None
    uc = next(o["updateComponents"] for o in env["a2ui_operations"] if "updateComponents" in o)
    assert any(c.get("id") == "root" for c in uc["components"])


def test_forwarded_list_catalog_normalized_not_crash():
    # The A2UI middleware forwards components as an ARRAY; the validator wants a
    # name->schema mapping. _resolve_catalog must normalize instead of crashing.
    schema = json.dumps({"catalogId": "cat", "components": [{"name": "Card"}]})
    slice_ = build_ag_ui_context_slice([{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": schema}])
    sub = _RenderSub(components=[{"id": "root", "component": "Card"}])
    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), sub, context_slice=slice_))))
    assert env is not None  # did not raise AttributeError on the list-shaped catalog


def test_forwarded_catalog_id_binds_surface_when_unconfigured():
    # Zero-config (advanced): no backend default_catalog_id -> bind the surface to the
    # catalog id the client forwarded, not the basic fallback.
    schema = json.dumps({"catalogId": "https://x/custom_catalog.json", "components": [{"name": "Card"}]})
    slice_ = build_ag_ui_context_slice([{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": schema}])
    sub = _RenderSub(components=[{"id": "root", "component": "Card"}])
    env = _generate_envelope(asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), sub, context_slice=slice_))))
    assert env["a2ui_operations"][0]["createSurface"]["catalogId"] == "https://x/custom_catalog.json"


def test_planner_options_do_not_carry_context_slice():
    # The forwarded context slice must never reach the planner's chat client as a run
    # option: additional_properties is sent to the provider SDK, which rejects unknown
    # keys. The slice rides in as a system message (A2UIAgent context prepend), and the
    # A2UIAgent passes the caller's options through untouched.
    class _RecordInner:
        id = name = description = "planner"

        def __init__(self):
            self.seen: list = []

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.seen.append(kwargs.get("options"))

            async def gen():
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

            return gen()

    inner = _RecordInner()
    slice_ = build_ag_ui_context_slice(
        [{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": '{"components":{"Card":{}}}'}]
    )
    asyncio.run(_drive(A2UIAgent(inner, _RenderSub(), context_slice=slice_)))
    seen = inner.seen[0]
    ap = seen.get("additional_properties", {}) if isinstance(seen, dict) else {}
    assert "ag_ui_context" not in ap


# Robustness to a DELTAS-ONLY provider (no coalesced-final fragment): the all-fragment
# concat fallback must reassemble the full args. Guards against a regression that only
# handles MAF's deltas+coalesced pattern (the reviewers' feared case).


class _RenderSubDeltasOnly:
    """Render sub-agent that streams args as deltas ONLY (name="" after the first
    fragment) with NO final coalesced fragment — the hypothetical provider the
    name-bearing concat alone cannot reassemble."""

    def __init__(self, components=None):
        self._components = components or [{"id": "root", "component": "Card"}]

    def get_response(self, messages, *, stream=False, options=None):
        full = json.dumps({"surfaceId": "s1", "components": self._components})
        third = max(1, len(full) // 3)
        pieces = [full[:third], full[third : 2 * third], full[2 * third :]]

        async def gen():
            # Opening fragment: name + id, empty args.
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_function_call(call_id="r1", name="render_a2ui", arguments="")],
            )
            # Argument deltas: name="" / call_id="", no coalesced final.
            for p in pieces:
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="", name="", arguments=p)],
                )

        return gen()


class _DeltasOnlyGenerateInner:
    """Planner streaming generate_a2ui as deltas ONLY (no coalesced final)."""

    id = name = description = "planner"

    def __init__(self):
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="g1", name="generate_a2ui", arguments="")],
                )
                # Deltas-only (no coalesced final); the all-fragment concat fallback must
                # reassemble intent=update + target_surface_id=ghost-surface.
                for p in ('{"intent":"upda', 'te","target_surface_id":', '"ghost-surface"}'):
                    yield AgentResponseUpdate(
                        role="assistant",
                        contents=[Content.from_function_call(call_id="", name="", arguments=p)],
                    )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


def test_streaming_render_reassembles_deltas_only_provider():
    kinds = asyncio.run(_drive(A2UIAgent(_GenerateOnceInner(), _RenderSubDeltasOnly())))
    env = _generate_envelope(kinds)
    assert env is not None  # all-fragment concat fallback reassembled the full args
    uc = next(o["updateComponents"] for o in env["a2ui_operations"] if "updateComponents" in o)
    assert any(c.get("id") == "root" for c in uc["components"])


def test_streaming_generate_reassembles_deltas_only_provider():
    kinds = asyncio.run(_drive(A2UIAgent(_DeltasOnlyGenerateInner(), _RenderSub())))
    gen_results = [k for k in kinds if k[0] == "result" and k[1] == "g1"]
    assert len(gen_results) == 1
    env = _generate_envelope(kinds)
    assert env is not None
    # Fallback all-fragment concat reassembled intent=update + ghost target -> the
    # "update target not found" error envelope (depends on the coalesced args).
    assert "error" in env
    assert "ghost-surface" in env["error"]


def test_streaming_aclose_mid_render_does_not_raise_generator_exit():
    # Closing the async generator mid-render (client disconnect / aclose) throws
    # GeneratorExit into the streaming loop. The mid-stream except must re-raise it
    # WITHOUT yielding a balancing tool result — yielding during GeneratorExit raises
    # "async generator ignored GeneratorExit". Red-green guard for that fix.
    sub = _RenderSub(fragments=['{"surfaceId":"s1","comp', 'onents":[{"id":"root",', '"component":"Card"}]}'])
    agent = A2UIAgent(_GenerateOnceInner(), sub)

    async def run():
        agen = agent.run("x", stream=True)
        async for update in agen:
            if any(
                getattr(c, "type", None) == "function_call" and getattr(c, "name", None) == "render_a2ui"
                for c in update.contents
            ):
                await agen.aclose()  # must complete cleanly, not raise RuntimeError
                return True
        return False

    assert asyncio.run(run()) is True


def test_sanitize_unanswered_tool_calls_strips_dangling_a2ui_calls():
    # A2UI surfaces persist as activities, so the assistant's generate_a2ui/render_a2ui
    # tool calls come back on a later turn WITHOUT tool results. Those dangling calls
    # must be stripped before the planner call (OpenAI rejects unanswered tool_calls),
    # while assistant text and balanced call/result pairs (log_a2ui_event) are kept.
    from agent_framework_ag_ui._a2ui._agent import _sanitize_unanswered_tool_calls

    msgs = [
        Message(role="user", contents=[Content.from_text(text="hi")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text(text="Here is your UI."),
                Content.from_function_call(call_id="g1", name="generate_a2ui", arguments="{}"),
                Content.from_function_call(call_id="r1", name="render_a2ui", arguments="{}"),
            ],
        ),
        Message(
            role="assistant", contents=[Content.from_function_call(call_id="e1", name="log_a2ui_event", arguments="{}")]
        ),
        Message(role="tool", contents=[Content.from_function_result(call_id="e1", result="{}")]),
    ]
    out = _sanitize_unanswered_tool_calls(msgs)
    call_ids = [
        getattr(c, "call_id", None)
        for m in out
        for c in (getattr(m, "contents", None) or [])
        if getattr(c, "type", None) == "function_call"
    ]
    assert "g1" not in call_ids and "r1" not in call_ids  # dangling a2ui calls dropped
    assert "e1" in call_ids  # balanced log_a2ui_event kept
    texts = [c.text for m in out for c in (getattr(m, "contents", None) or []) if getattr(c, "type", None) == "text"]
    assert "Here is your UI." in texts  # assistant narration preserved


# --------------------------------------------------------------------------- #
# Mixed batch: ordinary tool called alongside generate_a2ui
# --------------------------------------------------------------------------- #


class _SearchThenGenerateInner:
    """Planner that calls an ordinary tool AND generate_a2ui in the SAME turn."""

    def __init__(self):
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="s1", name="search", arguments=json.dumps({"query": "hotels"})
                        ),
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        ),
                    ],
                )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


def test_streaming_executes_ordinary_tool_called_with_generate():
    # The declaration-only generate_a2ui poisons the inner agent's batch invocation, so
    # a "look up data then render it" turn (search + generate_a2ui together) would skip
    # the backend search unless A2UIAgent executes it. Assert search runs, its result is
    # surfaced and fed back, and the surface still renders.
    from agent_framework import FunctionTool

    executed: list[str] = []

    def search(query: str = "") -> str:
        executed.append(query)
        return json.dumps({"results": ["Ritz", "Plaza"]})

    search_tool = FunctionTool(name="search", description="search", func=search)
    kinds = asyncio.run(_drive(A2UIAgent(_SearchThenGenerateInner(), _RenderSub()), tools=[search_tool]))

    assert executed == ["hotels"]  # ordinary tool actually ran
    search_results = [k for k in kinds if k[0] == "result" and k[1] == "s1"]
    assert len(search_results) == 1 and "Ritz" in search_results[0][2]  # surfaced + fed back
    assert _generate_envelope(kinds) is not None  # surface still rendered


# --------------------------------------------------------------------------- #
# Interleaved parallel generate calls: attribute nameless deltas by index
# --------------------------------------------------------------------------- #


class _InterleavedGenerateInner:
    """Two parallel generate_a2ui calls whose nameless argument deltas interleave.

    Each fragment carries the provider tool-call index on additional_properties, as the
    core chat client now preserves it.
    """

    def __init__(self):
        self.calls = 0

    @staticmethod
    def _frag(cid, name, args, idx):
        c = Content.from_function_call(call_id=cid, name=name, arguments=args)
        c.additional_properties["tool_call_index"] = idx
        return c

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls
        a1 = json.dumps({"intent": "create", "target_surface_id": "A"})
        a2 = json.dumps({"intent": "create", "target_surface_id": "B"})

        async def gen():
            if n == 1:
                # Open both calls, then interleave their argument deltas by index.
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("g1", "generate_a2ui", "", 0)])
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("g2", "generate_a2ui", "", 1)])
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("", "", a1[: len(a1) // 2], 0)])
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("", "", a2[: len(a2) // 2], 1)])
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("", "", a1[len(a1) // 2 :], 0)])
                yield AgentResponseUpdate(role="assistant", contents=[self._frag("", "", a2[len(a2) // 2 :], 1)])
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


def test_streaming_attributes_interleaved_fragments_by_index():
    captured: list[str] = []

    class _CapturingAgent(A2UIAgent):
        def _run_generate_streaming(self, call, conversation, state, box):
            captured.append(call.arguments)
            return super()._run_generate_streaming(call, conversation, state, box)

    asyncio.run(_drive(_CapturingAgent(_InterleavedGenerateInner(), _RenderSub())))
    # Each call's args reassembled from ITS OWN index-tagged fragments — not the
    # cross-contaminated concatenation a single global "last opened" pointer would give.
    assert [json.loads(a) for a in captured] == [
        {"intent": "create", "target_surface_id": "A"},
        {"intent": "create", "target_surface_id": "B"},
    ]


def test_a2ui_existing_tool_names_includes_agent_default_tools():
    # The no-double-injection check must see the agent's OWN default tools, not just the
    # runtime tools, or an agent already wired with generate_a2ui would get a second
    # declaration and the core tool merge would raise Duplicate tool name.
    from agent_framework import Agent, FunctionTool

    from agent_framework_ag_ui._agent_run import _a2ui_existing_tool_names

    tool = FunctionTool(name="generate_a2ui", description="d", func=lambda: None)
    agent = Agent(name="a", instructions="i", client=None, tools=[tool])  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    assert "generate_a2ui" in _a2ui_existing_tool_names(agent, None)  # no runtime tools


def test_mixed_batch_server_tool_runs_through_middleware_pipeline():
    # Server tools called alongside generate_a2ui must execute through the agent's real
    # function-invocation pipeline (client function_middleware preserved), not a direct
    # invoke that bypasses authorization/audit/policy middleware.
    from agent_framework import FunctionTool
    from agent_framework._middleware import FunctionMiddleware

    seen: list[str] = []

    class _RecordingMiddleware(FunctionMiddleware):
        async def process(self, context, call_next):
            seen.append("middleware-ran")
            await call_next()

    class _ClientWithMiddleware:
        function_middleware = (_RecordingMiddleware(),)
        function_invocation_configuration = None

    def search(query: str = "") -> str:
        return json.dumps({"results": ["Ritz"]})

    class _InnerWithClient(_SearchThenGenerateInner):
        client = _ClientWithMiddleware()

    search_tool = FunctionTool(name="search", description="search", func=search)
    kinds = asyncio.run(_drive(A2UIAgent(_InnerWithClient(), _RenderSub()), tools=[search_tool]))

    assert "middleware-ran" in seen  # executed through the real pipeline, not a bypass
    assert any(k[0] == "result" and k[1] == "s1" and "Ritz" in k[2] for k in kinds)


def test_mixed_batch_middleware_failure_aborts_without_rendering():
    # A fail-closed authorization/guardrail abort (MiddlewareFailure) raised while executing a
    # server tool alongside generate_a2ui must propagate and stop the run, exactly as the core
    # loop treats it, never be folded into an error result that lets the surface render anyway.
    from agent_framework import FunctionTool
    from agent_framework._middleware import FunctionMiddleware, MiddlewareFailure

    class _DenyMiddleware(FunctionMiddleware):
        async def process(self, context, call_next):
            raise MiddlewareFailure("denied by policy")

    class _ClientWithDenyMiddleware:
        function_middleware = (_DenyMiddleware(),)
        function_invocation_configuration = None

    def search(query: str = "") -> str:
        return json.dumps({"results": ["Ritz"]})

    class _InnerWithDeny(_SearchThenGenerateInner):
        client = _ClientWithDenyMiddleware()

    search_tool = FunctionTool(name="search", description="search", func=search)
    with pytest.raises(MiddlewareFailure):
        asyncio.run(_drive(A2UIAgent(_InnerWithDeny(), _RenderSub()), tools=[search_tool]))


def test_mixed_batch_tool_error_result_is_generic_not_leaking():
    # A server tool that raises must yield a generic error result (core's formatting), never the
    # raw exception text, which can carry credentials, provider payloads, or tenant data. Unlike
    # a MiddlewareFailure this is non-fatal, so the surface still renders.
    from agent_framework import FunctionTool

    secret = "sk-super-secret-token"  # noqa: S105 — test literal, not a real credential

    def search(query: str = "") -> str:
        raise RuntimeError(f"boom {secret}")

    search_tool = FunctionTool(name="search", description="search", func=search)
    kinds = asyncio.run(_drive(A2UIAgent(_SearchThenGenerateInner(), _RenderSub()), tools=[search_tool]))

    err = next(k for k in kinds if k[0] == "result" and k[1] == "s1")
    assert secret not in err[2]  # raw exception text never reaches the model
    assert "Error: Function failed." in err[2]
    assert _generate_envelope(kinds) is not None  # surface still rendered


class _ClientToolThenGenerateInner:
    """Planner that calls a declaration-only CLIENT tool AND generate_a2ui together."""

    def __init__(self):
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(call_id="c1", name="browser_action", arguments="{}"),
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        ),
                    ],
                )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


def test_mixed_batch_client_tool_left_as_user_input_not_synthesized():
    # A declaration-only client tool (func=None, browser-side) called alongside
    # generate_a2ui must NOT get a synthesized local result — that would break the
    # resumable client-tool flow. It stays a user-input call; the surface still renders.
    from agent_framework import FunctionTool

    client_tool = FunctionTool(name="browser_action", description="d", func=None, input_model={"type": "object"})
    kinds = asyncio.run(_drive(A2UIAgent(_ClientToolThenGenerateInner(), _RenderSub()), tools=[client_tool]))

    assert not any(k[0] == "result" and k[1] == "c1" for k in kinds)  # no synthesized client-tool result
    assert _generate_envelope(kinds) is not None  # surface still rendered


def test_mixed_batch_executes_agent_default_tool():
    # run_agent_stream passes no tools= when there are no AG-UI client tools, so a server
    # tool the developer wired on the agent is reachable only via default_options["tools"].
    # The mixed-batch lookup must cover it, or search returns "not executable" and the
    # surface is generated without the backend data.
    from agent_framework import FunctionTool

    ran: list[str] = []

    def search(query: str = "") -> str:
        ran.append(query)
        return json.dumps({"results": ["Ritz"]})

    search_tool = FunctionTool(name="search", description="search", func=search)

    class _InnerWithDefaultTool(_SearchThenGenerateInner):
        # No client/middleware; the server tool lives on the agent's default options only.
        default_options = {"tools": [search_tool]}

    kinds = asyncio.run(_drive(A2UIAgent(_InnerWithDefaultTool(), _RenderSub())))  # NO incoming tools
    assert ran == ["hotels"]  # default tool found + executed
    assert any(k[0] == "result" and k[1] == "s1" and "Ritz" in k[2] for k in kinds)


# --------------------------------------------------------------------------- #
# Bridge integration: client tool + generate_a2ui in one turn, through run_agent_stream
# --------------------------------------------------------------------------- #


class _ClientToolThenGenerateBridgeInner:
    """Planner double for the bridge test: turn 1 calls a client tool AND generate_a2ui
    together, turn 2 narrates."""

    id = "p"
    name = "planner"
    description = "d"

    def __init__(self):
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls

        async def gen():
            if n == 1:
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(call_id="c1", name="browser_action", arguments="{}"),
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        ),
                    ],
                )
            else:
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

        return gen()


def _etype(event):
    t = getattr(event, "type", None)
    return getattr(t, "name", None) or str(t)


async def test_bridge_client_tool_with_generate_surfaces_resumable_not_synthesized():
    # End-to-end through run_agent_stream: a turn that calls a declaration-only CLIENT
    # tool AND generate_a2ui together. Validates the resumable client-tool contract on
    # the AG-UI wire — the client tool surfaces as a frontend tool call (START/ARGS/END)
    # with NO server-synthesized result, so the frontend executes it and resumes with a
    # new run; the surface still renders; the run finishes cleanly; and (manual
    # enable_a2ui path) no terminal MESSAGES_SNAPSHOT is emitted to reorder the stream.
    from agent_framework.ag_ui import AgentFrameworkAgent

    inner = _ClientToolThenGenerateBridgeInner()
    runner = A2UIAgent(inner, _RenderSub())  # manual enable_a2ui path
    wrapper = AgentFrameworkAgent(agent=runner)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    input_data = {
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"name": "browser_action", "description": "d", "parameters": {"type": "object"}}],
    }
    events = [e async for e in wrapper.run(input_data)]
    types = [_etype(e) for e in events]

    def _ids(event_type):
        return [getattr(e, "tool_call_id", None) for e in events if _etype(e) == event_type]

    started = {
        getattr(e, "tool_call_name", None): getattr(e, "tool_call_id", None)
        for e in events
        if _etype(e) == "TOOL_CALL_START"
    }
    # Client tool surfaced as a frontend tool call the client can execute...
    assert started.get("browser_action") == "c1"
    # ...but the server did NOT synthesize a result for it (frontend resumes it).
    assert "c1" not in _ids("TOOL_CALL_RESULT")

    # The A2UI surface still generated + painted (progressive render_a2ui args + result).
    assert started.get("generate_a2ui") == "g1"
    assert "g1" in _ids("TOOL_CALL_RESULT")
    assert started.get("render_a2ui") == "r1"
    assert _ids("TOOL_CALL_ARGS").count("r1") >= 1

    # The planner is NOT re-entered after the client-tool turn: the run stops rather than
    # replay the unanswered client tool_call as unbalanced history (which the provider
    # rejects). The frontend resumes via a fresh run.
    assert inner.calls == 1

    # Run finishes (frontend-tool resume happens out of band via a new run), and no
    # terminal MESSAGES_SNAPSHOT is emitted for the A2UI run (streamed order preserved).
    assert "RUN_FINISHED" in types
    assert "MESSAGES_SNAPSHOT" not in types


# --------------------------------------------------------------------------- #
# Manual enable_a2ui() path: attribute delegation + per-request context
# --------------------------------------------------------------------------- #


def test_a2ui_agent_delegates_run_loop_attrs_to_inner():
    # The host reads client / default_options / context_providers off the runner in the
    # manual path; delegating them preserves configured tools, provider-state protection,
    # and approval middleware that the auto-injected path keeps.
    class _Inner:
        id = name = description = "p"
        client = object()
        default_options: dict[str, Any] = {"tools": []}
        context_providers = ["cp"]

    inner = _Inner()
    runner = A2UIAgent(inner, _RenderSub())
    assert runner.client is inner.client
    assert runner.default_options is inner.default_options
    assert runner.context_providers is inner.context_providers


def test_a2ui_agent_uses_per_request_context_over_constructor():
    # A reused runner must serve the CURRENT request's catalog, not a stale constructor one.
    old = build_ag_ui_context_slice(
        [{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": '{"components":{"OldCard":{}}}'}]
    )
    new = build_ag_ui_context_slice(
        [{"description": A2UI_SCHEMA_CONTEXT_DESCRIPTION, "value": '{"components":{"NewCard":{}}}'}]
    )

    class _RecordInner:
        id = name = description = "p"

        def __init__(self):
            self.seen: Any = None

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.seen = messages

            async def gen():
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(text="Done.")])

            return gen()

    inner = _RecordInner()
    runner = A2UIAgent(inner, _RenderSub(), context_slice=old)

    async def go():
        async for _ in runner.run("hi", stream=True, a2ui_context=new):
            pass

    asyncio.run(go())
    sys_text = inner.seen[0].text  # prepended system message
    assert "NewCard" in sys_text and "OldCard" not in sys_text


def test_facade_no_longer_advertises_removed_context_agent():
    import agent_framework_ag_ui as pkg

    assert "AGUIContextAgent" not in pkg.__all__
    assert pkg.A2UIAgent is A2UIAgent  # A2UI symbols still lazily importable
    with pytest.raises(AttributeError):
        _ = pkg.AGUIContextAgent


# --------------------------------------------------------------------------- #
# Mixed-batch server execution honors the core invocation controls
# --------------------------------------------------------------------------- #


class _FIConfigClient:
    """Minimal client exposing a function-invocation configuration + middleware."""

    def __init__(self, config, middleware=()):
        self.function_invocation_configuration = config
        self.function_middleware = middleware


class _RepeatSearchGenerateInner:
    """Planner that calls search + generate_a2ui every round, to exercise the cumulative
    function-call budget across A2UI planner rounds."""

    def __init__(self, client):
        self.client = client
        self.calls = 0

    def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
        self.calls += 1
        n = self.calls

        async def gen():
            yield AgentResponseUpdate(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id=f"s{n}", name="search", arguments="{}"),
                    Content.from_function_call(
                        call_id="g1" if n == 1 else f"g{n}",
                        name="generate_a2ui",
                        arguments=json.dumps({"intent": "create"}),
                    ),
                ],
            )

        return gen()


def test_mixed_batch_honors_max_function_calls_budget_across_rounds():
    # A side-effecting server tool requested alongside generate_a2ui every round must be
    # capped by the shared per-request max_function_calls budget — NOT executed once per
    # each of the A2UI planner rounds.
    from agent_framework import FunctionTool

    ran: list[int] = []

    def search(query: str = "") -> str:
        ran.append(1)
        return json.dumps({"ok": True})

    search_tool = FunctionTool(name="search", description="s", func=search)
    # Budget 4: each round spends 1 on search + 1 on generate, so search runs on rounds 1
    # and 2 (cumulative 4) then the budget stops the loop — not once per planner round.
    inner = _RepeatSearchGenerateInner(_FIConfigClient({"max_function_calls": 4}))
    asyncio.run(_drive(A2UIAgent(inner, _RenderSub()), tools=[search_tool]))
    assert len(ran) == 2  # capped cumulatively across rounds (search + generate both charge)


def test_generate_only_planner_honors_call_budget_then_narrates():
    # A generate-only planner must not run more render-subagent calls than
    # max_function_calls (generate_a2ui charges the budget), AND once the budget is spent
    # the run must still make a tools-off final narration turn — not end abruptly after the
    # surface — matching the core loop's budget-exhausted final response.
    seen_options: list = []
    seen_messages: list = []

    class _RepeatGenerateInner:
        client = _FIConfigClient({"max_function_calls": 1})

        def __init__(self):
            self.calls = 0

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.calls += 1
            seen_options.append(kwargs.get("options"))
            seen_messages.append(messages)

            async def gen():
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        )
                    ],
                )

            return gen()

    inner = _RepeatGenerateInner()
    kinds = asyncio.run(_drive(A2UIAgent(inner, _RenderSub())))
    gen_results = [k for k in kinds if k[0] == "result" and k[1] == "g1"]
    assert len(gen_results) == 1  # one render, not one per planner round
    assert inner.calls == 2  # planner round + a final narration turn (not an abrupt end)
    assert (seen_options[-1] or {}).get("tool_choice") == "none"  # final turn: tools off
    # The final turn must SEE this turn's surface (its generate_a2ui call + result), not
    # just the original user message, or it cannot narrate the result it just produced.
    final_call_ids = {
        getattr(c, "call_id", None)
        for m in seen_messages[-1]
        for c in (getattr(m, "contents", None) or [])
        if getattr(c, "type", None) in ("function_call", "function_result")
    }
    assert "g1" in final_call_ids


def test_generate_only_planner_honors_max_iterations():
    # The planner rounds are capped by max_iterations, so a generate-every-round planner
    # renders at most max_iterations surfaces.
    class _RepeatGenerateInner:
        client = _FIConfigClient({"max_iterations": 1})

        def __init__(self):
            self.calls = 0

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.calls += 1

            async def gen():
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        )
                    ],
                )

            return gen()

    inner = _RepeatGenerateInner()
    kinds = asyncio.run(_drive(A2UIAgent(inner, _RenderSub())))
    # One planner round (max_iterations=1) -> exactly one surface rendered, not one per
    # round up to MAX_PLANNER_ROUNDS.
    gen_results = [k for k in kinds if k[0] == "result" and k[1] == "g1"]
    assert len(gen_results) == 1


def test_mixed_batch_skips_server_tool_when_invocation_disabled():
    # With function invocation disabled, the core loop runs no tools at all — so neither
    # the server tool runs nor a surface is generated (generate_a2ui charges the same
    # budget), and nothing is fabricated. Matches the core loop's disabled behavior.
    from agent_framework import FunctionTool

    ran: list[int] = []

    def search(query: str = "") -> str:
        ran.append(1)
        return "{}"

    search_tool = FunctionTool(name="search", description="s", func=search)
    inner = _RepeatSearchGenerateInner(_FIConfigClient({"enabled": False}))
    kinds = asyncio.run(_drive(A2UIAgent(inner, _RenderSub()), tools=[search_tool]))
    assert ran == []  # invocation disabled -> server tool not executed
    assert _generate_envelope(kinds) is None  # and no surface generated (invocation off)
    assert not any(k[0] == "result" for k in kinds)  # nothing fabricated


def test_mixed_batch_surfaces_approval_request_and_stops():
    # An always_require server tool batched with generate_a2ui must be surfaced for
    # approval (not silently completed) and must stop the run rather than continue with an
    # orphaned assistant call.
    from agent_framework import FunctionTool

    ran: list[int] = []

    def wire_money(amount: str = "") -> str:
        ran.append(1)
        return "sent"

    approval_tool = FunctionTool(name="wire_money", description="w", func=wire_money, approval_mode="always_require")

    class _ApprovalThenGenerateInner:
        client = _FIConfigClient({})

        def __init__(self):
            self.calls = 0

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.calls += 1

            async def gen():
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(call_id="w1", name="wire_money", arguments="{}"),
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        ),
                    ],
                )

            return gen()

    inner = _ApprovalThenGenerateInner()
    kinds = asyncio.run(_drive(A2UIAgent(inner, _RenderSub()), tools=[approval_tool]))
    assert ran == []  # not executed without approval
    # No fabricated function_result for the protected tool...
    assert not any(k[0] == "result" and k[1] == "w1" for k in kinds)
    # ...and the planner is not re-entered (run stopped after surfacing the approval).
    assert inner.calls == 1


def test_final_narration_turn_forces_tools_off():
    # After the planner rounds/budget are spent, the final narration turn must force tools
    # off (tool_choice="none") so a fresh inner run cannot execute another tool batch past
    # the configured limits — matching the core loop's budget-exhausted final response.
    seen_options: list = []

    class _RecordInner:
        client = _FIConfigClient({"max_iterations": 1})

        def __init__(self):
            self.calls = 0

        def run(self, messages, *, stream=False, session=None, tools=None, **kwargs):
            self.calls += 1
            seen_options.append(kwargs.get("options"))

            async def gen():
                yield AgentResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="g1", name="generate_a2ui", arguments=json.dumps({"intent": "create"})
                        )
                    ],
                )

            return gen()

    inner = _RecordInner()
    asyncio.run(_drive(A2UIAgent(inner, _RenderSub())))
    assert inner.calls >= 2  # planner round(s) + a final narration turn
    assert (seen_options[-1] or {}).get("tool_choice") == "none"  # final turn: tools off
