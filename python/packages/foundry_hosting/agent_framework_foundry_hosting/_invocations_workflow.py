# Copyright (c) Microsoft. All rights reserved.

"""Host checkpoint-owned native workflows through the Invocations protocol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import CheckpointStorage
from starlette.requests import Request

from ._invocations_shared import _InvocationsHostServer  # pyright: ignore[reportPrivateUsage]
from ._shared import WorkflowSource, WorkflowTurn
from ._state_store import ContextScopedStoreProvider


class InvocationsWorkflowHostServer(_InvocationsHostServer):
    """Host a native, checkpoint-owned workflow with application-defined Invocations turns."""

    def __init__(
        self,
        workflow: WorkflowSource[Request],
        *,
        parse_input: Callable[[Request], WorkflowTurn[Any] | Awaitable[WorkflowTurn[Any]]],
        openapi_spec: dict[str, Any] | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        sse_keep_alive_interval_seconds: int | None = None,
        **agent_server_kwargs: Any,
    ) -> None:
        """Create a native workflow host with explicit parsing and checkpoint ownership.

        Args:
            workflow: Sync or async request-aware factory, called for each request. Build fresh workflows,
                executors, agents, clients, providers, and mutable tools inside the factory. Keep workflow
                and executor IDs stable for checkpoint restoration. The host enters and closes context-managed
                agents; applications own other resource cleanup. Known shared execution resources are rejected.

        Keyword Args:
            parse_input: Sync or async parser returning typed `WorkflowTurn` input or a complete pending
                reply batch. The application validates the request and explicitly supplies workflow kwargs.
            openapi_spec: Application OpenAPI specification forwarded to AgentServer.
            checkpoint_store_provider: Scoped checkpoint storage. Defaults to `CheckpointStoreProvider`.
                Native workflow history and pending replies are checkpoint-owned, not agent-session-owned.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval. If omitted, use a positive
                `SSE_KEEPALIVE_INTERVAL`, otherwise disable heartbeats. Not a request/model timeout.
            **agent_server_kwargs: Additional AgentServer SDK constructor arguments, such as
                `asyncapi_spec_json` and `asyncapi_spec_yaml`. Responses-only and agent-only settings are
                rejected. Output uses JSON or framed SSE workflow events.

        Raises:
            TypeError: If the workflow is not a request-aware factory, the parser or heartbeat type is invalid,
                or a Responses-only or agent-only setting is supplied.
            ValueError: If the heartbeat interval is nonpositive.
        """
        forbidden = {
            "agent",
            "agent_session_store_provider",
            "prepare_options",
            "unsupported_options",
        }.intersection(agent_server_kwargs)
        if forbidden:
            raise TypeError(f"Unsupported native workflow host settings: {', '.join(sorted(forbidden))}.")
        if not callable(parse_input):
            raise TypeError("parse_input must be a callable.")
        super().__init__(
            workflow=workflow,
            parse_input=parse_input,
            openapi_spec=openapi_spec,
            checkpoint_store_provider=checkpoint_store_provider,
            sse_keep_alive_interval_seconds=sse_keep_alive_interval_seconds,
            **agent_server_kwargs,
        )
