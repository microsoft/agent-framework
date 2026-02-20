# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import Sequence

from agent_framework import Message
from agent_framework._sessions import (
    AgentSession,
    BaseContextProvider,
    BaseHistoryProvider,
    InMemoryHistoryProvider,
    SessionContext,
)

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


# ---------------------------------------------------------------------------
# BaseContextProvider tests
# ---------------------------------------------------------------------------


class TestContextProviderBase:
    def test_source_id_required(self) -> None:
        provider = BaseContextProvider(source_id="test")
        assert provider.source_id == "test"

    async def test_before_run_is_noop(self) -> None:
        provider = BaseContextProvider(source_id="test")
        session = AgentSession()
        ctx = SessionContext(input_messages=[])
        # Should not raise
        await provider.before_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]

    async def test_after_run_is_noop(self) -> None:
        provider = BaseContextProvider(source_id="test")
        session = AgentSession()
        ctx = SessionContext(input_messages=[])
        await provider.after_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BaseHistoryProvider tests
# ---------------------------------------------------------------------------


class ConcreteHistoryProvider(BaseHistoryProvider):
    """Concrete test implementation."""

    def __init__(self, source_id: str, stored_messages: list[Message] | None = None, **kwargs) -> None:
        super().__init__(source_id, **kwargs)
        self.stored: list[Message] = []
        self._stored_messages = stored_messages or []

    async def get_messages(self, session_id: str | None, **kwargs) -> list[Message]:
        return list(self._stored_messages)

    async def save_messages(self, session_id: str | None, messages: Sequence[Message], **kwargs) -> None:
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
