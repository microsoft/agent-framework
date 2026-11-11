# Copyright (c) Microsoft. All rights reserved.

"""Offline storage boundaries for the custom session-storage sample."""

from __future__ import annotations

from copy import deepcopy
from types import ModuleType
from typing import Any

from agent_framework import AgentSession
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from agent_framework_foundry_hosting import FoundryRequestScope


def make_session(value: str) -> AgentSession:
    session = AgentSession(session_id="inner-maf-session")
    session.state["value"] = value
    return session


def http_error(status: int) -> CosmosHttpResponseError:
    if status == 404:
        return CosmosResourceNotFoundError(status_code=404, message="missing")
    return CosmosHttpResponseError(status_code=status, message=f"status {status}")


class FakeContainer:
    """Emulate Cosmos create-only and exact-ETag operations in one event loop."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self._version = 0
        self.omit_etag = False
        self.create_error: int | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _stamp(self, body: dict[str, Any]) -> dict[str, Any]:
        self._version += 1
        stored = {**deepcopy(body), "_etag": f'"{self._version}"'}
        self.items[body["scope_key"], body["id"]] = stored
        result = deepcopy(stored)
        if self.omit_etag:
            result["_etag"] = None
        return result

    async def read_item(self, *, item: str, partition_key: str) -> dict[str, Any]:
        stored = self.items.get((partition_key, item))
        if stored is None:
            raise http_error(404)
        return deepcopy(stored)

    async def create_item(self, *, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create", {}))
        if self.create_error is not None:
            raise http_error(self.create_error)
        if (body["scope_key"], body["id"]) in self.items:
            raise http_error(409)
        return self._stamp(body)

    async def replace_item(
        self, *, item: str, body: dict[str, Any], etag: str, match_condition: MatchConditions
    ) -> dict[str, Any]:
        self.calls.append(("replace", {"etag": etag, "match_condition": match_condition}))
        assert match_condition == MatchConditions.IfNotModified
        stored = self.items.get((body["scope_key"], item))
        if stored is None:
            raise http_error(404)
        if stored["_etag"] != etag:
            raise http_error(412)
        return self._stamp(body)

    async def delete_item(self, *, item: str, partition_key: str, etag: str, match_condition: MatchConditions) -> None:
        self.calls.append(("delete", {"etag": etag, "match_condition": match_condition}))
        assert match_condition == MatchConditions.IfNotModified
        stored = self.items.get((partition_key, item))
        if stored is None:
            raise http_error(404)
        if stored["_etag"] != etag:
            raise http_error(412)
        del self.items[partition_key, item]


def cosmos_store(sample: ModuleType, container: FakeContainer) -> Any:
    scope = FoundryRequestScope(session_id="sandbox", user_id="user", call_id="call", is_hosted=True)
    return sample.CosmosSessionStore(container=container, scope=scope)


def local_store(sample: ModuleType, snapshots: dict[Any, Any], scope_key: str = "scope") -> Any:
    return sample.LocalSessionStore(snapshots, scope_key=scope_key)
