# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for InvocationsHostServer.

These tests exercise ``InvocationsHostServer`` directly by constructing the
host, driving ``_partition_key`` and ``_handle_invoke`` with a fake agent and
mock requests. The Foundry request context is injected via the public
``set_request_context`` / ``reset_request_context`` helpers rather than by
patching, matching the style used in ``test_toolbox.py``.
"""

from __future__ import annotations

import asyncio
import json
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from itertools import product
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    ServiceSessionId,
    SessionStore,
    tool,
)
from anyio import CancelScope
from azure.ai.agentserver.core import (
    AgentConfig,
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response, StreamingResponse
from typing_extensions import Any

from agent_framework_foundry_hosting import InvocationsHostServer, StoreProvider
from agent_framework_foundry_hosting._state_store import FoundryAgentSessionStore

pytestmark = pytest.mark.filterwarnings("ignore:.*SessionStore is experimental.*")

# region Helpers


@pytest.fixture(autouse=True)
def configure_local_application(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "invocation-test-application")
    monkeypatch.delenv("FOUNDRY_AGENT_ID", raising=False)
    monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)


def _mock_session_store() -> MagicMock:
    store = MagicMock(spec=SessionStore)
    store.get.return_value = None
    return store


class _SessionStoreProvider(StoreProvider[SessionStore]):
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.contexts: list[FoundryAgentRequestContext] = []

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        self.contexts.append(platform_context)
        return self.store


class _FakeAgent:
    """Minimal agent implementing the ``SupportsAgentRun`` protocol.

    ``run`` returns an awaitable when ``stream`` is ``False`` and an async
    iterator when ``stream`` is ``True``. Call arguments are recorded on
    ``calls`` for assertions.
    """

    def __init__(
        self,
        *,
        response: AgentResponse | None = None,
        stream_updates: list[AgentResponseUpdate] | None = None,
        update_session: Callable[[AgentSession], None] | None = None,
    ) -> None:
        self.id = "fake-agent"
        self.name: str | None = "Fake Agent"
        self.description: str | None = "A fake agent for testing"
        self._response = response
        self._stream_updates = stream_updates or []
        self.calls: list[dict[str, Any]] = []
        self._update_session = update_session

    def run(
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "session": session})
        if session is not None and self._update_session is not None:
            self._update_session(session)
        if stream:

            async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                for update in self._stream_updates:
                    yield update

            return _gen()

        async def _run() -> AgentResponse:
            assert self._response is not None
            return self._response

        return _run()

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self,
        service_session_id: str | ServiceSessionId,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)


class _ContextAgent(_FakeAgent):
    def __init__(
        self,
        events: list[str],
        *,
        response: AgentResponse | None = None,
        stream_updates: list[AgentResponseUpdate] | None = None,
    ) -> None:
        super().__init__(response=response, stream_updates=stream_updates)
        self._events = events

    async def __aenter__(self) -> _ContextAgent:
        self._events.append("enter")
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._events.append("exit")

    def run(
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Any:
        self._events.append("run")
        result = super().run(messages, stream=stream, session=session, **kwargs)
        if not stream:
            return result

        async def _gen() -> AsyncIterator[AgentResponseUpdate]:
            try:
                async for update in result:
                    yield update
            finally:
                self._events.append("stream_close")

        return _gen()


def _make_agent(
    *,
    response_text: str | None = None,
    stream_texts: list[str] | None = None,
    update_session: Callable[[AgentSession], None] | None = None,
) -> _FakeAgent:
    """Build a ``_FakeAgent`` from plain text for non-streaming/streaming runs."""
    response = None
    if response_text is not None:
        response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(response_text)])])
    stream_updates = None
    if stream_texts is not None:
        stream_updates = [AgentResponseUpdate(contents=[Content.from_text(t)]) for t in stream_texts]
    return _FakeAgent(response=response, stream_updates=stream_updates, update_session=update_session)


def _make_request(payload: dict[str, Any]) -> Request:
    """Build a mock Starlette request whose ``json()`` returns ``payload``."""
    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value=payload)
    return request


@contextmanager
def _request_context(
    *,
    call_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[None]:
    """Install a Foundry request context for the duration of the block."""
    token = set_request_context(FoundryAgentRequestContext(call_id=call_id, user_id=user_id, session_id=session_id))
    try:
        yield
    finally:
        reset_request_context(token)


async def _collect_stream(response: StreamingResponse) -> str:
    """Concatenate the string chunks produced by a StreamingResponse."""
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else bytes(chunk).decode())
    return "".join(chunks)


# endregion


class TestSessionLifecycle:
    async def test_default_invocations_store_is_separate_from_responses(self) -> None:
        storage_keys: list[str] = []
        save = FoundryAgentSessionStore.set
        turns: list[int] = []

        async def record_save(store: FoundryAgentSessionStore, key: str, session: AgentSession) -> None:
            storage_keys.append(key)
            await save(store, key, session)

        def update_session(session: AgentSession) -> None:
            session.state["turn"] = session.state.get("turn", 0) + 1
            turns.append(session.state["turn"])

        server = InvocationsHostServer(_make_agent(response_text="ok", update_session=update_session))
        with (
            _request_context(session_id="session"),
            patch.object(FoundryAgentSessionStore, "set", record_save),
        ):
            await server._handle_invoke(_make_request({"message": "one"}))  # pyright: ignore[reportPrivateUsage]

        responses_store = FoundryAgentSessionStore(FoundryAgentRequestContext())
        key = storage_keys[0]
        assert await responses_store.get(key) is None
        responses_session = AgentSession(session_id="responses-session")
        responses_session.state["protocol"] = "responses"
        await responses_store.set(key, responses_session)
        with _request_context(session_id="session"):
            await server._handle_invoke(_make_request({"message": "two"}))  # pyright: ignore[reportPrivateUsage]
        assert turns == [1, 2]
        restored = await responses_store.get(key)
        assert restored is not None
        assert restored.state == {"protocol": "responses"}

    async def test_independent_application_names_do_not_share_sessions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[dict[str, Any]] = []

        for application in ["first-app", "second-app", "first-app"]:
            monkeypatch.setenv("FOUNDRY_AGENT_NAME", application)

            def update_session(session: AgentSession, application: str = application) -> None:
                seen.append(dict(session.state))
                session.state["application"] = application

            server = InvocationsHostServer(_make_agent(response_text="ok", update_session=update_session))
            with _request_context(session_id="shared-session"):
                await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]

        assert seen == [{}, {}, {"application": "first-app"}]

    @pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
    async def test_keep_alive_disconnect_joins_pump_before_session_cleanup(self, spec_version: str) -> None:
        entered = asyncio.Event()
        disconnected = asyncio.Event()
        saved: list[dict[str, Any]] = []
        pump: asyncio.Task[Any] | None = None
        store = _mock_session_store()

        async def save(key: str, session: AgentSession) -> None:
            saved.append(dict(session.state))

        store.set.side_effect = save

        class IdleAgent(_FakeAgent):
            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                async def updates() -> AsyncIterator[AgentResponseUpdate]:
                    nonlocal pump
                    assert session is not None
                    pump = asyncio.current_task()
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                        yield AgentResponseUpdate(contents=[Content.from_text("unused")])
                    finally:
                        await asyncio.sleep(0)
                        session.state["closed"] = True

                return updates()

        server = InvocationsHostServer(IdleAgent(), agent_session_store_provider=_SessionStoreProvider(store))
        server.config.sse_keepalive_interval = 1
        body = json.dumps({"message": "hello", "stream": True}).encode()
        received = False

        async def receive() -> Any:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body" and message.get("body") == b": keep-alive\n\n":
                assert entered.is_set()
                if spec_version == "2.4":
                    raise OSError("disconnected while idle")
                disconnected.set()
                await asyncio.Event().wait()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "method": "POST",
            "scheme": "http",
            "path": "/invocations",
            "root_path": "",
            "query_string": b"agent_session_id=session",
            "headers": [(b"content-type", b"application/json")],
            "server": ("test", 80),
            "client": ("test", 1234),
        }
        try:
            if spec_version == "2.4":
                with pytest.raises(ClientDisconnect):
                    await asyncio.wait_for(server(scope, receive, send), timeout=5)
            else:
                await asyncio.wait_for(server(scope, receive, send), timeout=5)
            assert saved == [{"closed": True}]
            assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]
            assert pump is not None
            assert pump.done()
        finally:
            if pump is not None and not pump.done():
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    @pytest.mark.parametrize("stream", [False, True])
    async def test_http_requests_restore_sessions_without_changing_response_format(self, stream: bool) -> None:
        turns: list[int] = []

        def update_session(session: AgentSession) -> None:
            session.state["turn"] = session.state.get("turn", 0) + 1
            turns.append(session.state["turn"])

        for _ in range(2):
            server = InvocationsHostServer(
                _make_agent(response_text="ok", stream_texts=["o", "k"], update_session=update_session)
            )
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
                response = await client.post(
                    "/invocations",
                    params={"agent_session_id": "session"},
                    json={"message": "hello", "stream": stream},
                )
            assert response.status_code == 200
            assert response.text == "ok"
            if stream:
                assert response.headers["content-type"].startswith("text/event-stream")
            assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]
        assert turns == [1, 2]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_function_history_is_restored_without_reexecuting_completed_tool(self, stream: bool) -> None:
        executed: list[str] = []

        @tool
        def remember() -> str:
            """Record a single completed tool call."""
            executed.append("called")
            return "remembered"

        class HistoryClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
            def __init__(self) -> None:
                super().__init__(middleware=[])
                self.calls: list[list[Message]] = []

            def _inner_get_response(
                self,
                *,
                messages: Sequence[Message],
                stream: bool,
                options: Mapping[str, Any],
                **kwargs: Any,
            ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
                self.calls.append(list(messages))
                contents = (
                    [Content.from_function_call(call_id="call-1", name="remember", arguments="{}")]
                    if len(self.calls) == 1
                    else [Content.from_text("ok")]
                )

                async def updates() -> AsyncIterator[ChatResponseUpdate]:
                    yield ChatResponseUpdate(role="assistant", contents=contents)

                async def complete() -> ChatResponse:
                    return ChatResponse(messages=[Message("assistant", contents=contents)])

                return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()

        client = HistoryClient()
        for message in ["first", "second"]:
            agent = Agent(client=client, tools=[remember], context_providers=[InMemoryHistoryProvider()])
            server = InvocationsHostServer(agent)
            with _request_context(session_id="session"):
                response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                    _make_request({"message": message, "stream": stream})
                )
                if isinstance(response, StreamingResponse):
                    assert await _collect_stream(response) == "ok"
                else:
                    assert bytes(response.body).decode() == "ok"

        assert executed == ["called"]
        assert len(client.calls) == 3
        restored = [content for message in client.calls[-1] for content in message.contents]
        assert sum(content.type == "function_call" for content in restored) == 1
        assert sum(content.type == "function_result" for content in restored) == 1
        assert client.calls[-1][0].text == "first"
        assert client.calls[-1][-1].text == "second"

    async def test_custom_store_can_restore_a_different_session_id(self) -> None:
        store = _mock_session_store()
        store.get = AsyncMock(return_value=AgentSession(session_id="different"))
        store.set = AsyncMock()
        agent = _make_agent(response_text="ok")
        server = InvocationsHostServer(agent, agent_session_store_provider=_SessionStoreProvider(store))
        with _request_context(session_id="session"):
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert agent.calls[0]["session"].session_id == "different"
        store.set.assert_awaited_once()
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_combined_failures_include_types_for_empty_messages(self) -> None:
        store = _mock_session_store()
        store.set.side_effect = RuntimeError()

        def update_session(session: AgentSession) -> None:
            raise ValueError

        server = InvocationsHostServer(
            _make_agent(response_text="ok", update_session=update_session),
            agent_session_store_provider=_SessionStoreProvider(store),
        )
        with (
            _request_context(session_id="session"),
            pytest.raises(
                RuntimeError, match="Invocation failed: ValueError; session persistence also failed: RuntimeError"
            ) as raised,
        ):
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert raised.value.__cause__ is store.set.side_effect

    async def test_control_flow_exception_still_closes_request_agent(self) -> None:
        class ControlFlowExit(BaseException):
            pass

        events: list[str] = []
        error = ControlFlowExit()
        store = _mock_session_store()
        store.set.side_effect = ValueError("save failed")

        class ExitingAgent(_ContextAgent):
            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                raise error

        server = InvocationsHostServer(
            lambda: ExitingAgent(events), agent_session_store_provider=_SessionStoreProvider(store)
        )
        with _request_context(session_id="session"), pytest.raises(ControlFlowExit) as raised:
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert raised.value is error
        assert events == ["enter", "exit"]
        store.set.assert_awaited_once()
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_cancelled_persistence_is_reported_and_releases_coordination(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = _mock_session_store()
        store.set = AsyncMock(side_effect=asyncio.CancelledError)
        server = InvocationsHostServer(
            _make_agent(response_text="ok"), agent_session_store_provider=_SessionStoreProvider(store)
        )
        with _request_context(session_id="session"), pytest.raises(asyncio.CancelledError):
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert "Invocation session persistence was cancelled" in caplog.text
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_factory_failure_does_not_retain_session(self, stream: bool) -> None:
        def create_agent() -> _FakeAgent:
            raise ValueError("factory failed")

        server = InvocationsHostServer(create_agent)
        with _request_context(session_id="session"), pytest.raises(ValueError, match="factory failed"):
            response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "hello", "stream": stream})
            )
            if isinstance(response, StreamingResponse):
                await _collect_stream(response)
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_stream_close_failure_is_reported_after_persistence(self) -> None:
        store = _mock_session_store()
        store.set = AsyncMock()
        agent = _make_agent(stream_texts=["ok"])
        iterator = MagicMock()
        iterator.__aiter__ = MagicMock(return_value=iterator)
        iterator.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
        iterator.aclose = AsyncMock(side_effect=ValueError("close failed"))
        server = InvocationsHostServer(agent, agent_session_store_provider=_SessionStoreProvider(store))
        with patch.object(agent, "run", return_value=iterator), _request_context(session_id="session"):
            response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "hello", "stream": True})
            )
            assert isinstance(response, StreamingResponse)
            with pytest.raises(ValueError, match="close failed"):
                await _collect_stream(response)
        store.set.assert_awaited_once()
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_custom_store_receives_request_context_and_namespaced_bounded_keys(self) -> None:
        store = _mock_session_store()
        store.get = AsyncMock(return_value=None)
        store.set = AsyncMock()
        provider = _SessionStoreProvider(store)
        server = InvocationsHostServer(_make_agent(response_text="ok"), agent_session_store_provider=provider)

        identities = ["x" * 1024, '["session","user"]']
        for identity in identities:
            with _request_context(call_id="call", session_id=identity):
                await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        server.config.is_hosted = True
        with _request_context(call_id="hosted-call", session_id="session", user_id="user"):
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]

        keys = [call.args[0] for call in store.set.await_args_list]
        assert len(set(keys)) == 3
        assert all(key.startswith("invocations:v1:") and len(key) <= 128 for key in keys)
        assert [call.args[1].session_id for call in store.set.await_args_list] == [
            *identities,
            '["session","user"]',
        ]
        assert provider.contexts[-1].user_id == "user"
        assert provider.contexts[-1].call_id == "hosted-call"
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_unconsumed_stream_and_invalid_input_do_not_access_storage(self) -> None:
        store = _mock_session_store()
        provider = _SessionStoreProvider(store)
        agent = _make_agent(stream_texts=["hello"])
        server = InvocationsHostServer(agent, agent_session_store_provider=provider)
        with _request_context(session_id="session"):
            response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "hello", "stream": True})
            )
            invalid = await server._handle_invoke(_make_request({}))  # pyright: ignore[reportPrivateUsage]
        assert invalid.status_code == 400
        assert isinstance(response, StreamingResponse)
        await cast(Any, response.body_iterator).aclose()
        assert provider.contexts == []
        assert agent.calls == []
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("cancel_waiter", [False, True])
    @pytest.mark.parametrize("stream", [False, True])
    async def test_same_session_serializes_and_waiter_cleanup_is_bounded(
        self, cancel_waiter: bool, stream: bool
    ) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        second_started = asyncio.Event()
        turns: list[int] = []

        class BlockingAgent(_FakeAgent):
            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                async def complete() -> AgentResponse:
                    assert session is not None
                    turn = session.state.get("turn", 0) + 1
                    if not turns:
                        entered.set()
                        await release.wait()
                    session.state["turn"] = turn
                    turns.append(turn)
                    return AgentResponse(messages=[Message("assistant", "ok")])

                async def updates() -> AsyncIterator[AgentResponseUpdate]:
                    await complete()
                    yield AgentResponseUpdate(contents=[Content.from_text("ok")])

                return updates() if stream else complete()

        server = InvocationsHostServer(BlockingAgent())

        async def invoke(*, second: bool = False) -> Response:
            with _request_context(session_id="session"):
                if second:
                    second_started.set()
                response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                    _make_request({"message": "hello", "stream": stream})
                )
                if isinstance(response, StreamingResponse):
                    await _collect_stream(response)
                return response

        first = asyncio.create_task(invoke())
        await entered.wait()
        second = asyncio.create_task(invoke(second=True))
        try:
            await second_started.wait()
            assert not second.done()
            assert server._session_locks["session"].users == 2  # pyright: ignore[reportPrivateUsage]
            if cancel_waiter:
                second.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await second
                assert server._session_locks["session"].users == 1  # pyright: ignore[reportPrivateUsage]
            release.set()
            await first
            if not cancel_waiter:
                await second
        finally:
            release.set()
            await asyncio.gather(first, second, return_exceptions=True)
        assert turns == ([1] if cancel_waiter else [1, 2])
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_different_sessions_run_concurrently(self) -> None:
        entered: set[str] = set()
        both_entered = asyncio.Event()

        class ConcurrentAgent(_FakeAgent):
            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                async def complete() -> AgentResponse:
                    assert session is not None
                    entered.add(session.session_id)
                    if len(entered) == 2:
                        both_entered.set()
                    await both_entered.wait()
                    return AgentResponse(messages=[Message("assistant", "ok")])

                return complete()

        server = InvocationsHostServer(ConcurrentAgent())

        async def invoke(session_id: str) -> None:
            with _request_context(session_id=session_id):
                await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]

        await asyncio.wait_for(asyncio.gather(invoke("one"), invoke("two")), timeout=5)
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("failure", ["load", "save", "run", "run_and_save"])
    async def test_storage_and_agent_errors_are_not_successful_responses(
        self, stream: bool, failure: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = _mock_session_store()
        store.get = (
            AsyncMock(side_effect=ValueError("load failed")) if failure == "load" else AsyncMock(return_value=None)
        )
        store.set = AsyncMock(side_effect=ValueError("save failed")) if "save" in failure else AsyncMock()

        def update_session(session: AgentSession) -> None:
            session.state["turn"] = 1
            if "run" in failure:
                raise ValueError("run failed")

        agent = _make_agent(response_text="ok", stream_texts=["ok"], update_session=update_session)
        server = InvocationsHostServer(agent, agent_session_store_provider=_SessionStoreProvider(store))
        expected = (
            "Invocation failed: run failed; session persistence also failed: save failed"
            if failure == "run_and_save"
            else (f"{failure} failed")
        )
        with _request_context(session_id="session"), pytest.raises((ValueError, RuntimeError), match=expected):
            result = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "hello", "stream": stream})
            )
            if isinstance(result, StreamingResponse):
                await _collect_stream(result)

        if failure == "load":
            assert agent.calls == []
            store.set.assert_not_awaited()
            assert "Failed to load invocation session" in caplog.text
        else:
            assert store.set.await_args is not None
            assert store.set.await_args.args[1].state == {"turn": 1}
        if "save" in failure:
            assert "Failed to persist invocation session" in caplog.text
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("fail_save", [False, True])
    async def test_cancellation_preserves_state_and_cancellation_signal(
        self, fail_save: bool, caplog: pytest.LogCaptureFixture
    ) -> None:
        entered = asyncio.Event()
        store = _mock_session_store()
        store.set = AsyncMock(side_effect=ValueError("save failed")) if fail_save else AsyncMock()

        class WaitingAgent(_FakeAgent):
            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                async def complete() -> AgentResponse:
                    assert session is not None
                    session.state["started"] = True
                    entered.set()
                    await asyncio.Event().wait()
                    return AgentResponse()

                return complete()

        server = InvocationsHostServer(WaitingAgent(), agent_session_store_provider=_SessionStoreProvider(store))
        with _request_context(session_id="session"):
            task = asyncio.create_task(
                server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
            )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.set.await_args is not None
        assert store.set.await_args.args[1].state == {"started": True}
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]
        if fail_save:
            assert "Failed to persist invocation session" in caplog.text

    @pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
    async def test_disconnect_closes_agent_and_saves_final_state(self, spec_version: str) -> None:
        sent = asyncio.Event()
        events: list[str] = []
        store = _mock_session_store()

        class StreamingAgent(_ContextAgent):
            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                await asyncio.sleep(0)
                events.append("exit")

            def run(
                self, messages: Any = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any
            ) -> Any:
                async def updates() -> AsyncIterator[AgentResponseUpdate]:
                    assert session is not None
                    try:
                        yield AgentResponseUpdate(contents=[Content.from_text("first")])
                        await asyncio.Event().wait()
                    finally:
                        await asyncio.sleep(0)
                        session.state["closed"] = True
                        events.append("close")

                return updates()

        server = InvocationsHostServer(
            lambda: StreamingAgent(events), agent_session_store_provider=_SessionStoreProvider(store)
        )
        with _request_context(session_id="session"):
            response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "hello", "stream": True})
            )

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body":
                sent.set()
                if spec_version == "2.4":
                    raise OSError("disconnected")
                await asyncio.Event().wait()

        async def receive() -> Any:
            await sent.wait()
            return {"type": "http.disconnect"}

        scope = {"type": "http", "asgi": {"spec_version": spec_version}}
        if spec_version == "2.4":
            with pytest.raises(ClientDisconnect):
                await response(scope, receive, send)
        else:
            await response(scope, receive, send)
        assert events == ["enter", "close", "exit"]
        assert store.set.await_args is not None
        assert store.set.await_args.args[1].state == {"closed": True}
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_cancelled_scope_still_awaits_persistence(self) -> None:
        store = _mock_session_store()
        saved = False

        async def save(session_id: str, session: AgentSession) -> None:
            nonlocal saved
            await asyncio.sleep(0)
            saved = True

        store.set = AsyncMock(side_effect=save)
        server = InvocationsHostServer(
            _make_agent(response_text="ok"), agent_session_store_provider=_SessionStoreProvider(store)
        )
        with _request_context(session_id="session"):
            with CancelScope() as scope:
                async with server._request_session("session", FoundryAgentRequestContext()):  # pyright: ignore[reportPrivateUsage]
                    scope.cancel()
                    await asyncio.sleep(0)
        assert saved
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_default_store_expiry_is_renewed_by_writes(self) -> None:
        turns: list[int] = []

        def update_session(session: AgentSession) -> None:
            session.state["turn"] = session.state.get("turn", 0) + 1
            turns.append(session.state["turn"])

        server = InvocationsHostServer(_make_agent(response_text="ok", update_session=update_session))
        day = 24 * 60 * 60
        with (
            _request_context(session_id="session"),
            patch("azure.ai.agentserver.core.storage._local_state._now") as now,
        ):
            for timestamp in [0, 29 * day, 58 * day, 88 * day]:
                now.return_value = timestamp
                await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert turns == [1, 2, 3, 1]

    async def test_unserializable_state_fails_explicitly(self) -> None:
        def update_session(session: AgentSession) -> None:
            session.state["unsupported"] = object()

        server = InvocationsHostServer(_make_agent(response_text="ok", update_session=update_session))
        with (
            _request_context(session_id="session"),
            pytest.warns(RuntimeWarning, match="unsupported type 'object'"),
            pytest.raises(TypeError),
        ):
            await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]


# region Initialization


class TestInit:
    def test_default_store_requires_application_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOUNDRY_AGENT_NAME")
        with pytest.raises(ValueError, match="Set session_store_namespace"):
            InvocationsHostServer(_make_agent(response_text="ok"))

        server = InvocationsHostServer(_make_agent(response_text="ok"), session_store_namespace="explicit-app")
        assert server._session_namespace == "explicit-app"  # pyright: ignore[reportPrivateUsage]

    def test_custom_store_can_own_application_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOUNDRY_AGENT_NAME")
        server = InvocationsHostServer(
            _make_agent(response_text="ok"), agent_session_store_provider=_SessionStoreProvider(_mock_session_store())
        )
        assert server._session_namespace is None  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("namespace", ["", " \t", 123])
    def test_rejects_invalid_explicit_namespace(self, namespace: Any) -> None:
        with pytest.raises(ValueError, match="session_store_namespace must be a non-empty string"):
            InvocationsHostServer(_make_agent(response_text="ok"), session_store_namespace=namespace)

    def test_namespace_precedence_is_explicit_then_agent_id_then_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        agent = _make_agent(response_text="ok")
        named = InvocationsHostServer(agent)
        assert named._session_namespace == "invocation-test-application"  # pyright: ignore[reportPrivateUsage]
        monkeypatch.setenv("FOUNDRY_AGENT_ID", "stable-agent-id")
        identified = InvocationsHostServer(agent)
        assert identified._session_namespace == "stable-agent-id"  # pyright: ignore[reportPrivateUsage]
        explicit = InvocationsHostServer(agent, session_store_namespace="explicit-app")
        assert explicit._session_namespace == "explicit-app"  # pyright: ignore[reportPrivateUsage]

    def test_accepts_supports_agent_run(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        assert server._agent is not None  # pyright: ignore[reportPrivateUsage]
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("agent", [None, 42])
    def test_rejects_invalid_agent_source(self, agent: Any) -> None:
        with pytest.raises(TypeError, match="agent must be an agent instance or a zero-argument callable"):
            InvocationsHostServer(agent)

    def test_rejects_agent_class_requiring_constructor_arguments(self) -> None:
        with pytest.raises(TypeError, match="agent callable must accept no arguments"):
            InvocationsHostServer(cast(Any, _ContextAgent))

    def test_rejects_factory_requiring_arguments(self) -> None:
        def create_agent(name: str) -> _FakeAgent:
            return _make_agent(response_text=name)

        with pytest.raises(TypeError, match="agent callable must accept no arguments"):
            InvocationsHostServer(cast(Any, create_agent))


# endregion


# region Partition key


class TestPartitionKey:
    def test_local_returns_session_id(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        with _request_context(session_id="sess-1"):
            assert server._partition_key() == "sess-1"  # pyright: ignore[reportPrivateUsage]

    def test_local_missing_session_id_raises(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        with _request_context(), pytest.raises(RuntimeError, match="missing session_id"):
            server._partition_key()  # pyright: ignore[reportPrivateUsage]

    def test_local_ignores_user_id(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        with _request_context(session_id="sess-1", user_id="user-1"):
            assert server._partition_key() == "sess-1"  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        ("session_id", "user_id"),
        [(None, "user-1"), ("", "user-1"), ("sess-1", None), ("sess-1", ""), (None, None)],
    )
    def test_hosted_requires_both_identifiers(self, session_id: str | None, user_id: str | None) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        server.config.is_hosted = True
        with (
            _request_context(call_id="call-1", session_id=session_id, user_id=user_id),
            pytest.raises(RuntimeError, match="missing session_id or user_id"),
        ):
            server._partition_key()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_returns_composite_key(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        server.config.is_hosted = True
        with _request_context(call_id="call-1", session_id="sess-1", user_id="user-1"):
            assert server._partition_key() == ("sess-1", "user-1")  # pyright: ignore[reportPrivateUsage]

    async def test_hosted_keys_and_session_ids_preserve_identifier_values(self) -> None:
        agent = _make_agent(response_text="hi")
        server = InvocationsHostServer(agent)
        server.config.is_hosted = True
        identifiers = ["part", "part:part", "part,part", "[part]", 'part"\\', "part\n\t", "\u00e9", r"\u00e9", " part "]
        keys: set[tuple[str, str]] = set()
        request = _make_request({"message": "Hi"})

        for session_id, user_id in product(identifiers, repeat=2):
            with _request_context(call_id="call-1", session_id=session_id, user_id=user_id):
                key = server._partition_key()  # pyright: ignore[reportPrivateUsage]
                response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]

            assert isinstance(key, tuple)
            assert key == (session_id, user_id)
            assert key not in keys
            keys.add(key)
            assert response.status_code == 200
            session = agent.calls[-1]["session"]
            assert isinstance(session, AgentSession)
            expected_id = json.dumps([session_id, user_id], separators=(",", ":"))
            assert session.session_id == expected_id
            assert session.to_dict()["session_id"] == expected_id


# endregion


# region Handle invoke


class TestHandleInvoke:
    async def test_completed_sessions_are_released_and_state_is_restored(self) -> None:
        sessions: list[weakref.ReferenceType[AgentSession]] = []
        turns: list[int] = []

        class CountingAgent(_FakeAgent):
            def run(
                self,
                messages: Any = None,
                *,
                stream: bool = False,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> Any:
                assert session is not None
                sessions.append(weakref.ref(session))
                turn = session.state.get("turn", 0) + 1
                session.state["turn"] = turn
                turns.append(turn)

                async def complete() -> AgentResponse:
                    return AgentResponse(messages=[Message("assistant", "ok")])

                return complete()

        server = InvocationsHostServer(CountingAgent())
        for session_id in ["first", "second", "third", "first"]:
            with _request_context(session_id=session_id):
                await server._handle_invoke(_make_request({"message": "hello"}))  # pyright: ignore[reportPrivateUsage]

        assert all(session() is None for session in sessions)
        assert turns == [1, 1, 1, 2]

    async def test_instance_context_lifetime_remains_caller_owned(self) -> None:
        events: list[str] = []
        response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])])
        server = InvocationsHostServer(_ContextAgent(events, response=response))

        with _request_context(session_id="sess-1"):
            await server._handle_invoke(_make_request({"message": "one"}))  # pyright: ignore[reportPrivateUsage]

        assert events == ["run"]

    async def test_factory_agent_context_lifetime_non_streaming(self) -> None:
        events: list[str] = []
        response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])])
        server = InvocationsHostServer(lambda: _ContextAgent(events, response=response))

        with _request_context(session_id="sess-1"):
            result = await server._handle_invoke(_make_request({"message": "one"}))  # pyright: ignore[reportPrivateUsage]

        assert bytes(result.body).decode() == "ok"
        assert events == ["enter", "run", "exit"]

    async def test_factory_agent_context_lifetime_until_stream_closes(self) -> None:
        events: list[str] = []
        updates = [
            AgentResponseUpdate(contents=[Content.from_text("one")]),
            AgentResponseUpdate(contents=[Content.from_text("two")]),
        ]
        server = InvocationsHostServer(lambda: _ContextAgent(events, stream_updates=updates))

        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "one", "stream": True})
            )

        assert isinstance(response, StreamingResponse)
        iterator = cast(Any, response.body_iterator)
        assert await anext(iterator) == "one"
        await iterator.aclose()

        assert events == ["enter", "run", "stream_close", "exit"]

    async def test_agent_callable_is_resolved_for_each_request(self) -> None:
        agents: list[_FakeAgent] = []

        def create_agent() -> _FakeAgent:
            agent = _make_agent(response_text=f"agent-{len(agents) + 1}")
            agents.append(agent)
            return agent

        server = InvocationsHostServer(create_agent)

        with _request_context(session_id="sess-1"):
            first = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "one"})
            )
            second = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                _make_request({"message": "two"})
            )

        assert bytes(first.body).decode() == "agent-1"
        assert bytes(second.body).decode() == "agent-2"
        assert len(agents) == 2
        assert agents[0] is not agents[1]
        assert agents[0].calls[0]["session"] is not agents[1].calls[0]["session"]
        assert agents[0].calls[0]["session"].session_id == agents[1].calls[0]["session"].session_id

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("hosted", [False, True])
    async def test_reusing_session_restores_identifier(self, hosted: bool, stream: bool) -> None:
        agent = _make_agent(response_text="ok", stream_texts=["ok"])
        server = InvocationsHostServer(agent)
        server.config.is_hosted = hosted
        request = _make_request({"message": "Hi", "stream": stream})
        expected_id = '["sess-1","user-1"]' if hosted else "sess-1"

        with (
            _request_context(call_id="call-1", session_id="sess-1", user_id="user-1"),
            patch("agent_framework_foundry_hosting._invocations.AgentSession", wraps=AgentSession) as session_factory,
        ):
            for _ in range(2):
                response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
                if isinstance(response, StreamingResponse):
                    assert await _collect_stream(response) == "ok"
                else:
                    assert bytes(response.body).decode() == "ok"

        assert agent.calls[0]["session"] is not agent.calls[1]["session"]
        assert agent.calls[0]["session"].session_id == agent.calls[1]["session"].session_id == expected_id
        session_factory.assert_called_once_with(session_id=expected_id)
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_missing_message_returns_400(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        request = _make_request({"stream": False})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, Response)
        assert response.status_code == 400

    async def test_missing_message_streaming_returns_400(self) -> None:
        server = InvocationsHostServer(_make_agent(stream_texts=["a"]))
        request = _make_request({"stream": True})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 400

    async def test_partition_key_failure_returns_500(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        request = _make_request({"message": "Hi"})
        # No session_id in the (local) context -> _partition_key raises -> 500.
        with _request_context():
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, Response)
        assert response.status_code == 500

    async def test_non_streaming_returns_agent_text(self) -> None:
        agent = _make_agent(response_text="Hello!")
        server = InvocationsHostServer(agent)
        request = _make_request({"message": "Hi", "stream": False})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert bytes(response.body).decode() == "Hello!"
        # Agent is called with the message wrapped in a list and the restored session.
        assert agent.calls[0]["messages"] == ["Hi"]
        assert agent.calls[0]["stream"] is False
        assert agent.calls[0]["session"].session_id == "sess-1"
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    async def test_streaming_yields_update_text(self) -> None:
        agent = _make_agent(stream_texts=["Hel", "lo", "!"])
        server = InvocationsHostServer(agent)
        request = _make_request({"message": "Hi", "stream": True})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert await _collect_stream(response) == "Hello!"
        assert agent.calls[0]["messages"] == "Hi"
        assert agent.calls[0]["stream"] is True

    async def test_session_state_is_restored_across_requests_and_hosts(self) -> None:
        def update_session(session: AgentSession) -> None:
            session.state["turn"] = session.state.get("turn", 0) + 1

        agent = _make_agent(response_text="ok", update_session=update_session)
        server = InvocationsHostServer(agent)

        with _request_context(session_id="sess-1"):
            await server._handle_invoke(_make_request({"message": "one"}))  # pyright: ignore[reportPrivateUsage]
            first_session = agent.calls[-1]["session"]
            server = InvocationsHostServer(agent)
            await server._handle_invoke(_make_request({"message": "two"}))  # pyright: ignore[reportPrivateUsage]
            second_session = agent.calls[-1]["session"]

        assert first_session is not second_session
        assert first_session.state == {"turn": 1}
        assert second_session.state == {"turn": 2}
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize(
        ("first_session_id", "first_user_id", "second_session_id", "second_user_id"),
        [
            ("session:segment", "user", "session", "segment:user"),
            ("session,segment", "user", "session", "segment,user"),
            ("session", "first-user", "session", "second-user"),
            ("first-session", "user", "second-session", "user"),
        ],
    )
    async def test_hosted_sessions_preserve_identifier_boundaries(
        self,
        stream: bool,
        first_session_id: str,
        first_user_id: str,
        second_session_id: str,
        second_user_id: str,
    ) -> None:
        def update_session(session: AgentSession) -> None:
            session.state.setdefault("turn", session.session_id)

        agent = _make_agent(response_text="ok", stream_texts=["ok"], update_session=update_session)
        server = InvocationsHostServer(agent)
        server.config.is_hosted = True
        identifiers = [(first_session_id, first_user_id), (second_session_id, second_user_id)]
        sessions: list[AgentSession] = []

        for session_id, user_id in identifiers:
            with _request_context(call_id="call-1", session_id=session_id, user_id=user_id):
                response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                    _make_request({"message": "Hi", "stream": stream})
                )
                if isinstance(response, StreamingResponse):
                    assert await _collect_stream(response) == "ok"
                else:
                    assert bytes(response.body).decode() == "ok"
                assert response.status_code == 200

            session = agent.calls[-1]["session"]
            assert isinstance(session, AgentSession)
            assert session.state == {"turn": session.session_id}
            sessions.append(session)

        assert sessions[0] is not sessions[1]
        assert sessions[0].session_id != sessions[1].session_id
        assert server._session_locks == {}  # pyright: ignore[reportPrivateUsage]

        for (session_id, user_id), session in zip(identifiers, sessions):
            with _request_context(call_id="call-2", session_id=session_id, user_id=user_id):
                response = await server._handle_invoke(  # pyright: ignore[reportPrivateUsage]
                    _make_request({"message": "Continue", "stream": stream})
                )
                if isinstance(response, StreamingResponse):
                    assert await _collect_stream(response) == "ok"
                else:
                    assert bytes(response.body).decode() == "ok"
                assert response.status_code == 200

            assert agent.calls[-1]["session"] is not session
            assert agent.calls[-1]["session"].state == {"turn": session.session_id}


# endregion
