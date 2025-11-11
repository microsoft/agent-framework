# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any

from agent_framework import (
    AgentExecutor,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
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

    # Verify checkpoint contains pending requests from agents and responses to be sent
    assert "pending_agent_requests" in executor_state
    assert "pending_responses_to_agent" in executor_state

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
    async for ev in wf_resume.run_stream(checkpoint_id=restore_checkpoint.checkpoint_id):
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
