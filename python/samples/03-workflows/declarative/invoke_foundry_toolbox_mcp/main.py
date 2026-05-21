# Copyright (c) Microsoft. All rights reserved.

"""Invoke Foundry Toolbox MCP sample — combines an MCP server tool and a
Foundry built-in tool through a single Foundry **toolbox** endpoint.

A Foundry toolbox bundles multiple tool definitions (MCP servers, built-in
Foundry tools such as ``web_search``, etc.) behind a single MCP-compatible
proxy URL. Calling MCP-server-backed tools through the toolbox returns
results namespaced as ``<server_label>___<tool_name>``; calling built-in
tools (e.g. ``web_search``) returns the tool under its plain name.

This sample mirrors the .NET sample
``dotnet/samples/03-workflows/Declarative/InvokeFoundryToolboxMcp/`` and
focuses on the **workflow execution path**:

  1. Build a bearer-authenticated ``httpx.AsyncClient`` for the toolbox
     MCP proxy and hand it to :class:`DefaultMCPToolHandler` so the YAML
     can call MCP tools (and introspect the toolbox tool list via the
     reserved ``"tools/list"`` tool name handled natively by the
     framework, matching .NET
     ``DefaultMcpToolHandler.ListToolsToolName``).
  2. Configure a :class:`WorkflowFactory` with that handler plus a local
     :class:`Agent` registered by name so the YAML's ``InvokeAzureAgent``
     action can summarise the combined tool output.
  3. Drive the workflow with a user question and render per-action
     progress markers plus the final agent summary.

One-off **toolbox administration** (delete + create_version) is delegated
to :mod:`toolbox_provisioning` so this file stays focused on the workflow.

Security note:
    The default ``DefaultMCPToolHandler`` performs no URL allowlisting or
    SSRF protection. This sample uses a project-scoped ``client_provider``
    that pins outbound requests to ``Authorization: Bearer …`` via Azure
    AD AND fails closed (raises) when the YAML resolves a different
    ``serverUrl``, so a tampered ``=Env.*`` value cannot redirect the
    bearer token to an attacker-controlled URL. MCP outputs flow back
    into agent conversations and share the prompt-injection risk
    surface of any other tool output.

Run with:
    python samples/03-workflows/declarative/invoke_foundry_toolbox_mcp/main.py

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT
        Azure AI Foundry project endpoint.
    FOUNDRY_MODEL
        Deployed Foundry model name used by ``FoundryChatClient``.

Optional environment variables:
    FOUNDRY_TOOLBOX_NAME
        Name of the toolbox to (re)create. Defaults to
        ``declarative_foundry_toolbox_mcp``.
    FOUNDRY_TOOLBOX_API_VERSION
        Toolbox MCP API version used when building the endpoint URL.
        Defaults to ``v1``.
    FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL
        The ``server_label`` registered for the Microsoft Learn Docs MCP
        server in the toolbox. Tool names from that server get the
        ``<server_label>___`` prefix on the toolbox MCP proxy.
        Defaults to ``microsoft_docs``.
    FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME
        Name of the Foundry built-in web-search tool surfaced by the
        toolbox. Defaults to ``web_search``.
    FOUNDRY_TOOLBOX_ENDPOINT
        Explicit toolbox MCP endpoint URL. When set, overrides the URL
        computed from ``FOUNDRY_PROJECT_ENDPOINT``,
        ``FOUNDRY_TOOLBOX_NAME``, and ``FOUNDRY_TOOLBOX_API_VERSION``.

Sample output:

    ============================================================
    Invoke Foundry Toolbox MCP Workflow Demo
    ============================================================
    Provisioning toolbox 'declarative_foundry_toolbox_mcp' in Foundry...
    Toolbox endpoint: https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/declarative_foundry_toolbox_mcp/mcp?api-version=v1

    Ask one question that benefits from both Microsoft Learn docs and a web search.

    You: How do I configure logging in the Agent Framework?
    [Listing toolbox tools...]
    [Searching Microsoft Learn docs...]
    [Searching the web...]
    [Summarizing results...]

    Agent: The Agent Framework declarative workflow runtime ...
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
from agent_framework import Agent
from agent_framework.declarative import (
    DefaultMCPToolHandler,
    MCPToolInvocation,
    WorkflowFactory,
)
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, get_bearer_token_provider
from toolbox_provisioning import (
    AZ_CLI_PROCESS_TIMEOUT_SECONDS,
    FOUNDRY_FEATURES_HEADERS,
    build_toolbox_mcp_server_url,
    create_sample_toolbox,
)

DEFAULT_TOOLBOX_NAME = "declarative_foundry_toolbox_mcp"
DEFAULT_TOOLBOX_API_VERSION = "v1"
DEFAULT_DOCS_SERVER_LABEL = "microsoft_docs"
DEFAULT_WEB_SEARCH_TOOL_NAME = "web_search"

AGENT_NAME = "FoundryToolboxMcpAgent"

# YAML action ids — kept in sync with ``workflow.yaml`` so the host can
# render progress markers as each step starts. Long-running MCP calls
# and a slow Foundry agent invocation can otherwise look like a hang.
LIST_TOOLS_ACTION_ID = "list_toolbox_tools"
DOCS_SEARCH_ACTION_ID = "search_docs_with_toolbox"
WEB_SEARCH_ACTION_ID = "search_web_with_toolbox"
SUMMARIZE_ACTION_ID = "summarize_toolbox_result"

_ACTION_PROGRESS_LABELS: dict[str, str] = {
    LIST_TOOLS_ACTION_ID: "Listing toolbox tools...",
    DOCS_SEARCH_ACTION_ID: "Searching Microsoft Learn docs...",
    WEB_SEARCH_ACTION_ID: "Searching the web...",
    SUMMARIZE_ACTION_ID: "Summarizing results...",
}

# AAD audience for the toolbox MCP proxy. Same scope used by the existing
# Foundry hosted-toolbox samples.
TOOLBOX_AAD_SCOPE = "https://ai.azure.com/.default"

# Match the MCP-recommended httpx timeouts (``mcp.shared._httpx_utils``:
# 30s connect/write/pool, 5min SSE read). httpx's default ``Timeout(5.0)``
# is far too aggressive for MCP streaming responses — long-running
# tool calls through the Foundry toolbox MCP proxy (e.g. the built-in
# ``web_search``) can take longer than 5s, and a read-timeout fired
# mid-stream leaves the upper-level ``call_tool`` awaiting a future that
# never resolves, surfacing as an indefinite hang.
MCP_CONNECT_TIMEOUT_SECONDS = 30.0
MCP_READ_TIMEOUT_SECONDS = 300.0

AGENT_INSTRUCTIONS = """\
You combine results from two tool calls in the conversation:

  - ``microsoft_docs_search`` from the Microsoft Learn Docs MCP server
    (authoritative Microsoft documentation), and
  - ``web_search`` (Foundry built-in) for general web context.

Answer the user's question using ONLY the information present in the
conversation. Prefer Microsoft Learn results for any product or API
question and cite document titles or URLs when available. If neither
result set contains an answer, say so plainly rather than guessing.
"""


class _BearerAuth(httpx.Auth):
    """Inject a fresh Azure AD bearer token on every request.

    ``httpx.Auth.auth_flow`` is a sync generator and works for both sync
    and async clients. ``get_bearer_token_provider`` caches/refreshes the
    token internally, so calling it per request is cheap.
    """

    def __init__(self, credential: TokenCredential) -> None:
        self._get_token = get_bearer_token_provider(credential, TOOLBOX_AAD_SCOPE)

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def main() -> None:
    """Run the Foundry toolbox MCP workflow."""
    # 1. Read configuration. ``FOUNDRY_PROJECT_ENDPOINT`` and
    #    ``FOUNDRY_MODEL`` are required; everything else has defaults.
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]
    toolbox_name = os.environ.get("FOUNDRY_TOOLBOX_NAME", DEFAULT_TOOLBOX_NAME)
    toolbox_api_version = os.environ.get("FOUNDRY_TOOLBOX_API_VERSION", DEFAULT_TOOLBOX_API_VERSION)
    docs_server_label = os.environ.get("FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL", DEFAULT_DOCS_SERVER_LABEL)
    web_search_tool_name = os.environ.get("FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME", DEFAULT_WEB_SEARCH_TOOL_NAME)

    print("=" * 60)
    print("Invoke Foundry Toolbox MCP Workflow Demo")
    print("=" * 60)

    # 2. Provision the toolbox in Foundry. Idempotent: delete-then-create.
    print(f"Provisioning toolbox '{toolbox_name}' in Foundry...")
    create_sample_toolbox(
        name=toolbox_name,
        docs_server_label=docs_server_label,
        project_endpoint=project_endpoint,
    )

    # 3. Resolve the toolbox MCP proxy URL. The workflow YAML references
    #    these values via ``=Env.FOUNDRY_TOOLBOX_*``; we publish them
    #    through ``WorkflowFactory(configuration=...)`` so the values stay scoped to
    #    this workflow.
    toolbox_endpoint = os.environ.get("FOUNDRY_TOOLBOX_ENDPOINT") or build_toolbox_mcp_server_url(
        project_endpoint=project_endpoint,
        name=toolbox_name,
        api_version=toolbox_api_version,
    )
    workflow_configuration: dict[str, str] = {
        "FOUNDRY_TOOLBOX_MCP_SERVER_URL": toolbox_endpoint,
        "FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL": docs_server_label,
        "FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME": web_search_tool_name,
    }
    print(f"Toolbox endpoint: {toolbox_endpoint}")
    print()

    # 4. Build the Foundry chat client + the summarising agent. The agent
    #    is registered with the factory by name, matching the sibling
    #    ``invoke_mcp_tool/`` sample.
    credential = AzureCliCredential(process_timeout=AZ_CLI_PROCESS_TIMEOUT_SECONDS)
    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )
    summary_agent = Agent(
        client=chat_client,
        name=AGENT_NAME,
        instructions=AGENT_INSTRUCTIONS,
    )

    # 5. Build a bearer-authenticated httpx client. The same client is
    #    reused for every MCP request: the LRU cache inside
    #    ``DefaultMCPToolHandler`` keeps a single MCP session alive
    #    for the toolbox URL, and ``tools/list`` reuses that same
    #    cached session for full transport-level consistency.
    #
    # Key configuration choices:
    #   * ``headers=FOUNDRY_FEATURES_HEADERS`` attaches the
    #     ``Foundry-Features: Toolboxes=V1Preview`` flag to EVERY
    #     outbound request — including the MCP ``initialize`` handshake
    #     during ``connect()``. The YAML's per-action ``headers:`` block
    #     also sets this value but only takes effect during
    #     ``call_tool`` (the ``MCPStreamableHTTPTool`` header_provider
    #     contextvar is empty during connect — see
    #     ``python/packages/core/agent_framework/_mcp.py:1639-1645``).
    #     Without the client-level default the toolbox MCP proxy rejects
    #     the session handshake and surfaces "unhandled errors in a
    #     TaskGroup".
    #   * ``timeout=Timeout(30.0, read=300.0)`` matches the MCP
    #     recommended defaults (``mcp.shared._httpx_utils``: 30s
    #     connect/write/pool, 5min SSE read). The httpx defaults of 5s
    #     EVERYWHERE break long-running MCP tool calls — the Foundry
    #     built-in ``web_search``, for instance, can take longer than
    #     5s to return through the toolbox SSE stream and would
    #     otherwise leave the client waiting on a future that never
    #     resolves (i.e. visibly hang on the host).
    #   * ``follow_redirects=True`` also mirrors the MCP defaults so
    #     proxy redirects don't surface as broken streams.
    http_client = httpx.AsyncClient(
        auth=_BearerAuth(credential),
        headers=FOUNDRY_FEATURES_HEADERS,
        timeout=httpx.Timeout(MCP_CONNECT_TIMEOUT_SECONDS, read=MCP_READ_TIMEOUT_SECONDS),
        follow_redirects=True,
    )

    async def _client_provider(invocation: MCPToolInvocation) -> httpx.AsyncClient | None:
        # Pin the bearer-authenticated client to the resolved toolbox URL.
        # The Foundry AAD bearer token is scoped to ``https://ai.azure.com``
        # but we still refuse to attach it to any URL we did not provision —
        # if the YAML resolves a different ``serverUrl`` (e.g. via a tampered
        # ``Env.*`` value or a config injection), fail closed by raising so
        # ``DefaultMCPToolHandler`` cannot fall back to an unauthenticated
        # client that silently leaks the request shape.
        if invocation.server_url.casefold() != toolbox_endpoint.casefold():
            raise ValueError(
                f"Refusing to attach Foundry bearer token to unexpected MCP URL: "
                f"{invocation.server_url!r}. Expected: {toolbox_endpoint!r}."
            )
        return http_client

    async with (
        http_client,
        DefaultMCPToolHandler(client_provider=_client_provider) as mcp_handler,
    ):
        factory = WorkflowFactory(
            agents={AGENT_NAME: summary_agent},
            mcp_tool_handler=mcp_handler,
            # The workflow YAML references ``=Env.FOUNDRY_TOOLBOX_*`` to keep
            # the toolbox URL / tool names configurable without editing the
            # YAML. We supply those values through ``configuration`` so the
            # PowerFx ``Env`` symbol is populated from a local dict instead
            # of the process environment. ``restrict_env_to_configuration``
            # defaults to ``True`` which suppresses any ``os.environ``
            # fallback — the workflow only sees the keys explicitly listed
            # in ``workflow_configuration`` below.
            configuration=workflow_configuration,
        )

        workflow_path = Path(__file__).parent / "workflow.yaml"
        workflow = factory.create_workflow_from_yaml_path(workflow_path)

        print("Ask one question that benefits from both Microsoft Learn docs and a web search.")
        print()
        user_input = input("You: ").strip()  # noqa: ASYNC250
        if not user_input:
            user_input = "How do I configure logging in the Agent Framework?"

        # 6. Drive the workflow with the user's question. The YAML fans
        #    out three MCP calls and finishes with the InvokeAzureAgent
        #    summarisation step. We render two kinds of host-visible
        #    feedback:
        #
        #      * Per-action progress lines via ``executor_invoked``
        #        events so a slow MCP call or agent invocation cannot
        #        look like a hang.
        #      * The final agent summary via ``output`` events. The
        #        three MCP actions use ``autoSend: false`` in the YAML
        #        so only the summarising agent's text reaches this
        #        branch.
        printed_prefix = False
        produced_output = False
        agent_executor_id = SUMMARIZE_ACTION_ID
        async for event in workflow.run({"text": user_input}, stream=True):
            if event.type == "executor_invoked":
                label = _ACTION_PROGRESS_LABELS.get(event.executor_id or "")
                if label is not None:
                    print(f"[{label}]")
                continue

            if event.type == "output" and isinstance(event.data, str):
                # Only the summarising agent action sends an output
                # event (MCP calls use ``autoSend: false``). Guard the
                # display so any future autoSend additions still print
                # under the "Agent:" prefix only when they come from
                # that action.
                if event.executor_id and event.executor_id != agent_executor_id:
                    continue
                if not printed_prefix:
                    print("\nAgent: ", end="", flush=True)
                    printed_prefix = True
                print(event.data, end="", flush=True)
                produced_output = True

        if produced_output:
            print()
        else:
            print("\n(no response produced)")


if __name__ == "__main__":
    asyncio.run(main())
