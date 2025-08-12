# Copyright (c) Microsoft. All rights reserved.

"""Tests for HttpActorClient."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from agent_runtime.http_actor_client import HttpActorClient, SimpleHttpActorResponseHandle
from agent_runtime.runtime_abstractions import ActorId, ActorMessageType, RequestStatus


class TestHttpActorClient:
    """Tests for HttpActorClient functionality."""

    def test_constructor_sets_base_url(self):
        """Test that constructor properly sets base URL."""
        client = HttpActorClient("http://localhost:8000")
        assert client._base_url == "http://localhost:8000"

    def test_constructor_strips_trailing_slash(self):
        """Test that constructor strips trailing slash from base URL."""
        client = HttpActorClient("http://localhost:8000/")
        assert client._base_url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_send_request_success(self):
        """Test successful request sending."""
        with patch('httpx.AsyncClient') as mock_client_class:
            # Setup mock response
            mock_response = Mock()
            mock_response.json.return_value = {
                "messages": [{"role": "assistant", "content": "Hello!"}],
                "status": "completed"
            }
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Test the client
            client = HttpActorClient("http://localhost:8000")
            actor_id = ActorId(type_name="test_agent", instance_id="thread_123")
            
            handle = await client.send_request(
                actor_id=actor_id,
                method="run",
                params={"messages": [{"role": "user", "content": "Hi"}]}
            )
            
            # Verify the request was made correctly
            mock_client.post.assert_called_once_with(
                "/agents/test_agent/run",
                json={
                    "agent_name": "test_agent",
                    "conversation_id": "thread_123",
                    "messages": [{"role": "user", "content": "Hi"}]
                }
            )
            
            # Verify the handle
            assert isinstance(handle, SimpleHttpActorResponseHandle)
            response = await handle.get_response()
            assert response.status == RequestStatus.COMPLETED
            assert response.sender_id == actor_id

    @pytest.mark.asyncio
    async def test_send_request_http_error(self):
        """Test request with HTTP error."""
        with patch('httpx.AsyncClient') as mock_client_class:
            # Setup mock HTTP error
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.reason_phrase = "Internal Server Error"
            
            error = httpx.HTTPStatusError("Server error", request=Mock(), response=mock_response)
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=error)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Test the client
            client = HttpActorClient("http://localhost:8000")
            actor_id = ActorId(type_name="test_agent", instance_id="thread_123")
            
            handle = await client.send_request(
                actor_id=actor_id,
                method="run",
                params={"messages": []}
            )
            
            # Verify error handling
            response = await handle.get_response()
            assert response.status == RequestStatus.FAILED
            assert "HTTP Error: 500 Internal Server Error" in str(response.data)

    @pytest.mark.asyncio
    async def test_send_request_generates_message_id(self):
        """Test that message ID is generated when not provided."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.json.return_value = {"messages": [], "status": "completed"}
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            
            client = HttpActorClient("http://localhost:8000")
            actor_id = ActorId(type_name="test_agent", instance_id="thread_123")
            
            handle = await client.send_request(actor_id=actor_id, method="run")
            response = await handle.get_response()
            
            # Should have generated a message ID
            assert response.message_id is not None
            assert len(response.message_id) > 0


class TestSimpleHttpActorResponseHandle:
    """Tests for SimpleHttpActorResponseHandle."""

    @pytest.mark.asyncio
    async def test_get_response_returns_stored_response(self):
        """Test that get_response returns the stored response."""
        from agent_runtime.runtime_abstractions import ActorResponseMessage
        
        original_response = ActorResponseMessage(
            message_id="test_id",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data={"test": "data"}
        )
        
        handle = SimpleHttpActorResponseHandle(original_response)
        response = await handle.get_response()
        
        assert response == original_response
        assert response.message_id == "test_id"
        assert response.status == RequestStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_watch_updates_simulates_streaming(self):
        """Test that watch_updates simulates streaming for successful responses."""
        from agent_runtime.runtime_abstractions import ActorResponseMessage
        
        response_data = {
            "messages": [{"role": "assistant", "content": "Hello world"}]
        }
        
        original_response = ActorResponseMessage(
            message_id="test_id",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data=response_data
        )
        
        handle = SimpleHttpActorResponseHandle(original_response)
        updates = []
        
        async for update in handle.watch_updates():
            updates.append(update)
        
        # Should have streaming updates plus final response
        assert len(updates) > 2  # At least some streaming updates + completion
        
        # Last update should be completion
        final_update = updates[-1]
        assert final_update.status == RequestStatus.COMPLETED
        
        # Earlier updates should be streaming (PENDING)
        streaming_updates = [u for u in updates[:-1] if u.status == RequestStatus.PENDING]
        assert len(streaming_updates) > 0

    @pytest.mark.asyncio
    async def test_watch_updates_handles_failed_response(self):
        """Test that watch_updates handles failed responses correctly."""
        from agent_runtime.runtime_abstractions import ActorResponseMessage
        
        failed_response = ActorResponseMessage(
            message_id="test_id",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.FAILED,
            data="Error occurred"
        )
        
        handle = SimpleHttpActorResponseHandle(failed_response)
        updates = []
        
        async for update in handle.watch_updates():
            updates.append(update)
        
        # Should just return the failed response
        assert len(updates) == 1
        assert updates[0].status == RequestStatus.FAILED
        assert updates[0].data == "Error occurred"