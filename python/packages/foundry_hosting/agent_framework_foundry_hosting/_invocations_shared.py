# Copyright (c) Microsoft. All rights reserved.

"""Protocol-neutral Invocations helpers used by the agent and workflow hosts."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Mapping
from typing import Any

from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import FoundryStorageConflictError, FoundryStoragePreconditionError
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from ._scope import FoundryRequestScope


def sse_frame(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def invocation_failure(exc: Exception) -> tuple[str, int, str]:
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, (FoundryStorageConflictError, FoundryStoragePreconditionError)):
            return "Another request advanced this agent session; reload before retrying.", 409, "session_conflict"
        cause = cause.__cause__
    return "Agent invocation failed.", 500, "invocation_failed"


class InvocationStreamingResponse(StreamingResponse):
    def __init__(self, content: AsyncGenerator[str]) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
        self._content = content

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # The SDK may wrap the iterator in a keep-alive pump; join it before closing its source.
            try:
                close = getattr(self.body_iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                if self.body_iterator is not self._content:
                    await self._content.aclose()


def partition_key(
    config: AgentConfig,
    context: FoundryAgentRequestContext,
    scope: FoundryRequestScope | None = None,
) -> str | tuple[str, str]:
    """Get the isolation key for the current request.

    Hosted keys are a ``(session_id, user_id)`` tuple, so one user cannot reach another user's
    state. Locally, the key is the session ID.

    Raises:
        RuntimeError: If the context does not contain the expected IDs.
    """
    if config.is_hosted:
        if not context.user_id:
            raise RuntimeError(
                "The hosted environment is missing user_id in the request context. "
                "Please ensure that the request is coming from a valid Foundry platform service."
            )
        hosted = scope or FoundryRequestScope.from_context(config, context)
        return hosted.session_id, context.user_id

    if not context.session_id:
        raise RuntimeError(
            "The request context is missing session_id. Please ensure that the request is a valid request."
        )
    return context.session_id


def hosted_scope(config: AgentConfig, request: Request, context: FoundryAgentRequestContext) -> FoundryRequestScope:
    """Accept an unconfigured session only when the routed Invocations query identifies it."""
    if not context.user_id:
        raise RuntimeError("The hosted environment is missing user_id in the request context.")

    routed_session_ids = request.query_params.getlist("agent_session_id")
    if len(routed_session_ids) > 1:
        raise RuntimeError("Hosted Invocations requires exactly one agent_session_id query parameter.")
    routed_session_id = routed_session_ids[0] if routed_session_ids else None
    if config.session_id:
        if routed_session_id is not None and routed_session_id != config.session_id:
            raise RuntimeError("The request agent_session_id does not match the platform session ID.")
        return FoundryRequestScope.from_context(config, context)

    if not routed_session_id or routed_session_id != context.session_id:
        raise RuntimeError(
            "Hosted Invocations without FOUNDRY_AGENT_SESSION_ID require an explicit routed "
            "agent_session_id query parameter matching the request context."
        )
    if not context.call_id:
        raise RuntimeError("Foundry hosted requests require a trusted user ID and call ID.")
    return FoundryRequestScope(
        session_id=routed_session_id,
        user_id=context.user_id,
        call_id=context.call_id,
        is_hosted=True,
    )
