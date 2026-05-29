# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Any

import pytest

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    AgentResponse,
    AgentSession,
    BackgroundTaskInfo,
    BackgroundTaskStatus,
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
    todos_remaining,
    tool,
)
from agent_framework._harness._loop import (
    DEFAULT_JUDGE_MAX_ITERATIONS,
    DEFAULT_NEXT_MESSAGE,
    AgentLoopMiddleware,
)


class RecordingChatClient:
    """A minimal chat client that records inputs and returns scripted responses."""

    def __init__(self, *, texts: list[str] | None = None, honor_response_format: bool = False) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.call_count: int = 0
        self.received_messages: list[list[str]] = []
        self.received_response_formats: list[Any] = []
        self._texts = list(texts) if texts is not None else []
        self._honor_response_format = honor_response_format

    def _next_text(self, messages: Sequence[Message]) -> str:
        if self._texts:
            return self._texts.pop(0)
        last = messages[-1].text if messages else ""
        return f"response to: {last}"

    def get_response(
        self,
        messages: Any,
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        normalized = messages if isinstance(messages, list) else [messages]
        self.received_messages.append([m.text for m in normalized if isinstance(m, Message)])
        response_format = options.get("response_format") if options else None
        self.received_response_formats.append(response_format)
        if stream:
            return self._stream(normalized)

        async def _get() -> ChatResponse:
            self.call_count += 1
            return ChatResponse(
                messages=Message(role="assistant", contents=[self._next_text(normalized)]),
                response_format=response_format if self._honor_response_format else None,
            )

        return _get()

    def _stream(self, messages: Sequence[Message]) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _gen() -> AsyncIterable[ChatResponseUpdate]:
            self.call_count += 1
            text = self._next_text(messages)
            yield ChatResponseUpdate(contents=[Content.from_text(text)], role="assistant", finish_reason="stop")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            return ChatResponse.from_updates(updates)

        return ResponseStream(_gen(), finalizer=_finalize)


# region construction / validation


def test_rejects_should_continue_and_judge_together() -> None:
    with pytest.raises(ValueError, match="not both"):
        AgentLoopMiddleware(should_continue=lambda **kwargs: True, judge_client=RecordingChatClient())


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_max_iterations(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        AgentLoopMiddleware(max_iterations=bad)


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_max_approval_rounds(bad: int) -> None:
    with pytest.raises(ValueError, match="max_approval_rounds"):
        AgentLoopMiddleware(max_approval_rounds=bad)


def test_judge_mode_default_max_iterations() -> None:
    middleware = AgentLoopMiddleware(judge_client=RecordingChatClient())
    assert middleware.max_iterations == DEFAULT_JUDGE_MAX_ITERATIONS


def test_judge_mode_explicit_unbounded() -> None:
    middleware = AgentLoopMiddleware(judge_client=RecordingChatClient(), max_iterations=None)
    assert middleware.max_iterations is None


def test_default_is_unbounded() -> None:
    assert AgentLoopMiddleware().max_iterations is None


def test_ralph_factory_configures_feedback_loop() -> None:
    record = lambda *, iteration, **kwargs: f"note-{iteration}"  # noqa: E731
    mw = AgentLoopMiddleware.ralph(
        max_iterations=4,
        record_feedback=record,
        fresh_context=True,
        is_complete="<promise>COMPLETE</promise>",
    )

    assert isinstance(mw, AgentLoopMiddleware)
    assert mw.max_iterations == 4
    assert mw.record_feedback is record
    assert mw.fresh_context is True
    assert mw.is_complete == "<promise>COMPLETE</promise>"
    assert mw.should_continue is None


def test_with_predicate_factory_sets_should_continue() -> None:
    predicate = lambda *, iteration, **kwargs: iteration < 3  # noqa: E731
    mw = AgentLoopMiddleware.with_predicate(predicate, max_iterations=5)

    assert mw.should_continue is predicate
    assert mw.max_iterations == 5


def test_with_judge_factory_builds_judge_condition() -> None:
    mw = AgentLoopMiddleware.with_judge(RecordingChatClient())

    # The judge client is wrapped into a should_continue predicate.
    assert mw.should_continue is not None
    assert mw.max_iterations == DEFAULT_JUDGE_MAX_ITERATIONS


# region non-streaming behavior


async def test_ralph_loop_stops_at_max_iterations() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(max_iterations=3)])

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


async def test_default_next_message_nudge_is_used() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(max_iterations=2)])

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
        middleware=[AgentLoopMiddleware(max_iterations=2, next_message=next_message)],
    )

    await agent.run("original task")

    assert any("iteration 1 follow-up" in text for text in client.received_messages[1])


async def test_next_message_returning_none_reuses_messages() -> None:
    client = RecordingChatClient()

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(max_iterations=2, next_message=lambda **kwargs: None)],
    )

    await agent.run("only message")

    assert any("only message" in text for text in client.received_messages[1])


# region ralph feedback loop


async def test_record_feedback_callable_captures_and_injects_progress() -> None:
    client = RecordingChatClient()
    captured: list[list[str]] = []

    def record_feedback(*, iteration: int, progress: list[str], **kwargs: Any) -> str:
        captured.append(list(progress))
        return f"step-{iteration}-done"

    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(max_iterations=3, record_feedback=record_feedback)],
    )

    await agent.run("task")

    # The progress passed to record_feedback reflects prior iterations, not the entry it produces.
    assert captured == [[], ["step-1-done"], ["step-1-done", "step-2-done"]]
    # With no session the full accumulated log is injected into later iterations' input.
    assert any("step-1-done" in text for text in client.received_messages[1])
    assert any("step-2-done" in text for text in client.received_messages[2])


async def test_feedback_fallback_records_response_text() -> None:
    client = RecordingChatClient(texts=["first answer", "second answer"])
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(max_iterations=2)])

    await agent.run("task")

    # Without a record_feedback callable, the response text becomes the progress entry.
    assert any("first answer" in text for text in client.received_messages[1])


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

    # The progress kwarg is still populated for callables...
    assert seen[0] == ["response to: task"]
    # ...but nothing is injected into the next iteration's input.
    assert not any("Progress so far" in text for text in client.received_messages[1])


async def test_fresh_context_resets_to_original_task_plus_progress() -> None:
    client = RecordingChatClient()
    agent = Agent(
        client=client,
        middleware=[
            AgentLoopMiddleware(
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


async def test_completion_marker_string_stops_loop_early() -> None:
    client = RecordingChatClient(texts=["working <promise>COMPLETE</promise>"])
    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(max_iterations=10, is_complete="<promise>COMPLETE</promise>")],
    )

    await agent.run("task")

    assert client.call_count == 1


async def test_completion_callable_stops_loop_early() -> None:
    client = RecordingChatClient()

    def is_complete(*, iteration: int, **kwargs: Any) -> bool:
        return iteration >= 2

    agent = Agent(client=client, middleware=[AgentLoopMiddleware(max_iterations=10, is_complete=is_complete)])

    await agent.run("task")

    assert client.call_count == 2


async def test_resolve_next_message_injects_full_log_without_session() -> None:
    mw = AgentLoopMiddleware(max_iterations=5)
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
    mw = AgentLoopMiddleware(max_iterations=5)
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
    judge_client = RecordingChatClient(texts=["ANSWERED"])

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 1
    assert judge_client.call_count == 1


async def test_judge_continues_until_answered() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["NOT_ANSWERED", "ANSWERED"])

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 2
    assert judge_client.call_count == 2


async def test_judge_respects_default_max_iterations() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=["NOT_ANSWERED"] * 20)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("never done")

    assert agent_client.call_count == DEFAULT_JUDGE_MAX_ITERATIONS


async def test_judge_requests_structured_output() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true}'], honor_response_format=True)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("solve it")

    assert judge_client.received_response_formats == [JudgeVerdict]


async def test_judge_uses_structured_value_to_stop() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(texts=['{"answered": true, "reasoning": "done"}'], honor_response_format=True)

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 1
    assert judge_client.call_count == 1


async def test_judge_uses_structured_value_to_continue() -> None:
    agent_client = RecordingChatClient()
    judge_client = RecordingChatClient(
        texts=['{"answered": false}', '{"answered": true}'],
        honor_response_format=True,
    )

    agent = Agent(client=agent_client, middleware=[AgentLoopMiddleware(judge_client=judge_client)])

    await agent.run("solve it")

    assert agent_client.call_count == 2
    assert judge_client.call_count == 2


# region provider helpers


async def test_todos_remaining_helper_reflects_store_state() -> None:
    provider = TodoProvider()
    session = AgentSession()
    predicate = todos_remaining(provider)

    # No items yet -> nothing to continue for.
    assert await predicate(session=session) is False

    await provider.store.save_state(
        session,
        [TodoItem(id=1, title="open item", is_complete=False)],
        next_id=2,
        source_id=provider.source_id,
    )
    assert await predicate(session=session) is True

    await provider.store.save_state(
        session,
        [TodoItem(id=1, title="open item", is_complete=True)],
        next_id=2,
        source_id=provider.source_id,
    )
    assert await predicate(session=session) is False


async def test_todos_remaining_helper_without_session() -> None:
    predicate = todos_remaining(TodoProvider())
    assert await predicate(session=None) is False


def test_background_tasks_running_helper_reflects_state() -> None:
    from agent_framework import BackgroundAgentsProvider

    provider_source = "background_agents"

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]
    session = AgentSession()
    predicate = background_tasks_running(provider)

    # No tasks -> not running.
    assert predicate(session=session) is False

    running = BackgroundTaskInfo(
        id=1,
        agent_name="worker",
        description="job",
        status=BackgroundTaskStatus.RUNNING,
    )
    session.state[provider_source] = {"next_task_id": 2, "tasks": [running.to_dict()]}
    assert predicate(session=session) is True

    completed = BackgroundTaskInfo(
        id=1,
        agent_name="worker",
        description="job",
        status=BackgroundTaskStatus.COMPLETED,
    )
    session.state[provider_source] = {"next_task_id": 2, "tasks": [completed.to_dict()]}
    assert predicate(session=session) is False


def test_background_tasks_running_helper_without_session() -> None:
    from agent_framework import BackgroundAgentsProvider

    class _DummyAgent:
        name = "worker"
        description = "does work"

        def run(self, *args: Any, **kwargs: Any) -> Any: ...

    provider = BackgroundAgentsProvider([_DummyAgent()])  # type: ignore[list-item]
    predicate = background_tasks_running(provider)
    assert predicate(session=None) is False


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


async def test_streaming_stops_at_max_iterations() -> None:
    client = RecordingChatClient()
    agent = Agent(client=client, middleware=[AgentLoopMiddleware(max_iterations=2)])

    stream = agent.run("go", stream=True)
    _ = [update async for update in stream]
    await stream.get_final_response()

    assert client.call_count == 2


async def test_streaming_completion_marker_stops_and_injects_progress() -> None:
    client = RecordingChatClient(texts=["progress made", "all <promise>COMPLETE</promise>"])
    agent = Agent(
        client=client,
        middleware=[AgentLoopMiddleware(max_iterations=10, is_complete="<promise>COMPLETE</promise>")],
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
        middleware=[AgentLoopMiddleware(max_iterations=5), terminator],
    )

    stream = agent.run("go", stream=True)
    updates = [update async for update in stream]
    final = await stream.get_final_response()

    # First iteration completed; the second was terminated before producing output.
    assert client.call_count == 1
    assert terminator.calls == 2
    assert "only" in final.text
    assert any("only" in (u.text or "") for u in updates)


# region approval handling


def _approval_tool() -> tuple[Any, dict[str, int]]:
    """Build a tool requiring approval plus a counter dict tracking executions."""
    state = {"executions": 0}

    @tool(name="risky_op", approval_mode="always_require")
    def risky_op(target: str) -> str:
        state["executions"] += 1
        return f"did {target}"

    return risky_op, state


def _func_call_response(call_id: str = "1", target: str = "prod") -> ChatResponse:
    return ChatResponse(
        messages=Message(
            role="assistant",
            contents=[Content.from_function_call(call_id=call_id, name="risky_op", arguments={"target": target})],
        )
    )


async def test_approval_bool_approve_executes_tool_and_exempt_from_max_iterations(
    chat_client_base: Any,
) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [
        _func_call_response(),
        ChatResponse(messages=Message(role="assistant", contents=["all done"])),
    ]

    calls: list[str] = []

    def on_approval_request(*, request: Content, **kwargs: Any) -> bool:
        calls.append(request.type)
        return True

    # max_iterations=1 proves the approval-resolution run is exempt: two model calls still happen.
    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=on_approval_request)],
    )

    response = await agent.run("please do prod")

    assert calls == ["function_approval_request"]
    assert state["executions"] == 1
    assert chat_client_base.call_count == 2
    assert "all done" in response.text
    assert response.user_input_requests == []


async def test_approval_bool_reject_does_not_execute_tool(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [
        _func_call_response(),
        ChatResponse(messages=Message(role="assistant", contents=["understood, skipped"])),
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=lambda **kwargs: False)],
    )

    response = await agent.run("please do prod")

    assert state["executions"] == 0
    assert "skipped" in response.text


async def test_approval_returns_content_directly(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [
        _func_call_response(),
        ChatResponse(messages=Message(role="assistant", contents=["completed"])),
    ]

    def on_approval_request(*, request: Content, **kwargs: Any) -> Content:
        return request.to_function_approval_response(approved=True)

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=on_approval_request)],
    )

    await agent.run("please do prod")

    assert state["executions"] == 1


async def test_approval_none_falls_through_and_leaves_request_pending(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [_func_call_response()]

    calls: list[str] = []

    def on_approval_request(*, request: Content, **kwargs: Any) -> None:
        calls.append(request.type)
        return

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=on_approval_request)],
    )

    response = await agent.run("please do prod")

    # No decision -> nothing submitted, normal continuation stops the loop, request stays pending.
    assert calls == ["function_approval_request"]
    assert state["executions"] == 0
    assert len(response.user_input_requests) == 1
    assert chat_client_base.call_count == 1


async def test_approval_compose_with_should_continue(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [
        _func_call_response(),
        ChatResponse(messages=Message(role="assistant", contents=["finished"])),
    ]

    work_iterations: list[int] = []

    def should_continue(*, iteration: int, **kwargs: Any) -> bool:
        work_iterations.append(iteration)
        return False

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(should_continue=should_continue, on_approval_request=lambda **kwargs: True)],
    )

    response = await agent.run("please do prod")

    # Approval handled first (exempt), then should_continue governs the work run and stops.
    assert state["executions"] == 1
    assert "finished" in response.text
    assert len(work_iterations) == 1


async def test_approval_max_approval_rounds_stops_loop(chat_client_base: Any) -> None:
    risky_op, _ = _approval_tool()
    # Every model call asks for another approval, so the loop only stops via max_approval_rounds.
    chat_client_base.run_responses = [_func_call_response(call_id=str(i)) for i in range(10)]

    calls: list[str] = []

    def on_approval_request(*, request: Content, **kwargs: Any) -> bool:
        calls.append(request.type)
        return True

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_approval_rounds=2, on_approval_request=on_approval_request)],
    )

    response = await agent.run("please do prod")

    # Rounds 1 and 2 submit responses; round 3 trips the cap (callback invoked, then stop).
    assert len(calls) == 3
    assert len(response.user_input_requests) == 1


async def test_approval_with_session(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.run_responses = [
        _func_call_response(),
        ChatResponse(messages=Message(role="assistant", contents=["done with session"])),
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=lambda **kwargs: True)],
    )
    session = agent.create_session()

    response = await agent.run("please do prod", session=session)

    assert state["executions"] == 1
    assert "done with session" in response.text


async def test_approval_parallel_requests_all_handled(chat_client_base: Any) -> None:
    state = {"executions": 0}

    @tool(name="op_a", approval_mode="always_require")
    def op_a(target: str) -> str:
        state["executions"] += 1
        return f"a:{target}"

    @tool(name="op_b", approval_mode="always_require")
    def op_b(target: str) -> str:
        state["executions"] += 1
        return f"b:{target}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="1", name="op_a", arguments={"target": "x"}),
                    Content.from_function_call(call_id="2", name="op_b", arguments={"target": "y"}),
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", contents=["both done"])),
    ]

    seen: list[str | None] = []

    def on_approval_request(*, request: Content, **kwargs: Any) -> bool:
        seen.append(request.function_call.name if request.function_call else None)
        return True

    agent = Agent(
        client=chat_client_base,
        tools=[op_a, op_b],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=on_approval_request)],
    )

    response = await agent.run("do both")

    assert sorted(filter(None, seen)) == ["op_a", "op_b"]
    assert state["executions"] == 2
    assert "both done" in response.text


async def test_approval_streaming_collects_requests_and_resolves(chat_client_base: Any) -> None:
    risky_op, state = _approval_tool()
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_function_call(call_id="1", name="risky_op", arguments='{"target":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[Content.from_function_call(call_id="1", name="risky_op", arguments='"prod"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[Content.from_text("streamed done")], role="assistant", finish_reason="stop")],
    ]

    calls: list[str] = []

    def on_approval_request(*, request: Content, **kwargs: Any) -> bool:
        calls.append(request.type)
        return True

    agent = Agent(
        client=chat_client_base,
        tools=[risky_op],
        middleware=[AgentLoopMiddleware(max_iterations=1, on_approval_request=on_approval_request)],
    )

    stream = agent.run("please do prod", stream=True)
    _ = [update async for update in stream]
    final = await stream.get_final_response()

    assert calls == ["function_approval_request"]
    assert state["executions"] == 1
    assert "streamed done" in final.text


# region approval helpers (unit)


def test_coerce_decision_bool_for_non_function_request_raises() -> None:
    middleware = AgentLoopMiddleware(on_approval_request=lambda **kwargs: True)
    oauth_request = Content.from_oauth_consent_request(consent_link="https://example.com/consent")
    with pytest.raises(ValueError, match="only valid for 'function_approval_request'"):
        middleware._coerce_decision(oauth_request, True)


def test_coerce_decision_content_id_mismatch_raises() -> None:
    middleware = AgentLoopMiddleware(on_approval_request=lambda **kwargs: True)
    request = Content.from_function_approval_request(
        id="req-1",
        function_call=Content.from_function_call(call_id="1", name="risky_op", arguments={}),
    )
    wrong = Content.from_function_approval_response(
        approved=True,
        id="req-2",
        function_call=Content.from_function_call(call_id="2", name="risky_op", arguments={}),
    )
    with pytest.raises(ValueError, match="does not match the request id"):
        middleware._coerce_decision(request, wrong)


def test_coerce_decision_invalid_type_raises() -> None:
    middleware = AgentLoopMiddleware(on_approval_request=lambda **kwargs: True)
    request = Content.from_function_approval_request(
        id="req-1",
        function_call=Content.from_function_call(call_id="1", name="risky_op", arguments={}),
    )
    with pytest.raises(TypeError, match="must return a bool, a Content, or None"):
        middleware._coerce_decision(request, "yes")  # type: ignore[arg-type]


def test_dedupe_requests_drops_duplicate_ids() -> None:
    middleware = AgentLoopMiddleware(on_approval_request=lambda **kwargs: True)
    fc = Content.from_function_call(call_id="1", name="risky_op", arguments={})
    a = Content.from_function_approval_request(id="dup", function_call=fc)
    b = Content.from_function_approval_request(id="dup", function_call=fc)
    c = Content.from_function_approval_request(id="other", function_call=fc)
    deduped = middleware._dedupe_requests([a, b, c])
    assert [r.id for r in deduped] == ["dup", "other"]
