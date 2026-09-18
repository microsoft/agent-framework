# Copyright (c) Microsoft. All rights reserved.

"""Live AG-UI multi-turn coverage for Foundry provider continuation modes."""

from __future__ import annotations

import json
import os
from typing import Any, Literal, cast
from uuid import uuid4

import pytest
from agent_framework import Agent, AgentSession, Message
from agent_framework_ag_ui import AgentFrameworkAgent, InMemoryAGUIThreadSnapshotStore
from azure.ai.projects import models as projects_models
from azure.ai.projects.aio import AIProjectClient
from azure.identity import AzureCliCredential

from agent_framework_foundry import FoundryAgent, FoundryChatClient

skip_if_foundry_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_MODEL", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL provided; skipping integration tests.",
)
skip_if_foundry_hosted_agent_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_AGENT_NAME", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_AGENT_NAME provided; skipping integration tests.",
)

_Mode = Literal["stateless", "conversation", "previous_response"]
_PROVIDER_SESSION_KEY = "__ag_ui_provider_service_session_id"
_MODES = [
    pytest.param("stateless", False, id="stateless-snapshot-replay"),
    pytest.param("conversation", True, id="conversation"),
    pytest.param("previous_response", True, id="previous-response-id"),
]


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


async def _exercise_agui_case(
    agent: Any,
    mode: _Mode,
) -> None:
    marker = f"AF-AGUI-{uuid4().hex}"
    follow_up = "Return only the exact marker from my previous message."
    thread_id = f"agui-thread-{uuid4().hex}"
    scope = f"agui-scope-{uuid4().hex}"
    snapshot_store = InMemoryAGUIThreadSnapshotStore()
    capturing = _ConversationCapturingAgent(agent) if mode == "conversation" else _CapturingAgent(agent)
    provider_id: str | None = None

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
        assert [[message.role for message in messages] for messages in capturing.inputs] == [["user"]]
        if mode == "stateless":
            assert capturing.service_session_ids == [None]
            assert first_stored.session_state is None
        else:
            assert first_stored.session_state is not None
            provider_id = first_stored.session_state[_PROVIDER_SESSION_KEY]
            assert isinstance(provider_id, str)
            assert provider_id != thread_id
            assert provider_id not in json.dumps(first_stored.messages)
            if mode == "conversation":
                assert provider_id.startswith("conv_")
                assert capturing.service_session_ids == [provider_id]
                assert capturing.created_conversation_ids == [provider_id]
            else:
                assert provider_id.startswith(("resp_", "caresp_"))
                assert capturing.service_session_ids == [None]
                assert not capturing.created_conversation_ids

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
        if mode == "stateless":
            assert [message.role for message in capturing.inputs[1]] == ["user", "assistant", "user"]
            assert capturing.service_session_ids == [None, None]
        else:
            assert [(message.role, message.text) for message in capturing.inputs[1]] == [("user", follow_up)]
            assert provider_id is not None
            assert capturing.service_session_ids[1] == provider_id
            if mode == "conversation":
                assert capturing.service_session_ids == [provider_id, provider_id]
            else:
                assert capturing.service_session_ids[0] is None

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
@skip_if_foundry_integration_tests_disabled
@pytest.mark.parametrize(("mode", "store"), _MODES)
async def test_foundry_chat_client_agui_provider_matrix(mode: _Mode, store: bool) -> None:
    credential = AzureCliCredential()
    client = FoundryChatClient(credential=cast(Any, credential))
    agent = Agent(client=cast(Any, client), default_options=cast(Any, {"store": store}))
    try:
        await _exercise_agui_case(agent, mode)
    finally:
        await client.client.close()
        await client.project_client.close()
        credential.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_integration_tests_disabled
@pytest.mark.parametrize(("mode", "store"), _MODES)
async def test_foundry_prompt_agent_agui_provider_matrix(mode: _Mode, store: bool) -> None:
    credential = AzureCliCredential()
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=cast(Any, credential),
        allow_preview=True,
    )
    created_agent: Any | None = None
    prompt_agent: FoundryAgent | None = None
    try:
        created_agent = await project_client.agents.create_version(
            agent_name=f"af-agui-{uuid4().hex[:12]}",
            definition=projects_models.PromptAgentDefinition(
                model=os.environ["FOUNDRY_MODEL"],
                instructions="Follow the user instructions exactly and answer concisely.",
            ),
        )
        prompt_agent = FoundryAgent(
            project_client=project_client,
            agent_name=created_agent.name,
            agent_version=created_agent.version,
            allow_preview=False,
            default_options=cast(Any, {"store": store}),
        )
        await _exercise_agui_case(prompt_agent, mode)
    finally:
        if created_agent is not None:
            await project_client.agents.delete(agent_name=created_agent.name, force=True)
        if prompt_agent is not None:
            await cast(Any, prompt_agent.client).client.close()
        await project_client.close()
        credential.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_hosted_agent_integration_tests_disabled
@pytest.mark.parametrize(("mode", "store"), _MODES)
async def test_foundry_hosted_agent_agui_provider_matrix(mode: _Mode, store: bool) -> None:
    credential = AzureCliCredential()
    hosted_agent = FoundryAgent(
        credential=cast(Any, credential),
        allow_preview=True,
        default_options=cast(Any, {"store": store}),
    )
    try:
        await _exercise_agui_case(hosted_agent, mode)
    finally:
        await cast(Any, hosted_agent.client).client.close()
        await cast(Any, hosted_agent.client).close()
        credential.close()
