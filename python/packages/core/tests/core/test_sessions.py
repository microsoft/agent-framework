# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_framework import (
    AgentContext,
    AgentSession,
    ChatContext,
    ContextProvider,
    ExperimentalFeature,
    FileHistoryProvider,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    SessionContext,
    agent_middleware,
    chat_middleware,
)
from agent_framework._sessions import LOCAL_HISTORY_CONVERSATION_ID, is_local_history_conversation_id
from agent_framework.exceptions import MiddlewareException

# ---------------------------------------------------------------------------
# SessionContext tests
# ---------------------------------------------------------------------------


class TestSessionContext:
    def test_init_defaults(self) -> None:
        ctx = SessionContext(input_messages=[])
        assert ctx.session_id is None
        assert ctx.service_session_id is None
        assert ctx.input_messages == []
        assert ctx.context_messages == {}
        assert ctx.instructions == []
        assert ctx.tools == []
        assert ctx.response is None
        assert ctx.options == {}
        assert ctx.metadata == {}

    def test_extend_messages_creates_key(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg = Message(role="user", contents=["hello"])
        ctx.extend_messages("rag", [msg])
        assert "rag" in ctx.context_messages
        assert len(ctx.context_messages["rag"]) == 1
        assert ctx.context_messages["rag"][0].text == "hello"

    def test_extend_messages_appends_to_existing(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg1 = Message(role="user", contents=["first"])
        msg2 = Message(role="user", contents=["second"])
        ctx.extend_messages("src", [msg1])
        ctx.extend_messages("src", [msg2])
        assert len(ctx.context_messages["src"]) == 2

    def test_extend_messages_preserves_source_order(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_messages("a", [Message(role="user", contents=["a"])])
        ctx.extend_messages("b", [Message(role="user", contents=["b"])])
        ctx.extend_messages("c", [Message(role="user", contents=["c"])])
        assert list(ctx.context_messages.keys()) == ["a", "b", "c"]

    def test_extend_messages_sets_attribution(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg = Message(role="system", contents=["context"])
        ctx.extend_messages("rag", [msg])
        stored = ctx.context_messages["rag"][0]
        assert stored.additional_properties["_attribution"] == {"source_id": "rag"}
        # Original message is not mutated
        assert "_attribution" not in msg.additional_properties

    def test_extend_messages_does_not_overwrite_existing_attribution(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg = Message(
            role="system", contents=["context"], additional_properties={"_attribution": {"source_id": "custom"}}
        )
        ctx.extend_messages("rag", [msg])
        stored = ctx.context_messages["rag"][0]
        assert stored.additional_properties["_attribution"] == {"source_id": "custom"}

    def test_extend_messages_copies_messages(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg = Message(role="user", contents=["hello"])
        ctx.extend_messages("src", [msg])
        stored = ctx.context_messages["src"][0]
        assert stored is not msg
        assert stored.text == "hello"
        # Mutating stored copy does not affect original
        stored.additional_properties["extra"] = True
        assert "extra" not in msg.additional_properties

    def test_extend_messages_sender_sets_source_type(self) -> None:
        class MyProvider:
            source_id = "rag"

        ctx = SessionContext(input_messages=[])
        msg = Message(role="system", contents=["ctx"])
        ctx.extend_messages(MyProvider(), [msg])
        stored = ctx.context_messages["rag"][0]
        assert stored.additional_properties["_attribution"] == {"source_id": "rag", "source_type": "MyProvider"}

    def test_extend_instructions_string(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_instructions("sys", "Be helpful")
        assert ctx.instructions == ["Be helpful"]

    def test_extend_instructions_sequence(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_instructions("sys", ["Be helpful", "Be concise"])
        assert ctx.instructions == ["Be helpful", "Be concise"]

    def test_extend_middleware_creates_key_and_appends(self) -> None:
        ctx = SessionContext(input_messages=[])

        @chat_middleware
        async def first_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        ctx.extend_middleware("rag", first_middleware)
        ctx.extend_middleware("rag", [second_middleware])

        assert ctx.middleware["rag"] == [first_middleware, second_middleware]
        assert ctx.get_middleware() == [first_middleware, second_middleware]

    def test_extend_middleware_preserves_source_order(self) -> None:
        ctx = SessionContext(input_messages=[])

        @chat_middleware
        async def first_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        ctx.extend_middleware("a", first_middleware)
        ctx.extend_middleware("b", second_middleware)

        assert list(ctx.middleware.keys()) == ["a", "b"]
        assert ctx.get_middleware() == [first_middleware, second_middleware]

    def test_extend_middleware_rejects_agent_middleware(self) -> None:
        ctx = SessionContext(input_messages=[])

        @agent_middleware
        async def provider_agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        with pytest.raises(MiddlewareException, match="Context providers may only add chat or function middleware"):
            ctx.extend_middleware("rag", provider_agent_middleware)

    def test_get_messages_all(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_messages("a", [Message(role="user", contents=["a"])])
        ctx.extend_messages("b", [Message(role="user", contents=["b"])])
        result = ctx.get_messages()
        assert len(result) == 2
        assert result[0].text == "a"
        assert result[1].text == "b"

    def test_get_messages_filter_sources(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_messages("a", [Message(role="user", contents=["a"])])
        ctx.extend_messages("b", [Message(role="user", contents=["b"])])
        result = ctx.get_messages(sources=["a"])
        assert len(result) == 1
        assert result[0].text == "a"

    def test_get_messages_exclude_sources(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_messages("a", [Message(role="user", contents=["a"])])
        ctx.extend_messages("b", [Message(role="user", contents=["b"])])
        result = ctx.get_messages(exclude_sources=["a"])
        assert len(result) == 1
        assert result[0].text == "b"

    def test_get_messages_include_input(self) -> None:
        input_msg = Message(role="user", contents=["input"])
        ctx = SessionContext(input_messages=[input_msg])
        ctx.extend_messages("a", [Message(role="user", contents=["context"])])
        result = ctx.get_messages(include_input=True)
        assert len(result) == 2
        assert result[1].text == "input"

    def test_get_messages_include_response(self) -> None:
        from agent_framework import AgentResponse

        ctx = SessionContext(input_messages=[])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["reply"])])
        result = ctx.get_messages(include_response=True)
        assert len(result) == 1
        assert result[0].text == "reply"

    def test_response_readonly(self) -> None:
        ctx = SessionContext(input_messages=[])
        assert ctx.response is None
        # Can set via _response internally
        from agent_framework import AgentResponse

        resp = AgentResponse(messages=[])
        ctx._response = resp
        assert ctx.response is resp

    def test_local_history_conversation_id_sentinel(self) -> None:
        assert is_local_history_conversation_id(LOCAL_HISTORY_CONVERSATION_ID) is True
        assert is_local_history_conversation_id("some_other_id") is False


# ---------------------------------------------------------------------------
# ContextProvider tests
# ---------------------------------------------------------------------------


class TestContextProvider:
    def test_source_id_required(self) -> None:
        provider = ContextProvider(source_id="test")
        assert provider.source_id == "test"

    async def test_before_run_is_noop(self) -> None:
        provider = ContextProvider(source_id="test")
        session = AgentSession()
        ctx = SessionContext(input_messages=[])
        # Should not raise
        await provider.before_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]

    async def test_after_run_is_noop(self) -> None:
        provider = ContextProvider(source_id="test")
        session = AgentSession()
        ctx = SessionContext(input_messages=[])
        await provider.after_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# HistoryProvider tests
# ---------------------------------------------------------------------------


class ConcreteHistoryProvider(HistoryProvider):
    """Concrete test implementation."""

    def __init__(self, source_id: str, stored_messages: list[Message] | None = None, **kwargs) -> None:
        super().__init__(source_id, **kwargs)
        self.stored: list[Message] = []
        self._stored_messages = stored_messages or []

    async def get_messages(self, session_id: str | None, *, state=None, **kwargs) -> list[Message]:
        return list(self._stored_messages)

    async def save_messages(self, session_id: str | None, messages: Sequence[Message], *, state=None, **kwargs) -> None:
        self.stored.extend(messages)


class TestHistoryProviderBase:
    def test_default_flags(self) -> None:
        provider = ConcreteHistoryProvider("mem")
        assert provider.load_messages is True
        assert provider.store_outputs is True
        assert provider.store_inputs is True
        assert provider.store_context_messages is False
        assert provider.store_context_from is None

    def test_custom_flags(self) -> None:
        provider = ConcreteHistoryProvider(
            "audit",
            load_messages=False,
            store_inputs=False,
            store_context_messages=True,
            store_context_from={"rag"},
        )
        assert provider.load_messages is False
        assert provider.store_inputs is False
        assert provider.store_context_messages is True
        assert provider.store_context_from == {"rag"}

    async def test_before_run_loads_messages(self) -> None:
        msgs = [Message(role="user", contents=["history"])]
        provider = ConcreteHistoryProvider("mem", stored_messages=msgs)
        session = AgentSession()
        ctx = SessionContext(session_id="s1", input_messages=[])
        await provider.before_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]
        assert len(ctx.context_messages["mem"]) == 1
        assert ctx.context_messages["mem"][0].text == "history"

    async def test_after_run_stores_inputs_and_responses(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("mem")
        session = AgentSession()
        input_msg = Message(role="user", contents=["hello"])
        resp_msg = Message(role="assistant", contents=["hi"])
        ctx = SessionContext(session_id="s1", input_messages=[input_msg])
        ctx._response = AgentResponse(messages=[resp_msg])
        await provider.after_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]
        assert len(provider.stored) == 2
        assert provider.stored[0].text == "hello"
        assert provider.stored[1].text == "hi"

    async def test_after_run_skips_inputs_when_disabled(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("mem", store_inputs=False)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]
        assert len(provider.stored) == 1
        assert provider.stored[0].text == "hi"

    async def test_after_run_skips_responses_when_disabled(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("mem", store_outputs=False)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]
        assert len(provider.stored) == 1
        assert provider.stored[0].text == "hello"

    async def test_after_run_stores_context_messages(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("audit", load_messages=False, store_context_messages=True)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx.extend_messages("rag", [Message(role="system", contents=["context"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]
        # Should store: context from rag + input + response
        texts = [m.text for m in provider.stored]
        assert "context" in texts
        assert "hello" in texts
        assert "hi" in texts

    async def test_after_run_stores_context_from_specific_sources(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider(
            "audit", load_messages=False, store_context_messages=True, store_context_from={"rag"}
        )
        ctx = SessionContext(session_id="s1", input_messages=[])
        ctx.extend_messages("rag", [Message(role="system", contents=["rag-context"])])
        ctx.extend_messages("other", [Message(role="system", contents=["other-context"])])
        ctx._response = AgentResponse(messages=[])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]
        texts = [m.text for m in provider.stored]
        assert "rag-context" in texts
        assert "other-context" not in texts


# ---------------------------------------------------------------------------
# AgentSession tests
# ---------------------------------------------------------------------------


class TestAgentSession:
    def test_auto_generates_session_id(self) -> None:
        session = AgentSession()
        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_custom_session_id(self) -> None:
        session = AgentSession(session_id="custom-123")
        assert session.session_id == "custom-123"

    def test_state_starts_empty(self) -> None:
        session = AgentSession()
        assert session.state == {}

    def test_service_session_id(self) -> None:
        session = AgentSession(service_session_id="svc-456")
        assert session.service_session_id == "svc-456"

    def test_to_dict(self) -> None:
        session = AgentSession(session_id="s1", service_session_id="svc1")
        session.state = {"key": "value"}
        d = session.to_dict()
        assert d["type"] == "session"
        assert d["session_id"] == "s1"
        assert d["service_session_id"] == "svc1"
        assert d["state"] == {"key": "value"}

    def test_from_dict(self) -> None:
        data = {
            "type": "session",
            "session_id": "s1",
            "service_session_id": "svc1",
            "state": {"key": "value"},
        }
        session = AgentSession.from_dict(data)
        assert session.session_id == "s1"
        assert session.service_session_id == "svc1"
        assert session.state == {"key": "value"}

    def test_roundtrip(self) -> None:
        session = AgentSession(session_id="rt-1")
        session.state = {"messages": ["a", "b"], "count": 42}
        json_str = json.dumps(session.to_dict())
        restored = AgentSession.from_dict(json.loads(json_str))
        assert restored.session_id == "rt-1"
        assert restored.state == {"messages": ["a", "b"], "count": 42}

    def test_from_dict_missing_state(self) -> None:
        data = {"session_id": "s1"}
        session = AgentSession.from_dict(data)
        assert session.state == {}


# ---------------------------------------------------------------------------
# InMemoryHistoryProvider tests
# ---------------------------------------------------------------------------


class TestInMemoryHistoryProvider:
    async def test_empty_state_returns_no_messages(self) -> None:
        provider = InMemoryHistoryProvider()
        session = AgentSession()
        ctx = SessionContext(session_id="s1", input_messages=[])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )
        assert ctx.context_messages.get(provider.source_id, []) == []

    async def test_stores_and_loads_messages(self) -> None:
        from agent_framework import AgentResponse

        provider = InMemoryHistoryProvider()
        session = AgentSession()

        # First run: send input, get response
        input_msg = Message(role="user", contents=["hello"])
        resp_msg = Message(role="assistant", contents=["hi there"])
        ctx1 = SessionContext(session_id="s1", input_messages=[input_msg])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx1,
            state=session.state.setdefault(provider.source_id, {}),
        )
        ctx1._response = AgentResponse(messages=[resp_msg])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx1,
            state=session.state.setdefault(provider.source_id, {}),
        )

        # Second run: should load previous messages
        ctx2 = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["again"])])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx2,
            state=session.state.setdefault(provider.source_id, {}),
        )
        loaded = ctx2.context_messages.get(provider.source_id, [])
        assert len(loaded) == 2
        assert loaded[0].text == "hello"
        assert loaded[1].text == "hi there"

    async def test_state_is_serializable(self) -> None:
        from agent_framework import AgentResponse

        provider = InMemoryHistoryProvider()
        session = AgentSession()

        input_msg = Message(role="user", contents=["test"])
        ctx = SessionContext(session_id="s1", input_messages=[input_msg])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["reply"])])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )

        # State contains Message objects (not dicts)
        assert isinstance(session.state[provider.source_id]["messages"][0], Message)

        # to_dict() serializes them via SerializationProtocol
        session_dict = session.to_dict()
        json_str = json.dumps(session_dict)
        assert json_str  # no error

        # Round-trip through session serialization restores Message objects
        restored = AgentSession.from_dict(json.loads(json_str))
        assert isinstance(restored.state[provider.source_id]["messages"][0], Message)
        assert restored.state[provider.source_id]["messages"][0].text == "test"
        assert restored.state[provider.source_id]["messages"][1].text == "reply"

    async def test_source_id_attribution(self) -> None:
        provider = InMemoryHistoryProvider("custom-source")
        assert provider.source_id == "custom-source"
        ctx = SessionContext(session_id="s1", input_messages=[])
        ctx.extend_messages("custom-source", [Message(role="user", contents=["test"])])
        assert "custom-source" in ctx.context_messages


class TestFileHistoryProvider:
    def test_is_marked_experimental(self) -> None:
        assert FileHistoryProvider.__feature_stage__ == "experimental"
        assert FileHistoryProvider.__feature_id__ == ExperimentalFeature.FILE_HISTORY.value
        assert FileHistoryProvider.__doc__ is not None
        assert ".. warning:: Experimental" in FileHistoryProvider.__doc__

    async def test_stores_and_loads_messages(self, tmp_path: Path) -> None:
        from agent_framework import AgentResponse

        provider = FileHistoryProvider(tmp_path)
        session = AgentSession(session_id="s1")

        input_message = Message(role="user", contents=["hello"])
        response_message = Message(role="assistant", contents=["hi there"])
        first_context = SessionContext(session_id=session.session_id, input_messages=[input_message])

        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=first_context,
            state={},
        )
        first_context._response = AgentResponse(messages=[response_message])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=first_context,
            state={},
        )

        session_file = provider._session_file_path(session.session_id)
        assert session_file.name == "s1.jsonl"
        assert session_file.exists()
        raw_lines = (await asyncio.to_thread(session_file.read_text, encoding="utf-8")).splitlines()
        assert len(raw_lines) == 2
        payloads = [json.loads(line) for line in raw_lines]
        assert all(payload["type"] == "message" for payload in payloads)
        assert all("session_id" not in payload for payload in payloads)

        second_context = SessionContext(
            session_id=session.session_id, input_messages=[Message(role="user", contents=["again"])]
        )
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,
            session=session,
            context=second_context,
            state={},
        )
        loaded = second_context.context_messages.get(provider.source_id, [])
        assert len(loaded) == 2
        assert loaded[0].text == "hello"
        assert loaded[1].text == "hi there"

    def test_creates_storage_directory(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "nested" / "history"
        provider = FileHistoryProvider(nested_path)
        assert provider.storage_path == nested_path
        assert nested_path.exists()
        assert nested_path.is_dir()

    async def test_uses_encoded_filename_for_unsafe_session_id(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)
        unsafe_session_id = "../unsafe/session"

        await provider.save_messages(unsafe_session_id, [Message(role="user", contents=["hello"])])

        session_file = provider._session_file_path(unsafe_session_id)
        assert session_file.parent == provider.storage_path
        assert session_file.name.startswith("~session-")
        assert session_file.suffix == ".jsonl"
        assert session_file.exists()
        jsonl_files = await asyncio.to_thread(
            lambda: sorted(path.name for path in provider.storage_path.glob("*.jsonl"))
        )
        assert jsonl_files == [session_file.name]

    async def test_allows_custom_serializers_returning_bytes(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def dumps(payload: object) -> bytes:
            calls.append("dumps")
            return json.dumps(payload).encode("utf-8")

        def loads(payload: str | bytes) -> object:
            calls.append("loads")
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return json.loads(payload)

        provider = FileHistoryProvider(tmp_path, dumps=dumps, loads=loads)

        await provider.save_messages("custom-serializer", [Message(role="user", contents=["hello"])])
        loaded = await provider.get_messages("custom-serializer")

        assert calls == ["dumps", "loads"]
        assert len(loaded) == 1
        assert loaded[0].text == "hello"

    async def test_invalid_jsonl_line_raises(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)
        await asyncio.to_thread(provider._session_file_path("broken").write_text, "{not-json}\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Failed to deserialize history line 1"):
            await provider.get_messages("broken")

    async def test_missing_session_file_returns_empty_messages(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)

        loaded = await provider.get_messages("missing")

        assert loaded == []

    async def test_none_session_id_uses_default_jsonl_file(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)

        await provider.save_messages(None, [Message(role="user", contents=["hello"])])

        session_file = provider._session_file_path(None)
        assert session_file.name == "default.jsonl"
        loaded = await provider.get_messages(None)
        assert [message.text for message in loaded] == ["hello"]

    async def test_non_mapping_jsonl_line_raises(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)
        await asyncio.to_thread(provider._session_file_path("non-mapping").write_text, "[1, 2, 3]\n", encoding="utf-8")

        with pytest.raises(ValueError, match="did not deserialize to a mapping"):
            await provider.get_messages("non-mapping")

    async def test_skip_excluded_omits_excluded_messages(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path, skip_excluded=True)

        await provider.save_messages(
            "skip-excluded",
            [
                Message(role="user", contents=["keep"]),
                Message(role="assistant", contents=["skip"], additional_properties={"_excluded": True}),
            ],
        )

        loaded = await provider.get_messages("skip-excluded")

        assert [message.text for message in loaded] == ["keep"]

    async def test_serializer_must_return_single_line_json(self, tmp_path: Path) -> None:
        def dumps(payload: object) -> str:
            return json.dumps(payload, indent=2)

        provider = FileHistoryProvider(tmp_path, dumps=dumps)

        with pytest.raises(ValueError, match="single-line JSON"):
            await provider.save_messages("pretty-json", [Message(role="user", contents=["hello"])])

    async def test_concurrent_writes_for_same_session_are_locked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        provider = FileHistoryProvider(tmp_path)
        session_id = "shared-session"
        file_path = provider._session_file_path(session_id)
        real_open = Path.open
        write_started = threading.Event()
        active_writes = 0
        overlap_detected = False

        class _TrackingFile:
            def __init__(self, wrapped: Any) -> None:
                self._wrapped = wrapped

            def __enter__(self) -> "_TrackingFile":
                self._wrapped.__enter__()
                return self

            def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                self._wrapped.__exit__(exc_type, exc_val, exc_tb)

            def write(self, data: str) -> int:
                nonlocal active_writes, overlap_detected
                write_started.set()
                active_writes += 1
                overlap_detected = overlap_detected or active_writes > 1
                try:
                    time.sleep(0.05)
                    return int(self._wrapped.write(data))
                finally:
                    active_writes -= 1

            def __getattr__(self, name: str) -> Any:
                return getattr(self._wrapped, name)

        def tracked_open(path: Path, *args: Any, **kwargs: Any) -> Any:
            handle = real_open(path, *args, **kwargs)
            if path == file_path and args and args[0] == "a":
                return _TrackingFile(handle)
            return handle

        monkeypatch.setattr(Path, "open", tracked_open)

        first_save = asyncio.create_task(provider.save_messages(session_id, [Message(role="user", contents=["first"])]))
        started = await asyncio.to_thread(write_started.wait, 1.0)
        assert started

        second_save = asyncio.create_task(
            provider.save_messages(session_id, [Message(role="assistant", contents=["second"])])
        )
        await asyncio.gather(first_save, second_save)

        assert not overlap_detected
        loaded = await provider.get_messages(session_id)
        assert [message.text for message in loaded] == ["first", "second"]
