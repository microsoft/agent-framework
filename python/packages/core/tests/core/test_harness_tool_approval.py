# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from agent_framework import (
    DEFAULT_TOOL_APPROVAL_SOURCE_ID,
    Agent,
    AgentSession,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ToolApprovalMiddleware,
    ToolApprovalState,
    create_always_approve_tool_response,
    create_always_approve_tool_with_arguments_response,
    tool,
)

from .conftest import MockBaseChatClient


def _approval_requests(messages: list[Message]) -> list[Content]:
    return [
        content for message in messages for content in message.contents if content.type == "function_approval_request"
    ]


def _function_call(request: Content) -> Content:
    assert request.function_call is not None
    return request.function_call


async def test_mixed_batch_hides_already_approved_request_until_approval_replay(
    chat_client_base: MockBaseChatClient,
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
    assert [_function_call(request).name for request in requests] == ["add_comment"]
    assert no_approval_calls == 0
    assert approval_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["complete"]))]
    second_response = await agent.run(requests[0].to_function_approval_response(approved=True), session=session)

    assert second_response.text == "complete"
    assert no_approval_calls == 1
    assert approval_calls == 1


async def test_mixed_batch_accepts_restored_tool_approval_state(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Mixed-batch bypass should work when session state contains ToolApprovalState."""
    safe_calls = 0
    risky_calls = 0

    @tool(name="safe_read", approval_mode="never_require")
    def safe_read() -> str:
        nonlocal safe_calls
        safe_calls += 1
        return "safe"

    @tool(name="risky_write", approval_mode="always_require")
    def risky_write() -> str:
        nonlocal risky_calls
        risky_calls += 1
        return "risky"

    agent = Agent(client=chat_client_base, tools=[safe_read, risky_write])
    session = AgentSession(session_id="restored-state-session")
    session.state[DEFAULT_TOOL_APPROVAL_SOURCE_ID] = ToolApprovalState()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_safe", name="safe_read", arguments="{}"),
                    Content.from_function_call(call_id="call_risky", name="risky_write", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("read and write", session=session)
    requests = _approval_requests(first_response.messages)

    assert [_function_call(request).name for request in requests] == ["risky_write"]
    assert safe_calls == 0
    assert risky_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(requests[0].to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert safe_calls == 1
    assert risky_calls == 1


async def test_hidden_mixed_batch_requests_do_not_replay_on_unrelated_turn(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Stored hidden approvals should only replay when an approval response resumes the flow."""
    safe_calls = 0
    risky_calls = 0

    @tool(name="safe_lookup", approval_mode="never_require")
    def safe_lookup() -> str:
        nonlocal safe_calls
        safe_calls += 1
        return "safe"

    @tool(name="risky_update", approval_mode="always_require")
    def risky_update() -> str:
        nonlocal risky_calls
        risky_calls += 1
        return "risky"

    agent = Agent(client=chat_client_base, tools=[safe_lookup, risky_update])
    session = AgentSession(session_id="stale-hidden-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_safe", name="safe_lookup", arguments="{}"),
                    Content.from_function_call(call_id="call_risky", name="risky_update", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("lookup and update", session=session)
    request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["unrelated"]))]
    unrelated_response = await agent.run("never mind, answer something else", session=session)

    assert unrelated_response.text == "unrelated"
    assert safe_calls == 0
    assert risky_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(request.to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert safe_calls == 1
    assert risky_calls == 1


async def test_hidden_mixed_batch_requests_replay_only_for_matching_visible_approval(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Approving one mixed batch must not replay hidden calls from another abandoned batch."""
    safe_a_calls = 0
    safe_b_calls = 0
    risky_a_calls = 0
    risky_b_calls = 0

    @tool(name="safe_a", approval_mode="never_require")
    def safe_a() -> str:
        nonlocal safe_a_calls
        safe_a_calls += 1
        return "safe-a"

    @tool(name="safe_b", approval_mode="never_require")
    def safe_b() -> str:
        nonlocal safe_b_calls
        safe_b_calls += 1
        return "safe-b"

    @tool(name="risky_a", approval_mode="always_require")
    def risky_a() -> str:
        nonlocal risky_a_calls
        risky_a_calls += 1
        return "risky-a"

    @tool(name="risky_b", approval_mode="always_require")
    def risky_b() -> str:
        nonlocal risky_b_calls
        risky_b_calls += 1
        return "risky-b"

    agent = Agent(client=chat_client_base, tools=[safe_a, safe_b, risky_a, risky_b])
    session = AgentSession(session_id="grouped-hidden-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_safe_a", name="safe_a", arguments="{}"),
                    Content.from_function_call(call_id="call_risky_a", name="risky_a", arguments="{}"),
                ],
            )
        )
    ]

    first_response = await agent.run("batch a", session=session)
    assert [_function_call(request).name for request in _approval_requests(first_response.messages)] == ["risky_a"]

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_safe_b", name="safe_b", arguments="{}"),
                    Content.from_function_call(call_id="call_risky_b", name="risky_b", arguments="{}"),
                ],
            )
        )
    ]

    second_response = await agent.run("batch b", session=session)
    second_request = _approval_requests(second_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(second_request.to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert safe_a_calls == 0
    assert risky_a_calls == 0
    assert safe_b_calls == 1
    assert risky_b_calls == 1


async def test_tool_approval_middleware_queues_multiple_approval_requests(
    chat_client_base: MockBaseChatClient,
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
    assert [_function_call(request).name for request in first_requests] == ["first_tool"]
    assert first_calls == 0
    assert second_calls == 0

    second_response = await agent.run(first_requests[0].to_function_approval_response(approved=True), session=session)

    second_requests = _approval_requests(second_response.messages)
    assert [_function_call(request).name for request in second_requests] == ["second_tool"]
    assert first_calls == 0
    assert second_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(second_requests[0].to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert first_calls == 1
    assert second_calls == 1


async def test_tool_approval_middleware_preserves_hidden_mixed_batch_requests(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Middleware state saves should not discard core hidden already-approved requests."""
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
    chat_client_base: MockBaseChatClient,
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
    assert [_function_call(request).name for request in requests] == ["manual_write"]
    assert seen_calls == [("function_call", "auto_write"), ("function_call", "manual_write")]
    assert auto_calls == 0
    assert manual_calls == 0

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["done"]))]
    final_response = await agent.run(requests[0].to_function_approval_response(approved=True), session=session)

    assert final_response.text == "done"
    assert auto_calls == 1
    assert manual_calls == 1


async def test_tool_approval_middleware_auto_approved_loops_share_function_call_budget(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Auto-approved re-entry should not reset max_function_calls."""
    calls = 0

    @tool(name="budgeted_tool", approval_mode="always_require")
    def budgeted_tool(value: str) -> str:
        nonlocal calls
        calls += 1
        return value

    def auto_approve_budgeted_tool(function_call: Content) -> bool:
        return function_call.name == "budgeted_tool"

    chat_client_base.function_invocation_configuration["max_function_calls"] = 1
    agent = Agent(
        client=chat_client_base,
        tools=[budgeted_tool],
        middleware=[ToolApprovalMiddleware(auto_approval_rules=[auto_approve_budgeted_tool])],
    )
    session = AgentSession(session_id="shared-budget-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_first",
                        name="budgeted_tool",
                        arguments='{"value": "first"}',
                    )
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_second",
                        name="budgeted_tool",
                        arguments='{"value": "second"}',
                    )
                ],
            )
        ),
    ]

    response = await agent.run("call repeatedly", session=session)

    assert response.text == "I broke out of the function invocation loop..."
    assert calls == 1


async def test_tool_approval_middleware_queues_streamed_approval_requests(
    chat_client_base: MockBaseChatClient,
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
    assert [_function_call(request).name for request in first_requests] == ["first_streamed_tool"]
    assert calls == 0

    second_stream = agent.run(
        first_requests[0].to_function_approval_response(approved=True),
        stream=True,
        session=session,
    )
    second_updates = [update async for update in second_stream]
    second_requests = [content for update in second_updates for content in update.user_input_requests]
    assert [_function_call(request).name for request in second_requests] == ["second_streamed_tool"]
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
    chat_client_base: MockBaseChatClient,
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


async def test_tool_approval_middleware_standing_rules_include_hosted_server_boundary(
    chat_client_base: MockBaseChatClient,
) -> None:
    """A standing hosted-tool rule should only match the same server_label."""
    calls = 0

    @tool(name="hosted_tool", approval_mode="always_require")
    def hosted_tool() -> str:
        nonlocal calls
        calls += 1
        return "hosted"

    def hosted_call(call_id: str, server_label: str) -> Content:
        return Content.from_function_call(
            call_id=call_id,
            name="hosted_tool",
            arguments="{}",
            additional_properties={"server_label": server_label},
        )

    agent = Agent(
        client=chat_client_base,
        tools=[hosted_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="hosted-boundary-session")
    chat_client_base.run_responses = [
        ChatResponse(messages=Message(role="assistant", contents=[hosted_call("call_initial", "server-a")]))
    ]

    first_response = await agent.run("call hosted a", session=session)
    first_request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["server a done"]))]
    await agent.run(create_always_approve_tool_response(first_request), session=session)

    assert calls == 0

    chat_client_base.run_responses = [
        ChatResponse(messages=Message(role="assistant", contents=[hosted_call("call_same_server", "server-a")])),
        ChatResponse(messages=Message(role="assistant", contents=["same server done"])),
    ]

    same_server_response = await agent.run("call hosted a again", session=session)

    assert same_server_response.text == "same server done"
    assert _approval_requests(same_server_response.messages) == []
    assert calls == 0

    chat_client_base.run_responses = [
        ChatResponse(messages=Message(role="assistant", contents=[hosted_call("call_other_server", "server-b")]))
    ]

    other_server_response = await agent.run("call hosted b", session=session)

    requests = _approval_requests(other_server_response.messages)
    assert [_function_call(request).additional_properties["server_label"] for request in requests] == ["server-b"]
    assert calls == 0


async def test_tool_approval_middleware_always_approve_tool_with_arguments_rule(
    chat_client_base: MockBaseChatClient,
) -> None:
    """Argument-scoped always-approve rules should require exact argument matches."""
    calls = 0

    @tool(name="argument_scoped_tool", approval_mode="always_require")
    def argument_scoped_tool(value: str) -> str:
        nonlocal calls
        calls += 1
        return value

    agent = Agent(
        client=chat_client_base,
        tools=[argument_scoped_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="argument-rule-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_initial",
                        name="argument_scoped_tool",
                        arguments='{"value": "same"}',
                    )
                ],
            )
        )
    ]

    first_response = await agent.run("call with same", session=session)
    first_request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["first done"]))]
    await agent.run(create_always_approve_tool_with_arguments_response(first_request), session=session)

    assert calls == 1

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_same",
                        name="argument_scoped_tool",
                        arguments='{"value": "same"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", contents=["same done"])),
    ]

    second_response = await agent.run("call with same again", session=session)

    assert second_response.text == "same done"
    assert calls == 2

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_different",
                        name="argument_scoped_tool",
                        arguments='{"value": "different"}',
                    )
                ],
            )
        )
    ]

    third_response = await agent.run("call with different args", session=session)

    requests = _approval_requests(third_response.messages)
    assert [_function_call(request).arguments for request in requests] == ['{"value": "different"}']
    assert calls == 2


async def test_tool_approval_middleware_empty_arguments_rule_is_not_tool_wide(
    chat_client_base: MockBaseChatClient,
) -> None:
    """An argument-scoped no-argument approval should not become a wildcard."""
    calls = 0

    @tool(name="optional_args_tool", approval_mode="always_require")
    def optional_args_tool(value: str = "default") -> str:
        nonlocal calls
        calls += 1
        return value

    agent = Agent(
        client=chat_client_base,
        tools=[optional_args_tool],
        middleware=[ToolApprovalMiddleware()],
    )
    session = AgentSession(session_id="empty-arguments-rule-session")
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_empty",
                        name="optional_args_tool",
                        arguments="{}",
                    )
                ],
            )
        )
    ]

    first_response = await agent.run("call without args", session=session)
    first_request = _approval_requests(first_response.messages)[0]

    chat_client_base.run_responses = [ChatResponse(messages=Message(role="assistant", contents=["empty done"]))]
    await agent.run(create_always_approve_tool_with_arguments_response(first_request), session=session)

    assert calls == 1

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_non_empty",
                        name="optional_args_tool",
                        arguments='{"value": "custom"}',
                    )
                ],
            )
        )
    ]

    second_response = await agent.run("call with args", session=session)

    requests = _approval_requests(second_response.messages)
    assert [_function_call(request).arguments for request in requests] == ['{"value": "custom"}']
    assert calls == 1
