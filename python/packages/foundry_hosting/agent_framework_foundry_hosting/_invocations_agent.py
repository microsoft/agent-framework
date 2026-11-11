# Copyright (c) Microsoft. All rights reserved.

"""Host session-owned agents through the Invocations protocol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import SessionStore
from starlette.requests import Request

from ._invocations_shared import (
    InvocationOptionsHook,
    _InvocationsHostServer,  # pyright: ignore[reportPrivateUsage]
)
from ._shared import AgentSource, InvocationRun, UnsupportedOptions
from ._state_store import StoreProvider


class InvocationsHostServer(_InvocationsHostServer):
    """Host an agent with application-defined Invocations turns."""

    def __init__(
        self,
        agent: AgentSource[Request],
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        parse_input: Callable[[Request], InvocationRun | Awaitable[InvocationRun]] | None = None,
        prepare_options: InvocationOptionsHook | None = None,
        unsupported_options: UnsupportedOptions = "warn",
        sse_keep_alive_interval_seconds: int | None = None,
        **agent_server_kwargs: Any,
    ) -> None:
        """Create an agent host with session-backed application turns.

        Args:
            agent: Agent instance or sync/async factory called once per request. Factories must declare a
                required parameter named `request`, accepting the Starlette `Request` passed by keyword.
                Extra parameters must have defaults. The factory may ignore the request.
                Factories run after request parsing and option preparation. Use a factory when mutable state
                is not session-scoped. The host enters and closes factory-owned
                context-managed agents; injected instances remain application-owned. `WorkflowAgent` is
                rejected; use `InvocationsWorkflowHostServer` with a native workflow factory instead.

        Keyword Args:
            openapi_spec: Application OpenAPI specification forwarded to AgentServer.
            agent_session_store_provider: Conversation session storage. Defaults to Foundry storage when
                hosted and file-backed storage locally. Default stores expire 30 days after the last write.
            parse_input: Sync or async parser returning `InvocationRun`. Without a parser, accept JSON
                `message`, optional `options`, and `stream`.
            prepare_options: Sync or async hook receiving the request and a copy of caller generation
                options. Return the replacement mapping.
                Hosting validates protected fields after the hook and before resolving the factory,
                unlike Responses factories which run before the hook. Defaults are not mutated.
                Invocations has no outer background mode, so hosting never sets `background`;
                a `background` value returned by the hook is passed through as the application's choice.
            unsupported_options: Policy for agents without runtime options: `"warn"`, `"ignore"`, or `"error"`.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval. If omitted, use a positive
                `SSE_KEEPALIVE_INTERVAL`, otherwise disable heartbeats. Not a request/model timeout.
            **agent_server_kwargs: Additional AgentServer SDK constructor arguments, such as
                `asyncapi_spec_json` and `asyncapi_spec_yaml`. The host settings listed above (`agent`,
                `openapi_spec`, `agent_session_store_provider`, `parse_input`, `prepare_options`,
                `unsupported_options`, and `sse_keep_alive_interval_seconds`) are handled directly by this host.

        Raises:
            TypeError: If the agent source, parser/hook, or heartbeat type is invalid.
            ValueError: If the heartbeat interval is nonpositive or an injected agent has unsupported
                background or transport defaults.
        """
        super().__init__(
            agent=agent,
            openapi_spec=openapi_spec,
            agent_session_store_provider=agent_session_store_provider,
            parse_input=parse_input,
            prepare_options=prepare_options,
            unsupported_options=unsupported_options,
            sse_keep_alive_interval_seconds=sse_keep_alive_interval_seconds,
            **agent_server_kwargs,
        )
