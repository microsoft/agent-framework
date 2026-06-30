# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from agent_framework import MCPSkillsSource, MCPStreamableHTTPTool, SkillsProvider, SkillsSource
from azure.ai.agentserver.core import get_request_context

if TYPE_CHECKING:
    from collections.abc import Generator

    from agent_framework import Skill
    from azure.core.credentials import TokenCredential

logger = logging.getLogger(__name__)

# Default Microsoft Entra scope for Foundry data-plane access.
DEFAULT_TOOLBOX_SCOPE = "https://ai.azure.com/.default"
# Default timeout (seconds) for toolbox MCP requests.
_DEFAULT_TIMEOUT = 120.0


def _resolve_toolbox_endpoint() -> str:
    """Resolve the toolbox MCP endpoint URL from the environment.

    Prefers the explicit ``TOOLBOX_ENDPOINT`` env var; falls back to building the
    URL from ``FOUNDRY_PROJECT_ENDPOINT`` and ``TOOLBOX_NAME``.
    """
    endpoint = os.environ.get("TOOLBOX_ENDPOINT")
    if endpoint is not None:
        if not endpoint:
            raise ValueError("TOOLBOX_ENDPOINT is set but empty.")
        return endpoint
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    toolbox_name = os.environ.get("TOOLBOX_NAME")
    if not project_endpoint or not toolbox_name:
        raise ValueError(
            "Pass 'url', or set TOOLBOX_ENDPOINT, or set both FOUNDRY_PROJECT_ENDPOINT "
            "and TOOLBOX_NAME to build the toolbox MCP endpoint."
        )
    return f"{project_endpoint.rstrip('/')}/toolboxes/{toolbox_name}/mcp?api-version=v1"


def _toolbox_name_from_endpoint(endpoint: str) -> str:
    """Extract the toolbox name from a toolbox MCP endpoint URL.

    Handles both the versioned (``.../toolboxes/<name>/versions/<n>/mcp``) and
    unversioned (``.../toolboxes/<name>/mcp``) endpoint shapes that Foundry
    produces. Falls back to ``"toolbox"`` when the path has no ``toolboxes`` segment.
    """
    segments = urlsplit(endpoint).path.split("/")
    if "toolboxes" in segments:
        idx = segments.index("toolboxes")
        if idx + 1 < len(segments) and segments[idx + 1]:
            return segments[idx + 1]
    return "toolbox"


class _ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token and the platform call-id on every request.

    ``auth_flow`` runs for *every* outbound request (connection handshake as well
    as tool calls), so the bearer token is always present. The per-request
    ``x-agent-foundry-call-id`` is read from the request-scoped context populated
    by the hosting endpoint; it resolves to a fresh value on each request and is
    absent (no header) for protocol ``1.0.0`` or local development.
    """

    def __init__(self, credential: TokenCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        # azure-core credentials cache the token internally and only refresh near
        # expiry, so calling get_token per request is cheap.
        token = self._credential.get_token(self._scope).token
        request.headers["Authorization"] = f"Bearer {token}"
        for key, value in get_request_context().platform_headers().items():
            request.headers[key] = value
        yield request


class FoundryToolbox(MCPStreamableHTTPTool):
    """A Foundry toolbox exposed as an MCP tool, with hosting wired in.

    This is a thin convenience wrapper over :class:`~agent_framework.MCPStreamableHTTPTool`
    that targets a Microsoft Foundry toolbox endpoint. Compared to constructing an
    ``MCPStreamableHTTPTool`` by hand it:

    - resolves the toolbox endpoint and tool name from the environment when not given,
    - authenticates every request with a bearer token from ``credential``, and
    - forwards the platform per-request call-id (``x-agent-foundry-call-id``) so the
      Foundry MCP proxy can resolve the caller context server-side.

    The call-id forwarding is transparent: it is read from the request-scoped context
    the hosting endpoint binds on each request, so no per-request wiring is needed.
    Because the toolbox endpoint is a first-party Foundry service, forwarding the
    opaque caller token to it is safe.

    Like any MCP tool, the connection lifecycle is driven by the agent: the hosting
    server enters the agent, which connects the toolbox on first use and closes it
    (and the HTTP client it owns) at shutdown. Using it as an ``async with`` context
    manager directly is supported but not required.

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.foundry import FoundryChatClient
            from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            # The hosting server enters the agent, which connects/closes the toolbox.
            toolbox = FoundryToolbox(credential)
            agent = Agent(
                client=FoundryChatClient(credential=credential),
                tools=toolbox,
                default_options={"store": False},
            )
            await ResponsesHostServer(agent).run_async()
    """

    def __init__(
        self,
        credential: TokenCredential,
        *,
        url: str | None = None,
        name: str | None = None,
        token_scope: str = DEFAULT_TOOLBOX_SCOPE,
        load_prompts: bool = False,
        load_tools: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize a Foundry toolbox tool.

        Args:
            credential: A Microsoft Entra credential used to obtain bearer tokens for
                the toolbox endpoint. Tokens are requested per outbound request and
                cached by the credential.

        Keyword Args:
            url: The toolbox MCP endpoint URL. When ``None``, it is resolved from
                ``TOOLBOX_ENDPOINT`` or from ``FOUNDRY_PROJECT_ENDPOINT`` plus
                ``TOOLBOX_NAME``.
            name: The local tool name. When ``None``, it is taken from ``TOOLBOX_NAME``
                or derived from the endpoint path.
            token_scope: The token scope to request. Defaults to the Foundry data-plane
                scope.
            load_prompts: Whether to load prompts from the toolbox. Defaults to ``False``
                because toolboxes expose tools.
            load_tools: Whether to load tools from the toolbox. Defaults to ``True``.
            timeout: Request timeout in seconds for the underlying HTTP client.
        """
        endpoint = url or _resolve_toolbox_endpoint()
        tool_name = name or os.environ.get("TOOLBOX_NAME") or _toolbox_name_from_endpoint(endpoint)

        http_client = httpx.AsyncClient(
            auth=_ToolboxAuth(credential, token_scope),
            timeout=timeout,
        )

        super().__init__(
            name=tool_name,
            url=endpoint,
            http_client=http_client,
            load_prompts=load_prompts,
            load_tools=load_tools,
        )

    async def close(self) -> None:
        """Close the MCP session and the toolbox-owned HTTP client."""
        try:
            await super().close()
        finally:
            client = self._httpx_client
            if client is not None:
                self._httpx_client = None
                await client.aclose()

    def as_skills_provider(
        self,
        *,
        source_id: str | None = None,
        instruction_template: str | None = None,
        disable_caching: bool = False,
    ) -> SkillsProvider:
        """Return a :class:`~agent_framework.SkillsProvider` backed by this toolbox.

        A Foundry toolbox can serve Agent Skills (SEP-2640) over MCP. This discovers
        them from the well-known ``skill://index.json`` resource on the toolbox's MCP
        session and exposes them through a provider you can pass to an agent via
        ``context_providers=[...]``.

        The toolbox must be **connected** before its skills are discovered (which
        happens lazily on the first agent run). Connect it by passing the toolbox to
        the agent via ``tools=`` -- set ``load_tools=False`` if you want skills only
        and no tools -- or by entering it as an ``async with`` context manager.

        Keyword Args:
            source_id: Unique identifier for the provider instance.
            instruction_template: Custom system-prompt template for advertising
                skills; see :class:`~agent_framework.SkillsProvider`.
            disable_caching: Re-query the toolbox on every agent run instead of
                caching after the first discovery.

        Returns:
            A :class:`~agent_framework.SkillsProvider` that advertises and loads the
            toolbox's skills.

        Examples:
            .. code-block:: python

                toolbox = FoundryToolbox(credential, load_tools=False)
                agent = Agent(
                    client=FoundryChatClient(credential=credential),
                    # ``tools=toolbox`` connects the MCP session; ``load_tools=False``
                    # keeps its tools hidden so only its skills are surfaced.
                    tools=toolbox,
                    context_providers=[toolbox.as_skills_provider()],
                    default_options={"store": False},
                )
                await ResponsesHostServer(agent).run_async()
        """
        return SkillsProvider(
            _FoundryToolboxSkillsSource(self),
            source_id=source_id,
            instruction_template=instruction_template,
            disable_caching=disable_caching,
        )


class _FoundryToolboxSkillsSource(SkillsSource):
    """Discovers skills from a connected :class:`FoundryToolbox` MCP session.

    The toolbox's MCP ``session`` is established lazily when the toolbox connects
    (via the agent or an ``async with`` block), so the session is resolved at
    discovery time rather than captured at construction.
    """

    def __init__(self, toolbox: FoundryToolbox) -> None:
        self._toolbox = toolbox

    async def get_skills(self) -> list[Skill]:
        session = self._toolbox.session
        if session is None:
            raise RuntimeError(
                "FoundryToolbox is not connected, so its skills cannot be discovered. "
                "Pass the toolbox to the agent (tools=...) or enter it as an async "
                "context manager before the agent runs."
            )
        return await MCPSkillsSource(client=session).get_skills()
