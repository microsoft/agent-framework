# Copyright (c) Microsoft. All rights reserved.

"""Trusted request identity for Foundry-hosted state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext


@dataclass(frozen=True)
class FoundryRequestScope:
    """Separate the platform sandbox and user from caller-facing continuation IDs."""

    session_id: str
    user_id: str | None
    call_id: str | None
    is_hosted: bool

    @classmethod
    def from_context(
        cls,
        config: AgentConfig,
        context: FoundryAgentRequestContext,
        *,
        local_session_id: str | None = None,
    ) -> FoundryRequestScope:
        """Resolve identity from the platform context, never from a hosted caller's request.

        Args:
            config: AgentServer's configuration for this host.
            context: Trusted platform request context.
            local_session_id: Fallback session ID for local, non-hosted requests only.

        Raises:
            RuntimeError: If a required platform identity is missing.
        """
        session_id = context.session_id or (local_session_id if not config.is_hosted else None)
        if not session_id:
            raise RuntimeError("A Foundry agent session ID is required to handle the request.")
        if config.is_hosted and (not context.user_id or not context.call_id):
            raise RuntimeError("Foundry hosted requests require a trusted user ID and call ID.")
        return cls(
            session_id=session_id,
            user_id=context.user_id,
            call_id=context.call_id,
            is_hosted=config.is_hosted,
        )

    @property
    def storage_key(self) -> str:
        """Hash the framed platform identity so store names reveal neither ID."""
        identity = json.dumps([self.user_id, self.session_id], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()
