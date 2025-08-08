"""Tests for core abstractions"""

import pytest
from datetime import datetime
from agent_runtime.runtime_abstractions import (
    ActorId, ActorMessage, ActorRequestMessage, ActorResponseMessage,
    ActorMessageType, RequestStatus
)
from agent_runtime.runtime import InMemoryStateStorage


class TestActorId:
    def test_actor_id_creation(self):
        actor_id = ActorId(type_name="test", instance_id="123")
        assert actor_id.type_name == "test"
        assert actor_id.instance_id == "123"
    
    def test_actor_id_string_representation(self):
        actor_id = ActorId(type_name="echo", instance_id="conv-1")
        assert str(actor_id) == "echo/conv-1"
    
    def test_actor_id_hashable(self):
        actor_id1 = ActorId(type_name="test", instance_id="123")
        actor_id2 = ActorId(type_name="test", instance_id="123")
        actor_id3 = ActorId(type_name="test", instance_id="456")
        
        # Should be hashable (can be used in sets/dicts)
        actor_set = {actor_id1, actor_id2, actor_id3}
        assert len(actor_set) == 2  # id1 and id2 are equal


class TestActorMessages:
    def test_actor_request_message_creation(self):
        msg = ActorRequestMessage(
            message_id="test-123",
            message_type=ActorMessageType.REQUEST,
            method="test_method",
            params={"key": "value"}
        )
        assert msg.message_id == "test-123"
        assert msg.message_type == ActorMessageType.REQUEST
        assert msg.method == "test_method"
        assert msg.params == {"key": "value"}
        assert isinstance(msg.timestamp, datetime)
    
    def test_actor_response_message_creation(self):
        actor_id = ActorId(type_name="test", instance_id="123")
        msg = ActorResponseMessage(
            message_id="test-123",
            message_type=ActorMessageType.RESPONSE,
            sender_id=actor_id,
            status=RequestStatus.COMPLETED,
            data={"result": "success"}
        )
        assert msg.message_id == "test-123"
        assert msg.message_type == ActorMessageType.RESPONSE
        assert msg.sender_id == actor_id
        assert msg.status == RequestStatus.COMPLETED
        assert msg.data == {"result": "success"}


# Note: ChatMessage and AgentRunResponse are now framework types
# and tested in the framework, not the runtime


class TestInMemoryStateStorage:
    @pytest.fixture
    def storage(self):
        return InMemoryStateStorage()
    
    @pytest.fixture  
    def actor_id(self):
        return ActorId(type_name="test", instance_id="123")
    
    @pytest.mark.asyncio
    async def test_read_write_state(self, storage, actor_id):
        # Test writing state
        state_data = {"key1": "value1", "key2": "value2"}
        result = await storage.write_state(actor_id, state_data)
        assert result is True
        
        # Test reading state
        read_state = await storage.read_state(actor_id)
        assert read_state == state_data
    
    @pytest.mark.asyncio
    async def test_read_nonexistent_actor(self, storage):
        nonexistent_actor = ActorId(type_name="nonexistent", instance_id="123")
        result = await storage.read_state(nonexistent_actor)
        assert result == {}  # Returns empty dict for nonexistent actor
    
    @pytest.mark.asyncio
    async def test_delete_state(self, storage, actor_id):
        # Write some state
        state_data = {"important": "data"}
        await storage.write_state(actor_id, state_data)
        
        # Verify state exists
        read_state = await storage.read_state(actor_id)
        assert read_state == state_data
        
        # Delete state
        result = await storage.delete_state(actor_id)
        assert result is True
        
        # Verify state is gone
        read_state = await storage.read_state(actor_id)
        assert read_state == {}
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, storage):
        import asyncio
        
        # Test concurrent writes to different actors
        actor1 = ActorId(type_name="concurrent", instance_id="1")
        actor2 = ActorId(type_name="concurrent", instance_id="2")
        
        async def write_actor_state(actor_id, data):
            return await storage.write_state(actor_id, data)
        
        # Write concurrently
        results = await asyncio.gather(
            write_actor_state(actor1, {"actor": "1"}),
            write_actor_state(actor2, {"actor": "2"})
        )
        
        assert all(results)
        
        # Read back
        state1 = await storage.read_state(actor1)
        state2 = await storage.read_state(actor2)
        
        assert state1 == {"actor": "1"}
        assert state2 == {"actor": "2"}