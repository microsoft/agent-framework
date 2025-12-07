# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import (
    ChatAgent,
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


async def test_function_invocation_inside_aiohttp_server(chat_client_base: ChatClientProtocol):
    import aiohttp
    from aiohttp import web

    exec_counter = 0

    @ai_function(name="start_todo_investigation")
    def ai_func(user_query: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Investigated {user_query}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(
                        call_id="1",
                        name="start_todo_investigation",
                        arguments='{"user_query": "issue"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    agent = ChatAgent(chat_client=chat_client_base, tools=[ai_func])

    async def handler(request: web.Request) -> web.Response:
        thread = agent.get_new_thread()
        result = await agent.run("Fix issue", thread=thread)
        return web.Response(text=result.text or "")

    app = web.Application()
    app.add_routes([web.post("/run", handler)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        port = site._server.sockets[0].getsockname()[1]
        async with aiohttp.ClientSession() as session, session.post(f"http://127.0.0.1:{port}/run") as response:
            assert response.status == 200
            await response.text()
    finally:
        await runner.cleanup()

    assert exec_counter == 1


async def test_function_invocation_in_threaded_aiohttp_app(chat_client_base: ChatClientProtocol):
    import asyncio
    import threading
    from queue import Queue

    import aiohttp
    from aiohttp import web

    exec_counter = 0

    @ai_function(name="start_threaded_investigation")
    def ai_func(user_query: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Threaded {user_query}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(
                        call_id="thread-1",
                        name="start_threaded_investigation",
                        arguments='{"user_query": "issue"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    agent = ChatAgent(chat_client=chat_client_base, tools=[ai_func])

    ready_event = threading.Event()
    port_queue: Queue[int] = Queue()
    shutdown_queue: Queue[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = Queue()

    async def init_app() -> web.Application:
        async def handler(request: web.Request) -> web.Response:
            thread = agent.get_new_thread()
            result = await agent.run("Fix issue", thread=thread)
            return web.Response(text=result.text or "")

        app = web.Application()
        app.add_routes([web.post("/run", handler)])
        return app

    def server_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def runner_main() -> None:
            app = await init_app()
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            shutdown_event = asyncio.Event()
            shutdown_queue.put((loop, shutdown_event))
            port = site._server.sockets[0].getsockname()[1]
            port_queue.put(port)
            ready_event.set()
            try:
                await shutdown_event.wait()
            finally:
                await runner.cleanup()

        try:
            loop.run_until_complete(runner_main())
        finally:
            loop.close()

    thread = threading.Thread(target=server_thread, daemon=True)
    thread.start()
    ready_event.wait(timeout=5)
    assert ready_event.is_set()
    loop_ref, shutdown_event = shutdown_queue.get(timeout=2)
    port = port_queue.get(timeout=2)

    async with aiohttp.ClientSession() as session, session.post(f"http://127.0.0.1:{port}/run") as response:
        assert response.status == 200
        await response.text()

    loop_ref.call_soon_threadsafe(shutdown_event.set)
    thread.join(timeout=5)
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
    chat_client_base.function_invocation_configuration.max_iterations = 1

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])

    # With max_iterations=1, we should:
    # 1. Execute first function call (exec_counter=1)
    # 2. Try to make second call but hit iteration limit
    # 3. Fall back to asking for a plain answer with tool_choice="none"
    assert exec_counter == 1  # Only first function executed
    assert response.messages[-1].text == "I broke out of the function invocation loop..."  # Failsafe response


async def test_function_invocation_config_enabled_false(chat_client_base: ChatClientProtocol):
    """Test that setting enabled=False disables function invocation."""
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(messages=ChatMessage(role="assistant", text="response without function calling")),
    ]

    # Disable function invocation
    chat_client_base.function_invocation_configuration.enabled = False

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])

    # Function should not be executed - when enabled=False, the loop doesn't run
    assert exec_counter == 0
    # The response should be from the mock client
    assert len(response.messages) > 0


async def test_function_invocation_config_max_consecutive_errors(chat_client_base: ChatClientProtocol):
    """Test that max_consecutive_errors_per_request limits error retries."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Function error")

    # Set up multiple function call responses that will all error
    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="2", name="error_function", arguments='{"arg1": "value2"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="3", name="error_function", arguments='{"arg1": "value3"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="4", name="error_function", arguments='{"arg1": "value4"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="final response")),
    ]

    # Set max_consecutive_errors to 2
    chat_client_base.function_invocation_configuration.max_consecutive_errors_per_request = 2

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[error_func])

    # Should stop after 2 consecutive errors and force a non-tool response
    error_results = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionResultContent) and content.exception
    ]
    # The first call errors, then the second call errors, hitting the limit
    # So we get 2 function calls with errors, but the responses show the behavior stopped
    assert len(error_results) >= 1  # At least one error occurred
    # Should have stopped making new function calls after hitting the error limit
    function_calls = [
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionCallContent)
    ]
    # Should have made at most 2 function calls before stopping
    assert len(function_calls) <= 2


async def test_function_invocation_config_terminate_on_unknown_calls_false(chat_client_base: ChatClientProtocol):
    """Test that terminate_on_unknown_calls=False returns error message for unknown functions."""
    exec_counter = 0

    @ai_function(name="known_function")
    def known_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="unknown_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set terminate_on_unknown_calls to False (default)
    chat_client_base.function_invocation_configuration.terminate_on_unknown_calls = False

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[known_func])

    # Should have a result message indicating the tool wasn't found
    assert len(response.messages) == 3
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    result_str = response.messages[1].contents[0].result or response.messages[1].contents[0].exception or ""
    assert "not found" in result_str.lower()
    assert exec_counter == 0  # Known function not executed


async def test_function_invocation_config_terminate_on_unknown_calls_true(chat_client_base: ChatClientProtocol):
    """Test that terminate_on_unknown_calls=True stops execution on unknown functions."""
    exec_counter = 0

    @ai_function(name="known_function")
    def known_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="unknown_function", arguments='{"arg1": "value1"}')],
            )
        ),
    ]

    # Set terminate_on_unknown_calls to True
    chat_client_base.function_invocation_configuration.terminate_on_unknown_calls = True

    # Should raise an exception when encountering an unknown function
    with pytest.raises(KeyError, match='Error: Requested function "unknown_function" not found'):
        await chat_client_base.get_response("hello", tool_choice="auto", tools=[known_func])

    assert exec_counter == 0


async def test_function_invocation_config_additional_tools(chat_client_base: ChatClientProtocol):
    """Test that additional_tools are available but treated as declaration_only."""
    exec_counter_visible = 0
    exec_counter_hidden = 0

    @ai_function(name="visible_function")
    def visible_func(arg1: str) -> str:
        nonlocal exec_counter_visible
        exec_counter_visible += 1
        return f"Visible {arg1}"

    @ai_function(name="hidden_function")
    def hidden_func(arg1: str) -> str:
        nonlocal exec_counter_hidden
        exec_counter_hidden += 1
        return f"Hidden {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="hidden_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Add hidden_func to additional_tools
    chat_client_base.function_invocation_configuration.additional_tools = [hidden_func]

    # Only pass visible_func in the tools parameter
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[visible_func])

    # Additional tools are treated as declaration_only, so not executed
    # The function call should be in the messages but not executed
    assert exec_counter_hidden == 0
    assert exec_counter_visible == 0
    # Should have the function call in messages (declaration_only behavior)
    function_calls = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionCallContent) and content.name == "hidden_function"
    ]
    assert len(function_calls) >= 1


async def test_function_invocation_config_include_detailed_errors_false(chat_client_base: ChatClientProtocol):
    """Test that include_detailed_errors=False returns generic error messages."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Specific error message that should not appear")

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to False (default)
    chat_client_base.function_invocation_configuration.include_detailed_errors = False

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[error_func])

    # Should have a generic error message
    error_result = next(
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Specific error message" not in error_result.result
    assert "Error:" in error_result.result  # Generic error prefix


async def test_function_invocation_config_include_detailed_errors_true(chat_client_base: ChatClientProtocol):
    """Test that include_detailed_errors=True returns detailed error information."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Specific error message that should appear")

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to True
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[error_func])

    # Should have detailed error message
    error_result = next(
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Specific error message that should appear" in error_result.result
    # The error format includes "Function failed. Exception:" prefix
    assert "Exception:" in error_result.result


async def test_function_invocation_config_validation_max_iterations():
    """Test that max_iterations validation works correctly."""
    from agent_framework import FunctionInvocationConfiguration

    # Valid values
    config = FunctionInvocationConfiguration(max_iterations=1)
    assert config.max_iterations == 1

    config = FunctionInvocationConfiguration(max_iterations=100)
    assert config.max_iterations == 100

    # Invalid value (less than 1)
    with pytest.raises(ValueError, match="max_iterations must be at least 1"):
        FunctionInvocationConfiguration(max_iterations=0)

    with pytest.raises(ValueError, match="max_iterations must be at least 1"):
        FunctionInvocationConfiguration(max_iterations=-1)


async def test_function_invocation_config_validation_max_consecutive_errors():
    """Test that max_consecutive_errors_per_request validation works correctly."""
    from agent_framework import FunctionInvocationConfiguration

    # Valid values
    config = FunctionInvocationConfiguration(max_consecutive_errors_per_request=0)
    assert config.max_consecutive_errors_per_request == 0

    config = FunctionInvocationConfiguration(max_consecutive_errors_per_request=5)
    assert config.max_consecutive_errors_per_request == 5

    # Invalid value (less than 0)
    with pytest.raises(ValueError, match="max_consecutive_errors_per_request must be 0 or more"):
        FunctionInvocationConfiguration(max_consecutive_errors_per_request=-1)


async def test_argument_validation_error_with_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that argument validation errors include details when include_detailed_errors=True."""

    @ai_function(name="typed_function")
    def typed_func(arg1: int) -> str:  # Expects int, not str
        return f"Got {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="typed_function", arguments='{"arg1": "not_an_int"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to True
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[typed_func])

    # Should have detailed validation error
    error_result = next(
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Argument parsing failed" in error_result.result
    assert "Exception:" in error_result.result  # Detailed error included


async def test_argument_validation_error_without_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that argument validation errors are generic when include_detailed_errors=False."""

    @ai_function(name="typed_function")
    def typed_func(arg1: int) -> str:  # Expects int, not str
        return f"Got {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="typed_function", arguments='{"arg1": "not_an_int"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to False (default)
    chat_client_base.function_invocation_configuration.include_detailed_errors = False

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[typed_func])

    # Should have generic validation error
    error_result = next(
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Argument parsing failed" in error_result.result
    assert "Exception:" not in error_result.result  # No detailed error


async def test_hosted_tool_approval_response(chat_client_base: ChatClientProtocol):
    """Test handling of approval responses for hosted tools (tools not in tool_map)."""
    from agent_framework import FunctionApprovalResponseContent

    @ai_function(name="local_function")
    def local_func(arg1: str) -> str:
        return f"Local {arg1}"

    # Create an approval response for a hosted tool that's not in our tool_map
    hosted_function_call = FunctionCallContent(
        call_id="hosted_1", name="hosted_function", arguments='{"arg1": "value"}'
    )
    approval_response = FunctionApprovalResponseContent(
        id="approval_1",
        function_call=hosted_function_call,
        approved=True,
    )

    chat_client_base.run_responses = [
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Send the approval response
    response = await chat_client_base.get_response(
        [ChatMessage(role="user", contents=[approval_response])],
        tool_choice="auto",
        tools=[local_func],
    )

    # The hosted tool approval should be returned as-is (not executed)
    # Check that we got a response without errors
    assert response is not None


async def test_unapproved_tool_execution_raises_exception(chat_client_base: ChatClientProtocol):
    """Test that attempting to execute an unapproved tool raises ToolException."""
    from agent_framework import FunctionApprovalResponseContent

    @ai_function(name="test_function", approval_mode="always_require")
    def test_func(arg1: str) -> str:
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[test_func])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]

    # Create a rejection response (approved=False)
    rejection_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=False,
    )

    # Continue conversation with rejection
    all_messages = response1.messages + [ChatMessage(role="user", contents=[rejection_response])]

    # This should handle the rejection gracefully (not raise ToolException to user)
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[test_func])

    # Should have a rejection result
    rejection_result = next(
        (
            content
            for msg in all_messages
            for content in msg.contents
            if isinstance(content, FunctionResultContent)
            and "rejected" in (content.result or content.exception or "").lower()
        ),
        None,
    )
    assert rejection_result is not None


async def test_approved_function_call_with_error_without_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that approved functions that raise errors return generic error messages.

    When include_detailed_errors=False.
    """
    from agent_framework import FunctionApprovalResponseContent

    exec_counter = 0

    @ai_function(name="error_func", approval_mode="always_require")
    def error_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        raise ValueError("Specific error from approved function")

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="error_func", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to False (default)
    chat_client_base.function_invocation_configuration.include_detailed_errors = False

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[error_func])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]

    # Approve the function
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[approval_response])]

    # Execute the approved function (which will error)
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[error_func])

    # Should have executed the function
    assert exec_counter == 1

    # Should have an error result with generic message
    error_result = next(
        (
            content
            for msg in all_messages
            for content in msg.contents
            if isinstance(content, FunctionResultContent) and content.exception is not None
        ),
        None,
    )
    assert error_result is not None
    assert error_result.result is not None
    assert "Error: Function failed." in error_result.result
    assert "Specific error from approved function" not in error_result.result  # Detail not included


async def test_approved_function_call_with_error_with_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that approved functions that raise errors return detailed error messages.

    When include_detailed_errors=True.
    """
    from agent_framework import FunctionApprovalResponseContent

    exec_counter = 0

    @ai_function(name="error_func", approval_mode="always_require")
    def error_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        raise ValueError("Specific error from approved function")

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="error_func", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to True
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[error_func])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]

    # Approve the function
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[approval_response])]

    # Execute the approved function (which will error)
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[error_func])

    # Should have executed the function
    assert exec_counter == 1

    # Should have an error result with detailed message
    error_result = next(
        (
            content
            for msg in all_messages
            for content in msg.contents
            if isinstance(content, FunctionResultContent) and content.exception is not None
        ),
        None,
    )
    assert error_result is not None
    assert error_result.result is not None
    assert "Error: Function failed." in error_result.result
    assert "Exception:" in error_result.result
    assert "Specific error from approved function" in error_result.result  # Detail included


async def test_approved_function_call_with_validation_error(chat_client_base: ChatClientProtocol):
    """Test that approved functions with validation errors are handled correctly."""
    from agent_framework import FunctionApprovalResponseContent

    exec_counter = 0

    @ai_function(name="typed_func", approval_mode="always_require")
    def typed_func(arg1: int) -> str:  # Expects int, not str
        nonlocal exec_counter
        exec_counter += 1
        return f"Got {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="typed_func", arguments='{"arg1": "not_an_int"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Set include_detailed_errors to True to see validation details
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[typed_func])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]

    # Approve the function (even though it will fail validation)
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[approval_response])]

    # Execute the approved function (which will fail validation)
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[typed_func])

    # Should NOT have executed the function (validation failed before execution)
    assert exec_counter == 0

    # Should have a validation error result
    error_result = next(
        (
            content
            for msg in all_messages
            for content in msg.contents
            if isinstance(content, FunctionResultContent) and content.exception is not None
        ),
        None,
    )
    assert error_result is not None
    assert error_result.result is not None
    assert "Argument parsing failed" in error_result.result


async def test_approved_function_call_successful_execution(chat_client_base: ChatClientProtocol):
    """Test that approved functions execute successfully when no errors occur."""
    from agent_framework import FunctionApprovalResponseContent

    exec_counter = 0

    @ai_function(name="success_func", approval_mode="always_require")
    def success_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Success {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="success_func", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Get approval request
    response1 = await chat_client_base.get_response("hello", tool_choice="auto", tools=[success_func])

    approval_req = [c for c in response1.messages[0].contents if isinstance(c, FunctionApprovalRequestContent)][0]

    # Approve the function
    approval_response = FunctionApprovalResponseContent(
        id=approval_req.id,
        function_call=approval_req.function_call,
        approved=True,
    )

    all_messages = response1.messages + [ChatMessage(role="user", contents=[approval_response])]

    # Execute the approved function
    await chat_client_base.get_response(all_messages, tool_choice="auto", tools=[success_func])

    # Should have executed successfully
    assert exec_counter == 1

    # Should have a success result
    success_result = next(
        (
            content
            for msg in all_messages
            for content in msg.contents
            if isinstance(content, FunctionResultContent) and content.exception is None
        ),
        None,
    )
    assert success_result is not None
    assert success_result.result == "Success value1"


async def test_declaration_only_tool(chat_client_base: ChatClientProtocol):
    """Test that declaration_only tools without implementation (func=None) are not executed."""
    from agent_framework import AIFunction

    # Create a truly declaration-only function with no implementation
    declaration_func = AIFunction(
        name="declaration_func",
        func=None,
        description="A declaration-only function for testing",
        input_model={"type": "object", "properties": {"arg1": {"type": "string"}}, "required": ["arg1"]},
    )

    # Verify it's marked as declaration_only
    assert declaration_func.declaration_only is True

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="declaration_func", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[declaration_func])

    # Should have the function call in messages but not a result
    function_calls = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionCallContent) and content.name == "declaration_func"
    ]
    assert len(function_calls) >= 1

    # Should not have a function result
    function_results = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionResultContent) and content.call_id == "1"
    ]
    assert len(function_results) == 0


async def test_multiple_function_calls_parallel_execution(chat_client_base: ChatClientProtocol):
    """Test that multiple function calls are executed in parallel."""
    import asyncio

    exec_order = []

    @ai_function(name="func1")
    async def func1(arg1: str) -> str:
        exec_order.append("func1_start")
        await asyncio.sleep(0.01)  # Small delay
        exec_order.append("func1_end")
        return f"Result1 {arg1}"

    @ai_function(name="func2")
    async def func2(arg1: str) -> str:
        exec_order.append("func2_start")
        await asyncio.sleep(0.01)  # Small delay
        exec_order.append("func2_end")
        return f"Result2 {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    FunctionCallContent(call_id="1", name="func1", arguments='{"arg1": "value1"}'),
                    FunctionCallContent(call_id="2", name="func2", arguments='{"arg1": "value2"}'),
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[func1, func2])

    # Both functions should have been executed
    assert "func1_start" in exec_order
    assert "func1_end" in exec_order
    assert "func2_start" in exec_order
    assert "func2_end" in exec_order

    # Should have results for both
    results = [
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    ]
    assert len(results) == 2


async def test_callable_function_converted_to_ai_function(chat_client_base: ChatClientProtocol):
    """Test that plain callable functions are converted to AIFunction."""
    exec_counter = 0

    def plain_function(arg1: str) -> str:
        """A plain function without decorator."""
        nonlocal exec_counter
        exec_counter += 1
        return f"Plain {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="plain_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    # Pass plain function (will be auto-converted)
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[plain_function])

    # Function should be executed
    assert exec_counter == 1
    result = next(
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    )
    assert result.result == "Plain value1"


async def test_conversation_id_handling(chat_client_base: ChatClientProtocol):
    """Test that conversation_id is properly handled and messages are cleared."""

    @ai_function(name="test_function")
    def test_func(arg1: str) -> str:
        return f"Result {arg1}"

    # Return a response with a conversation_id
    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            ),
            conversation_id="conv_123",  # Simulate service-side thread
        ),
        ChatResponse(
            messages=ChatMessage(role="assistant", text="done"),
            conversation_id="conv_123",
        ),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[test_func])

    # Should have executed the function
    results = [
        content for msg in response.messages for content in msg.contents if isinstance(content, FunctionResultContent)
    ]
    assert len(results) >= 1
    assert response.conversation_id == "conv_123"


async def test_function_result_appended_to_existing_assistant_message(chat_client_base: ChatClientProtocol):
    """Test that function results are appended to existing assistant message when appropriate."""

    @ai_function(name="test_function")
    def test_func(arg1: str) -> str:
        return f"Result {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[test_func])

    # Should have messages with both function call and function result
    assert len(response.messages) >= 2
    # Check that we have both a function call and a function result
    has_call = any(isinstance(content, FunctionCallContent) for msg in response.messages for content in msg.contents)
    has_result = any(
        isinstance(content, FunctionResultContent) for msg in response.messages for content in msg.contents
    )
    assert has_call
    assert has_result


async def test_error_recovery_resets_counter(chat_client_base: ChatClientProtocol):
    """Test that error counter resets after a successful function call."""

    call_count = 0

    @ai_function(name="sometimes_fails")
    def sometimes_fails(arg1: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First call fails")
        return f"Success {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="sometimes_fails", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="2", name="sometimes_fails", arguments='{"arg1": "value2"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[sometimes_fails])

    # Should have both an error and a success
    error_results = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionResultContent) and content.exception
    ]
    success_results = [
        content
        for msg in response.messages
        for content in msg.contents
        if isinstance(content, FunctionResultContent) and content.result
    ]

    assert len(error_results) >= 1
    assert len(success_results) >= 1
    assert call_count == 2  # Both calls executed


# ==================== STREAMING SCENARIO TESTS ====================


async def test_streaming_approval_request_generated(chat_client_base: ChatClientProtocol):
    """Test that approval requests are generated correctly in streaming mode."""
    exec_counter = 0

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Result {arg1}"

    # Setup: function call that requires approval, streamed
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
    ]

    # Get the streaming response with approval request
    updates = []
    async for update in chat_client_base.get_streaming_response(
        "hello", tool_choice="auto", tools=[func_with_approval]
    ):
        updates.append(update)

    # Should have function call update and approval request
    approval_requests = [
        content
        for update in updates
        for content in update.contents
        if isinstance(content, FunctionApprovalRequestContent)
    ]
    assert len(approval_requests) == 1
    assert approval_requests[0].function_call.name == "test_func"
    assert exec_counter == 0  # Function not executed yet due to approval requirement


async def test_streaming_max_iterations_limit(chat_client_base: ChatClientProtocol):
    """Test that MAX_ITERATIONS in streaming mode limits function call loops."""
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    # Set up multiple function call responses to create a loop
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
                contents=[FunctionCallContent(call_id="2", name="test_function", arguments='{"arg1":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="2", name="test_function", arguments='"value2"}')],
                role="assistant",
            ),
        ],
        # Failsafe response when tool_choice is set to "none"
        [ChatResponseUpdate(contents=[TextContent(text="giving up on tools")], role="assistant")],
    ]

    # Set max_iterations to 1 in additional_properties
    chat_client_base.function_invocation_configuration.max_iterations = 1

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)

    # With max_iterations=1, we should only execute first function
    assert exec_counter == 1  # Only first function executed
    # Should have the failsafe message
    last_text = "".join(u.text or "" for u in updates if u.text)
    assert "I broke out of the function invocation loop..." in last_text


async def test_streaming_function_invocation_config_enabled_false(chat_client_base: ChatClientProtocol):
    """Test that setting enabled=False disables function invocation in streaming mode."""
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [ChatResponseUpdate(contents=[TextContent(text="response without function calling")], role="assistant")],
    ]

    # Disable function invocation
    chat_client_base.function_invocation_configuration.enabled = False

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)

    # Function should not be executed - when enabled=False, the loop doesn't run
    assert exec_counter == 0
    # The response should be from the mock client
    assert len(updates) > 0


async def test_streaming_function_invocation_config_max_consecutive_errors(chat_client_base: ChatClientProtocol):
    """Test that max_consecutive_errors_per_request limits error retries in streaming mode."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Function error")

    # Set up multiple function call responses that will all error
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="2", name="error_function", arguments='{"arg1": "value2"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="3", name="error_function", arguments='{"arg1": "value3"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="final response")], role="assistant")],
    ]

    # Set max_consecutive_errors to 2
    chat_client_base.function_invocation_configuration.max_consecutive_errors_per_request = 2

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[error_func]):
        updates.append(update)

    # Should stop after 2 consecutive errors
    error_results = [
        content
        for update in updates
        for content in update.contents
        if isinstance(content, FunctionResultContent) and content.exception
    ]
    # At least one error occurred
    assert len(error_results) >= 1
    # Should have stopped making new function calls after hitting the error limit
    function_calls = [
        content for update in updates for content in update.contents if isinstance(content, FunctionCallContent)
    ]
    # Should have made at most 2 function calls before stopping
    assert len(function_calls) <= 2


async def test_streaming_function_invocation_config_terminate_on_unknown_calls_false(
    chat_client_base: ChatClientProtocol,
):
    """Test that terminate_on_unknown_calls=False returns error message for unknown functions in streaming mode."""
    exec_counter = 0

    @ai_function(name="known_function")
    def known_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="unknown_function", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    # Set terminate_on_unknown_calls to False (default)
    chat_client_base.function_invocation_configuration.terminate_on_unknown_calls = False

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[known_func]):
        updates.append(update)

    # Should have a result message indicating the tool wasn't found
    result_contents = [
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    ]
    assert len(result_contents) >= 1
    result_str = result_contents[0].result or result_contents[0].exception or ""
    assert "not found" in result_str.lower()
    assert exec_counter == 0  # Known function not executed


async def test_streaming_function_invocation_config_terminate_on_unknown_calls_true(
    chat_client_base: ChatClientProtocol,
):
    """Test that terminate_on_unknown_calls=True stops execution on unknown functions in streaming mode."""
    exec_counter = 0

    @ai_function(name="known_function")
    def known_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="unknown_function", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
    ]

    # Set terminate_on_unknown_calls to True
    chat_client_base.function_invocation_configuration.terminate_on_unknown_calls = True

    # Should raise an exception when encountering an unknown function
    with pytest.raises(KeyError, match='Error: Requested function "unknown_function" not found'):
        async for _ in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[known_func]):
            pass

    assert exec_counter == 0


async def test_streaming_function_invocation_config_include_detailed_errors_true(chat_client_base: ChatClientProtocol):
    """Test that include_detailed_errors=True returns detailed error information in streaming mode."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Specific error message that should appear")

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    # Set include_detailed_errors to True
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[error_func]):
        updates.append(update)

    # Should have detailed error message
    error_result = next(
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Specific error message that should appear" in error_result.result
    assert "Exception:" in error_result.result


async def test_streaming_function_invocation_config_include_detailed_errors_false(
    chat_client_base: ChatClientProtocol,
):
    """Test that include_detailed_errors=False returns generic error messages in streaming mode."""

    @ai_function(name="error_function")
    def error_func(arg1: str) -> str:
        raise ValueError("Specific error message that should not appear")

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="error_function", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    # Set include_detailed_errors to False (default)
    chat_client_base.function_invocation_configuration.include_detailed_errors = False

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[error_func]):
        updates.append(update)

    # Should have a generic error message
    error_result = next(
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Specific error message" not in error_result.result
    assert "Error:" in error_result.result  # Generic error prefix


async def test_streaming_argument_validation_error_with_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that argument validation errors include details when include_detailed_errors=True in streaming mode."""

    @ai_function(name="typed_function")
    def typed_func(arg1: int) -> str:  # Expects int, not str
        return f"Got {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="typed_function", arguments='{"arg1": "not_an_int"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    # Set include_detailed_errors to True
    chat_client_base.function_invocation_configuration.include_detailed_errors = True

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[typed_func]):
        updates.append(update)

    # Should have detailed validation error
    error_result = next(
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Argument parsing failed" in error_result.result
    assert "Exception:" in error_result.result  # Detailed error included


async def test_streaming_argument_validation_error_without_detailed_errors(chat_client_base: ChatClientProtocol):
    """Test that argument validation errors are generic when include_detailed_errors=False in streaming mode."""

    @ai_function(name="typed_function")
    def typed_func(arg1: int) -> str:  # Expects int, not str
        return f"Got {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="typed_function", arguments='{"arg1": "not_an_int"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    # Set include_detailed_errors to False (default)
    chat_client_base.function_invocation_configuration.include_detailed_errors = False

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[typed_func]):
        updates.append(update)

    # Should have generic validation error
    error_result = next(
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    )
    assert error_result.result is not None
    assert error_result.exception is not None
    assert "Argument parsing failed" in error_result.result
    assert "Exception:" not in error_result.result  # No detailed error


async def test_streaming_multiple_function_calls_parallel_execution(chat_client_base: ChatClientProtocol):
    """Test that multiple function calls are executed in parallel in streaming mode."""
    import asyncio

    exec_order = []

    @ai_function(name="func1")
    async def func1(arg1: str) -> str:
        exec_order.append("func1_start")
        await asyncio.sleep(0.01)  # Small delay
        exec_order.append("func1_end")
        return f"Result1 {arg1}"

    @ai_function(name="func2")
    async def func2(arg1: str) -> str:
        exec_order.append("func2_start")
        await asyncio.sleep(0.01)  # Small delay
        exec_order.append("func2_end")
        return f"Result2 {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="func1", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="2", name="func2", arguments='{"arg1": "value2"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[func1, func2]):
        updates.append(update)

    # Both functions should have been executed
    assert "func1_start" in exec_order
    assert "func1_end" in exec_order
    assert "func2_start" in exec_order
    assert "func2_end" in exec_order

    # Should have results for both
    results = [
        content for update in updates for content in update.contents if isinstance(content, FunctionResultContent)
    ]
    assert len(results) == 2


async def test_streaming_approval_requests_in_assistant_message(chat_client_base: ChatClientProtocol):
    """Approval requests should be added to assistant updates in streaming mode."""
    exec_counter = 0

    @ai_function(name="test_func", approval_mode="always_require")
    def func_with_approval(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Result {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[
                    FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}'),
                ],
                role="assistant",
            ),
        ],
    ]

    updates = []
    async for update in chat_client_base.get_streaming_response(
        "hello", tool_choice="auto", tools=[func_with_approval]
    ):
        updates.append(update)

    # Should have updates containing both the call and approval request
    approval_requests = [
        content
        for update in updates
        for content in update.contents
        if isinstance(content, FunctionApprovalRequestContent)
    ]
    assert len(approval_requests) == 1
    assert exec_counter == 0


async def test_streaming_error_recovery_resets_counter(chat_client_base: ChatClientProtocol):
    """Test that error counter resets after a successful function call in streaming mode."""

    call_count = 0

    @ai_function(name="sometimes_fails")
    def sometimes_fails(arg1: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First call fails")
        return f"Success {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="sometimes_fails", arguments='{"arg1": "value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="2", name="sometimes_fails", arguments='{"arg1": "value2"}')],
                role="assistant",
            ),
        ],
        [ChatResponseUpdate(contents=[TextContent(text="done")], role="assistant")],
    ]

    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[sometimes_fails]):
        updates.append(update)

    # Should have both an error and a success
    error_results = [
        content
        for update in updates
        for content in update.contents
        if isinstance(content, FunctionResultContent) and content.exception
    ]
    success_results = [
        content
        for update in updates
        for content in update.contents
        if isinstance(content, FunctionResultContent) and content.result
    ]

    assert len(error_results) >= 1
    assert len(success_results) >= 1
    assert call_count == 2  # Both calls executed
