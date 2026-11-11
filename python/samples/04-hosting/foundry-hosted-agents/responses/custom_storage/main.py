# Copyright (c) Microsoft. All rights reserved.

# /// script
# requires-python = ">=3.11"
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

"""Trusted user-and-sandbox session snapshots with optimistic concurrency.

Hosted runs use an existing Cosmos DB container partitioned by /scope_key and
authenticate with managed identity. Both stores also expose the structural
``get_with_revision``/``compare_and_set`` capability that hosted agent approvals
require. Cosmos uses server-side create-only writes and exact ETag matches; use
a single-write-region account for approval authority. Local runs use snapshots
owned by one provider: their conditional writes are atomic only within one
process and event loop, and they are not a multi-user authentication boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from contextlib import AsyncExitStack
from copy import deepcopy
from types import TracebackType
from typing import Any

from agent_framework import Agent, AgentSession, SessionStore
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryRequestScope, ResponsesHostServer, ResponsesRequest, StoreProvider
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext, get_request_context
from azure.core import MatchConditions
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv

_CONFLICT = "Another request advanced this agent session; reload before writing."
_SINGLE_ETAG = re.compile(r'"[\x21\x23-\x7e\x80-\xff]*"')
_MAX_COSMOS_ITEM_BYTES = 2_000_000
_SESSION_TOO_LARGE = (
    "Agent session exceeds the 2,000,000-byte Cosmos snapshot budget; reduce session state or start a new conversation."
)


def _validate_revision(expected_revision: str | None) -> None:
    if expected_revision is not None and (not isinstance(expected_revision, str) or not expected_revision):
        raise ValueError("expected_revision must be None or a non-empty string.")


def _validate_cosmos_etag(etag: str) -> None:
    # If-Match treats a wildcard or list as something other than one exact revision.
    if _SINGLE_ETAG.fullmatch(etag) is None:
        raise RuntimeError("A Cosmos revision must be a single strong ETag.")


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
        session, etag = await self.get_with_revision(session_id)
        self._etags[session_id] = etag
        return session

    async def get_with_revision(self, session_id: str) -> tuple[AgentSession | None, str | None]:
        """Return an independent snapshot and its ETag without caching that ETag."""
        item_id = self._item_id(session_id)
        try:
            item = await self._container.read_item(item=item_id, partition_key=self._scope_key)
        except CosmosResourceNotFoundError:
            return None, None
        if item.get("scope_key") != self._scope_key or item.get("id") != item_id:
            raise RuntimeError("A stored agent session does not belong to this trusted user and sandbox.")
        etag = item.get("_etag")
        if not isinstance(etag, str) or not etag:
            raise RuntimeError("Stored Cosmos session is missing its ETag.")
        _validate_cosmos_etag(etag)
        return AgentSession.from_dict(item["session"]), etag

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Create a new key, or replace only the version this request loaded."""
        self._etags[session_id] = await self.compare_and_set(
            session_id, session, expected_revision=self._etags.get(session_id)
        )

    async def compare_and_set(self, session_id: str, session: AgentSession, *, expected_revision: str | None) -> str:
        """Create only when ``expected_revision`` is None; otherwise replace only that ETag.

        Conflicts raise ``RuntimeError`` and are never retried as an upsert. A failed or
        cancelled write may still have committed, so callers must reload before deciding.
        """
        _validate_revision(expected_revision)
        if expected_revision is not None:
            _validate_cosmos_etag(expected_revision)
        item: dict[str, Any] = {
            "id": self._item_id(session_id),
            "scope_key": self._scope_key,
            "session": session.to_dict(),
        }
        if len(json.dumps(item, separators=(",", ":")).encode("utf-8")) > _MAX_COSMOS_ITEM_BYTES:
            raise ValueError(_SESSION_TOO_LARGE)
        try:
            if expected_revision is None:
                result = await self._container.create_item(body=item)
            else:
                result = await self._container.replace_item(
                    item=item["id"],
                    body=item,
                    etag=expected_revision,
                    match_condition=MatchConditions.IfNotModified,
                )
        except CosmosHttpResponseError as exc:
            if exc.status_code == 413:
                raise ValueError(_SESSION_TOO_LARGE) from exc
            if exc.status_code not in (404, 409, 412):
                raise
            raise RuntimeError(_CONFLICT) from exc
        new_etag = result.get("_etag")
        if not isinstance(new_etag, str) or not new_etag:
            raise RuntimeError("Cosmos did not return an ETag after saving.")
        _validate_cosmos_etag(new_etag)
        return new_etag

    async def delete(self, session_id: str) -> None:
        """Delete the loaded version; an absent key is an idempotent no-op."""
        item_id = self._item_id(session_id)
        if session_id not in self._etags:
            await self.get(session_id)
        etag = self._etags[session_id]
        if etag is not None:
            _validate_cosmos_etag(etag)
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
    """Request-local concurrency tokens over scoped, process-local snapshots.

    Conditional writes coordinate only stores sharing the same snapshots in one
    event loop. Separate providers, workers, and processes do not share them.
    """

    def __init__(self, snapshots: dict[tuple[str, str], tuple[str, dict[str, Any]]], *, scope_key: str) -> None:
        super().__init__()
        self._snapshots = snapshots
        self._scope_key = scope_key
        self._etags: dict[str, str | None] = {}

    def _key(self, session_id: str) -> tuple[str, str]:
        self.validate_session_id(session_id)
        return self._scope_key, session_id

    async def get(self, session_id: str) -> AgentSession | None:
        session, revision = await self.get_with_revision(session_id)
        self._etags[session_id] = revision
        return session

    async def get_with_revision(self, session_id: str) -> tuple[AgentSession | None, str | None]:
        """Return an independent snapshot and its revision without caching that revision."""
        item = self._snapshots.get(self._key(session_id))
        if item is None:
            return None, None
        return AgentSession.from_dict(deepcopy(item[1])), item[0]

    async def set(self, session_id: str, session: AgentSession) -> None:
        self._etags[session_id] = await self.compare_and_set(
            session_id, session, expected_revision=self._etags.get(session_id)
        )

    async def compare_and_set(self, session_id: str, session: AgentSession, *, expected_revision: str | None) -> str:
        """Create only when ``expected_revision`` is None; otherwise replace only that revision."""
        _validate_revision(expected_revision)
        key = self._key(session_id)
        snapshot = deepcopy(session.to_dict())
        # No await between the check and the write keeps this atomic within one event loop.
        item = self._snapshots.get(key)
        if (item[0] if item else None) != expected_revision:
            raise RuntimeError(_CONFLICT)
        revision = uuid.uuid4().hex
        self._snapshots[key] = revision, snapshot
        return revision

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
    """Share one backend across request-specific ETag and working-copy views."""

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


def create_agent(*, request: ResponsesRequest) -> Agent:
    """Create and clean up the request's own Foundry transports and credential."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
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
        agent=create_agent, history_source="host_managed", agent_session_store_provider=provider
    )
    server.shutdown_handler(provider.close)
    try:
        await server.run_async()
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
