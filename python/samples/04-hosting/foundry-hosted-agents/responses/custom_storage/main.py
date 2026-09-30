# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "azure-ai-agentserver-core>=2.1.0,<3",
#     "azure-core",
#     "azure-cosmos>=4.9.0",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Trusted user-and-sandbox session snapshots with optimistic concurrency.

Hosted runs use an existing Cosmos DB container partitioned by /scope_key and
authenticate with managed identity. Local runs use process-local snapshots with
the same create-only/conditional-write behavior; they are not a multi-user
authentication boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from contextlib import AsyncExitStack
from copy import deepcopy
from types import TracebackType
from typing import Any

from agent_framework import Agent, AgentSession, SessionStore
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryRequestScope, ResponsesHostServer, StoreProvider
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext, get_request_context
from azure.core import MatchConditions
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv

_CONFLICT = "Another request advanced this agent session; reload before writing."


class CosmosSessionStore(SessionStore):
    """Keep a request's ETags separate from every other request's working copy."""

    def __init__(self, *, container: ContainerProxy, scope: FoundryRequestScope) -> None:
        super().__init__()
        if (
            not scope.is_hosted
            or not scope.session_id.strip()
            or not scope.user_id
            or not scope.user_id.strip()
            or not scope.call_id
        ):
            raise RuntimeError("Cosmos session storage requires a trusted hosted user and call ID.")
        self._container = container
        self._scope_key = scope.storage_key
        self._etags: dict[str, str | None] = {}

    def _item_id(self, session_id: str) -> str:
        self.validate_session_id(session_id)
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    async def get(self, session_id: str) -> AgentSession | None:
        """Load by the host's response/conversation key, not the inner MAF ID."""
        item_id = self._item_id(session_id)
        try:
            item = await self._container.read_item(item=item_id, partition_key=self._scope_key)
        except CosmosResourceNotFoundError:
            self._etags[session_id] = None
            return None
        if item.get("scope_key") != self._scope_key or item.get("id") != item_id:
            raise RuntimeError("A stored agent session does not belong to this trusted user and sandbox.")
        etag = item.get("_etag")
        if not isinstance(etag, str) or not etag:
            raise RuntimeError("Stored Cosmos session is missing its ETag.")
        session = AgentSession.from_dict(item["session"])
        self._etags[session_id] = etag
        return session

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Create a new key, or replace only the version this request loaded."""
        item: dict[str, Any] = {
            "id": self._item_id(session_id),
            "scope_key": self._scope_key,
            "session": session.to_dict(),
        }
        try:
            etag = self._etags.get(session_id)
            if etag is None:
                result = await self._container.create_item(body=item)
            else:
                result = await self._container.replace_item(
                    item=item["id"],
                    body=item,
                    etag=etag,
                    match_condition=MatchConditions.IfNotModified,
                )
        except CosmosHttpResponseError as exc:
            if exc.status_code not in (409, 412):
                raise
            raise RuntimeError(_CONFLICT) from exc
        new_etag = result.get("_etag")
        if not isinstance(new_etag, str) or not new_etag:
            raise RuntimeError("Cosmos did not return an ETag after saving.")
        self._etags[session_id] = new_etag

    async def delete(self, session_id: str) -> None:
        """Delete the loaded version; an absent key is an idempotent no-op."""
        item_id = self._item_id(session_id)
        if session_id not in self._etags:
            await self.get(session_id)
        etag = self._etags[session_id]
        if etag is not None:
            try:
                await self._container.delete_item(
                    item=item_id,
                    partition_key=self._scope_key,
                    etag=etag,
                    match_condition=MatchConditions.IfNotModified,
                )
            except CosmosResourceNotFoundError:
                pass
            except CosmosHttpResponseError as exc:
                if exc.status_code not in (409, 412):
                    raise
                raise RuntimeError(_CONFLICT) from exc
        self._etags.pop(session_id, None)


class LocalSessionStore(SessionStore):
    """Request-local concurrency tokens over scoped, process-local snapshots."""

    def __init__(self, snapshots: dict[tuple[str, str], tuple[str, dict[str, Any]]], *, scope_key: str) -> None:
        super().__init__()
        self._snapshots = snapshots
        self._scope_key = scope_key
        self._etags: dict[str, str | None] = {}

    def _key(self, session_id: str) -> tuple[str, str]:
        self.validate_session_id(session_id)
        return self._scope_key, session_id

    async def get(self, session_id: str) -> AgentSession | None:
        item = self._snapshots.get(self._key(session_id))
        self._etags[session_id] = item[0] if item else None
        return AgentSession.from_dict(deepcopy(item[1])) if item else None

    async def set(self, session_id: str, session: AgentSession) -> None:
        key = self._key(session_id)
        item = self._snapshots.get(key)
        if (item[0] if item else None) != self._etags.get(session_id):
            raise RuntimeError(_CONFLICT)
        etag = uuid.uuid4().hex
        self._snapshots[key] = etag, deepcopy(session.to_dict())
        self._etags[session_id] = etag

    async def delete(self, session_id: str) -> None:
        key = self._key(session_id)
        if session_id not in self._etags:
            await self.get(session_id)
        item = self._snapshots.get(key)
        if item is not None and item[0] != self._etags[session_id]:
            raise RuntimeError(_CONFLICT)
        self._snapshots.pop(key, None)
        self._etags.pop(session_id, None)


class CustomSessionStoreProvider(StoreProvider[SessionStore]):
    """Reuse only the backend; each request gets an isolated ETag/working-copy view."""

    def __init__(self) -> None:
        self._local_snapshots: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._cosmos_client: CosmosClient | None = None
        self._cosmos_container: ContainerProxy | None = None
        self._cosmos_credential: ManagedIdentityCredential | None = None

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        scope = FoundryRequestScope.from_context(config, platform_context, local_session_id="local-development")
        if not config.is_hosted:
            return LocalSessionStore(self._local_snapshots, scope_key=scope.storage_key)

        if not scope.user_id or not scope.user_id.strip():
            raise RuntimeError("Foundry-hosted session storage requires a trusted user ID.")
        if self._cosmos_container is None:
            endpoint = os.environ["AZURE_COSMOS_ENDPOINT"]
            database_name = os.environ["COSMOS_DATABASE_NAME"]
            container_name = os.environ["COSMOS_CONTAINER_NAME"]
            self._cosmos_credential = ManagedIdentityCredential(
                client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID")
            )
            self._cosmos_client = CosmosClient(url=endpoint, credential=self._cosmos_credential)
            database = self._cosmos_client.get_database_client(database_name)
            self._cosmos_container = database.get_container_client(container_name)
        return CosmosSessionStore(container=self._cosmos_container, scope=scope)

    async def close(self) -> None:
        """Close only the backend client and credential created by this provider."""
        client, credential = self._cosmos_client, self._cosmos_credential
        self._cosmos_client = self._cosmos_container = self._cosmos_credential = None
        async with AsyncExitStack() as cleanup:
            if credential is not None:
                cleanup.push_async_callback(credential.close)
            if client is not None:
                cleanup.push_async_callback(client.close)


def create_agent() -> Agent:
    """Create and clean up the request's own Foundry transports and credential."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    credential = (
        ManagedIdentityCredential(client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID"))
        if AgentConfig.from_env().is_hosted
        else AzureCliCredential()
    )

    class RequestClient(FoundryChatClient):
        async def __aenter__(self) -> RequestClient:
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
        ) -> None:
            async with AsyncExitStack() as cleanup:
                cleanup.push_async_callback(credential.close)
                cleanup.push_async_callback(self.project_client.close)
                cleanup.push_async_callback(self.client.close)

    return Agent(
        client=RequestClient(
            project_endpoint=endpoint,
            model=model,
            credential=credential,
            default_headers=get_request_context().platform_headers(),
        ),
        instructions="You are a friendly assistant. Keep your answers brief.",
    )


async def main() -> None:
    load_dotenv()
    provider = CustomSessionStoreProvider()
    server = ResponsesHostServer(
        agent=create_agent, history_source="agent_server", agent_session_store_provider=provider
    )
    server.shutdown_handler(provider.close)
    try:
        await server.run_async()
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
