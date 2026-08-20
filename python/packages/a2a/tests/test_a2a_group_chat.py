# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from a2a.types import Artifact, Part, StreamResponse, Task, TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.types import Message as A2AMessage
from a2a.types import Role as A2ARole
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    FileCheckpointStorage,
    Message,
    ResponseStream,
)
from agent_framework.exceptions import AgentInvalidRequestException
from agent_framework.orchestrations import ConcurrentBuilder, GroupChatBuilder, GroupChatState

from agent_framework_a2a import A2AAgent


class RecordingA2AClient:
    """Minimal A2A transport that records real remote invocations."""

    def __init__(self) -> None:
        self.call_count = 0

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        self.call_count += 1
        yield StreamResponse(
            task=Task(
                id=f"task-{self.call_count}",
                context_id="group-chat-context",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Remote answer")])],
            )
        )


class InputRequiredA2AClient:
    """A2A transport that pauses once, then completes the same task."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        self.messages.append(request.message)
        if len(self.messages) == 1:
            yield StreamResponse(
                task=Task(
                    id="task-input",
                    context_id="group-chat-context",
                    status=TaskStatus(
                        state=TaskState.TASK_STATE_INPUT_REQUIRED,
                        message=A2AMessage(
                            message_id="input-request",
                            role=A2ARole.ROLE_AGENT,
                            parts=[Part(text="What is your name?")],
                        ),
                    ),
                )
            )
            return
        yield StreamResponse(
            task=Task(
                id="task-input",
                context_id="group-chat-context",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Thanks, Alice")])],
            )
        )


class MessageLessInputRequiredA2AClient(InputRequiredA2AClient):
    """A2A transport whose first input request omits the optional prompt."""

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        self.messages.append(request.message)
        if len(self.messages) == 1:
            yield StreamResponse(
                task=Task(
                    id="task-input-no-message",
                    context_id="group-chat-context",
                    status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
                )
            )
            return
        yield StreamResponse(
            task=Task(
                id="task-input-no-message",
                context_id="group-chat-context",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Thanks, Alice")])],
            )
        )


class DuplicateMessageLessInputRequiredA2AClient(InputRequiredA2AClient):
    """A2A transport that repeats one message-less prompt in two protocol shapes."""

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        self.messages.append(request.message)
        if len(self.messages) == 1:
            yield StreamResponse(
                status_update=TaskStatusUpdateEvent(
                    task_id="task-input-no-message",
                    context_id="group-chat-context",
                    status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
                )
            )
            yield StreamResponse(
                task=Task(
                    id="task-input-no-message",
                    context_id="group-chat-context",
                    status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
                )
            )
            return
        if len(self.messages) == 2:
            yield StreamResponse(
                task=Task(
                    id="task-input-no-message",
                    context_id="group-chat-context",
                    status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
                )
            )
            return
        yield StreamResponse(
            task=Task(
                id="task-input-no-message",
                context_id="group-chat-context",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Complete")])],
            )
        )


class RepeatedInputRequiredA2AClient(InputRequiredA2AClient):
    """A2A transport that requests caller input twice for the same task."""

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        self.messages.append(request.message)
        if len(self.messages) <= 2:
            prompt_number = len(self.messages)
            yield StreamResponse(
                task=Task(
                    id="task-input",
                    context_id="group-chat-context",
                    status=TaskStatus(
                        state=TaskState.TASK_STATE_INPUT_REQUIRED,
                        message=A2AMessage(
                            message_id=f"input-request-{prompt_number}",
                            role=A2ARole.ROLE_AGENT,
                            parts=[Part(text=f"Question {prompt_number}?")],
                        ),
                    ),
                )
            )
            return
        yield StreamResponse(
            task=Task(
                id="task-input",
                context_id="group-chat-context",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Complete")])],
            )
        )


class TextlessAgent(BaseAgent):
    """Participant whose response projects to no Group Chat messages."""

    def __init__(self) -> None:
        super().__init__(name="textless", description="Returns framework control content only")
        self.call_count = 0

    def run(  # type: ignore[override]
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Any:
        self.call_count += 1
        function_call = Content.from_function_call(call_id="control-1", name="internal_control")
        if stream:

            async def _stream() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[function_call], role="assistant", author_name=self.name)

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse[Any]:
            return AgentResponse(messages=[Message("assistant", [function_call], author_name=self.name)])

        return _run()


class SessionBackedAgent(BaseAgent):
    """Non-A2A participant that supports empty turns through its session."""

    def __init__(self) -> None:
        super().__init__(name="session-backed", description="Continues from session state")
        self.invocations: list[Any] = []

    def run(  # type: ignore[override]
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Any:
        assert session is not None
        self.invocations.append(messages)
        turn = int(session.state.get("turn", 0)) + 1
        session.state["turn"] = turn
        text = f"Session turn {turn}"
        if stream:

            async def _stream() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=text)],
                    role="assistant",
                    author_name=self.name,
                )

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse[Any]:
            return AgentResponse(messages=[Message("assistant", [text], author_name=self.name)])

        return _run()


async def test_concurrent_a2a_requests_with_same_remote_task_id_remain_isolated() -> None:
    """Caller responses remain scoped to the participant that requested them."""
    first_client = InputRequiredA2AClient()
    second_client = InputRequiredA2AClient()
    workflow = ConcurrentBuilder(
        participants=[
            A2AAgent(name="first-remote", client=cast(Any, first_client), http_client=None),
            A2AAgent(name="second-remote", client=cast(Any, second_client), http_client=None),
        ]
    ).build()

    initial_result = await workflow.run("Start")

    requests = {event.source_executor_id: event for event in initial_result.get_request_info_events()}
    assert set(requests) == {"first-remote", "second-remote"}
    assert requests["first-remote"].request_id != requests["second-remote"].request_id

    await workflow.run(
        responses={requests["first-remote"].request_id: "Alice"},
    )
    assert len(first_client.messages) == 2
    assert len(second_client.messages) == 1

    await workflow.run(
        responses={requests["second-remote"].request_id: "Bob"},
    )
    assert len(second_client.messages) == 2


async def test_input_required_round_trips_through_group_chat_as_agent() -> None:
    """A workflow agent exposes and accepts the generic request-info envelope."""
    client = InputRequiredA2AClient()
    workflow = GroupChatBuilder(
        participants=[A2AAgent(name="remote", client=cast(Any, client), http_client=None)],
        selection_func=lambda state: "remote",
        max_rounds=1,
    ).build()
    workflow_agent = workflow.as_agent(name="group-chat-agent")

    initial_response = await workflow_agent.run("Start")

    request_calls = [
        content
        for message in initial_response.messages
        for content in message.contents
        if content.type == "function_call" and content.name == "request_info"
    ]
    [request_call] = request_calls
    assert request_call.call_id is not None

    final_response = await workflow_agent.run(
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id=request_call.call_id, result="Alice")],
        )
    )

    assert final_response.user_input_requests == []
    assert len(client.messages) == 2
    assert client.messages[1].task_id == "task-input"
    assert client.messages[1].parts[0].text == "Alice"


async def test_message_less_input_required_pauses_and_resumes_group_chat() -> None:
    """Remote caller authority survives an omitted A2A prompt message."""
    client = MessageLessInputRequiredA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    peer = SessionBackedAgent()
    workflow = GroupChatBuilder(
        participants=[remote, peer],
        selection_func=lambda state: ["remote", "session-backed"][state.current_round],
        max_rounds=2,
    ).build()

    initial_result = await workflow.run("Start")

    [request] = initial_result.get_request_info_events()
    assert request.data.text == "Remote A2A task requires input."
    assert peer.invocations == []

    await workflow.run(responses={request.request_id: "Alice"})

    assert len(client.messages) == 2
    assert client.messages[1].task_id == "task-input-no-message"
    assert client.messages[1].parts[0].text == "Alice"
    assert len(peer.invocations) == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_duplicate_message_less_input_events_share_one_request_per_caller_turn(stream: bool) -> None:
    """Duplicate representations share identity until caller input starts a new prompt."""
    client = DuplicateMessageLessInputRequiredA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    peer = SessionBackedAgent()
    workflow = GroupChatBuilder(
        participants=[remote, peer],
        selection_func=lambda state: ["remote", "session-backed"][state.current_round],
        max_rounds=2,
    ).build()

    if stream:
        first_stream = workflow.run("Start", stream=True)
        async for _ in first_stream:
            pass
        first_result = await first_stream.get_final_response()
    else:
        first_result = await workflow.run("Start")
    [first_request] = first_result.get_request_info_events()

    second_result = await workflow.run(
        responses={first_request.request_id: Content.from_text(text="First answer")},
    )
    [second_request] = second_result.get_request_info_events()

    assert second_request.request_id != first_request.request_id
    assert len(client.messages) == 2

    await workflow.run(
        responses={second_request.request_id: Content.from_text(text="Second answer")},
    )
    assert len(client.messages) == 3
    assert len(peer.invocations) == 1


async def test_repeated_input_requests_for_same_remote_task_reject_stale_responses() -> None:
    """Each remote prompt occurrence has independent workflow correlation."""
    client = RepeatedInputRequiredA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    peer = SessionBackedAgent()
    workflow = GroupChatBuilder(
        participants=[remote, peer],
        selection_func=lambda state: ["remote", "session-backed"][state.current_round],
        max_rounds=2,
    ).build()

    first_result = await workflow.run("Start")
    [first_request] = first_result.get_request_info_events()

    second_result = await workflow.run(
        responses={first_request.request_id: Content.from_text(text="First answer")},
    )
    [second_request] = second_result.get_request_info_events()

    assert second_request.request_id != first_request.request_id
    with pytest.raises(ValueError, match="unknown request ID"):
        await workflow.run(
            responses={first_request.request_id: Content.from_text(text="Stale first answer")},
        )
    assert len(client.messages) == 2

    await workflow.run(
        responses={second_request.request_id: Content.from_text(text="Second answer")},
    )
    assert len(client.messages) == 3
    assert client.messages[2].task_id == "task-input"
    assert client.messages[2].parts[0].text == "Second answer"
    assert len(peer.invocations) == 1


async def test_input_required_accepts_structured_content_response() -> None:
    """Caller responses preserve structured content supported by A2A."""
    client = InputRequiredA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    peer = SessionBackedAgent()
    workflow = GroupChatBuilder(
        participants=[remote, peer],
        selection_func=lambda state: ["remote", "session-backed"][state.current_round],
        max_rounds=2,
    ).build()

    initial_result = await workflow.run("Start")
    [request] = initial_result.get_request_info_events()

    await workflow.run(
        responses={
            request.request_id: Content.from_uri(
                "https://example.com/answer.pdf",
                media_type="application/pdf",
            )
        },
    )

    assert len(client.messages) == 2
    assert client.messages[1].task_id == "task-input"
    assert client.messages[1].parts[0].url == "https://example.com/answer.pdf"


@pytest.mark.parametrize("stream", [False, True])
async def test_consecutive_a2a_selection_rejects_empty_invocation_without_remote_call(stream: bool) -> None:
    """A consecutive A2A turn fails instead of inventing continuation input."""
    client = RecordingA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)

    def select_remote(state: GroupChatState) -> str:
        return "remote"

    workflow = GroupChatBuilder(
        participants=[remote],
        selection_func=select_remote,
        max_rounds=2,
    ).build()

    with pytest.raises(
        AgentInvalidRequestException,
        match="A2A agent 'remote' requires a real message or an explicit continuation token",
    ):
        if stream:
            async for _ in workflow.run("Investigate the incident", stream=True):
                pass
        else:
            await workflow.run("Investigate the incident", stream=False)

    assert client.call_count == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_a2a_reselection_after_textless_peer_rejects_empty_invocation(stream: bool) -> None:
    """An intervening response with no projected messages cannot activate A2A."""
    client = RecordingA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    textless = TextlessAgent()
    speakers = ["remote", "textless", "remote"]

    def select_in_sequence(state: GroupChatState) -> str:
        return speakers[state.current_round]

    workflow = GroupChatBuilder(
        participants=[remote, textless],
        selection_func=select_in_sequence,
        max_rounds=3,
    ).build()

    with pytest.raises(
        AgentInvalidRequestException,
        match="A2A agent 'remote' requires a real message or an explicit continuation token",
    ):
        if stream:
            async for _ in workflow.run("Investigate the incident", stream=True):
                pass
        else:
            await workflow.run("Investigate the incident", stream=False)

    assert client.call_count == 1
    assert textless.call_count == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_consecutive_session_backed_participant_still_receives_empty_turn(stream: bool) -> None:
    """Group Chat preserves valid empty-input behavior for non-A2A agents."""
    participant = SessionBackedAgent()
    selection_count = 0

    def select_participant(state: GroupChatState) -> str:
        nonlocal selection_count
        selection_count += 1
        return "session-backed"

    workflow = GroupChatBuilder(
        participants=[participant],
        selection_func=select_participant,
        max_rounds=2,
    ).build()

    if stream:
        async for _ in workflow.run("Investigate the incident", stream=True):
            pass
    else:
        await workflow.run("Investigate the incident", stream=False)

    assert selection_count == 2
    assert len(participant.invocations) == 2
    assert participant.invocations[1] == []


@pytest.mark.parametrize("stream", [False, True])
async def test_input_required_pauses_group_chat_and_resumes_same_task(stream: bool) -> None:
    """Only caller input can resume the paused A2A participant."""
    client = InputRequiredA2AClient()
    remote = A2AAgent(name="remote", client=cast(Any, client), http_client=None)
    peer = SessionBackedAgent()
    speakers = ["remote", "session-backed"]

    def select_in_sequence(state: GroupChatState) -> str:
        return speakers[state.current_round]

    workflow = GroupChatBuilder(
        participants=[remote, peer],
        selection_func=select_in_sequence,
        max_rounds=2,
    ).build()

    if stream:
        initial_stream = workflow.run("Start", stream=True)
        async for _ in initial_stream:
            pass
        initial_result = await initial_stream.get_final_response()
    else:
        initial_result = await workflow.run("Start")

    requests = initial_result.get_request_info_events()
    assert len(requests) == 1
    assert requests[0].data.id == requests[0].request_id
    assert requests[0].request_id != "task-input"
    assert requests[0].data.text == "What is your name?"
    assert peer.invocations == []

    caller_response = Content.from_text(text="Alice")
    if stream:
        resumed_stream = workflow.run(
            stream=True,
            responses={requests[0].request_id: caller_response},
        )
        async for _ in resumed_stream:
            pass
        await resumed_stream.get_final_response()
    else:
        await workflow.run(responses={requests[0].request_id: caller_response})

    assert len(client.messages) == 2
    assert client.messages[1].task_id == "task-input"
    assert client.messages[1].parts[0].text == "Alice"
    assert len(peer.invocations) == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_input_required_survives_group_chat_checkpoint_restoration(stream: bool, tmp_path: Path) -> None:
    """Restoration preserves caller authority and the original remote task."""
    client = InputRequiredA2AClient()
    storage = FileCheckpointStorage(tmp_path)
    peers: list[SessionBackedAgent] = []

    def select_in_sequence(state: GroupChatState) -> str:
        return ["remote", "session-backed"][state.current_round]

    def build_workflow() -> Any:
        peer = SessionBackedAgent()
        peers.append(peer)
        return GroupChatBuilder(
            participants=[
                A2AAgent(name="remote", client=cast(Any, client), http_client=None),
                peer,
            ],
            selection_func=select_in_sequence,
            max_rounds=2,
            checkpoint_storage=storage,
        ).build()

    workflow = build_workflow()
    if stream:
        initial_stream = workflow.run("Start", stream=True)
        async for _ in initial_stream:
            pass
        initial_result = await initial_stream.get_final_response()
    else:
        initial_result = await workflow.run("Start")

    [request] = initial_result.get_request_info_events()
    assert request.data.id == request.request_id
    assert request.request_id != "task-input"
    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    checkpoint = next(
        checkpoint for checkpoint in checkpoints if request.request_id in checkpoint.pending_request_info_events
    )
    assert checkpoint.pending_request_info_events[request.request_id].data.id == request.request_id

    restored = build_workflow()
    with pytest.raises(ValueError, match="unknown request ID"):
        await restored.run(
            checkpoint_id=checkpoint.checkpoint_id,
            responses={"unrelated-request": "peer message"},
        )
    assert len(client.messages) == 1
    assert all(peer.invocations == [] for peer in peers)

    caller_response = "Alice"
    if stream:
        resumed_stream = restored.run(
            checkpoint_id=checkpoint.checkpoint_id,
            stream=True,
            responses={request.request_id: caller_response},
        )
        async for _ in resumed_stream:
            pass
        resumed_result = await resumed_stream.get_final_response()
    else:
        resumed_result = await restored.run(
            checkpoint_id=checkpoint.checkpoint_id,
            responses={request.request_id: caller_response},
        )

    assert resumed_result.get_request_info_events() == []
    assert len(client.messages) == 2
    assert client.messages[1].task_id == "task-input"
    assert client.messages[1].parts[0].text == "Alice"
    assert sum(len(peer.invocations) for peer in peers) == 1
