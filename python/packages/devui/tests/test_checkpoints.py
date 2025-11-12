# Copyright (c) Microsoft. All rights reserved.

"""Tests for checkpoint-as-conversation-items implementation."""

from dataclasses import dataclass

import pytest
from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from agent_framework_devui._conversations import (
    CheckpointConversationManager,
    InMemoryConversationStore,
)


@dataclass
class WorkflowTestData:
    """Simple test data."""

    value: str


@dataclass
class WorkflowHILRequest:
    """HIL request for testing."""

    question: str


class WorkflowTestExecutor(Executor):
    """Test executor with HIL."""

    @handler
    async def process(self, data: WorkflowTestData, ctx: WorkflowContext) -> None:
        """Process data and request approval."""
        await ctx.set_executor_state({"data_value": data.value})

        # Request HIL (checkpoint created here)
        await ctx.request_info(request_data=WorkflowHILRequest(question=f"Approve {data.value}?"), response_type=str)

    @response_handler
    async def handle_response(
        self, original_request: WorkflowHILRequest, response: str, ctx: WorkflowContext[str]
    ) -> None:
        """Handle HIL response."""
        state = await ctx.get_executor_state() or {}
        value = state.get("data_value", "")
        await ctx.send_message(f"{value}_approved" if response.lower() == "yes" else f"{value}_rejected")


@pytest.fixture
def conversation_store():
    """Create in-memory conversation store."""
    return InMemoryConversationStore()


@pytest.fixture
def checkpoint_manager(conversation_store):
    """Create checkpoint manager."""
    return CheckpointConversationManager(conversation_store)


@pytest.fixture
def test_workflow():
    """Create test workflow with checkpointing."""
    executor = WorkflowTestExecutor(id="test_executor")
    checkpoint_storage = InMemoryCheckpointStorage()

    return (
        WorkflowBuilder(name="Test Workflow", description="Test checkpoint behavior")
        .set_start_executor(executor)
        .with_checkpointing(checkpoint_storage)
        .build()
    )


class TestCheckpointConversationManager:
    """Test CheckpointConversationManager functionality - CONVERSATION-SCOPED."""

    @pytest.mark.asyncio
    async def test_conversation_scoped_checkpoint_save(self, checkpoint_manager, test_workflow):
        """Test checkpoint save in a specific conversation."""
        entity_id = "test_entity"
        conversation_id = f"conv_{entity_id}_test123"

        # Create conversation first
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Create test checkpoint
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()), workflow_id=test_workflow.id, messages={}, shared_state={"test": "data"}
        )

        # Get checkpoint storage for this conversation and save
        storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        checkpoint_id = await storage.save_checkpoint(checkpoint)

        assert checkpoint_id == checkpoint.checkpoint_id

        # Verify checkpoint stored in THIS conversation only
        checkpoints = await storage.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0].checkpoint_id == checkpoint.checkpoint_id

    @pytest.mark.asyncio
    async def test_conversation_isolation(self, checkpoint_manager, test_workflow):
        """Test that conversations are isolated - checkpoints don't leak between conversations."""
        entity_id = "test_entity"
        conv_a = f"conv_{entity_id}_aaa"
        conv_b = f"conv_{entity_id}_bbb"

        # Create two conversations
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conv_a
        )
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conv_b
        )

        # Save checkpoint to conversation A
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        checkpoint_a = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            workflow_id=test_workflow.id,
            messages={},
            shared_state={"conversation": "A"},
        )
        storage_a = checkpoint_manager.get_checkpoint_storage(conv_a)
        await storage_a.save_checkpoint(checkpoint_a)

        # Verify conversation A has checkpoint
        checkpoints_a = await storage_a.list_checkpoints()
        assert len(checkpoints_a) == 1

        # Verify conversation B has NO checkpoints (isolation)
        storage_b = checkpoint_manager.get_checkpoint_storage(conv_b)
        checkpoints_b = await storage_b.list_checkpoints()
        assert len(checkpoints_b) == 0

    @pytest.mark.asyncio
    async def test_list_checkpoints_in_session(self, checkpoint_manager, test_workflow):
        """Test listing checkpoints within a session."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_test456"

        # Create session
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Save multiple checkpoints
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        checkpoint_ids = []
        for i in range(3):
            checkpoint = WorkflowCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                workflow_id=test_workflow.id,
                messages={},
                shared_state={"iteration": i},
            )
            saved_id = await storage.save_checkpoint(checkpoint)
            checkpoint_ids.append(saved_id)

        # List checkpoints using the storage
        checkpoints_list = await storage.list_checkpoints()
        assert len(checkpoints_list) == 3

        # Verify all checkpoint IDs are present
        loaded_ids = [cp.checkpoint_id for cp in checkpoints_list]
        for saved_id in checkpoint_ids:
            assert saved_id in loaded_ids

    @pytest.mark.asyncio
    async def test_checkpoints_appear_as_conversation_items(self, checkpoint_manager, test_workflow):
        """Test that checkpoints appear as conversation items through the standard API."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_items_test"

        # Create session
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Save multiple checkpoints

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        checkpoint_ids = []
        for i in range(2):
            checkpoint = WorkflowCheckpoint(
                checkpoint_id=f"checkpoint_{i}",
                workflow_id=test_workflow.id,
                messages={},
                shared_state={"iteration": i},
            )
            saved_id = await storage.save_checkpoint(checkpoint)
            checkpoint_ids.append(saved_id)

        # List conversation items - should include checkpoints
        items, has_more = await checkpoint_manager.conversation_store.list_items(conversation_id)

        # Filter for checkpoint items
        checkpoint_items = [item for item in items if (isinstance(item, dict) and item.get("type") == "checkpoint")]

        # Verify we have the correct number of checkpoint items
        assert len(checkpoint_items) == 2, f"Expected 2 checkpoint items, got {len(checkpoint_items)}"

        # Verify checkpoint items have correct structure
        for item in checkpoint_items:
            assert item.get("type") == "checkpoint"
            assert item.get("checkpoint_id") in checkpoint_ids
            assert item.get("workflow_id") == test_workflow.id
            assert "timestamp" in item
            assert item.get("id").startswith("checkpoint_")  # ID format: checkpoint_{checkpoint_id}

    @pytest.mark.asyncio
    async def test_load_checkpoint_from_session(self, checkpoint_manager, test_workflow):
        """Test loading checkpoint from a specific session."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_test789"

        # Create session
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Create and save a checkpoint
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        original_checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            workflow_id=test_workflow.id,
            messages={},
            shared_state={"test_key": "test_value"},
        )

        # Save to this session
        storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        await storage.save_checkpoint(original_checkpoint)

        # Load checkpoint from this session
        loaded_checkpoint = await storage.load_checkpoint(original_checkpoint.checkpoint_id)

        assert loaded_checkpoint is not None
        assert loaded_checkpoint.checkpoint_id == original_checkpoint.checkpoint_id
        assert loaded_checkpoint.workflow_id == original_checkpoint.workflow_id
        assert loaded_checkpoint.shared_state == {"test_key": "test_value"}


class TestCheckpointStorage:
    """Test InMemoryCheckpointStorage per conversation - SESSION-SCOPED."""

    @pytest.mark.asyncio
    async def test_checkpoint_storage_protocol(self, checkpoint_manager, test_workflow):
        """Test that adapter implements CheckpointStorage protocol."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_adapter_test"

        # Create session
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Get storage adapter for this session
        storage = checkpoint_manager.get_checkpoint_storage(conversation_id)

        # Create test checkpoint
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()), workflow_id=test_workflow.id, messages={}, shared_state={"test": "data"}
        )

        # Test save_checkpoint
        checkpoint_id = await storage.save_checkpoint(checkpoint)
        assert checkpoint_id == checkpoint.checkpoint_id

        # Test load_checkpoint
        loaded = await storage.load_checkpoint(checkpoint_id)
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint_id

        # Test list_checkpoint_ids
        ids = await storage.list_checkpoint_ids(workflow_id=test_workflow.id)
        assert checkpoint_id in ids

        # Test list_checkpoints
        checkpoints_list = await storage.list_checkpoints(workflow_id=test_workflow.id)
        assert len(checkpoints_list) >= 1
        assert any(cp.checkpoint_id == checkpoint_id for cp in checkpoints_list)


class TestIntegration:
    """Integration tests for checkpoint workflow execution."""

    @pytest.mark.asyncio
    async def test_manual_checkpoint_save_via_injected_storage(self, checkpoint_manager, test_workflow):
        """Test manual checkpoint save via build-time storage injection."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_integration_test1"

        # Create session conversation
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Get checkpoint storage for this session
        checkpoint_storage = checkpoint_manager.get_checkpoint_storage(conversation_id)

        # Set build-time storage (equivalent to .with_checkpointing() at build time)
        # Note: In production, DevUI uses runtime injection via run_stream() parameter
        if hasattr(test_workflow, "_runner") and hasattr(test_workflow._runner, "context"):
            test_workflow._runner.context._checkpoint_storage = checkpoint_storage

        # Create and save a checkpoint via injected storage
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()), workflow_id=test_workflow.id, messages={}, shared_state={"injected": True}
        )
        await checkpoint_storage.save_checkpoint(checkpoint)

        # Verify checkpoint is accessible via storage (in this session)
        storage_checkpoints = await checkpoint_storage.list_checkpoints()
        assert len(storage_checkpoints) > 0
        assert storage_checkpoints[0].checkpoint_id == checkpoint.checkpoint_id

    @pytest.mark.asyncio
    async def test_checkpoint_roundtrip_via_storage(self, checkpoint_manager, test_workflow):
        """Test checkpoint save/load roundtrip via storage adapter."""
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_integration_test2"

        # Create session conversation
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Set build-time storage for testing
        checkpoint_storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        test_workflow._runner.context._checkpoint_storage = checkpoint_storage

        # Create checkpoint
        import uuid

        from agent_framework._workflows._checkpoint import WorkflowCheckpoint

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            workflow_id=test_workflow.id,
            messages={},
            shared_state={"ready_to_resume": True},
        )
        checkpoint_id = await checkpoint_storage.save_checkpoint(checkpoint)

        # Verify checkpoint can be loaded for resume
        loaded = await checkpoint_storage.load_checkpoint(checkpoint_id)
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint_id
        assert loaded.shared_state == {"ready_to_resume": True}

        # Verify checkpoint is accessible via storage (for UI to list checkpoints)
        checkpoints = await checkpoint_storage.list_checkpoints()
        assert len(checkpoints) > 0
        assert checkpoints[0].checkpoint_id == checkpoint_id

    @pytest.mark.asyncio
    async def test_workflow_auto_saves_checkpoints_to_injected_storage(self, checkpoint_manager, test_workflow):
        """Test that workflows automatically save checkpoints to our conversation-backed storage.

        This is the critical end-to-end test that verifies the entire checkpoint flow:
        1. Storage is set as build-time storage (simulates .with_checkpointing())
        2. Workflow runs and pauses at HIL point (IDLE_WITH_PENDING_REQUESTS status)
        3. Framework automatically saves checkpoint to our storage
        4. Checkpoint is accessible via manager for UI to list/resume

        Note: In production, DevUI passes checkpoint_storage to run_stream() as runtime parameter.
        This test uses build-time injection to verify framework's checkpoint auto-save behavior.
        """
        entity_id = "test_entity"
        conversation_id = f"session_{entity_id}_integration_test3"

        # Create session conversation
        checkpoint_manager.conversation_store.create_conversation(
            metadata={"entity_id": entity_id, "type": "workflow_session"}, conversation_id=conversation_id
        )

        # Set build-time storage to test automatic checkpoint saves
        checkpoint_storage = checkpoint_manager.get_checkpoint_storage(conversation_id)
        test_workflow._runner.context._checkpoint_storage = checkpoint_storage

        # Verify no checkpoints initially
        checkpoints_before = await checkpoint_storage.list_checkpoints()
        assert len(checkpoints_before) == 0

        # Run workflow until it reaches IDLE_WITH_PENDING_REQUESTS (after checkpoint is created)
        saw_request_event = False
        async for event in test_workflow.run_stream(WorkflowTestData(value="test")):
            if hasattr(event, "__class__"):
                if event.__class__.__name__ == "RequestInfoEvent":
                    saw_request_event = True
                # Wait for IDLE_WITH_PENDING_REQUESTS status (comes after checkpoint creation)
                is_status_event = event.__class__.__name__ == "WorkflowStatusEvent"
                has_pending_status = hasattr(event, "status") and "IDLE_WITH_PENDING_REQUESTS" in str(event.status)
                if is_status_event and has_pending_status:
                    break

        assert saw_request_event, "Test workflow should have emitted RequestInfoEvent"

        # Verify checkpoint was AUTOMATICALLY saved to our storage by the framework
        checkpoints_after = await checkpoint_storage.list_checkpoints()
        assert len(checkpoints_after) > 0, "Workflow should have auto-saved checkpoint at HIL pause"

        # Verify checkpoint has correct workflow_id
        checkpoint = checkpoints_after[0]
        assert checkpoint.workflow_id == test_workflow.id
