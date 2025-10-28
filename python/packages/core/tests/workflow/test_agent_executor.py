# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import AsyncIterable
from typing import Any

import pytest

from agent_framework import (
    AgentExecutor,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatAgent,
    ChatMessage,
    ChatMessageStore,
    Role,
    SequentialBuilder,
    TextContent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage

skip_if_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/"),
    reason="No real AZURE_AI_PROJECT_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


class _CountingAgent(BaseAgent):
    """Agent that echoes messages with a counter to verify thread state persistence."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.call_count = 0

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        self.call_count += 1
        return AgentRunResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, text=f"Response #{self.call_count}: {self.display_name}")]
        )

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        self.call_count += 1
        yield AgentRunResponseUpdate(contents=[TextContent(text=f"Response #{self.call_count}: {self.display_name}")])


async def test_agent_executor_checkpoint_stores_and_restores_state() -> None:
    """Test that workflow checkpoint stores AgentExecutor's cache and thread states and restores them correctly."""
    storage = InMemoryCheckpointStorage()

    # Create initial agent with a custom thread that has a message store
    initial_agent = _CountingAgent(id="test_agent", name="TestAgent")
    initial_thread = AgentThread(message_store=ChatMessageStore())

    # Add some initial messages to the thread to verify thread state persistence
    initial_messages = [
        ChatMessage(role=Role.USER, text="Initial message 1"),
        ChatMessage(role=Role.ASSISTANT, text="Initial response 1"),
    ]
    await initial_thread.on_new_messages(initial_messages)

    # Create AgentExecutor with the thread
    executor = AgentExecutor(initial_agent, agent_thread=initial_thread)

    # Build workflow with checkpointing enabled
    wf = SequentialBuilder().participants([executor]).with_checkpointing(storage).build()

    # Run the workflow with a user message
    first_run_output: AgentExecutorResponse | None = None
    async for ev in wf.run_stream("First workflow run"):
        if isinstance(ev, WorkflowOutputEvent):
            first_run_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            break

    assert first_run_output is not None
    assert initial_agent.call_count == 1

    # Verify checkpoint was created
    checkpoints = await storage.list_checkpoints()
    assert len(checkpoints) > 0

    # Find a suitable checkpoint to restore (prefer superstep checkpoint)
    checkpoints.sort(key=lambda cp: cp.timestamp)
    restore_checkpoint = next(
        (cp for cp in checkpoints if (cp.metadata or {}).get("checkpoint_type") == "superstep"),
        checkpoints[-1],
    )

    # Verify checkpoint contains executor state with both cache and thread
    assert "_executor_state" in restore_checkpoint.shared_state
    executor_states = restore_checkpoint.shared_state["_executor_state"]
    assert isinstance(executor_states, dict)
    assert executor.id in executor_states

    executor_state = executor_states[executor.id]  # type: ignore[index]
    assert "cache" in executor_state, "Checkpoint should store executor cache state"
    assert "agent_thread" in executor_state, "Checkpoint should store executor thread state"

    # Verify thread state includes message store
    thread_state = executor_state["agent_thread"]  # type: ignore[index]
    assert "chat_message_store_state" in thread_state, "Thread state should include message store"
    chat_store_state = thread_state["chat_message_store_state"]  # type: ignore[index]
    assert "messages" in chat_store_state, "Message store state should include messages"

    # Create a new agent and executor for restoration
    # This simulates starting from a fresh state and restoring from checkpoint
    restored_agent = _CountingAgent(id="test_agent", name="TestAgent")
    restored_thread = AgentThread(message_store=ChatMessageStore())
    restored_executor = AgentExecutor(restored_agent, agent_thread=restored_thread)

    # Verify the restored agent starts with a fresh state
    assert restored_agent.call_count == 0

    # Build new workflow with the restored executor
    wf_resume = SequentialBuilder().participants([restored_executor]).with_checkpointing(storage).build()

    # Resume from checkpoint
    resumed_output: AgentExecutorResponse | None = None
    async for ev in wf_resume.run_stream_from_checkpoint(restore_checkpoint.checkpoint_id):
        if isinstance(ev, WorkflowOutputEvent):
            resumed_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert resumed_output is not None

    # Verify the restored executor's state matches the original
    # The cache should be restored (though it may be cleared after processing)
    # The thread should have all messages including those from the initial state
    message_store = restored_executor._agent_thread.message_store  # type: ignore[reportPrivateUsage]
    assert message_store is not None
    thread_messages = await message_store.list_messages()

    # Thread should contain:
    # 1. Initial messages from before the checkpoint (2 messages)
    # 2. User message from first run (1 message)
    # 3. Assistant response from first run (1 message)
    assert len(thread_messages) >= 2, "Thread should preserve initial messages from before checkpoint"

    # Verify initial messages are preserved
    assert thread_messages[0].text == "Initial message 1"
    assert thread_messages[1].text == "Initial response 1"


async def test_agent_executor_snapshot_and_restore_state_directly() -> None:
    """Test AgentExecutor's snapshot_state and restore_state methods directly."""
    # Create agent with thread containing messages
    agent = _CountingAgent(id="direct_test_agent", name="DirectTestAgent")
    thread = AgentThread(message_store=ChatMessageStore())

    # Add messages to thread
    thread_messages = [
        ChatMessage(role=Role.USER, text="Message in thread 1"),
        ChatMessage(role=Role.ASSISTANT, text="Thread response 1"),
        ChatMessage(role=Role.USER, text="Message in thread 2"),
    ]
    await thread.on_new_messages(thread_messages)

    executor = AgentExecutor(agent, agent_thread=thread)

    # Add messages to executor cache
    cache_messages = [
        ChatMessage(role=Role.USER, text="Cached user message"),
        ChatMessage(role=Role.ASSISTANT, text="Cached assistant response"),
    ]
    executor._cache = list(cache_messages)  # type: ignore[reportPrivateUsage]

    # Snapshot the state
    state = await executor.snapshot_state()  # type: ignore[reportUnknownMemberType]

    # Verify snapshot contains both cache and thread
    assert "cache" in state
    assert "agent_thread" in state

    # Verify thread state structure
    thread_state = state["agent_thread"]  # type: ignore[index]
    assert "chat_message_store_state" in thread_state
    assert "messages" in thread_state["chat_message_store_state"]

    # Create new executor to restore into
    new_agent = _CountingAgent(id="direct_test_agent", name="DirectTestAgent")
    new_thread = AgentThread(message_store=ChatMessageStore())
    new_executor = AgentExecutor(new_agent, agent_thread=new_thread)

    # Verify new executor starts empty
    assert len(new_executor._cache) == 0  # type: ignore[reportPrivateUsage]
    initial_message_store = new_thread.message_store
    assert initial_message_store is not None
    initial_thread_msgs = await initial_message_store.list_messages()
    assert len(initial_thread_msgs) == 0

    # Restore state
    await new_executor.restore_state(state)  # type: ignore[reportUnknownMemberType]

    # Verify cache is restored
    restored_cache = new_executor._cache  # type: ignore[reportPrivateUsage]
    assert len(restored_cache) == len(cache_messages)
    assert restored_cache[0].text == "Cached user message"
    assert restored_cache[1].text == "Cached assistant response"

    # Verify thread messages are restored
    restored_message_store = new_executor._agent_thread.message_store  # type: ignore[reportPrivateUsage]
    assert restored_message_store is not None
    restored_thread_msgs = await restored_message_store.list_messages()
    assert len(restored_thread_msgs) == len(thread_messages)
    assert restored_thread_msgs[0].text == "Message in thread 1"
    assert restored_thread_msgs[1].text == "Thread response 1"
    assert restored_thread_msgs[2].text == "Message in thread 2"


async def test_agent_executor_snapshot_with_service_thread() -> None:
    """Test that snapshot_state converts server-side threads to local threads with messages."""
    # Create agent with a server-side thread
    agent = _CountingAgent(id="service_thread_agent", name="ServiceThreadAgent")

    # Create a service thread with messages
    # In real scenarios, the service maintains the messages, but we mock this by setting up the store
    message_store = ChatMessageStore()
    thread_messages = [
        ChatMessage(role=Role.USER, text="Server message 1"),
        ChatMessage(role=Role.ASSISTANT, text="Server response 1"),
    ]
    await message_store.add_messages(thread_messages)

    # Create service thread and manually set its message store (simulating server-side state)
    service_thread = AgentThread(service_thread_id="server-thread-123")
    service_thread._message_store = message_store  # type: ignore[reportPrivateUsage]

    executor = AgentExecutor(agent, agent_thread=service_thread)

    # Snapshot the state
    state = await executor.snapshot_state()  # type: ignore[reportUnknownMemberType]

    # Verify snapshot contains thread state
    assert "agent_thread" in state
    thread_state = state["agent_thread"]  # type: ignore[index]

    # Verify that the snapshotted thread is converted to a LOCAL thread (no service_thread_id)
    # This makes the checkpoint self-contained and prevents corruption
    assert thread_state.get("service_thread_id") is None, "Snapshot should convert to local thread"

    # Verify that the thread state HAS a message store with the copied messages
    assert thread_state.get("chat_message_store_state") is not None, "Local thread should include message store"

    # Now test restoration - the restored thread should be a local thread with messages
    new_agent = _CountingAgent(id="service_thread_agent", name="ServiceThreadAgent")
    new_thread = AgentThread(message_store=ChatMessageStore())
    new_executor = AgentExecutor(new_agent, agent_thread=new_thread)

    await new_executor.restore_state(state)  # type: ignore[reportUnknownMemberType]

    # Verify the restored thread is a LOCAL thread (no service_thread_id)
    assert (
        new_executor._agent_thread.service_thread_id is None  # type: ignore[reportPrivateUsage]
    ), "Restored thread should be local (no service_thread_id)"

    # Verify the messages are restored
    restored_message_store = new_executor._agent_thread.message_store  # type: ignore[reportPrivateUsage]
    assert restored_message_store is not None
    restored_messages = await restored_message_store.list_messages()
    assert len(restored_messages) == 2
    assert restored_messages[0].text == "Server message 1"
    assert restored_messages[1].text == "Server response 1"


@skip_if_integration_tests_disabled
async def test_agent_executor_checkpoint_with_azure_ai_agent() -> None:
    """Integration test for AgentExecutor checkpoint with AzureAIAgent (server-side threads)."""
    from agent_framework_azure_ai import AzureAIAgentClient
    from azure.ai.agents.models import MessageTextContent
    from azure.identity.aio import AzureCliCredential

    storage = InMemoryCheckpointStorage()
    original_service_thread_id: str | None = None
    checkpoint_id: str = ""

    # Create an Azure AI agent with server-side thread management
    async with AzureAIAgentClient(async_credential=AzureCliCredential()) as azure_client:
        agent = ChatAgent(
            id="azure_ai_agent",
            name="AzureAITestAgent",
            chat_client=azure_client,
            instructions="You are a helpful assistant.",
        )

        # Create executor with a new thread
        thread = agent.get_new_thread()
        executor = AgentExecutor(agent, agent_thread=thread)

        # Create workflow with checkpointing
        wf = SequentialBuilder().participants([executor]).with_checkpointing(storage).build()

        # Run the workflow with a simple message
        result: AgentExecutorResponse | None = None
        async for ev in wf.run_stream("What is 2 + 2?"):
            if isinstance(ev, WorkflowOutputEvent):
                result = ev.data  # type: ignore[assignment]

        assert result is not None

        # The thread should now have a service_thread_id from Azure AI
        assert executor._agent_thread.service_thread_id is not None  # type: ignore[reportPrivateUsage]
        original_service_thread_id = executor._agent_thread.service_thread_id  # type: ignore[reportPrivateUsage]

        # Get the checkpoint
        checkpoints = await storage.list_checkpoints()
        assert len(checkpoints) > 0
        checkpoints.sort(key=lambda cp: cp.timestamp)
        checkpoint = checkpoints[-1]
        checkpoint_id = checkpoint.checkpoint_id

        # Verify checkpoint contains executor state
        assert "_executor_state" in checkpoint.shared_state
        executor_states = checkpoint.shared_state["_executor_state"]
        assert executor.id in executor_states

        executor_state = executor_states[executor.id]  # type: ignore[index]
        thread_state = executor_state["agent_thread"]  # type: ignore[index]

        # Verify that the snapshot converted the server-side thread to a local thread
        assert (
            thread_state.get("service_thread_id") is None  # type: ignore[reportUnknownMemberType]
        ), "Snapshot should convert server-side thread to local thread"
        assert (
            thread_state.get("chat_message_store_state") is not None  # type: ignore[reportUnknownMemberType]
        ), "Snapshot should include message store with messages"

    # Create a new agent and executor for restoration (outside the first client's context)
    async with AzureAIAgentClient(async_credential=AzureCliCredential()) as azure_client2:
        new_agent = ChatAgent(
            id="azure_ai_agent",  # Same ID as original
            name="AzureAITestAgent",  # Same name as original
            chat_client=azure_client2,
            instructions="You are a helpful assistant.",
        )

        new_executor = AgentExecutor(new_agent, agent_thread=new_agent.get_new_thread())

        # Build new workflow with the restored executor and restore from checkpoint
        wf_resume = SequentialBuilder().participants([new_executor]).with_checkpointing(storage).build()

        # Resume from checkpoint
        # Run synchronously to completion.
        await wf_resume.run_from_checkpoint(checkpoint_id)

        # Verify that the restored thread has a service_thread_id (for Azure AI)
        final_service_thread_id = new_executor._agent_thread.service_thread_id  # type: ignore[reportPrivateUsage]

        # The key assertion: the final thread ID should NOT be the same as the original
        # This ensures we didn't corrupt the original server-side thread
        if final_service_thread_id is not None:
            assert final_service_thread_id != original_service_thread_id, (
                "Restored thread should have a different service_thread_id to avoid corrupting the original checkpoint"
            )

        # Verify messages were restored by checking the thread through the Azure AI API
        if final_service_thread_id is not None:
            # Use the Azure AI SDK to list messages in the thread
            messages_response = azure_client2.project_client.agents.messages.list(thread_id=final_service_thread_id)
            messages_list = [msg async for msg in messages_response]

            # Should have at least the user message ("What is 2 + 2?") and assistant response
            assert len(messages_list) > 0, "Restored thread should have messages from checkpoint"

            # Verify we have the user's question in the messages
            user_messages = [msg for msg in messages_list if msg.role == "user"]
            assert len(user_messages) > 0, "Should have user messages in restored thread"

            # Verify the content of the user message matches the original question
            found_original_question = False
            for msg in user_messages:
                if msg.content:
                    for content_item in msg.content:
                        # Check if this is a text content item with our question
                        if (
                            isinstance(content_item, MessageTextContent)
                            and content_item.text
                            and "What is 2 + 2?" in content_item.text.value
                        ):
                            found_original_question = True
                            break
                if found_original_question:
                    break

            assert found_original_question, "Original user message 'What is 2 + 2?' should be in restored thread"
