# Copyright (c) Microsoft. All rights reserved.

"""HTTP Actor Client implementation for communicating with remote actor runtime over HTTP."""

import asyncio
import json
import uuid
from typing import AsyncIterator, Dict, Any, Optional

import httpx

from .runtime_abstractions import (
    ActorId,
    ActorResponseHandle,
    ActorResponseMessage,
    ActorMessageType,
    IActorClient,
    RequestStatus,
)


class HttpActorResponseHandle(ActorResponseHandle):
    """HTTP-based actor response handle."""
    
    def __init__(self, client: httpx.AsyncClient, actor_id: ActorId, message_id: str):
        self._client = client
        self._actor_id = actor_id
        self._message_id = message_id
        self._response: Optional[ActorResponseMessage] = None

    async def get_response(self) -> ActorResponseMessage:
        """Get the final response from the HTTP actor."""
        if self._response is not None:
            return self._response
        
        # Poll for the response (simplified implementation)
        # In a real implementation, this would use WebSockets or Server-Sent Events
        max_retries = 30  # 30 seconds timeout
        for _ in range(max_retries):
            try:
                response = await self._client.get(
                    f"/actors/{self._actor_id.type_name}/requests/{self._message_id}"
                )
                if response.status_code == 200:
                    data = response.json()
                    status = RequestStatus(data["status"])
                    
                    if status in (RequestStatus.COMPLETED, RequestStatus.FAILED):
                        self._response = ActorResponseMessage(
                            message_id=self._message_id,
                            message_type=ActorMessageType.RESPONSE,
                            sender_id=self._actor_id,
                            status=status,
                            data=data.get("data")
                        )
                        return self._response
                        
                await asyncio.sleep(1)  # Wait 1 second before retry
            except httpx.HTTPStatusError:
                await asyncio.sleep(1)
                
        # Timeout
        self._response = ActorResponseMessage(
            message_id=self._message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=self._actor_id,
            status=RequestStatus.FAILED,
            data="Request timeout"
        )
        return self._response

    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """Watch for streaming updates (simplified implementation)."""
        # For now, just yield the final response
        # In a real implementation, this would connect to a streaming endpoint
        response = await self.get_response()
        
        # If it's a successful response, we can simulate streaming
        if response.status == RequestStatus.COMPLETED and response.data:
            # Simulate streaming by breaking the response into chunks
            if isinstance(response.data, dict) and "messages" in response.data:
                for msg_data in response.data["messages"]:
                    content = msg_data.get("text", "")
                    if content:
                        # Simulate streaming chunks
                        words = content.split()
                        current_chunk = ""
                        for word in words:
                            current_chunk += word + " "
                            yield ActorResponseMessage(
                                message_id=self._message_id,
                                message_type=ActorMessageType.RESPONSE,
                                sender_id=self._actor_id,
                                status=RequestStatus.PENDING,
                                data={"progress": {"contents": [{"text": current_chunk.strip()}], "role": "assistant"}}
                            )
        
        # Finally yield completion
        yield ActorResponseMessage(
            message_id=self._message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=self._actor_id,
            status=RequestStatus.COMPLETED,
            data=response.data
        )


class HttpActorClient(IActorClient):
    """HTTP-based actor client for communicating with remote actor runtime."""
    
    def __init__(self, base_url: str):
        """Initialize the HTTP actor client.
        
        Args:
            base_url: Base URL of the actor runtime HTTP API
        """
        self._base_url = base_url.rstrip('/')
        
    async def send_request(
        self, 
        actor_id: ActorId, 
        method: str, 
        params: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None
    ) -> ActorResponseHandle:
        """Send a request to an actor via HTTP.
        
        Args:
            actor_id: The target actor ID
            method: The method to call on the actor
            params: Parameters for the method call
            message_id: Optional message ID (will be generated if not provided)
            
        Returns:
            A response handle for the request
        """
        if message_id is None:
            message_id = str(uuid.uuid4())
            
        # Build the request payload matching the HTTP API format
        payload = {
            "agent_name": actor_id.type_name,
            "conversation_id": actor_id.instance_id,
            "messages": params.get("messages", []) if params else []
        }
        
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            try:
                # Send request to the HTTP API
                response = await client.post(
                    f"/agents/{actor_id.type_name}/run",
                    json=payload
                )
                response.raise_for_status()
                
                # For now, we'll create a handle that immediately has the response
                # In a full implementation, this would return a handle for async processing
                response_data = response.json()
                
                actor_response = ActorResponseMessage(
                    message_id=message_id,
                    message_type=ActorMessageType.RESPONSE,
                    sender_id=actor_id,
                    status=RequestStatus.COMPLETED,
                    data=response_data
                )
                
                # Create a simple handle that returns this response
                return SimpleHttpActorResponseHandle(actor_response)
                
            except httpx.HTTPStatusError as e:
                # Return failed response
                actor_response = ActorResponseMessage(
                    message_id=message_id,
                    message_type=ActorMessageType.RESPONSE,
                    sender_id=actor_id,
                    status=RequestStatus.FAILED,
                    data=f"HTTP Error: {e.response.status_code} {e.response.reason_phrase}"
                )
                return SimpleHttpActorResponseHandle(actor_response)


class SimpleHttpActorResponseHandle(ActorResponseHandle):
    """Simple response handle that immediately has the response."""
    
    def __init__(self, response: ActorResponseMessage):
        self._response = response

    async def get_response(self) -> ActorResponseMessage:
        """Get the response immediately."""
        return self._response

    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """For streaming, simulate updates from the response."""
        if self._response.status == RequestStatus.COMPLETED and self._response.data:
            # Try to extract message content for streaming simulation
            try:
                data = self._response.data
                if isinstance(data, dict) and "messages" in data and data["messages"]:
                    first_message = data["messages"][0]
                    content = first_message.get("text", "")
                    
                    if content:
                        # Simulate streaming by breaking content into words
                        words = content.split()
                        current_text = ""
                        
                        for word in words:
                            current_text += word + " "
                            yield ActorResponseMessage(
                                message_id=self._response.message_id,
                                message_type=ActorMessageType.RESPONSE,
                                sender_id=self._response.sender_id,
                                status=RequestStatus.PENDING,
                                data={
                                    "progress": {
                                        "contents": [{"text": current_text.strip()}],
                                        "role": "assistant"
                                    }
                                }
                            )
                            
                            # Small delay to simulate streaming
                            await asyncio.sleep(0.05)
                        
                        # Yield completion
                        yield ActorResponseMessage(
                            message_id=self._response.message_id,
                            message_type=ActorMessageType.RESPONSE,
                            sender_id=self._response.sender_id,
                            status=RequestStatus.COMPLETED,
                            data=self._response.data
                        )
                        return
                        
            except Exception:
                # If we can't simulate streaming, just return completion
                pass
        
        # Default: just yield the final response
        yield self._response