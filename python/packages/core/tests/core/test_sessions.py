# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import math
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

import msgspec
import pytest
from typing_extensions import Self

from agent_framework import (
    AgentContext,
    AgentSession,
    ChatContext,
    Content,
    ContextProvider,
    ExperimentalFeature,
    FileHistoryProvider,
    FileSessionStore,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    SessionContext,
    SessionStore,
    agent_middleware,
    chat_middleware,
    register_state_type,
)
from agent_framework._sessions import (
    LOCAL_HISTORY_CONVERSATION_ID,
    _adopt_run_persistence_gate_claim,
    _defer_run_persistence,
    _filter_approval_control_messages,
    _offer_run_persistence_gate_claim,
    _run_identity_scope,
    _RunPersistenceGate,
    _suspend_run_persistence_gate,
    is_local_history_conversation_id,
)
from agent_framework._telemetry import FeatureIndex
from agent_framework.exceptions import MiddlewareException

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

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

    def test_extend_messages_origin_session_ids_default_omits_field(self) -> None:
        ctx = SessionContext(input_messages=[])
        msg = Message(role="system", contents=["ctx"])
        ctx.extend_messages("rag", [msg])
        stored = ctx.context_messages["rag"][0]
        # Default (no origin_session_ids passed) preserves the historical attribution shape
        # so observers can distinguish "no origin info" from "explicit cross-session marker."
        assert "origin_session_ids" not in stored.additional_properties["_attribution"]

    def test_extend_messages_origin_session_ids_recorded_on_attribution(self) -> None:
        ctx = SessionContext(session_id="current", input_messages=[])
        msg = Message(role="system", contents=["loaded from a prior session"])
        ctx.extend_messages(
            "memory_provider",
            [msg],
            origin_session_ids=["prior-session-id", "another-session", "prior-session-id"],
        )
        stored = ctx.context_messages["memory_provider"][0]
        assert stored.additional_properties["_attribution"] == {
            "source_id": "memory_provider",
            "origin_session_ids": ["prior-session-id", "another-session"],
        }

    def test_extend_messages_origin_session_ids_with_provider_object(self) -> None:
        class MyMemoryProvider:
            source_id = "memory"

        ctx = SessionContext(session_id="current", input_messages=[])
        msg = Message(role="assistant", contents=["consolidated memory content"])
        ctx.extend_messages(MyMemoryProvider(), [msg], origin_session_ids=["prior"])
        stored = ctx.context_messages["memory"][0]
        assert stored.additional_properties["_attribution"] == {
            "source_id": "memory",
            "source_type": "MyMemoryProvider",
            "origin_session_ids": ["prior"],
        }

    def test_extend_messages_applies_all_origins_to_each_message(self) -> None:
        ctx = SessionContext(session_id="current", input_messages=[])
        messages = [
            Message(role="assistant", contents=["first composed memory"]),
            Message(role="assistant", contents=["second composed memory"]),
        ]

        ctx.extend_messages("memory_provider", messages, origin_session_ids=["session-a", "session-b"])

        stored_messages = ctx.context_messages["memory_provider"]
        assert [message.additional_properties["_attribution"] for message in stored_messages] == [
            {
                "source_id": "memory_provider",
                "origin_session_ids": ["session-a", "session-b"],
            },
            {
                "source_id": "memory_provider",
                "origin_session_ids": ["session-a", "session-b"],
            },
        ]

    def test_extend_messages_adds_origin_to_existing_attribution(self) -> None:
        ctx = SessionContext(session_id="current", input_messages=[])
        msg = Message(
            role="system",
            contents=["loaded from a prior session"],
            additional_properties={
                "_attribution": {
                    "source_id": "custom",
                    "custom_key": "value",
                    "origin_session_ids": ["existing", "prior"],
                }
            },
        )

        ctx.extend_messages("memory_provider", [msg], origin_session_ids=["prior", "new"])

        stored = ctx.context_messages["memory_provider"][0]
        assert stored.additional_properties["_attribution"] == {
            "source_id": "custom",
            "custom_key": "value",
            "origin_session_ids": ["existing", "prior", "new"],
        }
        assert msg.additional_properties["_attribution"] == {
            "source_id": "custom",
            "custom_key": "value",
            "origin_session_ids": ["existing", "prior"],
        }

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
        result = ctx.get_messages(sources=["a"])  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        assert len(result) == 1
        assert result[0].text == "a"

    def test_get_messages_exclude_sources(self) -> None:
        ctx = SessionContext(input_messages=[])
        ctx.extend_messages("a", [Message(role="user", contents=["a"])])
        ctx.extend_messages("b", [Message(role="user", contents=["b"])])
        result = ctx.get_messages(exclude_sources=["a"])  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
        await provider.before_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

    async def test_after_run_is_noop(self) -> None:
        provider = ContextProvider(source_id="test")
        session = AgentSession()
        ctx = SessionContext(input_messages=[])
        await provider.after_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


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


def test_filter_approval_controls_preserves_only_unresolved_occurrences() -> None:
    local_call = Content.from_function_call(call_id="local", name="guarded", arguments="{}")
    local_request = Content.from_function_approval_request(id="local_approval", function_call=local_call)
    hosted_call = Content.from_function_call(
        call_id="hosted",
        name="hosted_tool",
        arguments="{}",
        additional_properties={"server_label": "server"},
    )
    hosted_request = Content.from_function_approval_request(id="hosted_approval", function_call=hosted_call)
    resolved_call = Content.from_function_call(call_id="resolved", name="guarded", arguments="{}")
    resolved_request = Content.from_function_approval_request(id="resolved_approval", function_call=resolved_call)
    resolved_response = resolved_request.to_function_approval_response(approved=True)

    filtered = _filter_approval_control_messages([
        Message(role="assistant", contents=[local_call, local_request]),
        Message(role="assistant", contents=[hosted_request]),
        Message(role="assistant", contents=[resolved_call, resolved_request]),
        Message(role="user", contents=[resolved_response]),
        Message(role="tool", contents=[Content.from_function_result(call_id="resolved", result="done")]),
    ])

    controls = [
        content
        for message in filtered
        for content in message.contents
        if content.type in {"function_approval_request", "function_approval_response"}
    ]
    assert controls == [local_request, hosted_request]
    assert any(
        content.type == "function_result" and content.call_id == "resolved"
        for message in filtered
        for content in message.contents
    )


def test_filter_approval_controls_deduplicates_pending_request_replay() -> None:
    function_call = Content.from_function_call(call_id="call_1", name="guarded", arguments="{}")
    request = Content.from_function_approval_request(id="approval_1", function_call=function_call)
    replayed_request = Content.from_dict(request.to_dict())

    filtered = _filter_approval_control_messages([
        Message(role="assistant", contents=[function_call, request]),
        Message(role="assistant", contents=[replayed_request]),
    ])

    requests = [
        content for message in filtered for content in message.contents if content.type == "function_approval_request"
    ]
    assert requests == [request]


def test_filter_approval_controls_keeps_response_for_pending_placeholder() -> None:
    function_call = Content.from_function_call(call_id="call_pending", name="guarded", arguments="{}")
    request = Content.from_function_approval_request(id="approval_pending", function_call=function_call)
    response = request.to_function_approval_response(approved=True)
    placeholder = Content.from_function_result(
        call_id="call_pending",
        result="[APPROVAL_PENDING] waiting for execution",
    )

    filtered = _filter_approval_control_messages([
        Message(role="assistant", contents=[function_call, request]),
        Message(role="user", contents=[response]),
        Message(role="tool", contents=[placeholder]),
    ])

    controls = [
        content
        for message in filtered
        for content in message.contents
        if content.type in {"function_approval_request", "function_approval_response"}
    ]
    assert controls == [response]
    assert any(placeholder in message.contents for message in filtered)


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
        await provider.before_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
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
        await provider.after_run(agent=None, session=session, context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert len(provider.stored) == 2
        assert provider.stored[0].text == "hello"
        assert provider.stored[1].text == "hi"

    async def test_after_run_stores_coalesced_code_interpreter_chunks(self) -> None:
        from agent_framework import AgentResponse, AgentResponseUpdate, Content

        provider = ConcreteHistoryProvider("mem", store_inputs=False)
        updates = [
            AgentResponseUpdate(
                role="assistant",
                contents=[
                    Content.from_code_interpreter_tool_result(
                        call_id="ci_123",
                        outputs=[],
                    )
                ],
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_code_interpreter_tool_call(
                        call_id="ci_123",
                        inputs=[Content.from_text(text="import")],
                        additional_properties={"sequence_number": 1},
                    )
                ],
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_code_interpreter_tool_call(
                        call_id="ci_123",
                        inputs=[Content.from_text(text=" pandas")],
                        additional_properties={"sequence_number": 2},
                    )
                ],
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_code_interpreter_tool_call(
                        call_id="ci_123",
                        inputs=[Content.from_text(text="import pandas as pd")],
                        additional_properties={"sequence_number": 3},
                    )
                ],
            ),
        ]
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["make a sheet"])])
        ctx._response = AgentResponse.from_updates(updates)

        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

        assert len(provider.stored) == 1
        stored_contents = provider.stored[0].contents
        calls = [content for content in stored_contents if content.type == "code_interpreter_tool_call"]
        results = [content for content in stored_contents if content.type == "code_interpreter_tool_result"]
        assert len(calls) == 1
        assert len(results) == 1
        assert calls[0].inputs is not None
        assert len(calls[0].inputs) == 1
        assert calls[0].inputs[0].text == "import pandas as pd"

    async def test_after_run_skips_inputs_when_disabled(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("mem", store_inputs=False)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert len(provider.stored) == 1
        assert provider.stored[0].text == "hi"

    async def test_after_run_skips_responses_when_disabled(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("mem", store_outputs=False)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert len(provider.stored) == 1
        assert provider.stored[0].text == "hello"

    async def test_after_run_stores_context_messages(self) -> None:
        from agent_framework import AgentResponse

        provider = ConcreteHistoryProvider("audit", load_messages=False, store_context_messages=True)
        ctx = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["hello"])])
        ctx.extend_messages("rag", [Message(role="system", contents=["context"])])
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hi"])])
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
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
        await provider.after_run(agent=None, session=AgentSession(), context=ctx, state={})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
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

    def test_service_session_id_accepts_structured_mapping(self) -> None:
        service_session_id = {"context_id": "ctx-123", "task_id": "task-456", "task_state": "working"}
        session = AgentSession(service_session_id=service_session_id)
        assert session.service_session_id == service_session_id

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

    def test_roundtrip_with_structured_service_session_id(self) -> None:
        service_session_id = {"context_id": "ctx-123", "task_id": "task-456", "task_state": "working"}
        session = AgentSession(session_id="rt-2", service_session_id=service_session_id)
        json_str = json.dumps(session.to_dict())
        restored = AgentSession.from_dict(json.loads(json_str))
        assert restored.session_id == "rt-2"
        assert restored.service_session_id == service_session_id

    def test_from_dict_missing_state(self) -> None:
        data = {"session_id": "s1"}
        session = AgentSession.from_dict(data)
        assert session.state == {}


class _RegisteredSessionState:
    def __init__(self, value: str) -> None:
        self.value = value

    @classmethod
    def _get_type_identifier(cls) -> str:
        return "registered_session_state"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self._get_type_identifier(), "value": self.value}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "_RegisteredSessionState":
        return cls(value=str(value["value"]))


register_state_type(_RegisteredSessionState)


class TestStateTypeRegistry:
    def test_same_registration_is_idempotent(self) -> None:
        register_state_type(_RegisteredSessionState)

    def test_type_constant_is_used_as_default_identifier(self) -> None:
        class TypeConstantState:
            TYPE = "type_constant_state_test"

            def __init__(self, value: str) -> None:
                self.value = value

            def to_dict(self) -> dict[str, Any]:
                return {"value": self.value}

            @classmethod
            def from_dict(cls, value: dict[str, Any]) -> Self:
                return cls(str(value["value"]))

        register_state_type(TypeConstantState)
        session = AgentSession(session_id="type-constant")
        session.state["value"] = TypeConstantState("ok")

        restored = AgentSession.from_dict(session.to_dict())

        assert isinstance(restored.state["value"], TypeConstantState)
        assert restored.state["value"].value == "ok"

    def test_custom_encoder_and_decoder_support_plain_classes(self) -> None:
        @dataclass
        class CallbackState:
            value: str

        def encode(value: CallbackState) -> dict[str, Any]:
            return {"value": value.value}

        def decode(value: Mapping[str, Any]) -> CallbackState:
            return CallbackState(str(value["value"]))

        register_state_type(
            CallbackState,
            type_id="callback_state_test",
            encoder=encode,
            decoder=decode,
        )
        session = AgentSession(session_id="callback")
        session.state["value"] = CallbackState("ok")

        restored = AgentSession.from_dict(session.to_dict())

        assert isinstance(restored.state["value"], CallbackState)
        assert restored.state["value"].value == "ok"

    def test_explicit_pydantic_registration_round_trips(self) -> None:
        from pydantic import BaseModel

        class PydanticState(BaseModel):
            value: str

        register_state_type(PydanticState, type_id="pydantic_state_test")
        session = AgentSession(session_id="pydantic")
        session.state["value"] = PydanticState(value="ok")

        restored = AgentSession.from_dict(session.to_dict())

        assert isinstance(restored.state["value"], PydanticState)
        assert restored.state["value"].value == "ok"

    def test_conflicting_type_identifier_is_rejected(self) -> None:
        class FirstState:
            def to_dict(self) -> dict[str, Any]:
                return {}

            @classmethod
            def from_dict(cls, value: dict[str, Any]) -> Self:
                del value
                return cls()

        class SecondState(FirstState):
            pass

        register_state_type(FirstState, type_id="collision_state_test")

        with pytest.raises(ValueError, match="already registered"):
            register_state_type(SecondState, type_id="collision_state_test")

    def test_unregistered_to_dict_object_preserves_legacy_serialization(self) -> None:
        class UnregisteredState:
            def to_dict(self) -> dict[str, Any]:
                return {"type": "unregistered_state", "value": "legacy"}

        session = AgentSession(session_id="unregistered")
        session.state["nested"] = [{"value": UnregisteredState()}]

        assert session.to_dict()["state"]["nested"] == [{"value": {"type": "unregistered_state", "value": "legacy"}}]

    def test_unregistered_container_subclass_uses_to_dict(self) -> None:
        class MappingState(dict[str, Any]):
            def to_dict(self) -> dict[str, Any]:
                return {"serialized": True}

        session = AgentSession(session_id="mapping")
        session.state["value"] = MappingState(raw=True)

        assert session.to_dict()["state"]["value"] == {"serialized": True}

    def test_unregistered_pydantic_model_preserves_legacy_round_trip(self) -> None:
        from pydantic import BaseModel

        class AutoRegisteredPydanticState(BaseModel):
            value: str

        session = AgentSession(session_id="pydantic")
        session.state["value"] = AutoRegisteredPydanticState(value="legacy")

        with pytest.warns(DeprecationWarning, match="Cold-start deserialization"):
            serialized = session.to_dict()
        restored = AgentSession.from_dict(serialized)

        assert isinstance(restored.state["value"], AutoRegisteredPydanticState)
        assert restored.state["value"].value == "legacy"

    def test_unknown_type_tag_remains_a_raw_dict(self) -> None:
        session = AgentSession.from_dict({
            "session_id": "unknown",
            "state": {"value": {"type": "future_state_type", "nested": {"count": 1}}},
        })

        assert session.state["value"] == {
            "type": "future_state_type",
            "nested": {"count": 1},
        }

    def test_registered_child_tag_does_not_hijack_message_payload(self) -> None:
        @dataclass
        class TextState:
            value: str

        register_state_type(
            TextState,
            type_id="text",
            encoder=lambda value: {"value": value.value},
            decoder=lambda value: TextState(str(value["value"])),
        )
        session = AgentSession(session_id="message")
        session.state["message"] = Message(role="user", contents=["hello"])

        restored = AgentSession.from_dict(session.to_dict())

        assert isinstance(restored.state["message"], Message)
        assert restored.state["message"].text == "hello"

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_float_preserves_legacy_dictionary_serialization(self, value: float) -> None:
        session = AgentSession(session_id="float")
        session.state["value"] = value

        serialized = session.to_dict()

        restored = serialized["state"]["value"]
        if math.isnan(value):
            assert math.isnan(restored)
        else:
            assert restored == value


class TestSessionStore:
    def test_is_marked_experimental(self) -> None:
        for store_type in (SessionStore, FileSessionStore):
            assert store_type.__feature_stage__ == "experimental"  # type: ignore[attr-defined, union-attr]  # ty: ignore[unresolved-attribute]
            assert store_type.__feature_id__ == ExperimentalFeature.SESSION_STORE.value  # type: ignore[attr-defined, union-attr]  # ty: ignore[unresolved-attribute]
            assert store_type.__doc__ is not None
            assert ".. warning:: Experimental" in store_type.__doc__

    async def test_get_returns_none_for_missing_id(self) -> None:
        store = SessionStore()

        assert await store.get("session-1") is None

    async def test_set_then_get_returns_independent_copy(self) -> None:
        store = SessionStore()
        session = AgentSession(session_id="session-1")
        session.state["nested"] = {"values": ["original"]}

        await store.set("session-1", session)

        stored = await store.get("session-1")
        assert stored is not None
        assert stored is not session
        stored.state["nested"]["values"].append("changed")

        reread = await store.get("session-1")
        assert reread is not None
        assert reread.state["nested"]["values"] == ["original"]

    async def test_set_stores_independent_snapshot(self) -> None:
        store = SessionStore()
        session = AgentSession(session_id="session-1")
        session.state["nested"] = {"values": ["original"]}

        await store.set("session-1", session)
        session.state["nested"]["values"].append("changed")

        stored = await store.get("session-1")
        assert stored is not None
        assert stored.state["nested"]["values"] == ["original"]

    async def test_set_replaces_existing_entry(self) -> None:
        store = SessionStore()
        await store.set("session-1", AgentSession(session_id="first"))
        await store.set("session-1", AgentSession(session_id="second"))

        stored = await store.get("session-1")

        assert stored is not None
        assert stored.session_id == "second"

    async def test_delete_forgets_session(self) -> None:
        store = SessionStore()
        await store.set("session-1", AgentSession(session_id="session-1"))

        await store.delete("session-1")

        assert await store.get("session-1") is None

    @pytest.mark.parametrize("session_id", ["two words", "tenant/user", "session.id", "café"])
    async def test_accepts_opaque_non_empty_session_id(self, session_id: str) -> None:
        store = SessionStore()
        session = AgentSession()

        await store.set(session_id, session)
        assert await store.get(session_id) is not None
        await store.delete(session_id)
        assert await store.get(session_id) is None

    async def test_empty_session_id_raises(self) -> None:
        store = SessionStore()
        session = AgentSession()

        with pytest.raises(ValueError, match="session_id"):
            await store.get("")
        with pytest.raises(ValueError, match="session_id"):
            await store.set("", session)
        with pytest.raises(ValueError, match="session_id"):
            await store.delete("")

    @pytest.mark.parametrize("operation", ["get", "set", "delete"])
    async def test_operations_mark_feature_usage(self, operation: str) -> None:
        store = SessionStore()

        with patch("agent_framework._sessions.mark_feature_used") as mark_feature_used_mock:
            if operation == "get":
                await store.get("session-1")
            elif operation == "set":
                await store.set("session-1", AgentSession())
            else:
                await store.delete("session-1")

        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_SESSION_STORE)


class TestFileSessionStore:
    @pytest.mark.parametrize("operation", ["get", "set", "delete"])
    async def test_operations_mark_feature_usage(self, tmp_path: Path, operation: str) -> None:
        store = FileSessionStore(tmp_path)

        with patch("agent_framework._sessions.mark_feature_used") as mark_feature_used_mock:
            if operation == "get":
                await store.get("session-1")
            elif operation == "set":
                await store.set("session-1", AgentSession())
            else:
                await store.delete("session-1")

        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_SESSION_STORE)

    async def test_round_trips_session_across_store_instances(self, tmp_path: Path) -> None:
        session = AgentSession(session_id="framework-session", service_session_id={"response_id": "resp-1"})
        session.state["nested"] = {
            "messages": [Message(role="user", contents=["hello"])],
            "custom": [_RegisteredSessionState("persisted")],
        }

        await FileSessionStore(tmp_path).set("tenant_user-conversation", session)
        restored = await FileSessionStore(tmp_path).get("tenant_user-conversation")

        assert restored is not None
        assert restored is not session
        assert restored.session_id == "framework-session"
        assert restored.service_session_id == {"response_id": "resp-1"}
        assert isinstance(restored.state["nested"]["messages"][0], Message)
        assert restored.state["nested"]["messages"][0].text == "hello"
        assert isinstance(restored.state["nested"]["custom"][0], _RegisteredSessionState)
        assert restored.state["nested"]["custom"][0].value == "persisted"

        files = await asyncio.to_thread(lambda: list(tmp_path.iterdir()))
        assert len(files) == 1
        assert files[0].parent == tmp_path
        assert files[0].suffix == ".json"
        assert json.loads(files[0].read_bytes())["version"] == "1.0"

    async def test_round_trips_binary_messagepack_session(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path, serialization_format="msgpack")
        session = AgentSession(session_id="binary-session")
        session.state["nested"] = [_RegisteredSessionState("persisted")]

        await store.set("binary-session", session)
        restored = await store.get("binary-session")

        assert restored is not None
        assert isinstance(restored.state["nested"][0], _RegisteredSessionState)
        assert restored.state["nested"][0].value == "persisted"
        files = await asyncio.to_thread(lambda: list(tmp_path.iterdir()))
        assert len(files) == 1
        assert files[0].suffix == ".msgpack"
        serialized = await asyncio.to_thread(files[0].read_bytes)
        assert not serialized.startswith(b"{")
        assert msgspec.msgpack.decode(serialized)["version"] == "1.0"

    async def test_rejects_custom_agent_session_subclass(self, tmp_path: Path) -> None:
        class CustomAgentSession(AgentSession):
            pass

        store = FileSessionStore(tmp_path)

        with pytest.raises(TypeError, match="AgentSession instances only"):
            await store.set("custom-session", CustomAgentSession(session_id="custom-session"))

    async def test_unregistered_to_dict_state_preserves_legacy_durable_serialization(self, tmp_path: Path) -> None:
        class UnregisteredState:
            def to_dict(self) -> dict[str, Any]:
                return {"type": "unregistered_state", "value": "legacy"}

        session = AgentSession(session_id="unregistered")
        session.state["nested"] = [{"value": UnregisteredState()}]

        store = FileSessionStore(tmp_path)
        await store.set("unregistered", session)
        restored = await store.get("unregistered")

        assert restored is not None
        assert restored.state["nested"] == [{"value": {"type": "unregistered_state", "value": "legacy"}}]

    async def test_unregistered_pydantic_state_warns_for_durable_serialization(self, tmp_path: Path) -> None:
        from pydantic import BaseModel

        class DurableAutoRegisteredPydanticState(BaseModel):
            value: str

        session = AgentSession(session_id="pydantic")
        session.state["value"] = DurableAutoRegisteredPydanticState(value="legacy")

        with pytest.warns(DeprecationWarning, match="Cold-start deserialization"):
            await FileSessionStore(tmp_path).set("pydantic", session)

    async def test_unsupported_state_object_is_rejected_for_durable_storage(self, tmp_path: Path) -> None:
        class UnsupportedState:
            pass

        session = AgentSession(session_id="unsupported")
        session.state["nested"] = [{"value": UnsupportedState()}]

        with (
            pytest.warns(RuntimeWarning, match="leaving it unchanged"),
            pytest.raises(TypeError, match=r"state\.nested\[0\]\.value.*UnsupportedState"),
        ):
            await FileSessionStore(tmp_path).set("unsupported", session)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    async def test_non_finite_state_is_rejected_for_durable_storage(self, tmp_path: Path, value: float) -> None:
        session = AgentSession(session_id="float")
        session.state["value"] = value

        with pytest.raises(ValueError, match="finite float"):
            await FileSessionStore(tmp_path).set("float", session)

    async def test_missing_and_deleted_sessions_return_none(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        assert await store.get("session-1") is None

        await store.set("session-1", AgentSession(session_id="session-1"))
        await store.delete("session-1")

        assert await store.get("session-1") is None

    async def test_set_replaces_atomically_without_leaving_temp_files(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        await store.set("session-1", AgentSession(session_id="first"))
        await store.set("session-1", AgentSession(session_id="second"))

        stored = await store.get("session-1")

        assert stored is not None
        assert stored.session_id == "second"
        temp_files = await asyncio.to_thread(lambda: [*tmp_path.glob("*.tmp"), *tmp_path.glob(".*.tmp")])
        assert not temp_files

    async def test_corrupt_session_file_is_quarantined_and_retry_returns_none(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        await store.set("session-1", AgentSession(session_id="session-1"))
        session_file = await asyncio.to_thread(lambda: next(tmp_path.iterdir()))
        await asyncio.to_thread(session_file.write_text, "{not-json", encoding="utf-8")

        with pytest.raises(ValueError, match="quarantined.*retry"):
            await store.get("session-1")

        assert not session_file.exists()
        quarantined_files = await asyncio.to_thread(lambda: list(tmp_path.glob(".*.corrupt")))
        assert len(quarantined_files) == 1
        assert await store.get("session-1") is None

    async def test_invalid_registered_payload_preserves_snapshot(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        session_file = store._session_file_path("session-1")
        session_file.write_text(
            json.dumps({
                "type": "session",
                "version": "1.0",
                "session_id": "session-1",
                "service_session_id": None,
                "state": {"value": {"type": "registered_session_state"}},
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Failed to restore session state"):
            await store.get("session-1")

        assert session_file.exists()
        assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.corrupt")))

    async def test_registered_decoder_attribute_error_preserves_snapshot(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        session_file = store._session_file_path("session-1")
        session_file.write_text(
            json.dumps({
                "type": "session",
                "version": "1.0",
                "session_id": "session-1",
                "service_session_id": None,
                "state": {"value": {"type": "message", "role": "user", "contents": [123]}},
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Failed to restore session state"):
            await store.get("session-1")

        assert session_file.exists()
        assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.corrupt")))

    async def test_unsupported_snapshot_version_preserves_snapshot(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        session_file = store._session_file_path("session-1")
        session_file.write_text(
            json.dumps({
                "type": "session",
                "version": "1.1",
                "session_id": "session-1",
                "service_session_id": None,
                "state": {},
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Unsupported session snapshot version '1.1'"):
            await store.get("session-1")

        assert session_file.exists()
        assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.corrupt")))

    async def test_invalid_snapshot_schema_preserves_snapshot(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        session_file = store._session_file_path("session-1")
        session_file.write_text(
            json.dumps({
                "type": "session",
                "version": "1.0",
                "session_id": 123,
                "service_session_id": None,
                "state": {},
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="invalid schema"):
            await store.get("session-1")

        assert session_file.exists()
        assert not await asyncio.to_thread(lambda: list(tmp_path.glob(".*.corrupt")))

    async def test_corrupt_quarantine_does_not_remove_concurrent_replacement(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reader = FileSessionStore(tmp_path)
        writer = FileSessionStore(tmp_path)
        await reader.set("session-1", AgentSession(session_id="old"))
        session_file = reader._session_file_path("session-1")
        await asyncio.to_thread(session_file.write_text, "{not-json", encoding="utf-8")
        quarantine_started = threading.Event()
        release_quarantine = threading.Event()
        original_quarantine = FileSessionStore._quarantine_corrupt_snapshot

        def blocking_quarantine(file_path: Path, serialized: bytes) -> Path | None:
            quarantine_started.set()
            if not release_quarantine.wait(timeout=5):
                raise TimeoutError("Timed out waiting to release corrupt snapshot quarantine.")
            return original_quarantine(file_path, serialized)

        monkeypatch.setattr(
            FileSessionStore,
            "_quarantine_corrupt_snapshot",
            staticmethod(blocking_quarantine),
        )
        read_task = asyncio.create_task(reader.get("session-1"))
        assert await asyncio.to_thread(quarantine_started.wait, 5)
        write_task = asyncio.create_task(writer.set("session-1", AgentSession(session_id="replacement")))
        await asyncio.sleep(0)
        release_quarantine.set()

        with pytest.raises(ValueError, match="quarantined"):
            await read_task
        await write_task

        restored = await reader.get("session-1")
        assert restored is not None
        assert restored.session_id == "replacement"

    @pytest.mark.parametrize("session_id", ["", "x" * (FileSessionStore.MAX_SESSION_ID_LENGTH + 1)])
    async def test_invalid_session_id_raises(self, tmp_path: Path, session_id: str) -> None:
        store = FileSessionStore(tmp_path)
        session = AgentSession()

        with pytest.raises(ValueError, match="session_id"):
            await store.get(session_id)
        with pytest.raises(ValueError, match="session_id"):
            await store.set(session_id, session)
        with pytest.raises(ValueError, match="session_id"):
            await store.delete(session_id)

    @pytest.mark.parametrize(
        ("session_id", "is_encoded"),
        [
            ("two words", True),
            ("tenant/user", True),
            ("session.id", False),
            ("café", True),
            ("telegram:123:456", True),
            ("CON", True),
            ("x" * 128, False),
        ],
    )
    async def test_opaque_session_id_round_trips_through_safe_filename(
        self,
        tmp_path: Path,
        session_id: str,
        is_encoded: bool,
    ) -> None:
        store = FileSessionStore(tmp_path)
        session = AgentSession(session_id="framework-session")

        await store.set(session_id, session)
        restored = await store.get(session_id)

        assert restored is not None
        assert restored.session_id == "framework-session"
        session_file = store._session_file_path(session_id)
        assert session_file.is_file()
        assert session_file.parent == tmp_path
        assert session_file.name.startswith("~session-") is is_encoded

    async def test_rejects_symlinked_session_file_within_storage_root(self, tmp_path: Path) -> None:
        store = FileSessionStore(tmp_path)
        target_file = tmp_path / "other-session.json"
        session_file = tmp_path / "session-1.json"
        await asyncio.to_thread(target_file.write_text, "{}", encoding="utf-8")
        try:
            await asyncio.to_thread(session_file.symlink_to, target_file)
        except OSError as exc:
            pytest.skip(f"Symlinks are not available: {exc}")

        with pytest.raises(ValueError, match="escaped storage directory"):
            await store.get("session-1")

    @pytest.mark.parametrize("session_id", ["NUL.txt", "COM¹", "LPT².log"])
    async def test_reserved_windows_filename_is_encoded(self, tmp_path: Path, session_id: str) -> None:
        provider = FileHistoryProvider(tmp_path)

        await provider.save_messages(session_id, [Message(role="user", contents=["hello"])])

        session_file = provider._session_file_path(session_id)
        assert session_file.name.startswith("~session-")
        assert session_file.is_file()


# ---------------------------------------------------------------------------
# InMemoryHistoryProvider tests
# ---------------------------------------------------------------------------


class TestInMemoryHistoryProvider:
    async def test_empty_state_returns_no_messages(self) -> None:
        provider = InMemoryHistoryProvider()
        session = AgentSession()
        ctx = SessionContext(session_id="s1", input_messages=[])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=ctx1,
            state=session.state.setdefault(provider.source_id, {}),
        )
        ctx1._response = AgentResponse(messages=[resp_msg])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=ctx1,
            state=session.state.setdefault(provider.source_id, {}),
        )

        # Second run: should load previous messages
        ctx2 = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["again"])])
        await provider.before_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["reply"])])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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

    async def test_save_messages_deduplicates_identical_messages(self) -> None:
        """Test that save_messages does not re-append messages already in the store."""
        provider = InMemoryHistoryProvider()
        state: dict[str, Any] = {}

        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])

        await provider.save_messages("s1", [msg1, msg2], state=state)
        assert len(state["messages"]) == 2

        await provider.save_messages("s1", [msg1, msg2], state=state)
        assert len(state["messages"]) == 2

    async def test_save_messages_only_appends_new_messages(self) -> None:
        """Test that save_messages filters out old messages and only appends new ones"""
        provider = InMemoryHistoryProvider()
        state: dict[str, Any] = {}

        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])
        msg3 = Message(role="user", contents=["how are you?"])

        await provider.save_messages("s1", [msg1, msg2], state=state)
        assert len(state["messages"]) == 2

        await provider.save_messages("s1", [msg1, msg2, msg3], state=state)
        assert len(state["messages"]) == 3
        assert state["messages"][2].text == "how are you?"

    async def test_save_messages_different_roles_same_text_not_deduplicated(self) -> None:
        """Test that messages with the same text but different roles are kept separate."""
        provider = InMemoryHistoryProvider()
        state: dict[str, Any] = {}

        msg1 = Message(role="user", contents=["ping"])
        msg2 = Message(role="assistant", contents=["ping"])

        await provider.save_messages("s1", [msg1, msg2], state=state)
        assert len(state["messages"]) == 2

    async def test_save_messages_deduplication_with_none_state(self) -> None:
        """Test that save_messages with None state does not raise."""
        provider = InMemoryHistoryProvider()
        msg = Message(role="user", contents=["hello"])
        await provider.save_messages("s1", [msg], state=None)

    async def test_full_loop_does_not_grow_superlinearly(self) -> None:
        """Regression test: a multi-round looped run must not re-persist the whole
        conversation on every round."""
        from agent_framework import AgentResponse

        provider = InMemoryHistoryProvider()
        session = AgentSession()
        provider_state = session.state.setdefault(provider.source_id, {})
        ctx1 = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["turn 1"])])

        await provider.before_run(
            agent=cast("SupportsAgentRun", None),
            session=session,
            context=ctx1,
            state=provider_state,
        )
        ctx1._response = AgentResponse(messages=[Message(role="assistant", contents=["reply 1"])])
        await provider.after_run(
            agent=cast("SupportsAgentRun", None),
            session=session,
            context=ctx1,
            state=provider_state,
        )

        ctx2 = SessionContext(session_id="s1", input_messages=[Message(role="user", contents=["turn 2"])])
        await provider.before_run(
            agent=cast("SupportsAgentRun", None),
            session=session,
            context=ctx2,
            state=provider_state,
        )
        ctx2._response = AgentResponse(messages=[Message(role="assistant", contents=["reply 2"])])
        await provider.after_run(
            agent=cast("SupportsAgentRun", None),
            session=session,
            context=ctx2,
            state=provider_state,
        )

        stored = session.state[provider.source_id]["messages"]
        assert len(stored) == 4
        texts = [m.text for m in stored]
        assert texts == ["turn 1", "reply 1", "turn 2", "reply 2"]

    async def test_save_messages_preserves_duplicate_content(self) -> None:
        """Two separate user 'yes' replies in the same batch must both be persisted."""
        provider = InMemoryHistoryProvider()
        state: dict[str, Any] = {}

        yes_1 = Message(role="user", contents=["yes"])
        yes_2 = Message(role="user", contents=["yes"])

        await provider.save_messages("s1", [yes_1, yes_2], state=state)

        assert len(state["messages"]) == 2
        assert state["messages"][0].text == "yes"
        assert state["messages"][1].text == "yes"

    async def test_save_messages_handles_replayed_transcript_with_duplicates(self) -> None:
        provider = InMemoryHistoryProvider()
        state: dict[str, Any] = {}

        msg_b = Message(role="user", contents=["B"])
        await provider.save_messages("s1", [msg_b], state=state)
        assert len(state["messages"]) == 1

        msg_a = Message(role="user", contents=["A"])
        msg_c = Message(role="user", contents=["C"])
        msg_b2 = Message(role="user", contents=["B"])
        msg_d = Message(role="user", contents=["D"])

        await provider.save_messages("s1", [msg_a, msg_b, msg_c, msg_b2, msg_d], state=state)

        assert len(state["messages"]) == 4
        texts = [m.text for m in state["messages"]]
        assert texts == ["B", "C", "B", "D"]


class TestFileHistoryProvider:
    def test_is_marked_experimental(self) -> None:
        assert FileHistoryProvider.__feature_stage__ == "experimental"  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        assert FileHistoryProvider.__feature_id__ == ExperimentalFeature.FILE_HISTORY.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        assert FileHistoryProvider.__doc__ is not None
        assert ".. warning:: Experimental" in FileHistoryProvider.__doc__

    def test_uses_msgspec_json_by_default(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)

        serialized = provider.dumps({"text": "héllo"})

        assert isinstance(serialized, bytes)
        assert provider.loads(serialized) == {"text": "héllo"}

    async def test_stores_and_loads_length_prefixed_msgpack(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path, serialization_format="msgpack")
        messages = [
            Message(role="user", contents=["hello"]),
            Message(role="assistant", contents=["hi there"]),
        ]

        await provider.save_messages("binary-history", messages)
        loaded = await provider.get_messages("binary-history")

        assert [message.text for message in loaded] == ["hello", "hi there"]
        session_file = provider._session_file_path("binary-history")
        assert session_file.suffix == ".msgpack"
        raw = await asyncio.to_thread(session_file.read_bytes)
        first_record_length = int.from_bytes(raw[:4], "big")
        assert first_record_length > 0
        assert raw[4 : 4 + first_record_length] == msgspec.msgpack.encode(messages[0].to_dict())

    def test_msgpack_rejects_custom_json_codecs(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Custom dumps and loads"):
            FileHistoryProvider(tmp_path, serialization_format="msgpack", dumps=json.dumps)

    def test_custom_json_codecs_are_deprecated(self, tmp_path: Path) -> None:
        with pytest.warns(DeprecationWarning, match=r"dumps.*loads.*deprecated"):
            FileHistoryProvider(tmp_path / "dumps", dumps=json.dumps)
        with pytest.warns(DeprecationWarning, match=r"dumps.*loads.*deprecated"):
            FileHistoryProvider(tmp_path / "loads", loads=json.loads)

    async def test_stores_and_loads_messages(self, tmp_path: Path) -> None:
        from agent_framework import AgentResponse

        provider = FileHistoryProvider(tmp_path)
        session = AgentSession(session_id="s1")

        input_message = Message(role="user", contents=["hello"])
        response_message = Message(role="assistant", contents=["hi there"])
        first_context = SessionContext(session_id=session.session_id, input_messages=[input_message])

        await provider.before_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=first_context,
            state={},
        )
        first_context._response = AgentResponse(messages=[response_message])
        await provider.after_run(  # type: ignore[arg-type]
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
            agent=None,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            session=session,
            context=second_context,
            state={},
        )
        loaded = second_context.context_messages.get(provider.source_id, [])
        assert len(loaded) == 2
        assert loaded[0].text == "hello"
        assert loaded[1].text == "hi there"

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    async def test_preserves_non_finite_json_values(self, tmp_path: Path, value: float) -> None:
        provider = FileHistoryProvider(tmp_path)
        message = Message(role="user", contents=["hello"], additional_properties={"value": value})

        await provider.save_messages("non-finite", [message])
        loaded = await provider.get_messages("non-finite")

        restored = loaded[0].additional_properties["value"]
        if math.isnan(value):
            assert math.isnan(restored)
        else:
            assert restored == value

    async def test_reads_existing_stdlib_non_finite_json(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path)
        message = Message(role="user", contents=["hello"], additional_properties={"value": float("inf")})
        session_file = provider._session_file_path("legacy")
        await asyncio.to_thread(session_file.write_text, f"{json.dumps(message.to_dict())}\n", encoding="utf-8")

        loaded = await provider.get_messages("legacy")

        assert loaded[0].additional_properties["value"] == float("inf")

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

        with pytest.warns(DeprecationWarning, match=r"dumps.*loads.*deprecated"):
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

    async def test_truncated_msgpack_record_raises(self, tmp_path: Path) -> None:
        provider = FileHistoryProvider(tmp_path, serialization_format="msgpack")
        session_file = provider._session_file_path("broken")
        await asyncio.to_thread(session_file.write_bytes, (10).to_bytes(4, "big") + b"short")

        with pytest.raises(ValueError, match="record 1.*truncated"):
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

        with pytest.warns(DeprecationWarning, match=r"dumps.*loads.*deprecated"):
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

            def __enter__(self) -> "_TrackingFile":  # type: ignore[name-defined]
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

    async def test_save_messages_deduplicates_identical_messages(self, tmp_path: Path) -> None:
        """Test that FileHistoryProvider does not re-append already persisted messages."""
        provider = FileHistoryProvider(tmp_path)

        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])

        await provider.save_messages("s1", [msg1, msg2])
        loaded = await provider.get_messages("s1")
        assert len(loaded) == 2

        await provider.save_messages("s1", [msg1, msg2])
        loaded = await provider.get_messages("s1")
        assert len(loaded) == 2

    async def test_save_messages_only_appends_new_messages(self, tmp_path: Path) -> None:
        """Test that FileHistoryProvider filters out old messages and only appends new ones"""
        provider = FileHistoryProvider(tmp_path)

        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])
        msg3 = Message(role="user", contents=["how are you?"])

        await provider.save_messages("s1", [msg1, msg2])
        loaded = await provider.get_messages("s1")
        assert len(loaded) == 2

        await provider.save_messages("s1", [msg1, msg2, msg3])
        loaded = await provider.get_messages("s1")
        assert len(loaded) == 3
        assert loaded[2].text == "how are you?"

    async def test_save_messages_different_roles_same_text_not_deduplicated(self, tmp_path: Path) -> None:
        """Test that messages with the same text but different roles are kept separate."""
        provider = FileHistoryProvider(tmp_path)

        msg1 = Message(role="user", contents=["ping"])
        msg2 = Message(role="assistant", contents=["ping"])

        await provider.save_messages("s1", [msg1, msg2])
        loaded = await provider.get_messages("s1")
        assert len(loaded) == 2

    async def test_deduplication_file_integrity(self, tmp_path: Path) -> None:
        """Test that deduplication writes the correct number of lines to the JSONL file."""
        provider = FileHistoryProvider(tmp_path)

        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])
        msg3 = Message(role="user", contents=["follow-up"])

        await provider.save_messages("s1", [msg1, msg2])

        session_file = provider._session_file_path("s1")
        raw_lines = (await asyncio.to_thread(session_file.read_text, encoding="utf-8")).splitlines()
        assert len(raw_lines) == 2

        await provider.save_messages("s1", [msg1, msg2, msg3])
        raw_lines = (await asyncio.to_thread(session_file.read_text, encoding="utf-8")).splitlines()
        assert len(raw_lines) == 3

    async def test_save_messages_preserves_duplicate_content(self, tmp_path: Path) -> None:
        """Test that two identical user turns in the same batch are both persisted."""
        provider = FileHistoryProvider(tmp_path)

        yes_1 = Message(role="user", contents=["yes"])
        yes_2 = Message(role="user", contents=["yes"])

        await provider.save_messages("s1", [yes_1, yes_2])
        loaded = await provider.get_messages("s1")

        assert len(loaded) == 2
        assert loaded[0].text == "yes"
        assert loaded[1].text == "yes"


# ---------------------------------------------------------------------------
# Run-persistence gate tests
# ---------------------------------------------------------------------------


class TestRunPersistenceGate:
    """The deferral gate owned by _sessions (used by egress-enforcement middleware)."""

    @staticmethod
    def _recording_persist(executed: list[str], label: str) -> Callable[[], Awaitable[None]]:
        async def persist() -> None:
            executed.append(label)

        return persist

    async def test_gate_defers_and_flush_runs_in_order(self) -> None:
        executed: list[str] = []
        gate = _RunPersistenceGate()
        with gate:
            assert _defer_run_persistence(self._recording_persist(executed, "a")) is True
            assert _defer_run_persistence(self._recording_persist(executed, "b")) is True
            assert executed == []
        await gate.flush()
        assert executed == ["a", "b"]
        # Outside any gate scope, callers persist inline.
        assert _defer_run_persistence(self._recording_persist(executed, "c")) is False

    async def test_flush_inside_the_scope_raises(self) -> None:
        # Reset-before-drain by construction: draining while the gate is active would
        # re-defer re-entrant persistence into a list nobody drains.
        gate = _RunPersistenceGate()
        with gate, pytest.raises(RuntimeError, match="still active"):
            await gate.flush()
        await gate.flush()  # after exit the same flush is legal

    def test_reentering_an_active_gate_raises(self) -> None:
        gate = _RunPersistenceGate()
        with gate, pytest.raises(RuntimeError, match="not re-entrant"), gate:
            pass

    async def test_gate_can_be_reused_sequentially(self) -> None:
        # The streaming chat gate enters once around call_next and once around stream
        # consumption; both sections collect into the same handle.
        executed: list[str] = []
        gate = _RunPersistenceGate()
        with gate:
            _defer_run_persistence(self._recording_persist(executed, "first"))
        with gate:
            _defer_run_persistence(self._recording_persist(executed, "second"))
        await gate.flush()
        assert executed == ["first", "second"]

    async def test_drop_discards_deferred_persistence(self) -> None:
        executed: list[str] = []
        gate = _RunPersistenceGate()
        with gate:
            _defer_run_persistence(self._recording_persist(executed, "denied"))
        gate.drop()
        await gate.flush()
        assert executed == []

    async def test_nested_gates_collect_independently(self) -> None:
        executed: list[str] = []
        outer = _RunPersistenceGate()
        inner = _RunPersistenceGate()
        with outer:
            _defer_run_persistence(self._recording_persist(executed, "outer-1"))
            with inner:
                _defer_run_persistence(self._recording_persist(executed, "inner"))
            _defer_run_persistence(self._recording_persist(executed, "outer-2"))
        await inner.flush()
        assert executed == ["inner"]
        await outer.flush()
        assert executed == ["inner", "outer-1", "outer-2"]

    async def test_suspension_makes_nested_persistence_inline(self) -> None:
        # The function-invocation layer suspends the gate around tool invocations so
        # nested agent runs persist inline instead of deferring into the outer gate.
        executed: list[str] = []
        gate = _RunPersistenceGate()
        with gate:
            with _suspend_run_persistence_gate():
                assert _defer_run_persistence(self._recording_persist(executed, "nested")) is False
            assert _defer_run_persistence(self._recording_persist(executed, "own")) is True
        await gate.flush()
        assert executed == ["own"]

    async def test_reentrant_persist_during_flush_runs_inline(self) -> None:
        # Mirrors _run_after_providers: the deferred callable re-checks the gate when
        # executed. Because flush only runs after the scope was exited, the re-entrant
        # check finds no gate and the persist runs inline instead of re-deferring.
        executed: list[str] = []
        gate = _RunPersistenceGate()

        async def reentrant() -> None:
            if _defer_run_persistence(reentrant):
                return
            executed.append("ran")

        with gate:
            assert _defer_run_persistence(reentrant) is True
        await gate.flush()
        assert executed == ["ran"]

    async def test_bound_gate_defers_only_its_owner_run(self) -> None:
        executed: list[str] = []
        gate = _RunPersistenceGate()
        owner = object()
        other = object()
        gate.bind_owner(owner)
        with gate:
            with _run_identity_scope(owner):
                assert _defer_run_persistence(self._recording_persist(executed, "own")) is True
            with _run_identity_scope(other):
                # A different (nested or sibling) run's persist runs inline.
                assert _defer_run_persistence(self._recording_persist(executed, "other")) is False
            # An identity-less persist under a bound gate comes from a custom-loop
            # nested run (the owner always carries its identity): inline.
            assert _defer_run_persistence(self._recording_persist(executed, "identity-less")) is False
        await gate.flush()
        assert executed == ["own"]

    async def test_unbound_gate_defers_only_identity_less_persists(self) -> None:
        # An unbound gate (its run never adopted the claim: a fully custom run loop)
        # stays fail-closed for identity-less persists — the covered run's own — and
        # inline for identity-stamped (nested/sibling) runs.
        executed: list[str] = []
        gate = _RunPersistenceGate()
        with gate:
            assert _defer_run_persistence(self._recording_persist(executed, "custom-own")) is True
            with _run_identity_scope(object()):
                assert _defer_run_persistence(self._recording_persist(executed, "stamped-nested")) is False
        await gate.flush()
        assert executed == ["custom-own"]

    def test_bind_owner_accepts_every_adopted_identity(self) -> None:
        # A retrying/fallback middleware re-invokes call_next(): the final handler
        # re-offers the same gate and each attempt's run adopts it. Every adopted
        # identity must stay accepted — first-bind-wins would let attempt 2's
        # persistence run inline ahead of the final verdict (fail-open), and
        # rebind-replace would flip attempt 1's still-running work to inline.
        gate = _RunPersistenceGate()
        first = object()
        second = object()
        gate.bind_owner(first)
        gate.bind_owner(second)
        assert gate.accepts(first) is True
        assert gate.accepts(second) is True
        assert gate.accepts(object()) is False  # other runs still persist inline
        assert gate.accepts(None) is False  # bound gates reject identity-less persists

    def test_claim_handshake_is_keyed_to_the_agent_instance(self) -> None:
        gate = _RunPersistenceGate()
        target = object()
        stranger = object()
        identity = object()
        _offer_run_persistence_gate_claim(gate, target)
        # A nested or sibling run (a different agent instance) must not claim the gate...
        _adopt_run_persistence_gate_claim(stranger, object())
        assert gate.accepts(identity) is False
        # ...the targeted run does, and adoption consumes the ticket.
        _adopt_run_persistence_gate_claim(target, identity)
        assert gate.accepts(identity) is True
        _adopt_run_persistence_gate_claim(target, object())  # stale ticket is gone
        assert gate.accepts(identity) is True

    async def test_flush_runs_callables_with_the_gate_context_suspended(self) -> None:
        # A flushed callable that re-checks the gate (like _run_after_providers) must
        # run inline even when an enclosing gate is active at flush time: its own
        # covering verdict already permitted it, so it is never re-deferred.
        executed: list[str] = []
        outer = _RunPersistenceGate()
        inner = _RunPersistenceGate()

        async def reentrant() -> None:
            if _defer_run_persistence(reentrant):
                return
            executed.append("ran-inline")

        with inner:
            assert _defer_run_persistence(reentrant) is True
        with outer:  # an enclosing gate is active while the inner gate flushes
            await inner.flush()
        assert executed == ["ran-inline"]
        await outer.flush()
        assert executed == ["ran-inline"]
