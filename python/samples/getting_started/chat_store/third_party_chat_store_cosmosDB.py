# Copyright (c) Microsoft. All rights reserved.

"""Cosmos DB Chat Message Store Example

Demonstrates how to store and retrieve chat history using Azure Cosmos DB
as an external message store for the Microsoft Agent Framework.

Scenarios:
  1) Persist chat messages in Cosmos DB with thread-based partitioning.
  2) Retrieve messages in chronological order for conversation continuity.
  3) Serialize and deserialize thread state for persistence across sessions.
  4) Properly close async Cosmos DB and chat client sessions.

Requirements:
  - Azure Cosmos DB (Core SQL API) with an existing database and container.
  - Container partition key must be /thread_id.
  - Environment variables:
      COSMOS_DB_ENDPOINT, COSMOS_DB_KEY,
      AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
      AZURE_OPENAI_API_VERSION, AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
  - Dependencies:
      pip install azure-cosmos pydantic "agent-framework"

Run:
  python third_party_chat_store_cosmosDB.py
"""

import os
from time import time
from uuid import uuid4
from typing import Sequence, Any
import enum, datetime, uuid

from pydantic import BaseModel
from azure.cosmos.aio import CosmosClient

from agent_framework import ChatMessage, ChatAgent
from agent_framework.azure import AzureOpenAIChatClient


class CosmosDBStoreState(BaseModel):
    """Serializable state for CosmosDB chat message store."""
    thread_id: str
    cosmos_endpoint: str | None = None
    database_name: str = "agent_framework"
    container_name: str = "chat_messages"


class CosmosDBChatMessageStore:
    """
    Lightweight Cosmos DB-backed chat history store for Microsoft Agent Framework.

    This implementation:
        - Uses key-based authentication.
        - Stores one conversation thread per partition (partition key = /thread_id).
        - Appends messages and retrieves them chronologically.
        - Supports serialization/deserialization for persistent AgentThread state.
        - Assumes database and container already exist.
    """

    def __init__(
        self,
        cosmos_endpoint: str,
        cosmos_key: str,
        *,
        thread_id: str | None = None,
        database_name: str = "agent_framework",
        container_name: str = "chat_messages",
    ) -> None:
        if not cosmos_endpoint:
            raise ValueError("cosmos_endpoint is required")
        if not cosmos_key:
            raise ValueError("cosmos_key is required")

        self.cosmos_endpoint = cosmos_endpoint
        self.cosmos_key = cosmos_key
        self.thread_id = thread_id or f"thread_{uuid4()}"
        self.database_name = database_name
        self.container_name = container_name

        self._client: CosmosClient | None = None
        self._container = None
        self._ready = False

    async def _ensure(self) -> None:
        """Initialize the Cosmos DB client and container reference if not already set."""
        if self._ready:
            return
        self._client = CosmosClient(self.cosmos_endpoint, self.cosmos_key)
        db = self._client.get_database_client(self.database_name)
        self._container = db.get_container_client(self.container_name)
        self._ready = True

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Persist new chat messages for the current thread."""
        if not messages:
            return
        await self._ensure()
        for msg in messages:
            doc = {
                "id": f"{self.thread_id}_{uuid4()}",
                "thread_id": self.thread_id,
                "ts": time(),
                "message": self._to_dict(msg),
            }
            await self._container.upsert_item(doc)

    async def list_messages(self) -> list[ChatMessage]:
        """Retrieve all chat messages for the thread in chronological order."""
        await self._ensure()
        query = """
            SELECT c.message FROM c
            WHERE c.thread_id = @thread_id
            ORDER BY c.ts ASC
        """
        params = [{"name": "@thread_id", "value": self.thread_id}]
        messages: list[ChatMessage] = []
        async for row in self._container.query_items(
            query=query, parameters=params, partition_key=self.thread_id
        ):
            messages.append(self._from_dict(row["message"]))
        return messages

    async def clear(self) -> None:
        """Delete all chat messages for the current thread."""
        await self._ensure()
        query = "SELECT c.id FROM c WHERE c.thread_id = @thread_id"
        params = [{"name": "@thread_id", "value": self.thread_id}]
        async for row in self._container.query_items(
            query=query, parameters=params, partition_key=self.thread_id
        ):
            await self._container.delete_item(row["id"], partition_key=self.thread_id)

    async def aclose(self) -> None:
        """Close the Cosmos DB client connection."""
        if self._client:
            await self._client.close()
        self._ready = False

    async def serialize_state(self, **kwargs: Any) -> dict:
        """Serialize the store configuration for persistent thread state."""
        return CosmosDBStoreState(
            thread_id=self.thread_id,
            cosmos_endpoint=self.cosmos_endpoint,
            database_name=self.database_name,
            container_name=self.container_name,
        ).model_dump(**kwargs)

    async def deserialize_state(self, state: dict | None, **_: Any) -> None:
        """Restore store configuration from serialized thread state."""
        if not state:
            return
        s = CosmosDBStoreState.model_validate(state)
        self.thread_id = s.thread_id
        if (s.cosmos_endpoint and s.cosmos_endpoint != self.cosmos_endpoint) or \
           s.database_name != self.database_name or \
           s.container_name != self.container_name:
            self.cosmos_endpoint = s.cosmos_endpoint or self.cosmos_endpoint
            self.database_name = s.database_name
            self.container_name = s.container_name
            self._ready = False

    def _to_dict(self, message: ChatMessage) -> dict:
        """Convert ChatMessage into a JSON-safe dictionary."""
        def make_safe(obj):
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, enum.Enum):
                return obj.value
            if isinstance(obj, (datetime.datetime, datetime.date)):
                return obj.isoformat()
            if isinstance(obj, uuid.UUID):
                return str(obj)
            if isinstance(obj, list):
                return [make_safe(x) for x in obj]
            if isinstance(obj, dict):
                return {k: make_safe(v) for k, v in obj.items()}
            if hasattr(obj, "dict"):
                return make_safe(obj.dict())
            if hasattr(obj, "model_dump"):
                return make_safe(obj.model_dump())
            if hasattr(obj, "__dict__"):
                return make_safe(vars(obj))
            return str(obj)

        if hasattr(message, "model_dump"):
            raw = message.model_dump()
        elif hasattr(message, "dict"):
            raw = message.dict()
        else:
            raw = vars(message)
        return make_safe(raw)

    def _from_dict(self, data: dict) -> ChatMessage:
        """Reconstruct a ChatMessage from a stored dictionary."""
        if hasattr(ChatMessage, "model_validate"):   
            return ChatMessage.model_validate(data)
        if hasattr(ChatMessage, "parse_obj"):        
            return ChatMessage.parse_obj(data)
        return ChatMessage(**data)


async def main() -> None:
    """Demonstration of CosmosDBChatMessageStore with ChatAgent."""
    store = CosmosDBChatMessageStore(
        cosmos_endpoint=os.getenv("COSMOS_DB_ENDPOINT"),
        cosmos_key=os.getenv("COSMOS_DB_KEY"),
        database_name="agent-chat-conversation",
        container_name="chat_messages",
    )

    chat_client = AzureOpenAIChatClient(
        model_id=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )

    agent = ChatAgent(
        chat_client=chat_client,
        name="Joker",
        instructions="You are good at telling jokes.",
        chat_message_store_factory=lambda: store,
    )

    try:
        thread = agent.get_new_thread()
        await agent.run("Tell me a pirate joke.", thread=thread)
        await agent.run("One more!", thread=thread)
    finally:
        await store.aclose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())