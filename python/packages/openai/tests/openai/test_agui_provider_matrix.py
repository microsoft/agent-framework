# Copyright (c) Microsoft. All rights reserved.

"""Live AG-UI multi-turn coverage for OpenAI provider continuation modes."""

from __future__ import annotations

import json
import os
from typing import Any, Literal, cast
from uuid import uuid4

import pytest
from agent_framework import Agent, AgentSession, Message
from agent_framework_ag_ui import AgentFrameworkAgent, InMemoryAGUIThreadSnapshotStore

from agent_framework_openai import OpenAIChatClient, OpenAIChatCompletionClient

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests.",
)

_Mode = Literal["stateless", "conversation", "previous_response"]
_PROVIDER_SESSION_KEY = "__ag_ui_provider_service_session_id"


class _CapturingAgent:
    """Delegate to an Agent without exposing its conversation factory."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self.inputs: list[list[Message]] = []
        self.service_session_ids: list[Any] = []
        self.created_conversation_ids: list[str] = []

    def run(self, messages: Any = None, **kwargs: Any) -> Any:
        self.inputs.append(list(messages) if isinstance(messages, list) else [messages])
        session = kwargs.get("session")
        self.service_session_ids.append(session.service_session_id if session is not None else None)
        return self._agent.run(messages, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name == "create_conversation":
            raise AttributeError(name)
        return getattr(self._agent, name)


class _ConversationCapturingAgent(_CapturingAgent):
    """Expose backend conversation creation to AgentFrameworkAgent."""

    async def create_conversation(self, *, session_id: str | None = None) -> AgentSession:
        conversation = await self._agent.client.client.conversations.create()
        self.created_conversation_ids.append(conversation.id)
        return self._agent.get_session(conversation.id, session_id=session_id)


async def _exercise_agui_case(agent: Any, mode: _Mode) -> None:
    marker = f"AF-AGUI-{uuid4().hex}"
    follow_up = "Return only the exact marker from my previous message."
    thread_id = f"agui-thread-{uuid4().hex}"
    scope = f"agui-scope-{uuid4().hex}"
    snapshot_store = InMemoryAGUIThreadSnapshotStore()
    capturing = _ConversationCapturingAgent(agent) if mode == "conversation" else _CapturingAgent(agent)

    runner = AgentFrameworkAgent(
        agent=cast(Any, capturing),
        use_service_session=mode != "stateless",
        service_session_id_from_thread_id=False,
        snapshot_store=snapshot_store,
    )

    try:
        first_events = [
            event
            async for event in runner.run({
                "threadId": thread_id,
                "runId": f"run-1-{uuid4().hex}",
                "__ag_ui_snapshot_scope": scope,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Remember this exact marker for my next message: {marker}",
                    }
                ],
            })
        ]
        first_snapshot = next(
            event for event in reversed(first_events) if getattr(event, "type", None) == "MESSAGES_SNAPSHOT"
        )
        replay_messages = cast(list[dict[str, Any]], first_snapshot.model_dump(by_alias=True)["messages"])
        first_stored = await snapshot_store.get(scope=scope, thread_id=thread_id)
        assert first_stored is not None

        second_events = [
            event
            async for event in runner.run({
                "threadId": thread_id,
                "runId": f"run-2-{uuid4().hex}",
                "__ag_ui_snapshot_scope": scope,
                "messages": [*replay_messages, {"role": "user", "content": follow_up}],
            })
        ]

        assert not [event for event in second_events if getattr(event, "type", None) == "RUN_ERROR"]
        assert [[message.role for message in messages] for messages in capturing.inputs[:1]] == [["user"]]
        if mode == "stateless":
            assert [message.role for message in capturing.inputs[1]] == ["user", "assistant", "user"]
            assert capturing.service_session_ids == [None, None]
            assert first_stored.session_state is None
        else:
            assert [(message.role, message.text) for message in capturing.inputs[1]] == [("user", follow_up)]
            assert first_stored.session_state is not None
            provider_id = first_stored.session_state[_PROVIDER_SESSION_KEY]
            assert isinstance(provider_id, str)
            assert provider_id != thread_id
            assert capturing.service_session_ids[1] == provider_id
            assert provider_id not in json.dumps(first_stored.messages)
            if mode == "conversation":
                assert provider_id.startswith("conv_")
                assert capturing.service_session_ids == [provider_id, provider_id]
                assert capturing.created_conversation_ids == [provider_id]
            else:
                assert provider_id.startswith("resp_")
                assert capturing.service_session_ids[0] is None
                assert not capturing.created_conversation_ids

        assert marker in capturing.inputs[0][0].text
        assert capturing.inputs[1][-1].text == follow_up
        response_text = "".join(
            str(getattr(event, "delta", ""))
            for event in second_events
            if getattr(event, "type", None) == "TEXT_MESSAGE_CONTENT"
        )
        assert marker in response_text

        final_stored = await snapshot_store.get(scope=scope, thread_id=thread_id)
        assert final_stored is not None
        assert [message.get("role") for message in final_stored.messages].count("user") == 2
        assert [message.get("role") for message in final_stored.messages].count("assistant") >= 2
    finally:
        for conversation_id in capturing.created_conversation_ids:
            await agent.client.client.conversations.delete(conversation_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
@pytest.mark.parametrize(
    ("mode", "store"),
    [
        pytest.param("stateless", False, id="stateless-snapshot-replay"),
        pytest.param("conversation", True, id="conversation"),
        pytest.param("previous_response", True, id="previous-response-id"),
    ],
)
async def test_openai_responses_agui_provider_matrix(mode: _Mode, store: bool) -> None:
    client = OpenAIChatClient()
    agent = Agent(client=cast(Any, client), default_options=cast(Any, {"store": store}))
    try:
        await _exercise_agui_case(agent, mode)
    finally:
        await client.client.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
@pytest.mark.parametrize("store", [pytest.param(False, id="store-false"), pytest.param(True, id="store-true")])
async def test_openai_chat_completions_agui_provider_matrix(store: bool) -> None:
    client = OpenAIChatCompletionClient()
    agent = Agent(client=cast(Any, client), default_options=cast(Any, {"store": store}))
    try:
        await _exercise_agui_case(agent, "stateless")
    finally:
        await client.client.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_replays_real_assistant_logprobs() -> None:
    """Real provider logprobs survive direct assistant-message replay without fabrication."""
    client = OpenAIChatClient(model=os.environ["OPENAI_CHAT_COMPLETION_MODEL"])
    follow_up = Message(role="user", contents=["Reply with exactly: done"])
    try:
        first = await client.get_response(
            [Message(role="user", contents=["Reply with exactly: hello"])],
            options={
                "store": False,
                "include": ["message.output_text.logprobs"],
                "top_logprobs": 2,
            },
        )
        assistant_content = next(
            content
            for message in first.messages
            for content in message.contents
            if message.role == "assistant" and content.type == "text"
        )
        real_logprobs = assistant_content.additional_properties.get("logprobs")
        assert isinstance(real_logprobs, list)
        assert real_logprobs

        _, run_options, _ = await client._prepare_request(
            [*first.messages, follow_up],
            {"store": False},
        )
        assistant_input = next(item for item in run_options["input"] if item.get("role") == "assistant")
        replayed_logprobs = assistant_input["content"][0]["logprobs"]

        assert replayed_logprobs == real_logprobs
        second = await client.get_response([*first.messages, follow_up], options={"store": False})
        assert "done" in second.text.lower()
    finally:
        await client.client.close()
