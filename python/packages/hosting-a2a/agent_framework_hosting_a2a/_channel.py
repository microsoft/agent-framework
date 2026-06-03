# Copyright (c) Microsoft. All rights reserved.

"""A2A (Agent-to-Agent) channel for :mod:`agent_framework_hosting`.

Exposes the hosted target as an A2A peer agent: it publishes an agent card and
JSON-RPC routes, and drives every request through the host pipeline via
:class:`HostAgentExecutor`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelResponseHook,
    ChannelRunHook,
)

from ._executor import HostAgentExecutor

try:
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
except ImportError as exc:  # pragma: no cover - guards against incompatible a2a-sdk layout
    raise ImportError(
        "agent-framework-hosting-a2a requires a2a-sdk route helpers (create_agent_card_routes, create_jsonrpc_routes)."
    ) from exc


class A2AChannel:
    """Channel that exposes the hosted target over the A2A protocol.

    The A2A ``context_id`` maps onto the host session (caller-supplied session
    family) and each request is routed through :class:`ChannelContext`, so host
    session resolution and hooks apply.

    Note:
        Task state is held in an in-memory A2A task store for this version; it
        is independent of the host's session storage and is not persisted.
    """

    name: str = "a2a"

    def __init__(
        self,
        *,
        name: str | None = None,
        path: str = "",
        url: str = "/",
        agent_name: str | None = None,
        agent_description: str | None = None,
        agent_version: str = "1.0.0",
        agent_card: AgentCard | None = None,
        skills: Sequence[AgentSkill] | None = None,
        streaming: bool = True,
        rpc_url: str = "/",
        card_url: str = "/.well-known/agent-card.json",
        run_hook: ChannelRunHook | None = None,
        response_hook: ChannelResponseHook | None = None,
    ) -> None:
        """Configure the A2A channel.

        Keyword Args:
            name: Override the channel name (defaults to ``"a2a"``).
            path: Sub-path to mount the channel under; empty string (default)
                mounts the agent-card and JSON-RPC routes at the app root so
                the well-known card path is reachable.
            url: Public URL advertised in the agent card's interface (the base
                URL clients use to reach the JSON-RPC endpoint).
            agent_name: Name advertised in the default agent card. Defaults to
                the hosted target's name.
            agent_description: Description advertised in the default agent card.
                Defaults to the hosted target's description.
            agent_version: Version advertised in the default agent card.
            agent_card: A fully-specified agent card; when provided it takes
                precedence over the ``agent_*``/``url``/``skills`` fields.
            skills: Skills advertised in the default agent card.
            streaming: Consume the target via streaming and publish incremental
                A2A task artifacts (default ``True``).
            rpc_url: Path for the JSON-RPC endpoint (relative to ``path``).
            card_url: Path for the agent-card endpoint (relative to ``path``).
            run_hook: Optional run hook applied to each request.
            response_hook: Optional response hook applied to originating replies.
        """
        if name is not None:
            self.name = name
        self.path = path
        self._url = url
        self._agent_name = agent_name
        self._agent_description = agent_description
        self._agent_version = agent_version
        self._agent_card = agent_card
        self._skills = list(skills) if skills is not None else []
        self._streaming = streaming
        self._rpc_url = rpc_url
        self._card_url = card_url
        self._run_hook = run_hook
        self._response_hook = response_hook

    def _build_agent_card(self, context: ChannelContext) -> AgentCard:
        """Derive a default agent card from the hosted target, if not supplied."""
        if self._agent_card is not None:
            return self._agent_card
        target: Any = context.target
        name = self._agent_name or getattr(target, "name", None) or self.name
        description = self._agent_description or getattr(target, "description", None) or f"{name} (A2A)"
        return AgentCard(
            name=name,
            description=description,
            version=self._agent_version,
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=self._streaming),
            supported_interfaces=[AgentInterface(url=self._url, protocol_binding="JSONRPC")],
            skills=self._skills,
        )

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Build the A2A request handler and contribute its routes."""
        agent_card = self._build_agent_card(context)
        executor = HostAgentExecutor(
            context,
            channel_name=self.name,
            streaming=self._streaming,
            run_hook=self._run_hook,
            response_hook=self._response_hook,
        )
        handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
            agent_card=agent_card,
        )
        routes = [
            *create_agent_card_routes(agent_card, card_url=self._card_url),
            *create_jsonrpc_routes(handler, self._rpc_url),
        ]
        return ChannelContribution(routes=routes)
