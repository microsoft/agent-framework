# Copyright (c) Microsoft. All rights reserved.

import os
from contextlib import suppress
from typing import Any

from agent_framework import Agent, AgentSession, SessionStore
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer, StoreProvider
from azure.ai.agentserver.core import AgentConfig
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

"""Host an agent with a custom session storage provider.

The provider uses an in-memory store when the agent runs locally and Azure
Cosmos DB when the agent runs in Foundry. Create the database and container
before deploying the agent. The container must use /id as its partition key.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name.
    COSMOS_CONNECTION_STRING: Azure Cosmos DB connection string.
    COSMOS_DATABASE_NAME: Existing database name.
    COSMOS_CONTAINER_NAME: Existing container name partitioned by /id.
"""

load_dotenv()


class CosmosSessionStore(SessionStore):
    """Persist Agent Framework session snapshots in Azure Cosmos DB."""

    def __init__(self, *, connection_string: str, database_name: str, container_name: str) -> None:
        super().__init__()
        self._client = CosmosClient.from_connection_string(connection_string)
        database = self._client.get_database_client(database_name)
        self._container: ContainerProxy = database.get_container_client(container_name)

    async def get(self, session_id: str) -> AgentSession | None:
        """Load a session snapshot, or return None when it does not exist."""
        self.validate_session_id(session_id)
        try:
            item = await self._container.read_item(item=session_id, partition_key=session_id)
        except CosmosResourceNotFoundError:
            return None
        return AgentSession.from_dict(item["session"])

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Create or replace a session snapshot."""
        self.validate_session_id(session_id)
        item: dict[str, Any] = {"id": session_id, "session": session.to_dict()}
        await self._container.upsert_item(item)

    async def delete(self, session_id: str) -> None:
        """Delete a session snapshot when it exists."""
        self.validate_session_id(session_id)
        with suppress(CosmosResourceNotFoundError):
            await self._container.delete_item(item=session_id, partition_key=session_id)


class CustomSessionStoreProvider(StoreProvider[SessionStore]):
    """Provide in-memory storage locally and Cosmos-backed storage when hosted."""

    def __init__(self) -> None:
        self._local_store: SessionStore | None = None
        self._hosted_store: SessionStore | None = None

    def get_store(self, *, config: AgentConfig) -> SessionStore:
        """Return the session store for the current hosting environment."""
        if not config.is_hosted:
            if self._local_store is None:
                self._local_store = SessionStore()
            return self._local_store

        if self._hosted_store is None:
            self._hosted_store = CosmosSessionStore(
                connection_string=os.environ["COSMOS_CONNECTION_STRING"],
                database_name=os.environ["COSMOS_DATABASE_NAME"],
                container_name=os.environ["COSMOS_CONTAINER_NAME"],
            )
        return self._hosted_store


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )
    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        default_options={"store": False},
    )

    server = ResponsesHostServer(
        agent,
        agent_session_store_provider=CustomSessionStoreProvider(),
    )
    server.run()


if __name__ == "__main__":
    main()
