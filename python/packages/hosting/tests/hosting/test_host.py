# Copyright (c) Microsoft. All rights reserved.

"""Tests for :class:`AgentFrameworkHost` invocation, session, and delivery routing."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    Message,
    ResponseStream,
    ServiceSessionId,
)
from agent_framework._workflows._events import WorkflowEvent
from opentelemetry import context as otel_context
from opentelemetry import trace
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route
from starlette.testclient import TestClient

from agent_framework_hosting import (
    AgentFrameworkHost,
    Channel,
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelSession,
    HostedRunResult,
)
from agent_framework_hosting._host import _workflow_event_to_update


async def _ping(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeAgentSession:
    session_id: str | None = None
    service_session_id: str | None = None


@dataclass
class _FakeAgentResponse:
    text: str

    @property
    def messages(self) -> list[Message]:
        # Real ``AgentResponse`` carries a list of messages; the host's
        # ``_invoke`` forwards them on the ``HostedRunResult``. Synthesise
        # a single assistant text message so tests that assert on
        # ``payload.text`` keep working unchanged.
        return [Message(role="assistant", contents=[Content.from_text(text=self.text)])]


class _FakeAgent:
    """Minimal :class:`SupportsAgentRun` implementation that records invocations."""

    def __init__(self, reply: str = "ok") -> None:
        self.id = "fake-agent"
        self.name: str | None = "Fake Agent"
        self.description: str | None = "Test fake agent"
        self._reply = reply
        self.calls: list[dict[str, Any]] = []
        self.created_sessions: list[AgentSession] = []

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        s = AgentSession(session_id=session_id)
        self.created_sessions.append(s)
        return s

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "session": session, "kwargs": kwargs})
        if stream:
            updates = [AgentResponseUpdate(contents=[Content.from_text(text=self._reply)], role="assistant")]

            async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                for update in updates:
                    yield update

            async def _finalize(items: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
                return AgentResponse.from_updates(items)

            return ResponseStream[AgentResponseUpdate, AgentResponse](_gen(), finalizer=_finalize)

        async def _coro() -> _FakeAgentResponse:
            return _FakeAgentResponse(text=self._reply)

        return _coro()


class _RecordingChannel:
    """Minimal :class:`Channel` for host tests."""

    def __init__(self, name: str = "fake", path: str = "/fake") -> None:
        self.name = name
        self.path = path
        self.context: ChannelContext | None = None
        # Provide a single trivial route so contribute() exercises the endpoint path.
        self._routes: Sequence[BaseRoute] = (Route("/ping", _ping),)

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        self.context = context
        return ChannelContribution(routes=self._routes)


def _assistant_response(text: str) -> AgentResponse:
    """Build a one-message ``AgentResponse`` to use as a ``HostedRunResult.result``."""
    return AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(text=text)])])


def _make_reply(text: str = "reply") -> HostedRunResult[AgentResponse]:
    """Build a ``HostedRunResult[AgentResponse]`` carrying a single assistant text message.

    Test ergonomic mirroring what the host's ``_invoke`` produces for an
    agent target — channels (and our delivery tests) receive a typed
    envelope whose ``result`` is a real :class:`AgentResponse`.
    """
    return HostedRunResult(_assistant_response(text))


def _workflow_fixture(name: str) -> Any:
    return getattr(importlib.import_module("hosting_workflow_fixtures"), name)


@dataclass
class _LifecycleChannel:
    name: str = "lifecycle"
    path: str = ""
    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        async def on_start() -> None:
            self.started.append("up")

        async def on_stop() -> None:
            self.stopped.append("down")

        return ChannelContribution(on_startup=[on_start], on_shutdown=[on_stop])


# --------------------------------------------------------------------------- #
# Host wiring                                                                  #
# --------------------------------------------------------------------------- #


class TestHostWiring:
    def test_channel_is_recognized(self) -> None:
        ch = _RecordingChannel()
        assert isinstance(ch, Channel)

    def test_app_mounts_channel_routes_under_path(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel(path="/fake")
        host = AgentFrameworkHost(target=agent, channels=[ch])

        with TestClient(host.app) as client:
            r = client.get("/fake/ping")
            assert r.status_code == 200
            assert r.json() == {"ok": True}

    def test_app_mounts_root_route_at_exact_channel_path(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel(path="/fake")
        ch._routes = (Route("/", _ping),)
        host = AgentFrameworkHost(target=agent, channels=[ch])

        with TestClient(host.app, follow_redirects=False) as client:
            r = client.get("/fake")
            assert r.status_code == 200
            assert r.json() == {"ok": True}
            assert client.get("/fake/").status_code == 200

    def test_app_mounts_at_root_when_path_is_empty(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel(path="")
        host = AgentFrameworkHost(target=agent, channels=[ch])

        with TestClient(host.app) as client:
            r = client.get("/ping")
            assert r.status_code == 200

    def test_app_is_cached(self) -> None:
        host = AgentFrameworkHost(target=_FakeAgent(), channels=[_RecordingChannel()])
        assert host.app is host.app

    def test_lifespan_invokes_startup_and_shutdown(self) -> None:
        agent = _FakeAgent()
        ch = _LifecycleChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app):
            assert ch.started == ["up"]
        assert ch.stopped == ["down"]

    def test_app_exposes_readiness_probe(self) -> None:
        host = AgentFrameworkHost(target=_FakeAgent(), channels=[_RecordingChannel()])
        with TestClient(host.app) as client:
            r = client.get("/readiness")
            assert r.status_code == 200
            assert r.text == "ok"


# --------------------------------------------------------------------------- #
# Invoke + sessions                                                            #
# --------------------------------------------------------------------------- #


class TestHostInvoke:
    async def test_invoke_wraps_input_with_hosting_metadata(self) -> None:
        agent = _FakeAgent(reply="hello")
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        # Force ``app`` build to trigger ``contribute``.
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="user:1"),
            identity=ChannelIdentity(channel="responses", native_id="user:1"),
        )
        result = await ch.context.run(req)

        assert result.result.text == "hello"
        assert len(agent.calls) == 1
        msg = agent.calls[0]["messages"]
        assert msg.role == "user"
        assert msg.additional_properties["hosting"]["channel"] == "responses"
        assert msg.additional_properties["hosting"]["identity"] == {
            "channel": "responses",
            "native_id": "user:1",
            "attributes": {},
        }

    async def test_invoke_caches_session_per_isolation_key(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req_a = ChannelRequest(
            channel=ch.name, operation="op", input="1", session=ChannelSession(isolation_key="alice")
        )
        req_b = ChannelRequest(
            channel=ch.name, operation="op", input="2", session=ChannelSession(isolation_key="alice")
        )
        req_c = ChannelRequest(channel=ch.name, operation="op", input="3", session=ChannelSession(isolation_key="bob"))

        await ch.context.run(req_a)
        await ch.context.run(req_b)
        await ch.context.run(req_c)

        # Two distinct sessions created (alice, bob) — never re-created.
        assert len(agent.created_sessions) == 2
        assert agent.calls[0]["session"] is agent.calls[1]["session"]
        assert agent.calls[0]["session"] is not agent.calls[2]["session"]

    async def test_session_disabled_does_not_create_session(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel=ch.name,
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            session_mode="disabled",
        )
        await ch.context.run(req)
        assert agent.created_sessions == []
        assert agent.calls[0]["session"] is None

    async def test_reset_session_rotates_id_and_drops_cache(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel=ch.name, operation="op", input="x", session=ChannelSession(isolation_key="alice"))
        await ch.context.run(req)
        first_session = agent.calls[-1]["session"]
        assert first_session.session_id == "alice"

        host.reset_session("alice")
        await ch.context.run(req)
        second_session = agent.calls[-1]["session"]
        # New session, new id (alias rotation), distinct object.
        assert second_session is not first_session
        assert second_session.session_id != "alice"
        assert second_session.session_id.startswith("alice#")

    async def test_options_propagates_to_target_run(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel=ch.name,
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            options={"temperature": 0.4},
        )
        await ch.context.run(req)
        assert agent.calls[0]["kwargs"]["options"] == {"temperature": 0.4}


class TestHostOwnedHooks:
    async def test_context_run_applies_run_hook_before_invocation(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None
        captured: dict[str, Any] = {}

        async def hook(request: ChannelRequest, **kwargs: Any) -> ChannelRequest:
            captured["target"] = kwargs["target"]
            captured["protocol_request"] = kwargs["protocol_request"]
            return ChannelRequest(
                channel=request.channel,
                operation=request.operation,
                input="rewritten",
                session=request.session,
            )

        req = ChannelRequest(channel=ch.name, operation="op", input="original", session=ChannelSession("alice"))
        await ch.context.run(req, run_hook=hook, protocol_request={"raw": True})

        assert captured["target"] is agent
        assert captured["protocol_request"] == {"raw": True}
        assert agent.calls[0]["messages"].text == "rewritten"

    async def test_context_run_stream_applies_run_hook_before_opening_stream(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        def hook(request: ChannelRequest, **_: Any) -> ChannelRequest:
            return ChannelRequest(channel=request.channel, operation=request.operation, input="streamed")

        stream = await ch.context.run_stream(
            ChannelRequest(channel=ch.name, operation="op", input="original"),
            run_hook=hook,
            stream_update_hook=lambda update: AgentResponseUpdate(
                contents=[Content.from_text(text=update.text.upper())],
                role="assistant",
            ),
        )

        chunks = [update.text async for update in stream]
        assert chunks == ["OK"]
        assert agent.calls[0]["messages"].text == "streamed"


# --------------------------------------------------------------------------- #
# Workflow target                                                              #
# --------------------------------------------------------------------------- #


class TestHostWorkflowTarget:
    """The host accepts a ``Workflow`` and dispatches to ``workflow.run(...)``."""

    async def test_invoke_workflow_collapses_outputs_to_hosted_run_result(self) -> None:
        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch])
        _ = host.app
        assert ch.context is not None

        # The channel's run_hook is the canonical adapter from a free-form input
        # to a workflow's typed input; here the start executor accepts ``str``
        # already so the channel forwards ``input`` verbatim.
        req = ChannelRequest(channel="fake", operation="message.create", input="hello")
        result = await ch.context.run(req)

        assert list(result.result.get_outputs()) == ["HELLO"]
        # No session caching for workflow targets — Workflow has no
        # ``create_session`` and the host must not invent one.
        assert host._sessions == {}

    async def test_stream_workflow_yields_updates_and_finalizes(self) -> None:
        build_echo_workflow = _workflow_fixture("build_echo_workflow")
        workflow = build_echo_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="fake", operation="message.create", input="hi")
        stream = await ch.context.run_stream(req)

        updates: list[AgentResponseUpdate] = []
        async for update in stream:
            updates.append(update)

        # The echo workflow yields a single ``output`` event whose payload is
        # the original string; the host wraps non-update payloads into a
        # one-shot ``AgentResponseUpdate`` carrying the text.
        assert [u.text for u in updates] == ["hi"]
        # ``raw_representation`` preserves the source ``WorkflowEvent`` so
        # advanced consumers (telemetry, debug UIs) can recover the full
        # workflow timeline.
        assert all(u.raw_representation is not None for u in updates)

        final = await stream.get_final_response()
        assert final.text == "hi"

    async def test_stream_workflow_yields_one_update_per_output_event(self) -> None:
        build_multi_chunk_workflow = _workflow_fixture("build_multi_chunk_workflow")
        workflow = build_multi_chunk_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="fake", operation="message.create", input="x")
        stream = await ch.context.run_stream(req)

        chunks: list[str] = []
        async for update in stream:
            chunks.append(update.text)
            # The originating ``executor_id`` is propagated via author_name so
            # multi-agent workflows can route per-author rendering downstream.
            assert update.author_name == "multi"

        assert chunks == ["x-1", "x-2", "x-3"]
        final = await stream.get_final_response()
        assert final.text == "x-1x-2x-3"

    def test_workflow_event_to_update_drops_non_output_events(self) -> None:
        event = WorkflowEvent("intermediate", executor_id="worker", data="hidden")

        assert _workflow_event_to_update(event) is None

    def test_workflow_event_to_update_preserves_agent_response_update_payload(self) -> None:
        event = WorkflowEvent(
            "output",
            executor_id="worker",
            data=AgentResponseUpdate(contents=[Content.from_text("chunk")], role="assistant"),
        )

        update = _workflow_event_to_update(event)

        assert update is event.data
        assert update is not None
        assert update.raw_representation is event

    def test_workflow_event_to_update_preserves_content_payload(self) -> None:
        content = Content.from_data(data=b"\x89PNG", media_type="image/png", raw_representation={"source": "test"})
        event = WorkflowEvent("output", executor_id="worker", data=content)

        update = _workflow_event_to_update(event)

        assert update is not None
        assert update.contents == [content]
        assert update.contents[0].raw_representation == {"source": "test"}
        assert update.author_name == "worker"
        assert update.raw_representation is event


class TestHostWorkflowCheckpointing:
    """The host scopes per-conversation checkpoints when ``checkpoint_location`` is set."""

    def test_rejects_workflow_with_existing_checkpoint_storage(self, tmp_path: Any) -> None:
        from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder

        _UpperExecutor = _workflow_fixture("_UpperExecutor")
        workflow = WorkflowBuilder(
            start_executor=_UpperExecutor(id="upper"),
            checkpoint_storage=InMemoryCheckpointStorage(),
        ).build()
        with pytest.raises(RuntimeError, match="already has checkpoint storage"):
            AgentFrameworkHost(
                target=workflow,
                channels=[_RecordingChannel()],
                checkpoint_location=tmp_path,
            )

    def test_warns_when_target_is_agent(self, tmp_path: Any, caplog: Any) -> None:
        import logging as _logging

        agent = _FakeAgent()
        with caplog.at_level(_logging.WARNING, logger="agent_framework.hosting"):
            host = AgentFrameworkHost(target=agent, channels=[_RecordingChannel()], checkpoint_location=tmp_path)
        assert host._checkpoint_location is None
        assert any("checkpoint_location" in rec.message for rec in caplog.records)

    async def test_invoke_skips_checkpointing_when_no_isolation_key(self, tmp_path: Any) -> None:
        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        # No session -> no scoping key -> no checkpoint storage written.
        req = ChannelRequest(channel="fake", operation="message.create", input="hi")
        result = await ch.context.run(req)

        assert list(result.result.get_outputs()) == ["HI"]
        assert list(tmp_path.iterdir()) == []

    async def test_invoke_writes_checkpoint_under_isolation_key(self, tmp_path: Any) -> None:
        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="fake",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="alice"),
        )
        result = await ch.context.run(req)
        assert list(result.result.get_outputs()) == ["HI"]

        # FileCheckpointStorage rooted at <tmp_path>/<isolation_key> should
        # have produced at least one checkpoint file scoped to that user.
        scoped = tmp_path / "alice"
        assert scoped.exists()
        assert any(scoped.iterdir()), "expected at least one checkpoint to be written under the per-user dir"

    async def test_stream_writes_checkpoint_under_isolation_key(self, tmp_path: Any) -> None:
        build_echo_workflow = _workflow_fixture("build_echo_workflow")
        workflow = build_echo_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="fake",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="bob"),
        )
        stream = await ch.context.run_stream(req)
        async for _ in stream:
            pass
        await stream.get_final_response()

        scoped = tmp_path / "bob"
        assert scoped.exists()
        assert any(scoped.iterdir())

    async def test_caller_supplied_checkpoint_storage_used_as_is(self, tmp_path: Any) -> None:
        from agent_framework import InMemoryCheckpointStorage

        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        storage = InMemoryCheckpointStorage()
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=storage)
        _ = host.app
        assert ch.context is not None
        assert host._checkpoint_location is storage

        req = ChannelRequest(
            channel="fake",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="carol"),
        )
        await ch.context.run(req)

        # The caller-owned storage is used directly (no per-user scoping
        # applied by the host); a checkpoint should appear in it.
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        assert checkpoints, "expected the caller-supplied storage to receive a checkpoint"
        # And nothing should have been written into the tmp_path tree.
        assert list(tmp_path.iterdir()) == []


class TestCheckpointPathForIsolationKey:
    """Path-traversal hardening for isolation keys joined into checkpoint paths."""

    @pytest.mark.parametrize(
        "isolation_key",
        [
            "alice",
            "telegram:42",
            "entra:abc-def_0123",
            "responses:user.name",
            "x" * 200,
        ],
    )
    def test_accepts_legitimate_keys(self, tmp_path: Any, isolation_key: str) -> None:
        from agent_framework_hosting._host import _checkpoint_path_for_isolation_key

        target = _checkpoint_path_for_isolation_key(tmp_path, isolation_key)
        assert target == (tmp_path / isolation_key).resolve()
        assert target.is_relative_to(tmp_path.resolve())

    @pytest.mark.parametrize(
        "isolation_key",
        [
            "",
            ".",
            "..",
            "...",
            "../etc",
            "../../etc/passwd",
            "a/b",
            "a\\b",
            "with\x00nul",
            "/abs/path",
            "C:/foo",
            "C:foo",
        ],
    )
    def test_rejects_traversal_patterns(self, tmp_path: Any, isolation_key: str) -> None:
        from agent_framework_hosting._host import _checkpoint_path_for_isolation_key

        with pytest.raises(ValueError, match="isolation_key"):
            _checkpoint_path_for_isolation_key(tmp_path, isolation_key)

    def test_rejects_non_string(self, tmp_path: Any) -> None:
        from agent_framework_hosting._host import _checkpoint_path_for_isolation_key

        with pytest.raises(ValueError, match="non-empty string"):
            _checkpoint_path_for_isolation_key(tmp_path, cast(Any, None))


class TestHostWorkflowCheckpointingPathTraversal:
    """End-to-end: malicious isolation keys must not escape ``checkpoint_location``."""

    async def test_traversal_key_skips_checkpointing_with_warning(self, tmp_path: Any, caplog: Any) -> None:
        import logging as _logging

        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="fake",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="../escape"),
        )
        with caplog.at_level(_logging.WARNING, logger="agent_framework.hosting"):
            result = await ch.context.run(req)

        assert list(result.result.get_outputs()) == ["HI"]
        # Nothing should have been written under tmp_path.
        assert list(tmp_path.iterdir()) == []
        assert any(
            "Skipping checkpoint storage" in rec.message and "isolation_key" in rec.message for rec in caplog.records
        )

    async def test_separator_in_key_skips_checkpointing(self, tmp_path: Any) -> None:
        build_upper_workflow = _workflow_fixture("build_upper_workflow")
        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        # A literal separator in the key is a configuration smell at best
        # and an attack at worst; either way it must not create a sub-path.
        req = ChannelRequest(
            channel="fake",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="evil/sub"),
        )
        result = await ch.context.run(req)

        assert list(result.result.get_outputs()) == ["HI"]
        assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# HostedRunResult — generic typed envelope                                     #
# --------------------------------------------------------------------------- #


class TestHostedRunResult:
    """The envelope is a thin generic wrapper around the target's
    full-fidelity ``result`` plus an optional session reference. The
    host does NOT pre-shape or flatten ``result.messages`` /
    ``result.get_outputs()`` — channels read the canonical accessor on
    the underlying result type themselves."""

    def test_result_field_carries_full_fidelity_payload(self) -> None:
        resp = AgentResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("hello")])],
            response_id="r-1",
        )
        env: HostedRunResult[AgentResponse] = HostedRunResult(resp)
        # ``result`` is the canonical accessor; metadata like
        # ``response_id`` round-trips through unchanged because the host
        # never re-shapes the payload.
        assert env.result is resp
        assert env.result.text == "hello"
        assert env.result.response_id == "r-1"
        assert env.session is None

    def test_session_field_attached_and_optional(self) -> None:
        resp = _assistant_response("ok")
        session = _FakeAgentSession(session_id="sess-1")
        env = HostedRunResult(resp, session=session)
        assert env.session is session

    def test_replace_clones_envelope_without_touching_result_by_default(self) -> None:
        resp = _assistant_response("orig")
        original = HostedRunResult(resp, session=_FakeAgentSession(session_id="s"))
        clone = original.replace()
        # Clone is a distinct envelope but the inner ``result`` is the
        # same object — channels that need a deep copy of ``result``
        # itself do the copy themselves.
        assert clone is not original
        assert clone.result is original.result
        assert clone.session is original.session

    def test_replace_rebinds_result_without_perturbing_original(self) -> None:
        original = HostedRunResult(_assistant_response("orig"))
        clone = original.replace(result=_assistant_response("shaped"))
        assert original.result.text == "orig"
        assert clone.result.text == "shaped"

    def test_replace_supports_explicit_none_session(self) -> None:
        original = HostedRunResult(_assistant_response("x"), session=_FakeAgentSession(session_id="s"))
        clone = original.replace(session=None)
        assert clone.session is None
        # Source envelope untouched.
        assert original.session is not None

    async def test_invoke_preserves_full_agent_response_on_result(self) -> None:
        """The host's ``_invoke`` carries the agent's ``AgentResponse``
        through unchanged on ``result``. Channels see image / tool /
        structured content alongside text — and metadata like
        ``response_id`` — without the host pre-shaping anything."""

        class _MultiModalResponse:
            def __init__(self) -> None:
                self.text = "summary"
                self.response_id = "resp-xyz"
                self.messages = [
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_text("summary"),
                            # Non-text content the host must NOT drop.
                            Content.from_data(data=b"\x89PNG", media_type="image/png"),
                        ],
                    ),
                ]

        class _MultiModalAgent:
            id = "multi-modal-agent"
            name: str | None = "Multi Modal Agent"
            description: str | None = "Test multi-modal agent"

            def create_session(self, *, session_id: str | None = None) -> AgentSession:
                return AgentSession(session_id=session_id)

            def get_session(
                self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None
            ) -> AgentSession:
                return AgentSession(session_id=session_id, service_session_id=service_session_id)

            def run(self, *_args: Any, **_kwargs: Any) -> Any:
                async def _coro() -> Any:
                    return _MultiModalResponse()

                return _coro()

        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=_MultiModalAgent(), channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="responses", operation="op", input="hi")
        env = await ch.context.run(req)
        # Full agent response carried through verbatim — no flattening.
        assert env.result.text == "summary"
        assert env.result.response_id == "resp-xyz"
        assert len(env.result.messages) == 1
        types = [c.type for c in env.result.messages[0].contents]
        assert "text" in types and "data" in types


# --------------------------------------------------------------------------- #
# Bind request context — duck-typed hook on context providers                 #
# --------------------------------------------------------------------------- #


from contextlib import contextmanager  # noqa: E402


class _RecordingContextProvider:
    """Stand-in for a ``HistoryProvider`` that exposes the duck-typed
    ``bind_request_context(response_id=..., previous_response_id=..., **_)``
    seam the host calls. Records (event, payload) pairs so tests can
    assert call ordering relative to the agent run + stream lifecycle.
    """

    def __init__(self, *, name: str = "rec") -> None:
        self.name = name
        # (event, payload) tuples — events: "enter", "exit", "agent_start",
        # "agent_end", "stream_yield", "stream_done".
        self.events: list[tuple[str, Any]] = []

    @contextmanager
    def bind_request_context(self, **kwargs: Any) -> Any:
        # Snapshot the call kwargs on enter (so tests can assert
        # response_id / previous_response_id forwarding) and the same
        # snapshot on exit so we can verify the SAME payload bracketed
        # the agent run.
        snapshot = dict(kwargs)
        self.events.append(("enter", snapshot))
        try:
            yield
        finally:
            self.events.append(("exit", snapshot))


class _ProvidersAgent:
    """Agent stand-in that exposes ``context_providers`` so the host's
    ``_flat_context_providers`` finds the recording provider.

    Mirrors the real :class:`agent_framework.Agent.run` shape: a sync
    ``def`` that returns either an ``Awaitable[AgentResponse]`` (for
    ``stream=False``) or a :class:`ResponseStream` synchronously (for
    ``stream=True``). The host's ``_invoke_stream`` relies on the sync
    return so it can wrap the stream in ``_BoundResponseStream`` and
    hand it to channels for later iteration.
    """

    def __init__(self, providers: Sequence[Any], *, reply: str = "ok") -> None:
        self.id = "providers-agent"
        self.name: str | None = "Providers Agent"
        self.description: str | None = "Test providers agent"
        self.context_providers = list(providers)
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    def run(
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        session: Any = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "session": session, "kwargs": kwargs})

        if stream:
            providers = self.context_providers
            updates = [
                AgentResponseUpdate(contents=[Content.from_text("chunk-1")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text("chunk-2")], role="assistant"),
            ]

            async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                # ``agent_start`` is only recorded once iteration begins;
                # if the channel abandons the stream without iterating
                # we expect to see neither ``agent_start`` nor any
                # ``stream_yield`` events.
                for prov in providers:
                    if isinstance(prov, _RecordingContextProvider):
                        prov.events.append(("agent_start", None))
                for u in updates:
                    for prov in providers:
                        if isinstance(prov, _RecordingContextProvider):
                            prov.events.append(("stream_yield", u.text))
                    yield u

            async def _finalize(items: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
                for prov in providers:
                    if isinstance(prov, _RecordingContextProvider):
                        prov.events.append(("stream_done", len(items)))
                return AgentResponse.from_updates(items)

            return ResponseStream[AgentResponseUpdate, AgentResponse](_gen(), finalizer=_finalize)

        async def _coro() -> _FakeAgentResponse:
            for prov in self.context_providers:
                if isinstance(prov, _RecordingContextProvider):
                    prov.events.append(("agent_start", None))
                    prov.events.append(("agent_end", None))
            return _FakeAgentResponse(text=self._reply)

        return _coro()


class _ProviderWrapper:
    """Wrap children in a ``providers`` attribute (mirrors the
    ``ContextProviderBase`` aggregation shape)."""

    def __init__(self, providers: Sequence[Any]) -> None:
        self.providers = list(providers)


class TestBindRequestContext:
    """The host walks ``target.context_providers``, descends one level
    when a provider exposes a ``providers`` attribute, and calls
    ``bind_request_context(response_id=..., previous_response_id=...)``
    on every provider that supports it. Foundry response-id chaining
    plugs into this exact seam — a regression that mistypes the kwarg
    name, drops the descent, or fails to keep the binding open across
    the agent run silently breaks chained writes."""

    async def test_bind_called_with_request_attributes(self) -> None:
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            session=ChannelSession(isolation_key="alice"),
            attributes={"response_id": "resp_abc", "previous_response_id": "resp_prev"},
        )
        result = await ch.context.run(req)
        assert result.result.text == "ok"

        # Bind ↔ unbind brackets the agent run.
        events = [name for name, _ in prov.events]
        assert events == ["enter", "agent_start", "agent_end", "exit"]

        # Both response_id and previous_response_id forwarded by name.
        _, enter_payload = prov.events[0]
        assert enter_payload["response_id"] == "resp_abc"
        assert enter_payload["previous_response_id"] == "resp_prev"

    async def test_bind_skipped_when_no_response_id_attribute(self) -> None:
        """Without a ``response_id`` attribute on the request, the host
        skips the binding entirely — the contract requires one to anchor
        the chain."""
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="responses", operation="op", input="hi")
        await ch.context.run(req)
        assert prov.events == [("agent_start", None), ("agent_end", None)]

    async def test_bind_does_not_descend_into_providers_attribute(self) -> None:
        """The host does not introspect ``ContextProviderBase`` aggregator
        wrappers. Aggregator providers are responsible for forwarding the
        bind to their children themselves (``AggregateContextProvider``
        already does this). The host treats whatever ``agent.context_providers``
        exposes as the final, flat list."""
        prov = _RecordingContextProvider(name="inner")
        wrapper = _ProviderWrapper([prov])
        agent = _ProvidersAgent([wrapper])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            attributes={"response_id": "resp_xyz"},
        )
        await ch.context.run(req)
        # The wrapper does not implement ``response_context``, so the
        # inner provider must NOT have been entered by the host.
        assert ("enter", {"response_id": "resp_xyz", "previous_response_id": None}) not in prov.events

    async def test_bind_held_open_until_stream_exhaustion(self) -> None:
        """Streaming runs return a ``ResponseStream`` synchronously but
        consumption happens later. The binding must survive that gap and
        only release after the iterator drains so the provider sees
        every yielded chunk under the bound context."""
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_stream"},
        )
        stream = await ch.context.run_stream(req)

        # As soon as run_stream returns, the binding must already be open
        # so any provider work that happens during iteration sees it.
        names_after_create = [name for name, _ in prov.events]
        assert names_after_create.count("enter") == 1
        assert "exit" not in names_after_create

        chunks: list[str] = []
        async for u in stream:
            chunks.append(u.text)
        assert chunks == ["chunk-1", "chunk-2"]

        # After exhaustion the binding must be released — exactly once.
        names_after_drain = [name for name, _ in prov.events]
        assert names_after_drain.count("enter") == 1
        assert names_after_drain.count("exit") == 1
        # Brackets surround every stream_yield.
        enter_idx = names_after_drain.index("enter")
        exit_idx = names_after_drain.index("exit")
        yield_idxs = [i for i, name in enumerate(names_after_drain) if name == "stream_yield"]
        assert all(enter_idx < i < exit_idx for i in yield_idxs)


# --------------------------------------------------------------------------- #
# Agent-target streaming — `_BoundResponseStream` adapter behaviour            #
# --------------------------------------------------------------------------- #


class TestBoundResponseStream:
    """The ``_BoundResponseStream`` adapter holds the bind-context
    ``ExitStack`` open across iteration. Cover the iterator-finally
    close, ``get_final_response`` close, double-close idempotence,
    ``aclose()``, ``__getattr__`` forwarding, and the awaitable path
    (which now routes through ``get_final_response`` so it doesn't
    leak the binding)."""

    async def test_get_final_response_closes_binding(self) -> None:
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_get_final"},
        )
        stream = await ch.context.run_stream(req)
        # Skip iteration and go straight to ``get_final_response``;
        # the adapter must drain the inner stream itself and close
        # the binding in ``finally``.
        final = await stream.get_final_response()
        assert final.text == "chunk-1chunk-2"
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1

    async def test_double_close_is_idempotent(self) -> None:
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_idem"},
        )
        stream = await ch.context.run_stream(req)
        async for _u in stream:
            pass
        # Iteration's finally already closed; an explicit ``aclose``
        # afterwards must be a no-op (no second exit event).
        await cast(Any, stream).aclose()
        await cast(Any, stream).aclose()
        names = [n for n, _ in prov.events]
        assert names.count("exit") == 1

    async def test_aclose_releases_binding_when_stream_abandoned(self) -> None:
        """A channel that abandons the stream without iterating must
        be able to call ``aclose()`` so the host-bound contextvars
        don't leak for the host's lifetime."""
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_abandon"},
        )
        stream = await ch.context.run_stream(req)
        await cast(Any, stream).aclose()

        # Binding released without iterating.
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1
        # Agent never ran — we abandoned before iteration.
        assert "agent_start" not in names

    async def test_getattr_forwards_to_inner_stream(self) -> None:
        """``_BoundResponseStream.__getattr__`` forwards unknown
        attributes to the inner ``ResponseStream``; channels that
        check, e.g., ``stream.add_result_hook(...)`` must keep working."""
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_getattr"},
        )
        stream = await ch.context.run_stream(req)
        # ``with_result_hook`` is a real method on ``ResponseStream``;
        # if forwarding broke this would AttributeError.
        try:
            assert callable(cast(Any, stream).with_result_hook)
        finally:
            await cast(Any, stream).aclose()

    async def test_await_path_routes_through_get_final_response(self) -> None:
        """``await stream`` is a convenience for ``await
        get_final_response()``. The previous direct delegation leaked
        the binding for the host's lifetime; the new routing closes the
        stack in the same ``finally`` as ``get_final_response``."""
        prov = _RecordingContextProvider()
        agent = _ProvidersAgent([prov])
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_await"},
        )
        stream = await ch.context.run_stream(req)
        final = await stream  # exercises __await__
        assert final.text == "chunk-1chunk-2"
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1

    async def test_deferred_streaming_keeps_captured_otel_parent_context(self) -> None:
        """`run_stream()` captures the current OTel context and reuses it for deferred pulls.

        Reproduces channel behavior where stream consumption starts later than stream
        construction (for example via StreamingResponse body iteration).
        """

        class _SpanRecordingAgent:
            id = "span-recorder"
            name: str | None = "SpanRecorder"
            description: str | None = "Records active span ids during stream pulls/finalization."

            def __init__(self) -> None:
                self.seen_span_ids: list[int] = []

            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                if not stream:
                    raise AssertionError("non-streaming path not exercised here")

                async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                    self.seen_span_ids.append(trace.get_current_span().get_span_context().span_id)
                    yield AgentResponseUpdate(contents=[Content.from_text("chunk")], role="assistant")

                async def _finalize(items: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
                    self.seen_span_ids.append(trace.get_current_span().get_span_context().span_id)
                    return AgentResponse.from_updates(items)

                return ResponseStream(_gen(), finalizer=_finalize)

        agent = _SpanRecordingAgent()
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=cast(Any, agent), channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="hi",
            stream=True,
            attributes={"response_id": "resp_otel"},
        )

        parent_ctx = trace.SpanContext(
            trace_id=0x123456789ABCDEF0123456789ABCDEF0,
            span_id=0x123456789ABCDEF0,
            is_remote=False,
            trace_flags=trace.TraceFlags(0x01),
            trace_state=trace.TraceState(),
        )
        parent_span = trace.NonRecordingSpan(parent_ctx)
        token = otel_context.attach(trace.set_span_in_context(parent_span))
        try:
            stream = await ch.context.run_stream(req)
        finally:
            otel_context.detach(token)

        # Consumption happens after the caller context has ended.
        chunks = [u.text async for u in stream]
        final = await stream.get_final_response()

        assert chunks == ["chunk"]
        assert final.text == "chunk"
        assert agent.seen_span_ids == [parent_ctx.span_id, parent_ctx.span_id]

    async def test_run_stream_captures_otel_context_before_target_run(self, monkeypatch: Any) -> None:
        """Guard the evaluation-order pitfall called out in review.

        ``_invoke_stream`` must capture OTel context before calling
        ``target.run(...)``. If that order flips, deferred streaming can bind to
        the wrong parent context.
        """

        from agent_framework_hosting import _host as host_module

        order: list[str] = []

        def _capture() -> None:
            order.append("capture")
            return

        monkeypatch.setattr(host_module, "_capture_current_otel_context", _capture)

        class _OrderAgent:
            id = "order-agent"
            name: str | None = "OrderAgent"
            description: str | None = "Records call order."

            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                order.append("run")

                async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                    yield AgentResponseUpdate(contents=[Content.from_text("chunk")], role="assistant")

                async def _finalize(items: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
                    return AgentResponse.from_updates(items)

                return ResponseStream(_gen(), finalizer=_finalize)

        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=cast(Any, _OrderAgent()), channels=[ch])
        _ = host.app
        assert ch.context is not None

        stream = await ch.context.run_stream(
            ChannelRequest(channel="responses", operation="op", input="hi", stream=True),
        )
        await cast(Any, stream).aclose()

        assert order[:2] == ["capture", "run"]


# --------------------------------------------------------------------------- #
# `_wrap_input` — list[Message] LAST-message metadata stamping                 #
# --------------------------------------------------------------------------- #


class TestWrapInputListMessages:
    """The ``hosting`` block lands on the LAST message of a list — the
    contract is load-bearing: the user turn (typically last) must
    carry the channel provenance + identity for history correlation;
    a regression stamping ``messages[0]`` instead silently breaks
    every multi-message payload."""

    async def test_metadata_lands_on_last_message_only(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        # Responses-API style: a system instruction followed by a user
        # turn. Only the user turn (LAST) gets stamped.
        system = Message(role="system", contents=[Content.from_text("be concise")])
        user = Message(role="user", contents=[Content.from_text("hi")])
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input=[system, user],
            identity=ChannelIdentity(channel="responses", native_id="user:1"),
        )
        await ch.context.run(req)

        forwarded = agent.calls[0]["messages"]
        assert isinstance(forwarded, list)
        assert len(forwarded) == 2
        # System stays clean.
        assert (system.additional_properties or {}).get("hosting") is None
        # User turn carries the metadata.
        hosting = forwarded[-1].additional_properties["hosting"]
        assert hosting["channel"] == "responses"
        assert hosting["identity"]["native_id"] == "user:1"

    async def test_single_message_payload_still_works(self) -> None:
        """Regression guard: the single-``Message`` branch must be
        unchanged by the LAST-of-list logic above."""
        agent = _FakeAgent()
        ch = _RecordingChannel(name="responses")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        _ = host.app
        assert ch.context is not None

        only = Message(role="user", contents=[Content.from_text("hi")])
        req = ChannelRequest(channel="responses", operation="op", input=only)
        await ch.context.run(req)
        forwarded = agent.calls[0]["messages"]
        assert isinstance(forwarded, Message)
        assert forwarded.additional_properties["hosting"]["channel"] == "responses"


# --------------------------------------------------------------------------- #
# Lifespan callback aggregation                                                 #
# --------------------------------------------------------------------------- #


class _RaisingLifecycleChannel:
    """Channel whose startup OR shutdown callback raises a controlled error."""

    def __init__(self, name: str, *, fail_on: str) -> None:
        self.name = name
        self.path = ""
        self._fail_on = fail_on  # "startup" | "shutdown"
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        del context

        async def _start() -> None:
            self.start_calls.append("up")
            if self._fail_on == "startup":
                raise RuntimeError(f"startup-boom-{self.name}")

        async def _stop() -> None:
            self.stop_calls.append("down")
            if self._fail_on == "shutdown":
                raise RuntimeError(f"shutdown-boom-{self.name}")

        return ChannelContribution(on_startup=[_start], on_shutdown=[_stop])


class _OkLifecycleChannel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.path = ""
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        del context

        async def _start() -> None:
            self.start_calls.append("up")

        async def _stop() -> None:
            self.stop_calls.append("down")

        return ChannelContribution(on_startup=[_start], on_shutdown=[_stop])


class TestLifespanAggregation:
    """One bad startup / shutdown callback must NOT abort the rest —
    every channel gets a chance to wire / unwire so half-initialised
    state doesn't leak. The first error is still raised so the
    process exits with a failure; remaining errors are logged so
    operators see them all in one log scrape."""

    def test_shutdown_failure_does_not_skip_peer_shutdowns(self, caplog: Any) -> None:
        import logging as _logging

        agent = _FakeAgent()
        bad = _RaisingLifecycleChannel("bad", fail_on="shutdown")
        ok1 = _OkLifecycleChannel("ok1")
        ok2 = _OkLifecycleChannel("ok2")
        # Order: bad first so that without aggregation, ok1+ok2 would
        # never get to run their shutdown callbacks.
        host = AgentFrameworkHost(target=agent, channels=[bad, ok1, ok2])

        with caplog.at_level(_logging.ERROR, logger="agent_framework.hosting"):  # noqa: SIM117
            with pytest.raises(RuntimeError, match="shutdown-boom-bad"), TestClient(host.app):
                pass

        # Every channel had its shutdown attempted, even though `bad` raised.
        assert bad.stop_calls == ["down"]
        assert ok1.stop_calls == ["down"]
        assert ok2.stop_calls == ["down"]

    def test_startup_failure_aggregates_logs_and_raises_first(self, caplog: Any) -> None:
        import logging as _logging

        agent = _FakeAgent()
        ok1 = _OkLifecycleChannel("ok1")
        bad = _RaisingLifecycleChannel("bad", fail_on="startup")
        ok2 = _OkLifecycleChannel("ok2")
        another_bad = _RaisingLifecycleChannel("bad2", fail_on="startup")
        host = AgentFrameworkHost(
            target=agent,
            channels=[ok1, bad, ok2, another_bad],
        )

        with caplog.at_level(_logging.ERROR, logger="agent_framework.hosting"):  # noqa: SIM117
            # The first failing callback's error is the one that
            # propagates; remaining failures are logged.
            with pytest.raises(RuntimeError, match="startup-boom-bad"), TestClient(host.app):
                pass

        # Every startup callback ran (even ok2 / another_bad after the
        # first failure) so we get a complete picture in the logs.
        assert ok1.start_calls == ["up"]
        assert bad.start_calls == ["up"]
        assert ok2.start_calls == ["up"]
        assert another_bad.start_calls == ["up"]

        # Both failures show up in operator logs. ``logger.exception`` puts
        # the exception payload in ``record.exc_text``; the formatted summary
        # of the second failure goes into ``record.message`` via the
        # aggregate "N callback(s) failed" line.
        log_messages = [rec.getMessage() for rec in caplog.records]
        log_exc_texts = [rec.exc_text or "" for rec in caplog.records]
        log_text = "\n".join(log_messages + log_exc_texts)
        assert "startup-boom-bad" in log_text
        assert "startup-boom-bad2" in log_text or "callback(s) failed" in log_text
