# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from agent_framework import FileSessionStore, SessionStore
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse

ResponsesSessionIsolationKeyResolver: TypeAlias = Callable[
    [CreateResponse, ResponseContext],
    str | Awaitable[str | None] | None,
]
"""Resolve a stable authenticated identity used to partition Responses state."""

_MAX_ISOLATION_KEY_LENGTH = 128
_INVALID_PATH_CHARACTERS = frozenset('<>:"/\\|?*')


@dataclass(frozen=True, slots=True)
class ResolvedSessionIsolation:
    """Validated per-request storage isolation."""

    key: str | None
    directory_segment: str | None
    fingerprint: str | None


class IsolationKeyScopedFileSessionStore(FileSessionStore):
    """FileSessionStore that scopes each operation to the bound user directory."""

    def __init__(
        self,
        storage_path: str | Path,
        *,
        serialization_format: Literal["json", "msgpack"] = "json",
    ) -> None:
        """Initialize a scoped file store rooted at ``storage_path``."""
        super().__init__(storage_path, serialization_format=serialization_format)
        self._current_directory: ContextVar[str | None] = ContextVar(
            f"foundry_session_isolation_{id(self)}",
            default=None,
        )

    @contextmanager
    def use_isolation(self, isolation: ResolvedSessionIsolation) -> Generator[None]:
        """Bind one resolved request identity for subsequent store operations."""
        token = self._current_directory.set(isolation.directory_segment)
        try:
            yield
        finally:
            self._current_directory.reset(token)

    def _session_file_path(self, session_id: str) -> Path:
        """Resolve the session file beneath the currently bound user directory."""
        SessionStore.validate_session_id(session_id)
        storage_root = self.storage_path.resolve()
        directory_segment = self._current_directory.get()
        if directory_segment is not None:
            storage_root = (storage_root / directory_segment).resolve()
            if not storage_root.is_relative_to(self.storage_path.resolve()):
                raise ValueError(f"Session isolation path escaped storage directory: {directory_segment!r}")
            storage_root.mkdir(parents=True, exist_ok=True)
        return storage_root / f"{session_id}{self._file_extension}"


def platform_session_isolation_key_resolver(
    request: CreateResponse,
    context: ResponseContext,
) -> str | None:
    """Resolve the trusted Foundry platform user partition key."""
    del request
    return context.platform_context.user_id_key


def _validate_isolation_key(key: str) -> None:
    """Validate a portable single-directory identity value."""
    if len(key) > _MAX_ISOLATION_KEY_LENGTH:
        raise ValueError(f"Session isolation key must be at most {_MAX_ISOLATION_KEY_LENGTH} characters.")
    if key in {".", ".."} or key.endswith((" ", ".")):
        raise ValueError("Session isolation key is not a safe directory name.")
    if any(ord(character) < 32 or character in _INVALID_PATH_CHARACTERS for character in key):
        raise ValueError("Session isolation key contains characters that are unsafe in a directory name.")


async def resolve_session_isolation(
    resolver: ResponsesSessionIsolationKeyResolver,
    request: CreateResponse,
    context: ResponseContext,
    *,
    is_hosted: bool,
) -> ResolvedSessionIsolation:
    """Resolve, normalize, validate, and fingerprint one request identity."""
    value = resolver(request, context)
    if inspect.isawaitable(value):
        value = await value
    if value is None or not value.strip():
        if is_hosted:
            raise RuntimeError(
                "The hosted request did not resolve a session isolation key; refusing to use unscoped session storage."
            )
        return ResolvedSessionIsolation(key=None, directory_segment=None, fingerprint=None)

    key = value.strip()
    _validate_isolation_key(key)
    return ResolvedSessionIsolation(
        key=key,
        directory_segment=f"user-{key}",
        fingerprint=hashlib.sha256(key.encode("utf-8")).hexdigest(),
    )
