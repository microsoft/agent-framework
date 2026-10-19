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
        """Resolve hosted identity from platform configuration, not caller-controlled session IDs.

        Args:
            config: AgentServer's configuration for this host.
            context: Request context with platform user/call IDs and a potentially caller-supplied session ID.
            local_session_id: Fallback session ID for local, non-hosted requests only.

        Raises:
            RuntimeError: If a required platform identity is missing.
        """
        if config.is_hosted:
            if not config.session_id.strip():
                raise RuntimeError("Foundry hosted requests require a platform FOUNDRY_AGENT_SESSION_ID.")
            if context.session_id and context.session_id != config.session_id:
                raise RuntimeError("The request agent_session_id does not match the platform session ID.")
            if not context.user_id or not context.call_id:
                raise RuntimeError("Foundry hosted requests require a trusted user ID and call ID.")
            session_id = config.session_id
        else:
            session_id = context.session_id or local_session_id
            if not session_id:
                raise RuntimeError("A Foundry agent session ID is required to handle the request.")
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
