# Copyright (c) Microsoft. All rights reserved.
"""Regression tests for issue #1366: agent.run() returns with unexecuted tool calls.

When max_iterations is reached, the function invocation loop should make a final
model call with tool_choice="none" to get a plain text response. Instead, it
returns the last iteration's response directly, which may contain function_call
items without a subsequent final text answer — and critically, the thread/response
may contain FunctionCallContent without matching FunctionResultContent if the
loop structure doesn't guarantee tool execution before returning.

Additionally, when the loop exhausts all iterations while the model keeps
requesting tools, fcc_messages from prior iterations are NOT prepended to the
returned response, potentially losing conversation history.

See: https://github.com/microsoft/agent-framework/issues/1366
"""

from agent_framework import (
    ChatResponse,
    Content,
    Message,
    SupportsChatGetResponse,
    tool,
)


async def test_max_iterations_exhausted_returns_orphaned_function_calls(
    chat_client_base: SupportsChatGetResponse,
):
    """When max_iterations is reached, verify the returned response has no orphaned
    FunctionCallContent (i.e., every function_call has a matching function_result).

    Bug: The loop at _tools.py returns `response` directly when max_iterations is
    exhausted (`if response is not None: return response`). No final model call
    with tool_choice='none' is made, and fcc_messages are not prepended.

    Expected: Either all FunctionCallContent have matching FunctionResultContent,
    OR a final model call is made with tool_choice='none'.
    """
    exec_counter = 0

    @tool(name="test_function", approval_mode="never_require")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    # Model keeps requesting tool calls on every iteration
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_1", name="test_function", arguments='{"arg1": "v1"}')
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_2", name="test_function", arguments='{"arg1": "v2"}')
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_3", name="test_function", arguments='{"arg1": "v3"}')
                ],
            )
        ),
    ]

    chat_client_base.function_invocation_configuration["max_iterations"] = 2

    response = await chat_client_base.get_response(
        [Message(role="user", text="hello")],
        options={"tool_choice": "auto", "tools": [ai_func]},
    )

    # Collect all function_call and function_result call_ids from response
    all_call_ids = set()
    all_result_ids = set()
    for msg in response.messages:
        for content in msg.contents:
            if content.type == "function_call":
                all_call_ids.add(content.call_id)
            elif content.type == "function_result":
                all_result_ids.add(content.call_id)

    orphaned_calls = all_call_ids - all_result_ids
    assert not orphaned_calls, (
        f"Response contains orphaned FunctionCallContent without matching "
        f"FunctionResultContent: {orphaned_calls}. "
        f"This will cause OpenAI 400 error on next API call."
    )


async def test_max_iterations_exhausted_makes_final_toolchoice_none_call(
    chat_client_base: SupportsChatGetResponse,
):
    """When max_iterations is reached, verify a final model call is made with
    tool_choice='none' to produce a clean text response.

    Bug: After the loop exhausts, the code does `if response is not None: return response`
    skipping the failsafe path that would call the model with tool_choice='none'.

    The test verifies the response ends with a plain text message (no function calls).
    """
    exec_counter = 0

    @tool(name="test_function", approval_mode="never_require")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    # Model keeps requesting tool calls
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_1", name="test_function", arguments='{"arg1": "v1"}')
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_2", name="test_function", arguments='{"arg1": "v2"}')
                ],
            )
        ),
        # This response should be reached via failsafe (tool_choice="none")
        ChatResponse(messages=Message(role="assistant", text="Final answer after giving up on tools.")),
    ]

    chat_client_base.function_invocation_configuration["max_iterations"] = 1

    response = await chat_client_base.get_response(
        [Message(role="user", text="hello")],
        options={"tool_choice": "auto", "tools": [ai_func]},
    )

    assert exec_counter == 1, f"Expected 1 function execution, got {exec_counter}"

    # The response should end with a plain text message (from the failsafe call)
    # NOT with function_call or tool messages
    last_msg = response.messages[-1]
    has_function_calls = any(c.type == "function_call" for c in last_msg.contents)

    assert not has_function_calls, (
        f"Last message in response still contains function_call items. "
        f"Expected a clean text response after max_iterations failsafe. "
        f"Got message with role={last_msg.role}, contents={[c.type for c in last_msg.contents]}"
    )

    # The mock client returns "I broke out of the function invocation loop..."
    # when tool_choice="none"
    assert last_msg.text == "I broke out of the function invocation loop...", (
        f"Expected failsafe text response, got: {last_msg.text!r}"
    )


async def test_max_iterations_preserves_all_fcc_messages(
    chat_client_base: SupportsChatGetResponse,
):
    """When max_iterations is reached and a final response is produced, all
    intermediate function call/result messages should be included.

    Bug: fcc_messages from prior iterations are discarded when the loop returns
    `response` directly instead of going through the failsafe path.
    """
    exec_counter = 0

    @tool(name="test_function", approval_mode="never_require")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Result {exec_counter}"

    # Two iterations of function calls, then failsafe
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_1", name="test_function", arguments='{"arg1": "v1"}')
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_2", name="test_function", arguments='{"arg1": "v2"}')
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", text="Done")),
    ]

    chat_client_base.function_invocation_configuration["max_iterations"] = 2

    response = await chat_client_base.get_response(
        [Message(role="user", text="hello")],
        options={"tool_choice": "auto", "tools": [ai_func]},
    )

    assert exec_counter == 2, f"Expected 2 function executions, got {exec_counter}"

    # All function calls from both iterations should be present in the response
    all_call_ids = set()
    all_result_ids = set()
    for msg in response.messages:
        for content in msg.contents:
            if content.type == "function_call":
                all_call_ids.add(content.call_id)
            elif content.type == "function_result":
                all_result_ids.add(content.call_id)

    # Both iterations' function calls should be present
    assert "call_1" in all_call_ids, "First iteration's function call missing from response"
    assert "call_2" in all_call_ids, "Second iteration's function call missing from response"

    # Both should have matching results
    assert all_call_ids == all_result_ids, (
        f"Mismatched function calls and results. Calls: {all_call_ids}, Results: {all_result_ids}"
    )


async def test_thread_safe_after_max_iterations_with_agent(
    chat_client_base: SupportsChatGetResponse,
):
    """Simulate the full agent.run() → thread → agent.run() flow to verify
    that the thread doesn't contain orphaned function calls after max_iterations.

    This reproduces the exact user-reported scenario: agent.run() returns,
    response is stored in thread, next agent.run() fails with OpenAI 400 error.
    """
    from agent_framework import Agent

    @tool(name="browser_snapshot", approval_mode="never_require")
    def browser_snapshot(url: str) -> str:
        return f"Screenshot of {url}"

    # First call: model returns a function call, it's executed, then model
    # returns ANOTHER function call (on the last iteration), which is executed
    # but no final text answer is produced.
    # Note: Only 2 responses are listed here for 2 iterations. The failsafe
    # call (with tool_choice="none") after the loop is handled automatically
    # by the mock client, which returns a hardcoded text response when
    # tool_choice="none" (see conftest.py ChatClientBase.get_response).
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_abc", name="browser_snapshot", arguments='{"url": "https://example.com"}'
                    )
                ],
            )
        ),
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_xyz", name="browser_snapshot", arguments='{"url": "https://test.com"}'
                    )
                ],
            )
        ),
    ]

    chat_client_base.function_invocation_configuration["max_iterations"] = 2

    agent = Agent(
        client=chat_client_base,
        name="test-agent",
        tools=[browser_snapshot],
    )

    response = await agent.run(
        "Take screenshots",
        options={"tool_choice": "auto"},
    )

    # Check for orphaned function calls in the response messages
    all_call_ids = set()
    all_result_ids = set()
    for msg in response.messages:
        for content in msg.contents:
            if content.type == "function_call":
                all_call_ids.add(content.call_id)
            elif content.type == "function_result":
                all_result_ids.add(content.call_id)

    orphaned_calls = all_call_ids - all_result_ids
    assert not orphaned_calls, (
        f"Thread corruption: response contains orphaned function calls {orphaned_calls}. "
        f"Passing this thread to OpenAI will cause 400 error: "
        f"'An assistant message with tool_calls must be followed by tool messages.'"
    )
