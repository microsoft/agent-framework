# Copyright (c) Microsoft. All rights reserved.

"""Tests for :class:`AgentFrameworkHost` invocation, session, and delivery routing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream
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
    async def test_push_exception_lands_in_failed_no_fallback(self) -> None:
        """Push-raised destinations land in ``DeliveryReport.failed`` (with
        an ``error_summary``) and do NOT trigger the originating-fallback.

        Distinct from a "no link recorded" drop — that lands in
        ``skipped`` (and DOES trigger the fallback). The originating
        channel is meant to inspect ``failed`` and decide whether to
        surface a degraded reply itself rather than double-delivering
        on a flaky link.
        """
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
        # Push raised → ``failed``, NOT ``skipped``.
        assert report.skipped == ()
        assert len(report.failed) == 1
        token, summary = report.failed[0]
        assert token == "telegram:42"
        assert "RuntimeError" in summary
        assert "boom" in summary
        # No fallback: caller decides whether to surface a degraded reply.
        assert report.include_originating is False


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
        self.context_providers = list(providers)
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    def create_session(self, *, session_id: str | None = None) -> _FakeAgentSession:
        return _FakeAgentSession(session_id=session_id)

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

    @pytest.mark.asyncio
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
        assert result.text == "ok"

        # Bind ↔ unbind brackets the agent run.
        events = [name for name, _ in prov.events]
        assert events == ["enter", "agent_start", "agent_end", "exit"]

        # Both response_id and previous_response_id forwarded by name.
        _, enter_payload = prov.events[0]
        assert enter_payload["response_id"] == "resp_abc"
        assert enter_payload["previous_response_id"] == "resp_prev"

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_bind_descends_one_level_into_providers_attribute(self) -> None:
        """``ContextProviderBase`` style aggregation wraps children under
        a ``providers`` attribute; the host descends one level so the
        Foundry history provider gets called even when the agent
        configures it via the wrapper."""
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
        assert ("enter", {"response_id": "resp_xyz", "previous_response_id": None}) in prov.events

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)

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

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)
        # Skip iteration and go straight to ``get_final_response``;
        # the adapter must drain the inner stream itself and close
        # the binding in ``finally``.
        final = await stream.get_final_response()
        assert final.text == "chunk-1chunk-2"
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)
        async for _u in stream:
            pass
        # Iteration's finally already closed; an explicit ``aclose``
        # afterwards must be a no-op (no second exit event).
        await stream.aclose()  # type: ignore[attr-defined]
        await stream.aclose()  # type: ignore[attr-defined]
        names = [n for n, _ in prov.events]
        assert names.count("exit") == 1

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)
        await stream.aclose()  # type: ignore[attr-defined]

        # Binding released without iterating.
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1
        # Agent never ran — we abandoned before iteration.
        assert "agent_start" not in names

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)
        # ``with_result_hook`` is a real method on ``ResponseStream``;
        # if forwarding broke this would AttributeError.
        try:
            assert callable(stream.with_result_hook)  # type: ignore[attr-defined]
        finally:
            await stream.aclose()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
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
        stream = ch.context.run_stream(req)
        final = await stream  # exercises __await__
        assert final.text == "chunk-1chunk-2"
        names = [n for n, _ in prov.events]
        assert names.count("enter") == 1
        assert names.count("exit") == 1


# --------------------------------------------------------------------------- #
# `_wrap_input` — list[Message] LAST-message metadata stamping                 #
# --------------------------------------------------------------------------- #


class TestWrapInputListMessages:
    """The ``hosting`` block lands on the LAST message of a list — the
    contract is load-bearing: the user turn (typically last) must
    carry the channel provenance + identity for history correlation;
    a regression stamping ``messages[0]`` instead silently breaks
    every multi-message payload."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    def contribute(self, _context: ChannelContext) -> ChannelContribution:
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

    def contribute(self, _context: ChannelContext) -> ChannelContribution:
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
