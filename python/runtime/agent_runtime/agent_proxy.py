# Copyright (c) Microsoft. All rights reserved.

"""Agent proxy implementation for Python runtime.

This module provides the agent proxy pattern that allows agents running in the
actor runtime to be used as regular AIAgent instances. The proxy transparently
delegates all agent method calls to the actor runtime using send_request.
"""

import json
import os
import re
import sys
import uuid
from typing import Any, AsyncIterable, List, Optional, Union

# Add framework to path (same approach as agent_actor.py)
sys.path.append(os.path.join(os.path.dirname(__file__), "../../packages/main"))

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, AgentThread, AIAgent, ChatMessage, ChatRole

from .runtime_abstractions import (
    ActorId,
    ActorResponseHandle,
    IActorClient,
    RequestStatus,
)


class AgentProxyThread(AgentThread):
    """Represents an agent thread for an AgentProxy."""

    def __init__(self, conversation_id: Optional[str] = None) -> None:
        """Initialize a new AgentProxyThread.

        Args:
            conversation_id: Optional conversation ID. If not provided, a new UUID is generated.
        """
        if conversation_id is None:
            conversation_id = self._create_id()

        self._validate_id(conversation_id)
        super().__init__(id=conversation_id)

    @staticmethod
    def _create_id() -> str:
        """Create a new thread ID."""
        return str(uuid.uuid4()).replace("-", "")

    @staticmethod
    def _validate_id(thread_id: str) -> None:
        """Validate that the thread ID matches the required pattern.

        Thread IDs must be alphanumeric and can contain hyphens, underscores, dots, and tildes.
        """
        pattern = r"^[a-zA-Z0-9_.\-~]+$"
        if not re.match(pattern, thread_id):
            raise ValueError(
                f"Thread ID '{thread_id}' is not valid. Thread IDs must contain only "
                "alphanumeric characters, hyphens, underscores, dots, and tildes."
            )


class AgentProxy(AIAgent):
    """Represents a proxy for an AI agent that communicates with the agent runtime via an actor client.

    This proxy allows agents running in the actor runtime to be used as regular AIAgent instances.
    It delegates all agent method calls to the actor runtime using send_request and handles
    serialization/deserialization of agent messages.
    """

    def __init__(self, name: str, client: IActorClient) -> None:
        """Initialize a new AgentProxy.

        Args:
            name: The name of the agent.
            client: The actor client used to communicate with the agent.

        Raises:
            ValueError: If name is empty or client is None.
        """
        if not name:
            raise ValueError("Agent name cannot be empty")
        if client is None:
            raise ValueError("Client cannot be None")

        self._name = name
        self._client = client

    @property
    def id(self) -> str:
        """Returns the ID of the agent."""
        return self._name

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        return self._name

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent."""
        return self._name

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        return None

    def get_new_thread(self) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        return AgentProxyThread()

    def get_thread(self, conversation_id: str) -> AgentThread:
        """Gets a thread by its conversation ID.

        Args:
            conversation_id: The thread identifier.

        Returns:
            The thread.
        """
        return AgentProxyThread(conversation_id)

    async def run(
        self,
        messages: Union[str, ChatMessage, List[str], List[ChatMessage], None] = None,
        *,
        thread: Optional[AgentThread] = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the agent.

        Args:
            messages: The messages to send to the agent.
            thread: Optional thread to use for the conversation.
            **kwargs: Additional options.

        Returns:
            The agent's response.

        Raises:
            ValueError: If messages is None.
            TypeError: If thread is not an AgentProxyThread.
            RuntimeError: If the agent run request fails.
        """
        if messages is None:
            raise ValueError("Messages cannot be None")

        # Normalize messages to list of ChatMessage
        normalized_messages = self._normalize_messages(messages)

        # Get thread ID
        thread_id = self._get_agent_thread_id(thread)

        # Send request and wait for completion
        handle = await self._run_core(normalized_messages, thread_id)
        response = await handle.get_response()

        if response.status == RequestStatus.COMPLETED:
            # Deserialize response data
            if response.data is None:
                raise RuntimeError("Response data is None")

            # Handle both dict and already deserialized AgentRunResponse
            if isinstance(response.data, dict):
                return AgentRunResponse(**response.data)
            if isinstance(response.data, AgentRunResponse):
                return response.data
            # Try to deserialize from JSON if it's a string
            if isinstance(response.data, str):
                data = json.loads(response.data)
                return AgentRunResponse(**data)
            raise RuntimeError(f"Unexpected response data type: {type(response.data)}")

        if response.status == RequestStatus.FAILED:
            raise RuntimeError(f"The agent run request failed: {response.data}")
        if response.status == RequestStatus.PENDING:
            raise RuntimeError("The agent run request is still pending")
        raise RuntimeError(f"The agent run request returned an unsupported status: {response.status}")

    def run_streaming(
        self,
        messages: Union[str, ChatMessage, List[str], List[ChatMessage], None] = None,
        *,
        thread: Optional[AgentThread] = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Run the agent as a stream.

        Args:
            messages: The messages to send to the agent.
            thread: Optional thread to use for the conversation.
            **kwargs: Additional options.

        Returns:
            An async iterable of response updates.

        Raises:
            ValueError: If messages is None.
            TypeError: If thread is not an AgentProxyThread.
            RuntimeError: If the agent run request fails.
        """
        if messages is None:
            raise ValueError("Messages cannot be None")

        # Normalize messages to list of ChatMessage
        normalized_messages = self._normalize_messages(messages)

        # Get thread ID
        thread_id = self._get_agent_thread_id(thread)

        return self._run_streaming_core(normalized_messages, thread_id)

    def _normalize_messages(
        self, messages: Union[str, ChatMessage, List[str], List[ChatMessage]]
    ) -> List[ChatMessage]:
        """Normalize messages to a list of ChatMessage objects."""
        if isinstance(messages, str):
            return [ChatMessage(role=ChatRole.USER, text=messages)]
        if isinstance(messages, ChatMessage):
            return [messages]
        if isinstance(messages, list):
            normalized = []
            for msg in messages:
                if isinstance(msg, str):
                    normalized.append(ChatMessage(role=ChatRole.USER, text=msg))
                elif isinstance(msg, ChatMessage):
                    normalized.append(msg)
                else:
                    raise ValueError(f"Unexpected message type: {type(msg)}")
            return normalized
        raise ValueError(f"Unexpected messages type: {type(messages)}")

    def _get_agent_thread_id(self, thread: Optional[AgentThread]) -> str:
        """Get the thread ID for the request."""
        if thread is None:
            return AgentProxyThread._create_id()

        if not isinstance(thread, AgentProxyThread):
            raise TypeError("The thread must be an instance of AgentProxyThread")

        if thread.id is None:
            raise ValueError("Thread ID cannot be None")

        return thread.id

    async def _run_core(
        self, messages: List[ChatMessage], thread_id: str
    ) -> ActorResponseHandle:
        """Core method to send a run request to the actor."""
        # Create the run request
        run_request = {
            "messages": [
                {
                    "role": msg.role.value,
                    "text": msg.text,
                    "message_id": msg.message_id
                }
                for msg in messages
            ]
        }

        # Get message ID from last message or generate new one
        message_id = None
        if messages:
            message_id = messages[-1].message_id
        if not message_id:
            message_id = str(uuid.uuid4())

        # Send request to actor
        actor_id = ActorId(type_name=self._name, instance_id=thread_id)
        return await self._client.send_request(
            actor_id=actor_id,
            method="run",  # This should match the agent actor's run method
            params=run_request,
            message_id=message_id
        )

    async def _run_streaming_core(
        self, messages: List[ChatMessage], thread_id: str
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Core method to send a streaming run request to the actor."""
        handle = await self._run_core(messages, thread_id)

        async for update in handle.watch_updates():
            if update.status == RequestStatus.FAILED:
                raise RuntimeError(f"The agent run request failed: {update.data}")

            if update.status == RequestStatus.COMPLETED:
                return

            # Deserialize the update data
            if update.data is not None:
                if isinstance(update.data, dict):
                    # Handle progress updates with sequence info
                    if "progress" in update.data:
                        progress_data = update.data["progress"]
                        if isinstance(progress_data, dict):
                            yield AgentRunResponseUpdate(**progress_data)
                        else:
                            # If progress data is already an AgentRunResponseUpdate
                            yield progress_data
                    else:
                        # Direct AgentRunResponseUpdate data
                        yield AgentRunResponseUpdate(**update.data)
                elif isinstance(update.data, AgentRunResponseUpdate):
                    yield update.data
                elif isinstance(update.data, str):
                    # Try to deserialize from JSON
                    try:
                        data = json.loads(update.data)
                        yield AgentRunResponseUpdate(**data)
                    except (json.JSONDecodeError, TypeError):
                        # Skip malformed updates
                        continue
