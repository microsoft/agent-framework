# Copyright (c) Microsoft. All rights reserved.

"""Tests for :class:`AgentFrameworkHost` invocation, session, and delivery routing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from agent_framework import AgentResponseUpdate
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
    ChannelPush,
    ChannelRequest,
    ChannelSession,
    HostedRunResult,
    ResponseTarget,
)


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


class _FakeAgent:
    """Minimal :class:`SupportsAgentRun` implementation that records invocations."""

    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply
        self.calls: list[dict[str, Any]] = []
        self.created_sessions: list[_FakeAgentSession] = []

    def create_session(self, *, session_id: str | None = None) -> _FakeAgentSession:
        s = _FakeAgentSession(session_id=session_id)
        self.created_sessions.append(s)
        return s

    async def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "session": session, "kwargs": kwargs})
        if stream:  # pragma: no cover - not used by these tests

            async def _gen() -> AsyncIterator[Any]:
                yield self._reply

            return _gen()
        return _FakeAgentResponse(text=self._reply)


class _RecordingChannel:
    """Minimal :class:`Channel` + :class:`ChannelPush` for routing tests."""

    def __init__(self, name: str = "fake", path: str = "/fake", supports_push: bool = True) -> None:
        self.name = name
        self.path = path
        self.context: ChannelContext | None = None
        self.pushes: list[tuple[ChannelIdentity, HostedRunResult]] = []
        self._push_raises: Exception | None = None
        self._supports_push = supports_push
        # Provide a single trivial route so contribute() exercises the mount path.
        self._routes: Sequence[BaseRoute] = (Route("/ping", _ping),)

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        self.context = context
        return ChannelContribution(routes=self._routes)

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult) -> None:
        if self._push_raises is not None:
            raise self._push_raises
        self.pushes.append((identity, payload))


class _NoPushChannel:
    """A channel that does NOT implement :class:`ChannelPush`."""

    def __init__(self, name: str = "nopush", path: str = "/nopush") -> None:
        self.name = name
        self.path = path

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        return ChannelContribution()


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
        assert isinstance(ch, ChannelPush)

    def test_app_mounts_channel_routes_under_path(self) -> None:
        agent = _FakeAgent()
        ch = _RecordingChannel(path="/fake")
        host = AgentFrameworkHost(target=agent, channels=[ch])

        with TestClient(host.app) as client:
            r = client.get("/fake/ping")
            assert r.status_code == 200
            assert r.json() == {"ok": True}

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
    @pytest.mark.asyncio
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

        assert result.text == "hello"
        assert len(agent.calls) == 1
        msg = agent.calls[0]["messages"]
        assert msg.role == "user"
        assert msg.additional_properties["hosting"]["channel"] == "responses"
        assert msg.additional_properties["hosting"]["identity"] == {
            "channel": "responses",
            "native_id": "user:1",
            "attributes": {},
        }
        assert msg.additional_properties["hosting"]["response_target"] == {
            "kind": "originating",
            "targets": [],
        }

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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


# --------------------------------------------------------------------------- #
# Workflow target                                                              #
# --------------------------------------------------------------------------- #


class TestHostWorkflowTarget:
    """The host accepts a ``Workflow`` and dispatches to ``workflow.run(...)``."""

    @pytest.mark.asyncio
    async def test_invoke_workflow_collapses_outputs_to_hosted_run_result(self) -> None:
        from tests._workflow_fixtures import build_upper_workflow

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

        assert result.text == "HELLO"
        # No session caching for workflow targets — Workflow has no
        # ``create_session`` and the host must not invent one.
        assert host._sessions == {}

    @pytest.mark.asyncio
    async def test_stream_workflow_yields_updates_and_finalizes(self) -> None:
        from tests._workflow_fixtures import build_echo_workflow

        workflow = build_echo_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="fake", operation="message.create", input="hi")
        stream = ch.context.run_stream(req)

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

    @pytest.mark.asyncio
    async def test_stream_workflow_yields_one_update_per_output_event(self) -> None:
        from tests._workflow_fixtures import build_multi_chunk_workflow

        workflow = build_multi_chunk_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch])
        _ = host.app
        assert ch.context is not None

        req = ChannelRequest(channel="fake", operation="message.create", input="x")
        stream = ch.context.run_stream(req)

        chunks: list[str] = []
        async for update in stream:
            chunks.append(update.text)
            # The originating ``executor_id`` is propagated via author_name so
            # multi-agent workflows can route per-author rendering downstream.
            assert update.author_name == "multi"

        assert chunks == ["x-1", "x-2", "x-3"]
        final = await stream.get_final_response()
        assert final.text == "x-1x-2x-3"


class TestHostWorkflowCheckpointing:
    """The host scopes per-conversation checkpoints when ``checkpoint_location`` is set."""

    def test_rejects_workflow_with_existing_checkpoint_storage(self, tmp_path: Any) -> None:
        from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder

        from tests._workflow_fixtures import _UpperExecutor

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

    @pytest.mark.asyncio
    async def test_invoke_skips_checkpointing_when_no_isolation_key(self, tmp_path: Any) -> None:
        from tests._workflow_fixtures import build_upper_workflow

        workflow = build_upper_workflow()
        ch = _RecordingChannel()
        host = AgentFrameworkHost(target=workflow, channels=[ch], checkpoint_location=tmp_path)
        _ = host.app
        assert ch.context is not None

        # No session -> no scoping key -> no checkpoint storage written.
        req = ChannelRequest(channel="fake", operation="message.create", input="hi")
        result = await ch.context.run(req)

        assert result.text == "HI"
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_invoke_writes_checkpoint_under_isolation_key(self, tmp_path: Any) -> None:
        from tests._workflow_fixtures import build_upper_workflow

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
        assert result.text == "HI"

        # FileCheckpointStorage rooted at <tmp_path>/<isolation_key> should
        # have produced at least one checkpoint file scoped to that user.
        scoped = tmp_path / "alice"
        assert scoped.exists()
        assert any(scoped.iterdir()), "expected at least one checkpoint to be written under the per-user dir"

    @pytest.mark.asyncio
    async def test_stream_writes_checkpoint_under_isolation_key(self, tmp_path: Any) -> None:
        from tests._workflow_fixtures import build_echo_workflow

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
        stream = ch.context.run_stream(req)
        async for _ in stream:
            pass
        await stream.get_final_response()

        scoped = tmp_path / "bob"
        assert scoped.exists()
        assert any(scoped.iterdir())

    @pytest.mark.asyncio
    async def test_caller_supplied_checkpoint_storage_used_as_is(self, tmp_path: Any) -> None:
        from agent_framework import InMemoryCheckpointStorage

        from tests._workflow_fixtures import build_upper_workflow

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


# --------------------------------------------------------------------------- #
# Delivery routing                                                             #
# --------------------------------------------------------------------------- #


def _make_host_with_two_channels() -> tuple[AgentFrameworkHost, _RecordingChannel, _RecordingChannel, ChannelContext]:
    agent = _FakeAgent()
    a = _RecordingChannel(name="responses", path="/r")
    b = _RecordingChannel(name="telegram", path="/t")
    host = AgentFrameworkHost(target=agent, channels=[a, b])
    _ = host.app
    assert a.context is not None
    return host, a, b, a.context


def _record_identity_on(host: AgentFrameworkHost, isolation_key: str, channel: str, native_id: str) -> None:
    """Pre-seed the host's identity registry by running a request."""
    host._identities.setdefault(isolation_key, {})[channel] = ChannelIdentity(channel=channel, native_id=native_id)
    host._active[isolation_key] = channel


class TestDeliverResponse:
    @pytest.mark.asyncio
    async def test_originating_returns_include_originating(self) -> None:
        _, _, _, ctx = _make_host_with_two_channels()
        req = ChannelRequest(channel="responses", operation="op", input="x")
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True
        assert report.pushed == ()
        assert report.skipped == ()

    @pytest.mark.asyncio
    async def test_none_suppresses_everything(self) -> None:
        _, _, _, ctx = _make_host_with_two_channels()
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            response_target=ResponseTarget.none,  # type: ignore[attr-defined]
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is False
        assert report.pushed == ()
        assert report.skipped == ()

    @pytest.mark.asyncio
    async def test_active_pushes_to_other_channel(self) -> None:
        host, a, b, ctx = _make_host_with_two_channels()
        # Alice was last seen on telegram.
        _record_identity_on(host, "alice", "telegram", "42")
        # Now she sends a message via responses; ResponseTarget.active should
        # push to telegram, not back to responses.
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.active,  # type: ignore[attr-defined]
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is False
        assert report.pushed == ("telegram:42",)
        assert b.pushes and b.pushes[0][0].native_id == "42"

    @pytest.mark.asyncio
    async def test_active_falls_back_to_originating_when_self(self) -> None:
        host, _a, _b, ctx = _make_host_with_two_channels()
        _record_identity_on(host, "alice", "responses", "user:1")
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.active,  # type: ignore[attr-defined]
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True

    @pytest.mark.asyncio
    async def test_channels_with_unknown_identity_skipped(self) -> None:
        _, _, _, ctx = _make_host_with_two_channels()
        # No prior identity seeded for telegram on alice.
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.channel("telegram"),
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        # Skipped → fallback to originating.
        assert report.include_originating is True
        assert report.skipped == ("telegram",)
        assert report.pushed == ()

    @pytest.mark.asyncio
    async def test_channels_with_explicit_native_id_token(self) -> None:
        _, _, b, ctx = _make_host_with_two_channels()
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            response_target=ResponseTarget.channel("telegram:99"),
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.pushed == ("telegram:99",)
        assert report.include_originating is False
        assert b.pushes[0][0].native_id == "99"

    @pytest.mark.asyncio
    async def test_channels_originating_pseudo_includes_origin(self) -> None:
        host, _a, _b, ctx = _make_host_with_two_channels()
        _record_identity_on(host, "alice", "telegram", "42")
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.channels(["originating", "telegram"]),
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True
        assert report.pushed == ("telegram:42",)

    @pytest.mark.asyncio
    async def test_channels_unknown_channel_name_skipped(self) -> None:
        _, _, _, ctx = _make_host_with_two_channels()
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            response_target=ResponseTarget.channel("nope"),
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True  # fallback
        assert report.skipped == ("nope",)

    @pytest.mark.asyncio
    async def test_no_push_capability_skipped(self) -> None:
        agent = _FakeAgent()
        a = _RecordingChannel(name="responses", path="/r")
        b = _NoPushChannel(name="nopush", path="/n")
        host = AgentFrameworkHost(target=agent, channels=[a, b])
        _ = host.app
        assert a.context is not None
        # Pre-seed identity on the no-push channel so we get past the
        # identity check and hit the ChannelPush check.
        host._identities.setdefault("alice", {})["nopush"] = ChannelIdentity(channel="nopush", native_id="42")
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.channel("nopush"),
        )
        report = await a.context.deliver_response(req, HostedRunResult(text="reply"))
        assert report.skipped == ("nopush:42",)
        assert report.include_originating is True  # fallback

    @pytest.mark.asyncio
    async def test_all_linked_pushes_to_every_other_channel(self) -> None:
        host, _a, b, ctx = _make_host_with_two_channels()
        # Alice on responses (originating) and telegram.
        host._identities.setdefault("alice", {})
        host._identities["alice"]["responses"] = ChannelIdentity(channel="responses", native_id="user:1")
        host._identities["alice"]["telegram"] = ChannelIdentity(channel="telegram", native_id="42")
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.all_linked,  # type: ignore[attr-defined]
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True
        assert report.pushed == ("telegram:42",)
        assert b.pushes and b.pushes[0][1].text == "reply"

    @pytest.mark.asyncio
    async def test_all_linked_no_other_channels_falls_back(self) -> None:
        host, _a, _b, ctx = _make_host_with_two_channels()
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.all_linked,  # type: ignore[attr-defined]
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.include_originating is True
        assert report.pushed == ()

    @pytest.mark.asyncio
    async def test_push_exception_marks_skipped(self) -> None:
        host, _a, b, ctx = _make_host_with_two_channels()
        b._push_raises = RuntimeError("boom")  # type: ignore[attr-defined]
        host._identities.setdefault("alice", {})["telegram"] = ChannelIdentity(channel="telegram", native_id="42")
        req = ChannelRequest(
            channel="responses",
            operation="op",
            input="x",
            session=ChannelSession(isolation_key="alice"),
            response_target=ResponseTarget.channel("telegram"),
        )
        report = await ctx.deliver_response(req, HostedRunResult(text="reply"))
        assert report.skipped == ("telegram:42",)
        assert report.include_originating is True  # fallback
