# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    AgentModeProvider,
    AgentResponse,
    AgentSession,
    BackgroundTaskInfo,
    BackgroundTaskStatus,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    JudgeVerdict,
    Message,
    MiddlewareTermination,
    ResponseStream,
    TodoItem,
    TodoProvider,
    background_tasks_running,
    background_tasks_running_message,
    set_agent_mode,
    todos_remaining,
    todos_remaining_message,
)
from agent_framework._harness._loop import (
    DEFAULT_JUDGE_MAX_ITERATIONS,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_NEXT_MESSAGE,
    AgentLoopMiddleware,
)


class RecordingChatClient(BaseChatClient[ChatOptions[None]]):
    """A minimal chat client that records inputs and returns scripted responses.

    When ``service_mode=True`` it emulates a service that stores history: it advertises
    ``STORES_BY_DEFAULT=True``, records the ``conversation_id`` threaded into each call
    (``received_conversation_ids``) and stamps every response with a fresh ``conversation_id``
    (``conv-<n>``) so the agent propagates it onto the session.
    """

    def __init__(
        self,
        *,
        texts: list[str] | None = None,
        honor_response_format: bool = False,
        service_mode: bool = False,
    ) -> None:
        super().__init__()
        self.call_count: int = 0
        self.received_messages: list[list[str]] = []
        self.received_response_formats: list[Any] = []
        self.received_conversation_ids: list[str | None] = []
        self._texts = list(texts) if texts is not None else []
        self._honor_response_format = honor_response_format
        self.service_mode = service_mode
        if service_mode:
            object.__setattr__(self, "STORES_BY_DEFAULT", True)
        self._conv_counter = 0

    def _next_text(self, messages: Sequence[Message]) -> str:
        if self._texts:
            return self._texts.pop(0)
        last = messages[-1].text if messages else ""
        return f"response to: {last}"

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.received_messages.append([m.text for m in messages])
        response_format = options.get("response_format")
        self.received_response_formats.append(response_format)
        conversation_id_option = options.get("conversation_id")
        self.received_conversation_ids.append(
            conversation_id_option if isinstance(conversation_id_option, str) else None
        )
        conversation_id: str | None = None
        if self.service_mode:
            self._conv_counter += 1
            conversation_id = f"conv-{self._conv_counter}"
        if stream:
            return self._stream(messages, conversation_id)

        async def _get() -> ChatResponse:
            self.call_count += 1
            return ChatResponse(
                messages=Message(role="assistant", contents=[self._next_text(messages)]),
                response_format=response_format if self._honor_response_format else None,
                conversation_id=conversation_id,
            )

        return _get()

    def _stream(
        self, messages: Sequence[Message], conversation_id: str | None = None
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _gen() -> AsyncIterable[ChatResponseUpdate]:
            self.call_count += 1
            text = self._next_text(messages)
            yield ChatResponseUpdate(
                contents=[Content.from_text(text)],
                role="assistant",
                finish_reason="stop",
                conversation_id=conversation_id,
            )

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            return ChatResponse.from_updates(updates)

        return ResponseStream(_gen(), finalizer=_finalize)


# region construction / validation


def always_continue(**kwargs: Any) -> bool:
    """A ``should_continue`` predicate that always keeps looping (bounded by ``max_iterations``)."""
    return True


async def _resolve_should_continue_result(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_max_iterations(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        AgentLoopMiddleware(always_continue, max_iterations=bad)


def test_judge_mode_default_max_iterations() -> None:
    middleware = AgentLoopMiddleware.with_judge(RecordingChatClient())
    assert middleware.max_iterations == DEFAULT_JUDGE_MAX_ITERATIONS


def test_judge_mode_explicit_unbounded() -> None:
    middleware = AgentLoopMiddleware.with_judge(RecordingChatClient(), max_iterations=None)
    assert middleware.max_iterations is None


def test_judge_mode_custom_max_iterations() -> None:
    middleware = AgentLoopMiddleware.with_judge(RecordingChatClient(), max_iterations=3)
    assert middleware.max_iterations == 3


def test_default_max_iterations_applied() -> None:
    assert AgentLoopMiddleware(always_continue).max_iterations == DEFAULT_MAX_ITERATIONS


def test_explicit_none_is_unbounded() -> None:
    assert AgentLoopMiddleware(always_continue, max_iterations=None).max_iterations is None


def test_constructor_configures_feedback_loop() -> None:
    record = lambda *, iteration, **kwargs: f"note-{iteration}"  # noqa: E731
    mw = AgentLoopMiddleware(
        always_continue,
        max_iterations=4,
        record_feedback=record,
        fresh_context=True,
    )

    assert isinstance(mw, AgentLoopMiddleware)
    assert mw.max_iterations == 4
    assert mw.record_feedback is record
    assert mw.fresh_context is True
    assert mw.should_continue is always_continue


def test_constructor_sets_should_continue() -> None:
    predicate = lambda *, iteration, **kwargs: iteration < 3  # noqa: E731
    mw = AgentLoopMiddleware(should_continue=predicate, max_iterations=5)

    assert mw.should_continue is predicate
    assert mw.max_iterations == 5


def test_with_judge_factory_builds_judge_condition() -> None:
    mw = AgentLoopMiddleware.with_judge(RecordingChatClient())

    # The judge client is wrapped into a should_continue predicate.
    assert mw.should_continue is not None
    assert mw.max_iterations == DEFAULT_JUDGE_MAX_ITERATIONS
    # fresh_context defaults to False and is forwarded to the constructor.
    assert mw.fresh_context is False


def test_with_judge_forwards_fresh_context() -> None:
    mw = AgentLoopMiddleware.with_judge(RecordingChatClient(), fresh_context=True)

    assert mw.fresh_context is True


# region non-streaming behavior


async def test_loop_stops_at_max_iterations() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(always_continue, max_iterations=3)])

    response = await agent.run("start")

    assert client.call_count == 3
    assert isinstance(response, AgentResponse)


async def test_should_continue_controls_iterations_and_receives_kwargs() -> None:
    client = RecordingChatClient()
    seen: list[dict[str, Any]] = []

    def should_continue(*, iteration: int, last_result: AgentResponse, **kwargs: Any) -> bool:
        seen.append({"iteration": iteration, "last_result": last_result, **kwargs})
        return iteration < 2

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue=should_continue)])

    await agent.run("start")

    # Runs twice: predicate returns True after iteration 1, then False after iteration 2.
    assert client.call_count == 2
    assert [entry["iteration"] for entry in seen] == [1, 2]
    assert all(isinstance(entry["last_result"], AgentResponse) for entry in seen)
    assert seen[0]["original_messages"][0].text == "start"


async def test_async_should_continue_is_awaited() -> None:
    client = RecordingChatClient()
    calls: list[int] = []

    async def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        calls.append(iteration)
        return iteration < 3

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue=should_continue)])

    await agent.run("start")

    # The coroutine predicate is awaited each iteration and governs the stop at iteration 3.
    assert client.call_count == 3
    assert calls == [1, 2, 3]


async def test_default_next_message_nudge_is_used() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(always_continue, max_iterations=2)])

    await agent.run("original task")

    # First run carries the original prompt; the second carries the default nudge.
    assert any("original task" in text for text in client.received_messages[0])
    assert any(DEFAULT_NEXT_MESSAGE in text for text in client.received_messages[1])


async def test_custom_next_message_callable() -> None:
    client = RecordingChatClient()

    def next_message(*, iteration: int, **kwargs: Any) -> str:
        return f"iteration {iteration} follow-up"

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=2, next_message=next_message)],
    )

    await agent.run("original task")

    assert any("iteration 1 follow-up" in text for text in client.received_messages[1])


async def test_next_message_returning_none_reuses_messages() -> None:
    client = RecordingChatClient()

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=2, next_message=lambda **kwargs: None)],
    )

    await agent.run("only message")

    assert any("only message" in text for text in client.received_messages[1])


# region return aggregation


async def test_non_streaming_returns_aggregated_transcript_by_default() -> None:
    client = RecordingChatClient(texts=["first answer", "second answer"])
    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=2, inject_progress=False)],
    )

    response = await agent.run("start")

    assert isinstance(response, AgentResponse)
    # Both iterations' assistant messages and the injected user nudge are present.
    assert "first answer" in response.text
    assert "second answer" in response.text
    assert DEFAULT_NEXT_MESSAGE in response.text
    roles = [m.role for m in response.messages]
    assert roles == ["assistant", "user", "assistant"]


async def test_non_streaming_return_final_only_returns_last_response() -> None:
    client = RecordingChatClient(texts=["first answer", "second answer"])
    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=2, return_final_only=True)],
    )

    response = await agent.run("start")

    assert isinstance(response, AgentResponse)
    assert response.text == "second answer"
    assert "first answer" not in response.text


# region feedback loop


async def test_record_feedback_callable_captures_and_injects_progress() -> None:
    client = RecordingChatClient()
    captured: list[list[str]] = []

    def record_feedback(*, iteration: int, progress: list[str], **kwargs: Any) -> str:
        captured.append(list(progress))
        return f"step-{iteration}-done"

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=3, record_feedback=record_feedback)],
    )

    await agent.run("task")

    # The progress passed to record_feedback reflects prior iterations, not the entry it produces.
    assert captured == [[], ["step-1-done"], ["step-1-done", "step-2-done"]]
    # With no session the full accumulated log is injected into later iterations' input.
    assert any("step-1-done" in text for text in client.received_messages[1])
    assert any("step-2-done" in text for text in client.received_messages[2])


async def test_feedback_fallback_records_response_text() -> None:
    client = RecordingChatClient(texts=["first answer", "second answer"])
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(always_continue, max_iterations=2)])

    await agent.run("task")

    # Without a record_feedback callable, the response text becomes the progress entry.
    assert any("first answer" in text for text in client.received_messages[1])


async def test_should_continue_feedback_flows_to_callables() -> None:
    client = RecordingChatClient()
    seen_feedback: list[str | None] = []

    def should_continue(*, iteration: int, **kwargs: Any) -> tuple[bool, str | None]:
        return iteration < 2, f"feedback-{iteration}"

    def record_feedback(*, feedback: str | None, **kwargs: Any) -> str:
        seen_feedback.append(feedback)
        return f"logged-{feedback}"

    def next_message(*, feedback: str | None, **kwargs: Any) -> str:
        return f"address: {feedback}"

    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                should_continue=should_continue,
                record_feedback=record_feedback,
                next_message=next_message,
            )
        ],
    )

    await agent.run("task")

    # record_feedback sees the same iteration's should_continue feedback.
    assert seen_feedback == ["feedback-1", "feedback-2"]
    # next_message relays the feedback into the second iteration's input.
    assert any("address: feedback-1" in text for text in client.received_messages[1])


async def test_should_continue_plain_bool_yields_no_feedback() -> None:
    client = RecordingChatClient()
    seen: list[str | None] = []

    def next_message(*, feedback: str | None, **kwargs: Any) -> str:
        seen.append(feedback)
        return "continue"

    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                should_continue=lambda *, iteration, **kwargs: iteration < 2,
                next_message=next_message,
            )
        ],
    )

    await agent.run("task")

    assert seen == [None]


async def test_inject_progress_false_exposes_kwarg_without_injecting() -> None:
    client = RecordingChatClient()
    seen: list[list[str]] = []

    def should_continue(*, iteration: int, progress: list[str], **kwargs: Any) -> bool:
        seen.append(list(progress))
        return iteration < 2

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(should_continue=should_continue, inject_progress=False)],
    )

    await agent.run("task")

    # ``should_continue`` is evaluated before this iteration's entry is recorded, so it sees the
    # log from prior iterations: empty on the first pass, the first entry on the second.
    assert seen == [[], ["response to: task"]]
    # ...but nothing is injected into the next iteration's input.
    assert not any("Progress so far" in text for text in client.received_messages[1])


async def test_fresh_context_resets_to_original_task_plus_progress() -> None:
    client = RecordingChatClient()
    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                always_continue,
                max_iterations=2,
                fresh_context=True,
                record_feedback=lambda *, iteration, **kwargs: f"note-{iteration}",
            )
        ],
    )

    await agent.run("original task")

    # Fresh context restarts from the original task and carries the progress log forward.
    assert any("original task" in text for text in client.received_messages[1])
    assert any("note-1" in text for text in client.received_messages[1])


def test_restore_session_resets_to_snapshot() -> None:
    session = AgentSession(service_session_id="svc-baseline")
    session.state["k"] = "baseline"
    snapshot = session.to_dict()

    # Mutate as a run would: change the service id and working state.
    session.service_session_id = "svc-mutated"
    session.state["k"] = "mutated"
    session.state["added"] = "in-loop"

    AgentLoopMiddleware._restore_session(session, snapshot)

    assert session.service_session_id == "svc-baseline"
    assert session.state == {"k": "baseline"}
    # The same session_id is preserved (restored in place).
    assert session.session_id == AgentSession.from_dict(snapshot).session_id


async def test_fresh_context_with_session_resets_history() -> None:
    # With a local-history session, a non-fresh loop would re-feed the prior assistant turn into
    # the next iteration. fresh_context must snapshot the session and restore it between iterations
    # so the second run does not see iteration 1's response.
    client = RecordingChatClient(texts=["alpha", "beta"])
    session = AgentSession()
    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                always_continue,
                max_iterations=2,
                fresh_context=True,
                inject_progress=False,
            )
        ],
    )

    await agent.run("task", session=session)

    # The first iteration's assistant response ("alpha") must not leak into the second run's input.
    assert not any("alpha" in text for text in client.received_messages[1])
    assert any("task" in text for text in client.received_messages[1])


def _session_history_text(session: AgentSession) -> str:
    """Join all history messages stored under any provider key in the session state."""
    parts: list[str] = []
    for value in session.state.values():
        if isinstance(value, dict):
            for msg in value.get("messages", []):
                if isinstance(msg, Message):
                    parts.append(msg.text)
    return " | ".join(parts)


@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
@pytest.mark.parametrize("fresh_context", [False, True], ids=["accumulate", "fresh"])
@pytest.mark.parametrize("inject_progress", [False, True], ids=["no_progress", "progress"])
@pytest.mark.parametrize("store", [False, True], ids=["local", "service"])
async def test_fresh_context_session_matrix(
    stream: bool, fresh_context: bool, inject_progress: bool, store: bool
) -> None:
    """Validate session handling across the streaming x fresh_context x inject_progress x store matrix.

    The loop runs two iterations per ``agent.run`` (``max_iterations=2``) and we drive two runs on
    the same session. ``record_feedback`` emits a distinct ``note-<n>`` marker (not the response
    text) so the *session* observables (local history / service conversation id) stay decoupled from
    the in-memory progress log: ``r1i1``/``r1i2`` only ever reach the model through the session,
    while ``"Progress so far"`` only appears when ``inject_progress`` injects the log.

    Expectations:
    * Within a run, ``fresh_context`` restores the pre-loop baseline before each later iteration, so
      iteration 2 does not see iteration 1's output; without it, context accumulates.
    * After a run the session reflects the *final* iteration's pass (it is not reset to the
      pre-loop baseline), so the next ``agent.run`` continues from there regardless of
      ``fresh_context``.
    * ``inject_progress`` controls whether the progress log is injected into later iterations'
      input, independently of the session axes.
    """
    # Four client calls total: run1[iter1, iter2], run2[iter1, iter2].
    client = RecordingChatClient(texts=["r1i1", "r1i2", "r2i1", "r2i2"], service_mode=store)

    def make_agent() -> Agent[Any]:
        return Agent(
            client=client,
            middleware=[
                AgentLoopMiddleware(
                    always_continue,
                    max_iterations=2,
                    fresh_context=fresh_context,
                    inject_progress=inject_progress,
                    record_feedback=lambda *, iteration, **kwargs: f"note-{iteration}",
                )
            ],
        )

    session = AgentSession()

    async def run(agent: Agent[Any], text: str) -> None:
        if stream:
            async for _ in agent.run(text, session=session, stream=True):
                pass
        else:
            await agent.run(text, session=session)

    await run(make_agent(), "task-1")
    history_after_run1 = _session_history_text(session)
    svc_after_run1 = session.service_session_id
    await run(make_agent(), "task-2")
    history_after_run2 = _session_history_text(session)
    svc_after_run2 = session.service_session_id

    # Exactly four model calls were made (two iterations per run, no function calling).
    assert len(client.received_messages) == 4
    r1i2_in = client.received_messages[1]
    r2i1_in = client.received_messages[2]
    r2i2_in = client.received_messages[3]

    # inject_progress controls whether the progress log is injected into later iterations' input,
    # independently of every other axis.
    if inject_progress:
        assert any("Progress so far" in text for text in r1i2_in)
        assert any("note-1" in text for text in r1i2_in)
        assert any("Progress so far" in text for text in r2i2_in)
    else:
        assert not any("Progress so far" in text for text in r1i2_in)
        assert not any("Progress so far" in text for text in r2i2_in)

    if store:
        # Service-side storage: history lives behind a conversation id, not in local state.
        # conv-1..conv-4 are minted across the four calls; the session holds the latest per run.
        assert client.received_conversation_ids[0] is None  # run1 iter1: clean baseline
        assert svc_after_run1 == "conv-2"  # run1 persisted its final (iter2) pass
        assert client.received_conversation_ids[2] == "conv-2"  # run2 continues from run1's final
        assert svc_after_run2 == "conv-4"  # run2 persisted its final (iter2) pass
        if fresh_context:
            # Each later iteration is restored to that run's pre-loop baseline conversation id.
            assert client.received_conversation_ids[1] is None  # run1 iter2 reset to baseline
            assert client.received_conversation_ids[3] == "conv-2"  # run2 iter2 reset to run2 baseline
        else:
            # Conversation id threads forward across iterations within a run.
            assert client.received_conversation_ids[1] == "conv-1"
            assert client.received_conversation_ids[3] == "conv-3"
    else:
        # Local history: prior turns are replayed into later calls via the session state. The
        # progress log carries note-<n> markers, so r1i1/r1i2 reach the model only via the session.
        # Cross-run continuity always holds: run2 sees run1's final (iter2) response.
        assert any("r1i2" in text for text in r2i1_in)
        assert "r1i2" in history_after_run1
        assert "r1i2" in history_after_run2
        if fresh_context:
            # Within a run, iteration 2 is restored to the baseline and does not see iteration 1.
            assert not any("r1i1" in text for text in r1i2_in)
            assert not any("r2i1" in text for text in r2i2_in)
            # The intermediate (iter1) pass is discarded; only the final pass is persisted.
            assert "r1i1" not in history_after_run1
        else:
            # Without fresh_context, iteration 2 sees iteration 1's accumulated turn.
            assert any("r1i1" in text for text in r1i2_in)
            assert any("r2i1" in text for text in r2i2_in)
            assert "r1i1" in history_after_run1


class _Answer(BaseModel):
    name: str


@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
@pytest.mark.parametrize("return_final_only", [False, True], ids=["aggregate", "final_only"])
@pytest.mark.parametrize("fresh_context", [False, True], ids=["accumulate", "fresh"])
async def test_response_format_parsed_across_loop(stream: bool, return_final_only: bool, fresh_context: bool) -> None:
    """A response_format set on the agent is applied every iteration and parsed on the final result.

    Each iteration returns a *different* valid JSON object. The aggregated (``return_final_only=False``)
    non-streaming response concatenates every iteration's text plus the injected nudges, which is not
    valid JSON on its own; ``.value`` must still return the final iteration's pre-parsed object rather
    than attempting (and failing) to re-parse the combined text.
    """
    client = RecordingChatClient(
        texts=['{"name": "first"}', '{"name": "final"}'],
        honor_response_format=True,
    )
    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                always_continue,
                max_iterations=2,
                fresh_context=fresh_context,
                return_final_only=return_final_only,
            )
        ],
    )

    if stream:
        run_stream = agent.run("question", options={"response_format": _Answer}, stream=True)
        async for _ in run_stream:
            pass
        result = await run_stream.get_final_response()
    else:
        result = await agent.run("question", options={"response_format": _Answer})

    # The response_format is forwarded to every iteration, so each response is parsed independently.
    assert client.received_response_formats == [_Answer, _Answer]
    # The structured value reflects the final iteration and is not re-derived from aggregated text.
    assert result.value == _Answer(name="final")


async def test_should_continue_marker_stops_loop_early() -> None:
    client = RecordingChatClient(texts=["working <promise>COMPLETE</promise>"])

    def should_continue(*, last_result: AgentResponse, **kwargs: Any) -> bool:
        return "<promise>COMPLETE</promise>" not in last_result.text

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(should_continue, max_iterations=10)],
    )

    await agent.run("task")

    assert client.call_count == 1


async def test_should_continue_callable_stops_loop_early() -> None:
    client = RecordingChatClient()

    def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        return iteration < 2

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue, max_iterations=10)])

    await agent.run("task")

    assert client.call_count == 2


async def test_resolve_next_message_injects_full_log_without_session() -> None:
    mw = AgentLoopMiddleware(always_continue, max_iterations=5)
    loop_kwargs: dict[str, Any] = {
        "progress": ["e1", "e2"],
        "session": None,
        "iteration": 1,
        "last_result": None,
        "messages": [],
        "original_messages": [],
        "agent": None,
    }

    result = await mw._resolve_next_message(
        loop_kwargs,
        messages_used=[Message(role="user", contents=["x"])],
        original_messages=[Message(role="user", contents=["orig"])],
    )

    progress_text = result[0].text
    assert "e1" in progress_text
    assert "e2" in progress_text


async def test_resolve_next_message_injects_latest_entry_with_session() -> None:
    mw = AgentLoopMiddleware(always_continue, max_iterations=5)
    loop_kwargs: dict[str, Any] = {
        "progress": ["e1", "e2"],
        "session": object(),
        "iteration": 1,
        "last_result": None,
        "messages": [],
        "original_messages": [],
        "agent": None,
    }

    result = await mw._resolve_next_message(
        loop_kwargs,
        messages_used=[Message(role="user", contents=["x"])],
        original_messages=[Message(role="user", contents=["orig"])],
    )

    progress_text = result[0].text
    assert "e2" in progress_text
    assert "e1" not in progress_text


# region judge mode


async def test_judge_stops_when_answered_on_first_pass() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["VERDICT: DONE"])

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 1
    assert judge_client.call_count == 1


async def test_judge_continues_until_answered() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["VERDICT: MORE", "VERDICT: DONE"])

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 2
    assert judge_client.call_count == 2


async def test_judge_text_fallback_negative_verdict_keeps_looping() -> None:
    """Regression: a negative verdict in the text fallback must not be read as success.

    ``{"answered": false}`` upper-cases to contain the substring ``ANSWERED`` and not
    ``NOT_ANSWERED``; the non-overlapping ``VERDICT: MORE`` marker keeps the loop running rather
    than stopping on the incomplete answer.
    """
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(
        texts=['{"answered": false}\nVERDICT: MORE', '{"answered": true}\nVERDICT: DONE'],
    )

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 2
    assert judge_client.call_count == 2


async def test_judge_text_fallback_without_marker_keeps_looping() -> None:
    """A fallback reply with no recognizable verdict marker keeps the loop running until the cap."""
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["The response looks reasonable."] * 20)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == DEFAULT_JUDGE_MAX_ITERATIONS


async def test_judge_respects_default_max_iterations() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["VERDICT: MORE"] * 20)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("never done")

    assert agent_client.call_count == DEFAULT_JUDGE_MAX_ITERATIONS


async def test_judge_requests_structured_output() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true}'], honor_response_format=True)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert judge_client.received_response_formats == [JudgeVerdict]


async def test_judge_uses_structured_value_to_stop() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true, "reasoning": "done"}'], honor_response_format=True)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 1
    assert judge_client.call_count == 1


async def test_judge_uses_structured_value_to_continue() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(
        texts=['{"answered": false}', '{"answered": true}'],
        honor_response_format=True,
    )

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 2
    assert judge_client.call_count == 2


async def test_judge_feedback_is_returned_to_agent() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(
        texts=[
            '{"answered": false, "reasoning": "Mention the moon too."}',
            '{"answered": true, "reasoning": "Looks complete."}',
        ],
        honor_response_format=True,
    )

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("explain the night sky")

    # The judge's reasoning from the first verdict is injected into the second iteration's input.
    assert agent_client.call_count == 2
    assert any("Mention the moon too." in text for text in agent_client.received_messages[1])


async def test_judge_criteria_injects_agent_instruction_and_judge_criteria() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true}'], honor_response_format=True)

    agent = Agent(
        client=agent_client,
        middleware=[
            AgentLoopMiddleware.with_judge(
                judge_client,
                criteria=["Mentions the moon", "Cites a source"],
            )
        ],
    )

    await agent.run("explain the night sky")

    # The criteria are injected as an extra instruction for the agent on its first run.
    assert any("Mentions the moon" in text for text in agent_client.received_messages[0])
    assert any("Cites a source" in text for text in agent_client.received_messages[0])
    # ...and rendered into the judge instructions (the judge's first message is its system prompt).
    assert "Mentions the moon" in judge_client.received_messages[0][0]
    assert "Cites a source" in judge_client.received_messages[0][0]


async def test_judge_custom_instructions_template_substitutes_criteria() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true}'], honor_response_format=True)

    agent = Agent(
        client=agent_client,
        middleware=[
            AgentLoopMiddleware.with_judge(
                judge_client,
                instructions="Judge strictly. Criteria:{{criteria}}",
                criteria=["Is concise"],
            )
        ],
    )

    await agent.run("write a haiku")

    system_prompt = judge_client.received_messages[0][0]
    assert "Judge strictly." in system_prompt
    assert "Is concise" in system_prompt
    assert "{{criteria}}" not in system_prompt


async def test_judge_without_criteria_strips_placeholder() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true}'], honor_response_format=True)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware.with_judge(judge_client)])

    await agent.run("solve it")

    # The default instructions contain the placeholder, which is removed when no criteria are given.
    assert "{{criteria}}" not in judge_client.received_messages[0][0]
    # No extra system instruction is injected for the agent.
    assert not any("must satisfy all of the following criteria" in text for text in agent_client.received_messages[0])


async def test_additional_instructions_injected_as_system_message() -> None:
    client = RecordingChatClient()
    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
                always_continue,
                max_iterations=2,
                fresh_context=True,
                additional_instructions="Be terse.",
            )
        ],
    )

    await agent.run("hello")

    # The extra instruction is injected ahead of the input and preserved across fresh_context resets.
    assert any("Be terse." in text for text in client.received_messages[0])
    assert any("Be terse." in text for text in client.received_messages[1])


# region provider helpers


def test_background_tasks_running_helper_reflects_state() -> None:
    from agent_framework import BackgroundAgentsProvider

    provider_source = "background_agents"

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)
    predicate = background_tasks_running()

    # No tasks -> not running.
    assert predicate(session=session, agent=agent) is False

    running = BackgroundTaskInfo(
        id=1,
        agent_name="worker",
        description="job",
        status=BackgroundTaskStatus.RUNNING,
    )
    session.state[provider_source] = {"next_task_id": 2, "tasks": [running.to_dict()]}
    assert predicate(session=session, agent=agent) is True

    completed = BackgroundTaskInfo(
        id=1,
        agent_name="worker",
        description="job",
        status=BackgroundTaskStatus.COMPLETED,
    )
    session.state[provider_source] = {"next_task_id": 2, "tasks": [completed.to_dict()]}
    assert predicate(session=session, agent=agent) is False


def test_background_tasks_running_helper_requires_session_agent_and_provider() -> None:
    from agent_framework import BackgroundAgentsProvider

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    session = AgentSession()
    session.state["background_agents"] = {
        "next_task_id": 2,
        "tasks": [
            BackgroundTaskInfo(
                id=1, agent_name="worker", description="job", status=BackgroundTaskStatus.RUNNING
            ).to_dict()
        ],
    }
    predicate = background_tasks_running()

    # Missing session or agent -> False.
    assert predicate(session=None, agent=_FakeHarnessAgent(provider)) is False
    assert predicate(session=session, agent=None) is False
    # Agent without a BackgroundAgentsProvider -> False.
    assert predicate(session=session, agent=_FakeHarnessAgent()) is False


def test_background_tasks_running_message_lists_running_tasks() -> None:
    from agent_framework import BackgroundAgentsProvider

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)
    session.state["background_agents"] = {
        "next_task_id": 4,
        "tasks": [
            BackgroundTaskInfo(
                id=1, agent_name="worker", description="first job", status=BackgroundTaskStatus.RUNNING
            ).to_dict(),
            BackgroundTaskInfo(
                id=2, agent_name="worker", description="done job", status=BackgroundTaskStatus.COMPLETED
            ).to_dict(),
            BackgroundTaskInfo(
                id=3, agent_name="worker", description="third job", status=BackgroundTaskStatus.RUNNING
            ).to_dict(),
        ],
    }

    message = background_tasks_running_message(session=session, agent=agent)
    assert message is not None
    assert "2 background task(s) running" in message
    assert "#1 (worker): first job" in message
    assert "#3 (worker): third job" in message
    assert "done job" not in message


def test_background_tasks_running_message_returns_none_when_idle() -> None:
    from agent_framework import BackgroundAgentsProvider

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)

    # No running tasks at all.
    assert background_tasks_running_message(session=session, agent=agent) is None
    # Missing session/agent/provider -> None.
    assert background_tasks_running_message(session=None, agent=agent) is None
    assert background_tasks_running_message(session=session, agent=None) is None
    assert background_tasks_running_message(session=session, agent=_FakeHarnessAgent()) is None


# region todos_remaining / todos_remaining_message helpers


class _FakeHarnessAgent:
    """Minimal stand-in for a harness agent exposing built-in context providers."""

    def __init__(self, *providers: Any) -> None:
        self.context_providers = list(providers)


async def _save_todos(provider: TodoProvider, session: AgentSession, items: list[TodoItem]) -> None:
    await provider.store.save_state(
        session,
        items,
        next_id=len(items) + 1,
        source_id=provider.source_id,
    )


async def test_todos_remaining_reflects_store_state() -> None:
    provider = TodoProvider()
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)
    predicate = todos_remaining()

    # No items yet -> nothing to continue for.
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is False

    await _save_todos(provider, session, [TodoItem(id=1, title="open", is_complete=False)])
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is True

    await _save_todos(provider, session, [TodoItem(id=1, title="open", is_complete=True)])
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is False


async def test_todos_remaining_requires_session_agent_and_provider() -> None:
    provider = TodoProvider()
    session = AgentSession()
    await _save_todos(provider, session, [TodoItem(id=1, title="open", is_complete=False)])

    predicate = todos_remaining()
    # Missing session or agent -> False.
    assert await _resolve_should_continue_result(predicate(session=None, agent=_FakeHarnessAgent(provider))) is False
    assert await _resolve_should_continue_result(predicate(session=session, agent=None)) is False
    # Agent without a TodoProvider -> False.
    assert await _resolve_should_continue_result(predicate(session=session, agent=_FakeHarnessAgent())) is False


async def test_todos_remaining_mode_gating() -> None:
    provider = TodoProvider()
    mode_provider = AgentModeProvider()
    session = AgentSession()
    agent = _FakeHarnessAgent(provider, mode_provider)
    await _save_todos(provider, session, [TodoItem(id=1, title="open", is_complete=False)])

    predicate = todos_remaining(looping_modes=["execute"])

    # Default mode is "plan" -> not in allowed modes -> False even with open todos.
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is False

    set_agent_mode(session, "execute")
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is True

    # Case-insensitive matching.
    predicate_upper = todos_remaining(looping_modes=["EXECUTE"])
    assert await _resolve_should_continue_result(predicate_upper(session=session, agent=agent)) is True


async def test_todos_remaining_modes_none_ignores_mode() -> None:
    provider = TodoProvider()
    mode_provider = AgentModeProvider()
    session = AgentSession()
    agent = _FakeHarnessAgent(provider, mode_provider)
    await _save_todos(provider, session, [TodoItem(id=1, title="open", is_complete=False)])

    predicate = todos_remaining(looping_modes=None)
    # "plan" mode still loops because no mode gating is applied.
    assert await _resolve_should_continue_result(predicate(session=session, agent=agent)) is True


def test_todos_remaining_rejects_empty_modes() -> None:
    with pytest.raises(ValueError):
        todos_remaining(looping_modes=[])


async def test_todos_remaining_message_lists_open_items() -> None:
    provider = TodoProvider()
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)
    await _save_todos(
        provider,
        session,
        [
            TodoItem(id=1, title="first", is_complete=False),
            TodoItem(id=2, title="second", is_complete=True),
            TodoItem(id=3, title="third", is_complete=False),
        ],
    )

    message = await todos_remaining_message(session=session, agent=agent)
    assert message is not None
    assert "2 open todo item(s)" in message
    assert "- first" in message
    assert "- third" in message
    assert "second" not in message


async def test_todos_remaining_message_returns_none_when_unavailable() -> None:
    provider = TodoProvider()
    session = AgentSession()
    agent = _FakeHarnessAgent(provider)

    # No session / agent.
    assert await todos_remaining_message(session=None, agent=agent) is None
    assert await todos_remaining_message(session=session, agent=None) is None
    # Agent without a TodoProvider.
    assert await todos_remaining_message(session=session, agent=_FakeHarnessAgent()) is None
    # All todos complete -> nothing to remind about.
    await _save_todos(provider, session, [TodoItem(id=1, title="done", is_complete=True)])
    assert await todos_remaining_message(session=session, agent=agent) is None


# region streaming behavior


async def test_streaming_reyields_updates_and_final_is_last_iteration() -> None:
    client = RecordingChatClient(texts=["first", "second"])

    def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        return iteration < 2

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue=should_continue)])

    stream = agent.run("go", stream=True)
    updates = [update async for update in stream]
    final = await stream.get_final_response()

    texts = "".join(u.text for u in updates if u.text)
    assert "first" in texts
    assert "second" in texts
    # Final response reflects the last iteration only.
    assert "second" in final.text
    assert "first" not in final.text
    assert client.call_count == 2


async def test_streaming_injects_nudge_messages_as_user_updates() -> None:
    client = RecordingChatClient(texts=["first", "second"])
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(always_continue, max_iterations=2)])

    stream = agent.run("go", stream=True)
    updates = [update async for update in stream]
    await stream.get_final_response()

    # The nudge that drives the second iteration is surfaced as a user update in the stream.
    user_texts = [u.text for u in updates if u.role == "user"]
    assert any(DEFAULT_NEXT_MESSAGE in text for text in user_texts)


async def test_streaming_stops_at_max_iterations() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(always_continue, max_iterations=2)])

    stream = agent.run("go", stream=True)
    _ = [update async for update in stream]
    await stream.get_final_response()

    assert client.call_count == 2


async def test_streaming_should_continue_marker_stops_and_injects_progress() -> None:
    client = RecordingChatClient(texts=["progress made", "all <promise>COMPLETE</promise>"])

    def should_continue(*, last_result: AgentResponse, **kwargs: Any) -> bool:
        return "<promise>COMPLETE</promise>" not in last_result.text

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(should_continue, max_iterations=10)],
    )

    stream = agent.run("go", stream=True)
    _ = [update async for update in stream]
    await stream.get_final_response()

    # Loop stops once the marker appears (second iteration), not at max_iterations.
    assert client.call_count == 2
    # The first iteration's feedback was injected into the second iteration's input.
    assert any("progress made" in text for text in client.received_messages[1])


async def test_streaming_middleware_termination_stops_cleanly() -> None:
    client = RecordingChatClient(texts=["only"])

    class TerminateOnSecond(AgentMiddleware):
        def __init__(self) -> None:
            self.calls = 0

        async def process(self, context: AgentContext, call_next: Any) -> None:
            self.calls += 1
            if self.calls >= 2:
                raise MiddlewareTermination
            await call_next()

    terminator = TerminateOnSecond()
    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(always_continue, max_iterations=5), terminator],
    )

    stream = agent.run("go", stream=True)
    updates = [update async for update in stream]
    final = await stream.get_final_response()

    # First iteration completed; the second was terminated before producing output.
    assert client.call_count == 1
    assert terminator.calls == 2
    assert "only" in final.text
    assert any("only" in (u.text or "") for u in updates)


# region approval escape hatch


def _approval_request_content() -> Content:
    """Build a pending tool-approval request content (as a downstream approval middleware would)."""
    return Content.from_function_approval_request(
        id="call-1",
        function_call=Content.from_function_call(call_id="call-1", name="write_file"),
    )


class _ApprovalChatClient(BaseChatClient[ChatOptions[None]]):
    """A minimal client that returns a pending approval request on its first call, text thereafter."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        first = self.call_count == 0
        contents: list[Any] = [_approval_request_content()] if first else [Content.from_text("done")]
        if stream:

            async def _gen() -> AsyncIterable[ChatResponseUpdate]:
                self.call_count += 1
                yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

            return ResponseStream(_gen(), finalizer=lambda updates: ChatResponse.from_updates(updates))

        async def _get() -> ChatResponse:
            self.call_count += 1
            return ChatResponse(messages=Message(role="assistant", contents=contents))

        return _get()


def test_has_pending_approval_request_detects_request() -> None:
    response = AgentResponse(messages=[Message(role="assistant", contents=[_approval_request_content()])])
    assert AgentLoopMiddleware._has_pending_approval_request(response) is True


def test_has_pending_approval_request_false_for_plain_response() -> None:
    response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
    assert AgentLoopMiddleware._has_pending_approval_request(response) is False
    assert AgentLoopMiddleware._has_pending_approval_request(None) is False


async def test_non_streaming_escape_hatch_stops_on_pending_approval() -> None:
    client = _ApprovalChatClient()
    calls: list[int] = []

    def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        calls.append(iteration)
        return True

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue, max_iterations=5)])

    response = await agent.run("write a file")

    # The loop stops after the first iteration because it carries a pending approval request,
    # before should_continue is evaluated and without injecting next_message.
    assert client.call_count == 1
    assert calls == []
    assert AgentLoopMiddleware._has_pending_approval_request(response) is True


async def test_streaming_escape_hatch_stops_on_pending_approval() -> None:
    client = _ApprovalChatClient()
    calls: list[int] = []

    def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        calls.append(iteration)
        return True

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue, max_iterations=5)])

    stream = agent.run("write a file", stream=True)
    _ = [update async for update in stream]
    final = await stream.get_final_response()

    assert client.call_count == 1
    assert calls == []
    assert AgentLoopMiddleware._has_pending_approval_request(final) is True
