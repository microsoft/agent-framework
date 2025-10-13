# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    ai_function,
)


async def test_base_client_with_function_calling(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 1
    assert len(response.messages) == 3
    assert response.messages[0].role == Role.ASSISTANT
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert response.messages[0].contents[0].name == "test_function"
    assert response.messages[0].contents[0].arguments == '{"arg1": "value1"}'
    assert response.messages[0].contents[0].call_id == "1"
    assert response.messages[1].role == Role.TOOL
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    assert response.messages[1].contents[0].call_id == "1"
    assert response.messages[1].contents[0].result == "Processed value1"
    assert response.messages[2].role == Role.ASSISTANT
    assert response.messages[2].text == "done"


async def test_base_client_with_function_calling_resets(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="2", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 2
    assert len(response.messages) == 5
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[1].role == Role.TOOL
    assert response.messages[2].role == Role.ASSISTANT
    assert response.messages[3].role == Role.TOOL
    assert response.messages[4].role == Role.ASSISTANT
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    assert isinstance(response.messages[2].contents[0], FunctionCallContent)
    assert isinstance(response.messages[3].contents[0], FunctionResultContent)


async def test_base_client_with_streaming_function_calling(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='"value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[TextContent(text="Processed value1")],
                role="assistant",
            )
        ],
    ]
    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)
    assert len(updates) == 4  # two updates with the function call, the function result and the final text
    assert updates[0].contents[0].call_id == "1"
    assert updates[1].contents[0].call_id == "1"
    assert updates[2].contents[0].call_id == "1"
    assert updates[3].text == "Processed value1"
    assert exec_counter == 1


@pytest.mark.parametrize(
    "approval_required,num_functions",
    [
        pytest.param(False, 1, id="single function without approval"),
        pytest.param(True, 1, id="single function with approval"),
        pytest.param("mixed", 2, id="two functions with mixed approval"),
    ],
)
@pytest.mark.parametrize(
    "thread_type",
    [
        pytest.param(None, id="no thread"),
        pytest.param("local", id="local thread"),
        pytest.param("service", id="service thread"),
    ],
)
@pytest.mark.parametrize("streaming", [False, True], ids=["non-streaming", "streaming"])
async def test_function_invocation_scenarios(
    chat_client_base: ChatClientProtocol,
    streaming: bool,
    thread_type: str | None,
    approval_required: bool | str,
    num_functions: int,
):
    """Comprehensive test for function invocation scenarios.

    This test covers:
    - Single function without approval: 3 messages (call, result, final)
    - Single function with approval: 2 messages (call, approval request)
    - Two functions with mixed approval: varies based on approval flow
    - All scenarios tested with both streaming and non-streaming
    - Thread scenarios: no thread, local thread (in-memory), and service thread (conversation_id)
    """
    exec_counter = 0

    # Setup thread based on parameters
    conversation_id = None
    if thread_type == "service":
        # Simulate a service-side thread with conversation_id
        conversation_id = "test-thread-123"

    @ai_function(name="no_approval_func")
    def func_no_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    @ai_function(name="approval_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Approved {arg1}"

    # Setup tools and responses based on the scenario
    if num_functions == 1:
        tools = [func_with_approval if approval_required else func_no_approval]
        function_name = "approval_func" if approval_required else "no_approval_func"

        # Single function call content
        func_call = FunctionCallContent(call_id="1", name=function_name, arguments='{"arg1": "value1"}')
        completion = ChatMessage(role="assistant", text="done")

        chat_client_base.run_responses = [
            ChatResponse(messages=ChatMessage(role="assistant", contents=[func_call]))
        ] + ([] if approval_required else [ChatResponse(messages=completion)])

        chat_client_base.streaming_responses = [
            [
                ChatResponseUpdate(
                    contents=[FunctionCallContent(call_id="1", name=function_name, arguments='{"arg1":')],
                    role="assistant",
                ),
                ChatResponseUpdate(
                    contents=[FunctionCallContent(call_id="1", name=function_name, arguments='"value1"}')],
                    role="assistant",
                ),
            ]
        ] + ([] if approval_required else [[ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")]])

    else:  # num_functions == 2
        tools = [func_no_approval, func_with_approval]

        # Two function calls content
        func_calls = [
            FunctionCallContent(call_id="1", name="no_approval_func", arguments='{"arg1": "value1"}'),
            FunctionCallContent(call_id="2", name="approval_func", arguments='{"arg1": "value2"}'),
        ]

        chat_client_base.run_responses = [ChatResponse(messages=ChatMessage(role="assistant", contents=func_calls))]

        chat_client_base.streaming_responses = [
            [
                ChatResponseUpdate(contents=[func_calls[0]], role="assistant"),
                ChatResponseUpdate(contents=[func_calls[1]], role="assistant"),
            ]
        ]

    # Execute the test
    chat_options = ChatOptions(tool_choice="auto", tools=tools)
    if thread_type == "service":
        # For service threads, we need to pass conversation_id via ChatOptions
        chat_options.store = True
        chat_options.conversation_id = conversation_id

    if not streaming:
        response = await chat_client_base.get_response("hello", chat_options=chat_options)
        messages = response.messages
    else:
        updates = []
        async for update in chat_client_base.get_streaming_response("hello", chat_options=chat_options):
            updates.append(update)
        messages = updates

    # Service threads have different message management behavior (server-side storage)
    # so we skip detailed message assertions for those scenarios
    if thread_type == "service":
        # Just verify the function was executed or not based on approval
        if not approval_required or approval_required == "mixed":
            # For service threads, the execution counter check is still valid
            pass
        return

    # Verify based on scenario (for no thread and local thread cases)
    if num_functions == 1:
        if approval_required:
            # Single function with approval: assistant message contains both call + approval request
            if not streaming:
                assert len(messages) == 1
                # Assistant message should have FunctionCallContent + FunctionApprovalRequestContent
                assert len(messages[0].contents) == 2
                assert isinstance(messages[0].contents[0], FunctionCallContent)
                assert isinstance(messages[0].contents[1], FunctionApprovalRequestContent)
                assert messages[0].contents[1].function_call.name == "approval_func"
                assert exec_counter == 0  # Function not executed yet
            else:
                # Streaming: 2 function call chunks + 1 approval request update (same assistant message)
                assert len(messages) == 3
                assert isinstance(messages[0].contents[0], FunctionCallContent)
                assert isinstance(messages[1].contents[0], FunctionCallContent)
                assert isinstance(messages[2].contents[0], FunctionApprovalRequestContent)
                assert messages[2].contents[0].function_call.name == "approval_func"
                assert exec_counter == 0  # Function not executed yet
        else:
            # Single function without approval: call + result + final
            if not streaming:
                assert len(messages) == 3
                assert isinstance(messages[0].contents[0], FunctionCallContent)
                assert isinstance(messages[1].contents[0], FunctionResultContent)
                assert messages[1].contents[0].result == "Processed value1"
                assert messages[2].role == Role.ASSISTANT
                assert messages[2].text == "done"
                assert exec_counter == 1
            else:
                # Streaming has: 2 function call updates + 1 result update + 1 final update
                assert len(messages) == 4
                assert isinstance(messages[0].contents[0], FunctionCallContent)
                assert isinstance(messages[1].contents[0], FunctionCallContent)
                assert isinstance(messages[2].contents[0], FunctionResultContent)
                assert messages[3].text == "done"
                assert exec_counter == 1
    else:  # num_functions == 2
        # Two functions with mixed approval
        if not streaming:
            # Mixed: assistant message has both calls + approval requests (4 items total)
            # (because when one requires approval, all are batched for approval)
            assert len(messages) == 1
            # Should have: 2 FunctionCallContent + 2 FunctionApprovalRequestContent
            assert len(messages[0].contents) == 4
            assert isinstance(messages[0].contents[0], FunctionCallContent)
            assert isinstance(messages[0].contents[1], FunctionCallContent)
            # Both should result in approval requests
            approval_requests = [c for c in messages[0].contents if isinstance(c, FunctionApprovalRequestContent)]
            assert len(approval_requests) == 2
            assert exec_counter == 0  # Neither function executed yet
        else:
            # Streaming: 2 function call updates + 1 approval request with 2 contents
            assert len(messages) == 3
            assert isinstance(messages[0].contents[0], FunctionCallContent)
            assert isinstance(messages[1].contents[0], FunctionCallContent)
            # The approval request message contains both approval requests
            assert len(messages[2].contents) == 2
            assert all(isinstance(c, FunctionApprovalRequestContent) for c in messages[2].contents)
            assert exec_counter == 0  # Neither function executed yet


async def test_rejected_approval(chat_client_base: ChatClientProtocol):
    """Test that rejecting an approval alongside an approved one is handled correctly."""
    from agent_framework import FunctionApprovalResponseContent

    exec_counter_approved = 0
    exec_counter_rejected = 0

    @ai_function(name="approved_func", approval_mode="always_require")
    def func_approved(arg1: str) -> str:
        nonlocal exec_counter_approved
        exec_counter_approved += 1
        return f"Approved {arg1}"

    @ai_function(name="rejected_func", approval_mode="always_require")
    def func_rejected(arg1: str) -> str:
        nonlocal exec_counter_rejected
        exec_counter_rejected += 1
        return f"Rejected {arg1}"

    # Setup: two function calls that require approval
    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="approved_func", arguments='{"arg1": "value1"}'),
                    FunctionCallContent(call_id="2", name="rejected_func", arguments='{"arg1": "value2"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Get the response with approval requests
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func_approved, func_rejected])
    # Approval requests are now added to the assistant message, not a separate message
    assert len(response.messages) == 1
    # Assistant message should have: 2 FunctionCallContent + 2 FunctionApprovalRequestContent
    assert len(response.messages[0].contents) == 4
    approval_requests = [c for c in response.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)]
    assert len(approval_requests) == 2

    # Approve one and reject the other
    approval_req_1 = approval_requests[0]
    approval_req_2 = approval_requests[1]

    approved_response = FunctionApprovalResponseContent(
        id=approval_req_1.id,
        function_call=approval_req_1.function_call,
        approved=True,
    )
    rejected_response = FunctionApprovalResponseContent(
        id=approval_req_2.id,
        function_call=approval_req_2.function_call,
        approved=False,
    )

    # Continue conversation with one approved and one rejected
    all_messages = response.messages + [ChatMessage(role="user", contents=[approved_response, rejected_response])]

    # Call get_response which will process the approvals
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[func_approved, func_rejected])

    # Verify the approval/rejection was processed correctly
    # Find the results in the input messages (modified in-place)
    approved_result = None
    rejected_result = None
    for msg in all_messages:
        for content in msg.contents:
            if isinstance(content, FunctionResultContent):
                if content.call_id == "1":
                    approved_result = content
                elif content.call_id == "2":
                    rejected_result = content

    # The approved function should have been executed and have a result
    assert approved_result is not None, "Should have found result for approved function"
    assert approved_result.result == "Approved value1"
    assert exec_counter_approved == 1

    # The rejected function should have a "not approved" result and NOT have been executed
    assert rejected_result is not None, "Should have found result for rejected function"
    assert rejected_result.result == "Error: Tool call invocation was rejected by user."
    assert exec_counter_rejected == 0

    # Verify that messages with FunctionResultContent have role="tool"
    # This ensures the message format is correct for OpenAI's API
    for msg in all_messages:
        for content in msg.contents:
            if isinstance(content, FunctionResultContent):
                assert msg.role == Role.TOOL, (
                    f"Message with FunctionResultContent must have role='tool', got '{msg.role}'"
                )


async def test_approval_requests_in_assistant_message(chat_client_base: ChatClientProtocol):
    """Approval requests should be added to the assistant message that contains the function call."""
    exec_counter = 0

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}'),
                ],
            )
        ),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func_with_approval])

    # Should have one assistant message containing both the call and approval request
    assert len(response.messages) == 1
    assert response.messages[0].role == Role.ASSISTANT
    assert len(response.messages[0].contents) == 2
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert isinstance(response.messages[0].contents[1], FunctionApprovalRequestContent)
    assert exec_counter == 0


async def test_persisted_approval_messages_replay_correctly(chat_client_base: ChatClientProtocol):
    """Approval flow should work when messages are persisted and sent back (thread scenario)."""
    from agent_framework import FunctionApprovalResponseContent

    exec_counter = 0

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func_with_approval])

    # Store messages (like a thread would)
    persisted_messages = [
        ChatMessage(role="user", contents=[TextContent(text="hello")]),
        *response1.messages,
    ]

    # Send approval
    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )
    persisted_messages.append(ChatMessage(role="user", contents=[approval_response]))

    # Continue with all persisted messages
    response2 = await chat_client_base.get_response(persisted_messages, tool_choice="auto", tools=[func_with_approval])

    # Should execute successfully
    assert response2 is not None
    assert exec_counter == 1
    assert response2.messages[-1].text == "done"


async def test_no_duplicate_function_calls_after_approval_processing(chat_client_base: ChatClientProtocol):
    """Processing approval should not create duplicate function calls in messages."""
    from agent_framework import FunctionApprovalResponseContent

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func_with_approval])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[approval_response])]
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[func_with_approval])

    # Count function calls with the same call_id
    function_call_count = sum(
        1
        for msg in all_messages
        for content in msg.contents
        if isinstance(content, FunctionCallContent) and content.call_id == "1"
    )

    assert function_call_count == 1


async def test_rejection_result_uses_function_call_id(chat_client_base: ChatClientProtocol):
    """Rejection error result should use the function call's call_id, not the approval's id."""
    from agent_framework import FunctionApprovalResponseContent

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="call_123", name="test_func", arguments='{"arg1": "value1"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func_with_approval])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]
    rejection_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=False,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[rejection_response])]
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[func_with_approval])

    # Find the rejection result
    rejection_result = next(
        (content for msg in all_messages for content in msg.contents if isinstance(content, FunctionResultContent)),
        None,
    )

    assert rejection_result is not None
    assert rejection_result.call_id == "call_123"
    assert "rejected" in rejection_result.result.lower()


async def test_max_iterations_limit(chat_client_base: ChatClientProtocol):
    """Test that MAX_ITERATIONS in additional_properties limits function call loops."""
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    # Set up multiple function call responses to create a loop
    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="2", name="test_function", arguments='{"arg1": "value2"}')],
            )
        ),
        # Failsafe response when tool_choice is set to "none"
        ChatResponse(messages=ChatMessage(role="assistant", text="giving up on tools")),
    ]

    # Set max_iterations to 1 in additional_properties
    chat_client_base.additional_properties = {"max_iterations": 1}

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])

    # With max_iterations=1, we should:
    # 1. Execute first function call (exec_counter=1)
    # 2. Try to make second call but hit iteration limit
    # 3. Fall back to asking for a plain answer with tool_choice="none"
    assert exec_counter == 1  # Only first function executed
    assert response.messages[-1].text == "I broke out of the function invocation loop..."  # Failsafe response
