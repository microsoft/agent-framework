# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from agent_framework import (
    Agent,
    AgentSession,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    SupportsChatGetResponse,
    ToolApprovalMiddleware,
    create_always_approve_tool_response,
    tool,
)


def _approval_requests(messages: list[Message]) -> list[Content]:
    return [
        content for message in messages for content in message.contents if content.type == "function_approval_request"
    ]


async def test_mixed_batch_hides_auto_approvable_request_until_approval_replay(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Mixed batches should only show real approval requests when a session can store hidden requests."""
    no_approval_calls = 0
    approval_calls = 0

    @tool(name="lookup_work_items", approval_mode="never_require")
    def lookup_work_items(query: str) -> str:
        nonlocal no_approval_calls
        no_approval_calls += 1
        return f"found {query}"

    @tool(name="add_comment", approval_mode="always_require")
    def add_comment(comment: str) -> str:
        nonlocal approval_calls
        approval_calls += 1
        return f"added {comment}"

    agent = Agent(client=chat_client_base, tools=[lookup_work_items, add_comment])
    session = AgentSession(session_id="approval-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_lookup",
                        name="lookup_work_items",
                        arguments='{"query": "mine"}',
                    ),
                    Content.from_function_call(
                        call_id="call_comment",
                        name="add_comment",
                        arguments='{"comment": "done"}',
                    ),
                ],
            )
        )
    ]

    first_response = await agent.run("update work item", session=session)

    requests = _approval_requests(first_response.messages)
    assert [request.function_call.name for request in requests] == ["add_comment"]
    assert no_approval_calls == 0
    assert approval_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["complete"]))]
    second_response = await agent.run(requests[0].to_function_approval_response(approved=True), session=session)

    assert second_response.text == "complete"
    assert no_approval_calls == 1
    assert approval_calls == 1


async def test_tool_approval_middleware_queues_multiple_approval_requests(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """The opt-in middleware should present multiple unresolved approvals one at a time."""
    first_calls = 0
    second_calls = 0

    @tool(name="first_tool", approval_mode="always_require")
    def first_tool() -> str:
        nonlocal first_calls
        first_calls += 1
        return "first"

    @tool(name="second_tool", approval_mode="always_require")
    def second_tool() -> str:
        nonlocal second_calls
        second_calls += 1
        return "second"

    agent = Agent(
        client=chat_client_base,
        tools=[first_tool, second_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="queue-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_first", name="first_tool", arguments="{}"),
                    Content.from_function_call(call_id="call_second", name="second_tool", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("call both", session=session)

    first_requests = _approval_requests(first_response.messages)
    assert [request.function_call.name for request in first_requests] == ["first_tool"]
    assert first_calls == 0
    assert second_calls == 0

    second_response = await agent.run(first_requests[0].to_function_approval_response(approved=True), session=session)

    second_requests = _approval_requests(second_response.messages)
    assert [request.function_call.name for request in second_requests] == ["second_tool"]
    assert first_calls == 0
    assert second_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(second_requests[0].to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert first_calls == 1
    assert second_calls == 1


async def test_tool_approval_middleware_preserves_hidden_mixed_batch_requests(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Middleware state saves should not discard core hidden auto-approvable requests."""
    lookup_calls = 0
    write_calls = 0

    @tool(name="lookup_records", approval_mode="never_require")
    def lookup_records() -> str:
        nonlocal lookup_calls
        lookup_calls += 1
        return "records"

    @tool(name="write_record", approval_mode="always_require")
    def write_record() -> str:
        nonlocal write_calls
        write_calls += 1
        return "written"

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_records, write_record],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="mixed-middleware-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_lookup", name="lookup_records", arguments="{}"),
                    Content.from_function_call(call_id="call_write", name="write_record", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("lookup and write", session=session)
    request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    second_response = await agent.run(request.to_function_approval_response(approved=True), session=session)

    assert second_response.text == "done"
    assert lookup_calls == 1
    assert write_calls == 1


async def test_tool_approval_middleware_auto_approval_rule_receives_function_call(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Heuristic auto-approval callbacks should receive function-call content and approve matching calls."""
    auto_calls = 0
    manual_calls = 0
    seen_calls: list[tuple[str, str | None]] = []

    @tool(name="auto_write", approval_mode="always_require")
    def auto_write() -> str:
        nonlocal auto_calls
        auto_calls += 1
        return "auto"

    @tool(name="manual_write", approval_mode="always_require")
    def manual_write() -> str:
        nonlocal manual_calls
        manual_calls += 1
        return "manual"

    async def auto_approve_auto_write(function_call: Content) -> bool:
        seen_calls.append((function_call.type, function_call.name))
        return function_call.name == "auto_write"

    agent = Agent(
        client=chat_client_base,
        tools=[auto_write, manual_write],
        middleware=[ToolApprovalMiddleware(auto_approval_rules=[auto_approve_auto_write])],
    )
    session = AgentSession(session_id="heuristic-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_auto", name="auto_write", arguments="{}"),
                    Content.from_function_call(call_id="call_manual", name="manual_write", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("write both", session=session)

    requests = _approval_requests(first_response.messages)
    assert [request.function_call.name for request in requests] == ["manual_write"]
    assert seen_calls == [("function_call", "auto_write"), ("function_call", "manual_write")]
    assert auto_calls == 0
    assert manual_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(requests[0].to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert auto_calls == 1
    assert manual_calls == 1


async def test_tool_approval_middleware_queues_streamed_approval_requests(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Streaming approval requests should also be queued one at a time."""
    calls = 0

    @tool(name="first_streamed_tool", approval_mode="always_require")
    def first_streamed_tool() -> str:
        nonlocal calls
        calls += 1
        return "first"

    @tool(name="second_streamed_tool", approval_mode="always_require")
    def second_streamed_tool() -> str:
        nonlocal calls
        calls += 1
        return "second"

    agent = Agent(
        client=chat_client_base,
        tools=[first_streamed_tool, second_streamed_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="stream-queue-session")
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_function_call(call_id="call_first", name="first_streamed_tool", arguments="{}")],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[
                    Content.from_function_call(call_id="call_second", name="second_streamed_tool", arguments="{}")
                ],
                role="assistant",
            ),
        ]
    ]

    first_stream = agent.run("call both", stream=True, session=session)
    first_updates = [update async for update in first_stream]
    first_requests = [content for update in first_updates for content in update.user_input_requests]
    assert [request.function_call.name for request in first_requests] == ["first_streamed_tool"]
    assert calls == 0

    second_stream = agent.run(
        first_requests[0].to_function_approval_response(approved=True),
        stream=True,
        session=session,
    )
    second_updates = [update async for update in second_stream]
    second_requests = [content for update in second_updates for content in update.user_input_requests]
    assert [request.function_call.name for request in second_requests] == ["second_streamed_tool"]
    assert calls == 0

    chat_client_base.streaming_responses = [
        [ChatResponseUpdate(contents=[Content.from_text("done")], role="assistant")]
    ]
    final_stream = agent.run(
        second_requests[0].to_function_approval_response(approved=True),
        stream=True,
        session=session,
    )
    final_updates = [update async for update in final_stream]
    final_response = await final_stream.get_final_response()

    assert final_updates[-1].text == "done"
    assert final_response.text == "done"
    assert calls == 2


async def test_tool_approval_middleware_always_approve_tool_rule(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """An always-approve response should add a standing tool-level approval rule."""
    calls = 0

    @tool(name="dangerous_tool", approval_mode="always_require")
    def dangerous_tool(value: str) -> str:
        nonlocal calls
        calls += 1
        return value

    agent = Agent(
        client=chat_client_base,
        tools=[dangerous_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="standing-rule-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_initial",
                        name="dangerous_tool",
                        arguments='{"value": "one"}',
                    )
                ],
            )
        )
    ]

    first_response = await agent.run("call once", session=session)
    first_request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["first done"]))]
    await agent.run(create_always_approve_tool_response(first_request), session=session)

    assert calls == 1

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_auto",
                        name="dangerous_tool",
                        arguments='{"value": "two"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", contents=["second done"])),
    ]

    second_response = await agent.run("call again", session=session)

    assert second_response.text == "second done"
    assert calls == 2
