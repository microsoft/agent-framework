# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from agent_framework import ExperimentalFeature, FileSessionStore
from agent_framework._feature_stage import experimental
from azure.ai.agentserver.core import FoundryAgentRequestContext, get_request_context

_PROTOCOL_V2_REQUIRED_MESSAGE = (
    "The hosted environment is running on protocol 1.0.0, but the agent requires protocol 2.0.0. "
    "Please upgrade your agent protocol to 2.0.0 in `agent.manifest.yaml` or `agent.yaml`, or "
    "downgrade the `agent-framework-foundry-hosting` package to `1.0.0a260625` or before to use 1.0.0."
)


def _get_foundry_request_context(  # pyright: ignore[reportUnusedFunction]
    *,
    is_hosted: bool,
) -> FoundryAgentRequestContext:
    """Return the current request context and validate hosted v2 identity."""
    context = get_request_context()
    if is_hosted and context.call_id is None:
        raise RuntimeError(_PROTOCOL_V2_REQUIRED_MESSAGE)
    if is_hosted and not context.user_id:
        raise RuntimeError(
            "The hosted environment is missing the platform user ID in the request context. "
            "Please ensure that the request is coming from a valid Foundry platform service."
        )
    return context


def _request_user_id_key() -> str | None:
    """Return the platform user partition key for the active request."""
    # FoundryAgentRequestContext.user_id is populated from the same
    # x-agent-user-id value exposed as ResponseContext.platform_context.user_id_key.
    return get_request_context().user_id


def _request_user_fingerprint() -> str | None:
    """Return a stable opaque fingerprint for the active request user."""
    user_id_key = _request_user_id_key()
    return hashlib.sha256(user_id_key.encode("utf-8")).hexdigest() if user_id_key else None


def _request_user_directory_segment() -> str | None:
    """Return the safe on-disk directory segment for the active request user."""
    fingerprint = _request_user_fingerprint()
    return f"user-{fingerprint}" if fingerprint else None


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class FoundrySessionStore(FileSessionStore):
    """File-backed session store isolated by the active Foundry request user.

    This implementation currently persists through :class:`FileSessionStore`.
    The Foundry-specific type leaves room to use a platform storage API later
    without changing :class:`ResponsesHostServer` configuration.
    """

    def __init__(
        self,
        storage_path: str | Path,
        *,
        serialization_format: Literal["json", "msgpack"] = "json",
    ) -> None:
        """Initialize a Foundry-scoped file store rooted at ``storage_path``."""
        super().__init__(storage_path, serialization_format=serialization_format)

    def get_session_directory(self) -> Path:
        """Return the active request user's session directory."""
        directory_segment = _request_user_directory_segment()
        return self.storage_path / directory_segment if directory_segment else self.storage_path
