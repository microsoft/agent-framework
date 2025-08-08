"""Tests for the in-process actor runtime"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, Mock

from agent_runtime.runtime import InProcessActorRuntime, InProcessActorClient
from agent_runtime.runtime_abstractions import (
    ActorId, ActorRequestMessage, ActorResponseMessage,
    ActorMessageType, RequestStatus, IActor
)


class MockActor:
    """Simple mock actor for testing"""
    
    def __init__(self, context):
        self.actor_id = context.actor_id
        self.context = context
    
    async def run(self, context):
        """Main actor execution loop"""
        try:
            async for message in context.watch_messages():
                if isinstance(message, ActorRequestMessage):
                    if message.method == "echo":
                        response = ActorResponseMessage(
                            message_id=message.message_id,
                            message_type=ActorMessageType.RESPONSE,
                            sender_id=self.actor_id,
                            status=RequestStatus.COMPLETED,
                            data={"echo": message.params.get("text", "")}
                        )
                        self.context.complete_request(message.message_id, response)
                    else:
                        response = ActorResponseMessage(
                            message_id=message.message_id,
                            message_type=ActorMessageType.RESPONSE,
                            sender_id=self.actor_id,
                            status=RequestStatus.FAILED,
                            data={"error": "Unknown method"}
                        )
                        self.context.complete_request(message.message_id, response)
        except asyncio.CancelledError:
            # Expected when the runtime shuts down
            pass
        except Exception as e:
            print(f"Error in MockActor.run(): {e}")
            raise


class TestInProcessActorRuntime:
    @pytest_asyncio.fixture
    async def runtime(self):
        runtime = InProcessActorRuntime()
        runtime.register_actor_type("test", lambda context: MockActor(context))
        await runtime.start()
        yield runtime
        await runtime.stop()
    
    @pytest.mark.asyncio
    async def test_runtime_lifecycle(self):
        runtime = InProcessActorRuntime()
        
        # Test start
        await runtime.start()
        assert runtime._running is True
        
        # Test stop
        await runtime.stop()
        assert runtime._running is False
    
    @pytest.mark.asyncio
    async def test_actor_registration(self, runtime):
        # Actor type should be registered
        assert "test" in runtime._actor_factories
    
    @pytest.mark.asyncio
    async def test_actor_creation(self, runtime):
        actor_id = ActorId(type_name="test", instance_id="123")
        
        # Create actor
        context = runtime.get_or_create_actor(actor_id)
        assert context is not None
        assert context.actor_id == actor_id
        
        # Should return same context for same ID
        context2 = runtime.get_or_create_actor(actor_id)
        assert context is context2
    
    @pytest.mark.asyncio
    async def test_unknown_actor_type(self, runtime):
        actor_id = ActorId(type_name="unknown", instance_id="123")
        
        with pytest.raises(ValueError, match="No factory registered for actor type: unknown"):
            runtime.get_or_create_actor(actor_id)


class TestInProcessActorClient:
    @pytest_asyncio.fixture
    async def runtime_and_client(self):
        runtime = InProcessActorRuntime()
        runtime.register_actor_type("test", lambda context: MockActor(context))
        await runtime.start()
        
        client = InProcessActorClient(runtime)
        
        yield runtime, client
        
        await runtime.stop()
    
    @pytest.mark.asyncio
    async def test_send_request_success(self, runtime_and_client):
        runtime, client = runtime_and_client
        actor_id = ActorId(type_name="test", instance_id="echo-test")
        
        # Send echo request
        response_handle = await client.send_request(
            actor_id=actor_id,
            method="echo",
            params={"text": "hello world"}
        )
        
        # Get response
        response = await response_handle.get_response()
        
        assert response.status == RequestStatus.COMPLETED
        assert response.data["echo"] == "hello world"
    
    @pytest.mark.asyncio
    async def test_send_request_failure(self, runtime_and_client):
        runtime, client = runtime_and_client
        actor_id = ActorId(type_name="test", instance_id="fail-test")
        
        # Send unknown method request
        response_handle = await client.send_request(
            actor_id=actor_id,
            method="unknown_method",
            params={}
        )
        
        # Get response
        response = await response_handle.get_response()
        
        assert response.status == RequestStatus.FAILED
        assert "error" in response.data
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, runtime_and_client):
        runtime, client = runtime_and_client
        
        # Send multiple concurrent requests
        tasks = []
        for i in range(5):
            actor_id = ActorId(type_name="test", instance_id=f"concurrent-{i}")
            task = client.send_request(
                actor_id=actor_id,
                method="echo", 
                params={"text": f"message-{i}"}
            )
            tasks.append(task)
        
        # Wait for all response handles
        response_handles = await asyncio.gather(*tasks)
        
        # Get all responses
        responses = await asyncio.gather(*[
            handle.get_response() for handle in response_handles
        ])
        
        # Verify all succeeded
        for i, response in enumerate(responses):
            assert response.status == RequestStatus.COMPLETED
            assert response.data["echo"] == f"message-{i}"
    
    @pytest.mark.asyncio
    async def test_watch_updates(self, runtime_and_client):
        runtime, client = runtime_and_client
        actor_id = ActorId(type_name="test", instance_id="stream-test")
        
        # Send request
        response_handle = await client.send_request(
            actor_id=actor_id,
            method="echo",
            params={"text": "streaming test"}
        )
        
        # Watch for updates (should get final response)
        updates = []
        async for update in response_handle.watch_updates():
            updates.append(update)
            break  # Just get the first (and only) update
        
        assert len(updates) == 1
        assert updates[0].status == RequestStatus.COMPLETED
        assert updates[0].data["echo"] == "streaming test"