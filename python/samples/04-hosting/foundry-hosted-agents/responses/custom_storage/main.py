# Copyright (c) Microsoft. All rights reserved.

import os
from contextlib import suppress
from typing import Any

from agent_framework import Agent, AgentSession, SessionStore
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer, StoreProvider
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

"""Host an agent with a custom session storage provider.

The provider uses an in-memory store when the agent runs locally and Azure
Cosmos DB when the agent runs in Foundry. Create the database and container
before deploying the agent. The container must use /user_id as its partition key.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name.
    COSMOS_CONNECTION_STRING: Azure Cosmos DB connection string.
    COSMOS_DATABASE_NAME: Existing database name.
    COSMOS_CONTAINER_NAME: Existing container name partitioned by /user_id.
"""

load_dotenv()


class CosmosSessionStore(SessionStore):
    """Persist Agent Framework session snapshots in Azure Cosmos DB."""

    def __init__(self, *, container: ContainerProxy, user_id: str) -> None:
        super().__init__()
        self._container = container
        self._user_id = user_id

    async def get(self, session_id: str) -> AgentSession | None:
        """Load a session snapshot, or return None when it does not exist."""
        self.validate_session_id(session_id)
        try:
            item = await self._container.read_item(item=session_id, partition_key=self._user_id)
        except CosmosResourceNotFoundError:
            return None
        return AgentSession.from_dict(item["session"])

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Create or replace a session snapshot."""
        self.validate_session_id(session_id)
        item: dict[str, Any] = {"id": session_id, "user_id": self._user_id, "session": session.to_dict()}
        await self._container.upsert_item(item)

    async def delete(self, session_id: str) -> None:
        """Delete a session snapshot when it exists."""
        self.validate_session_id(session_id)
        with suppress(CosmosResourceNotFoundError):
            await self._container.delete_item(item=session_id, partition_key=self._user_id)


class CustomSessionStoreProvider(StoreProvider[SessionStore]):
    """Provide in-memory storage locally and Cosmos-backed storage when hosted."""

    def __init__(self) -> None:
        self._local_store: SessionStore | None = None
        self._cosmos_client: CosmosClient | None = None
        self._cosmos_container: ContainerProxy | None = None

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        """Return the session store for the current hosting environment."""
        if not config.is_hosted:
            if self._local_store is None:
                self._local_store = SessionStore()
            return self._local_store

        if not platform_context.user_id:
            raise RuntimeError("Foundry-hosted session storage requires a user ID in the platform context.")

        if self._cosmos_container is None:
            self._cosmos_client = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION_STRING"])
            database = self._cosmos_client.get_database_client(os.environ["COSMOS_DATABASE_NAME"])
            self._cosmos_container = database.get_container_client(os.environ["COSMOS_CONTAINER_NAME"])

        return CosmosSessionStore(container=self._cosmos_container, user_id=platform_context.user_id)


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
