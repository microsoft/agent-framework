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
shows how to:

  1. Provision a toolbox in a Foundry project (delete-then-create_version,
     so the sample can be re-run without manual cleanup).
  2. Configure a ``WorkflowFactory`` with a custom :class:`MCPToolHandler`
     that:
       * routes every MCP request through a single
         :class:`httpx.AsyncClient` carrying an Azure AD bearer token
         (the toolbox endpoint requires AAD auth), and
       * intercepts the reserved tool name ``"tools/list"`` so the YAML
         can introspect the toolbox tool set without an extra Python
         round-trip (matching the .NET ``DefaultMcpToolHandler``
         behaviour).
  3. Invoke ``microsoft_docs_search`` (from the Microsoft Learn Docs MCP
     server surfaced by the toolbox) and ``web_search`` (Foundry built-in)
     from a single declarative workflow.
  4. Hand both result sets to a local :class:`Agent` registered with the
     factory by name so the workflow's ``InvokeAzureAgent`` action can
     summarise them.

Security note:
    The default ``DefaultMCPToolHandler`` performs no URL allowlisting or
    SSRF protection. This sample wraps it with a project-scoped handler
    that pins outbound requests to ``Authorization: Bearer …`` via Azure
    AD; for production deployments, additionally constrain the workflow
    YAML to a known toolbox URL and reject any other server URL before
    delegating to the inner handler. MCP outputs flow back into agent
    conversations and share the prompt-injection risk surface of any
    other tool output.

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
import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from agent_framework import Agent, Content, MCPStreamableHTTPTool
from agent_framework.declarative import (
    DefaultMCPToolHandler,
    MCPToolInvocation,
    MCPToolResult,
    WorkflowFactory,
)
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, get_bearer_token_provider

DEFAULT_TOOLBOX_NAME = "declarative_foundry_toolbox_mcp"
DEFAULT_TOOLBOX_API_VERSION = "v1"
DEFAULT_DOCS_SERVER_LABEL = "microsoft_docs"
DEFAULT_WEB_SEARCH_TOOL_NAME = "web_search"
DEFAULT_DOCS_MCP_SERVER_URL = "https://learn.microsoft.com/api/mcp"

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

# Reserved tool name that the YAML uses to ask the handler for the toolbox
# tool list. Mirrors .NET ``DefaultMcpToolHandler.ListToolsToolName``.
LIST_TOOLS_TOOL_NAME = "tools/list"

# AAD audience for the toolbox MCP proxy. Same scope used by the existing
# Foundry hosted-toolbox samples.
TOOLBOX_AAD_SCOPE = "https://ai.azure.com/.default"

# Toolbox administration is gated by an Azure AI Foundry preview feature
# flag. The .NET sample injects this header via a pipeline policy on the
# ``AgentAdministrationClient``; the Python ``AIProjectClient`` doesn't
# add it automatically, so we pass it as a per-call header on every
# toolbox admin operation (delete + create_version) to make sure the
# toolbox is actually provisioned in the V1Preview routing path that the
# MCP proxy serves. Without this header, the calls can succeed at the
# HTTP layer but the toolbox is never wired up to the MCP endpoint —
# which surfaces at runtime as "MCP server failed to initialize:
# Session terminated" on the first ``InvokeMcpTool`` call.
FOUNDRY_FEATURES_HEADER_NAME = "Foundry-Features"
FOUNDRY_FEATURES_HEADER_VALUE = "Toolboxes=V1Preview"
FOUNDRY_FEATURES_HEADERS: dict[str, str] = {
    FOUNDRY_FEATURES_HEADER_NAME: FOUNDRY_FEATURES_HEADER_VALUE,
}

# Bump the ``az.cmd`` subprocess timeout from the default 10s. On Windows
# the Azure CLI batch wrapper can take noticeably longer than 10s to
# return a token (cold-start + ``az`` self-update checks + AAD round-trip),
# which surfaces as ``CredentialUnavailableError: Failed to invoke the
# Azure CLI`` after a ``subprocess.TimeoutExpired`` from the credential's
# internal call.
AZ_CLI_PROCESS_TIMEOUT_SECONDS = 60

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


def build_toolbox_mcp_server_url(project_endpoint: str, name: str, api_version: str) -> str:
    """Compose the Foundry toolbox MCP proxy URL.

    Toolboxes provisioned via ``AIProjectClient.beta.toolboxes`` live under
    the ``/toolboxes/{name}`` resource path (the Python SDK's
    ``BetaToolboxesOperations`` routes POST/GET/DELETE there — see
    ``azure/ai/projects/operations/_operations.py``). Their MCP proxy URL
    is ``<project_endpoint>/toolboxes/{name}/mcp?api-version=<api_version>``,
    matching the .NET sample.
    """
    base = project_endpoint.rstrip("/")
    return f"{base}/toolboxes/{name}/mcp?api-version={api_version}"


def create_sample_toolbox(
    *,
    name: str,
    docs_server_label: str,
    project_endpoint: str,
    docs_server_url: str = DEFAULT_DOCS_MCP_SERVER_URL,
) -> None:
    """Provision a toolbox version in the Foundry project (idempotent).

    Toolboxes are normally provisioned through the Foundry portal or a
    deployment script; this helper exists so the sample can be re-run
    end-to-end without manual cleanup. It deletes any toolbox under
    ``name`` and then creates a new version that bundles:

    - the Microsoft Learn Docs MCP server (``server_label=docs_server_label``),
      and
    - the Foundry built-in ``web_search`` tool.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, Tool, WebSearchTool
    from azure.core.exceptions import ResourceNotFoundError

    with (
        AzureCliCredential(process_timeout=AZ_CLI_PROCESS_TIMEOUT_SECONDS) as credential,
        AIProjectClient(credential=credential, endpoint=project_endpoint) as project_client,
    ):
        try:
            project_client.beta.toolboxes.delete(name, headers=FOUNDRY_FEATURES_HEADERS)
            print(f"Toolbox '{name}' deleted (replacing with a fresh version).")
        except ResourceNotFoundError:
            pass

        tools: list[Tool] = [
            MCPTool(
                server_label=docs_server_label,
                server_url=docs_server_url,
                require_approval="never",
            ),
            WebSearchTool(),
        ]

        created = project_client.beta.toolboxes.create_version(
            name=name,
            description="Sample toolbox combining Microsoft Learn Docs MCP and Foundry web search.",
            tools=tools,
            headers=FOUNDRY_FEATURES_HEADERS,
        )
        print(f"Created toolbox {created.name}@{created.version} ({len(created.tools)} tool(s)).")


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


class _ToolboxMcpToolHandler:
    """:class:`MCPToolHandler` that adds ``tools/list`` support to the default handler.

    The reserved tool name ``"tools/list"`` is intercepted client-side: it
    is translated to an MCP ``session.list_tools()`` call and the result
    is returned as a single JSON-encoded ``TextContent`` matching the
    shape produced by the .NET ``DefaultMcpToolHandler``
    (``{"tools": [{name, description, inputSchema, outputSchema}]}``).

    All other tool invocations delegate to the wrapped
    :class:`DefaultMCPToolHandler` so the LRU client cache, error
    normalisation, and approval flow remain unchanged.

    The ``tools/list`` path uses a transient :class:`MCPStreamableHTTPTool`
    (``load_tools=False`` so MCP discovery only happens once via the
    explicit ``session.list_tools()`` call). The same caller-supplied
    ``httpx.AsyncClient`` is reused so the bearer token and any other
    transport-level configuration stay consistent with the cached calls.
    """

    def __init__(self, inner: DefaultMCPToolHandler, http_client: httpx.AsyncClient) -> None:
        self._inner = inner
        self._http_client = http_client

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        if invocation.tool_name == LIST_TOOLS_TOOL_NAME:
            return await self._list_tools(invocation)
        return await self._inner.invoke_tool(invocation)

    async def _list_tools(self, invocation: MCPToolInvocation) -> MCPToolResult:
        if invocation.arguments:
            return MCPToolResult(
                outputs=[Content.from_text("Error: 'tools/list' does not accept arguments.")],
                is_error=True,
                error_message="'tools/list' does not accept arguments.",
            )

        # Snapshot headers so the closure does not see later mutations.
        captured_headers = dict(invocation.headers)

        def _header_provider(_kwargs: dict[str, Any]) -> dict[str, str]:
            return dict(captured_headers)

        tool = MCPStreamableHTTPTool(
            name=invocation.server_label or "foundry_toolbox_list",
            url=invocation.server_url,
            http_client=self._http_client,
            header_provider=_header_provider if captured_headers else None,
            load_tools=False,
            load_prompts=False,
        )

        try:
            await tool.connect()
            tool_list = await tool.session.list_tools()  # type: ignore[union-attr]
            payload = {
                "tools": [
                    {
                        "name": entry.name,
                        "description": entry.description,
                        "inputSchema": entry.inputSchema,
                        "outputSchema": entry.outputSchema,
                    }
                    for entry in tool_list.tools
                ]
            }
            return MCPToolResult(outputs=[Content.from_text(json.dumps(payload))])
        except Exception as exc:  # noqa: BLE001 - surface as tool error per protocol contract
            message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )
        finally:
            with contextlib.suppress(Exception):
                await tool.close()

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "_ToolboxMcpToolHandler":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()


async def main() -> None:
    """Run the Foundry toolbox MCP workflow."""
    # 1. Read configuration. ``FOUNDRY_PROJECT_ENDPOINT`` and
    #    ``FOUNDRY_MODEL`` are required; everything else has defaults.
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]
    toolbox_name = os.environ.get("FOUNDRY_TOOLBOX_NAME", DEFAULT_TOOLBOX_NAME)
    toolbox_api_version = os.environ.get("FOUNDRY_TOOLBOX_API_VERSION", DEFAULT_TOOLBOX_API_VERSION)
    docs_server_label = os.environ.get("FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL", DEFAULT_DOCS_SERVER_LABEL)
    web_search_tool_name = os.environ.get(
        "FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME", DEFAULT_WEB_SEARCH_TOOL_NAME
    )

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

    # 3. Resolve the toolbox MCP proxy URL and publish all dynamic values
    #    the YAML expects via ``Env.*``. Setting them after toolbox
    #    creation ensures the URL points at the freshly created version.
    toolbox_endpoint = os.environ.get("FOUNDRY_TOOLBOX_ENDPOINT") or build_toolbox_mcp_server_url(
        project_endpoint=project_endpoint,
        name=toolbox_name,
        api_version=toolbox_api_version,
    )
    os.environ["FOUNDRY_TOOLBOX_MCP_SERVER_URL"] = toolbox_endpoint
    os.environ["FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL"] = docs_server_label
    os.environ["FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME"] = web_search_tool_name
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
    #    ``DefaultMCPToolHandler`` will keep a single MCP session alive
    #    for the toolbox URL, and the ``tools/list`` interceptor reuses
    #    the same httpx client so headers / auth stay consistent.
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

    async def _client_provider(_inv: MCPToolInvocation) -> httpx.AsyncClient | None:
        return http_client

    async with (
        http_client,
        DefaultMCPToolHandler(client_provider=_client_provider) as inner_handler,
        _ToolboxMcpToolHandler(inner_handler, http_client) as mcp_handler,
    ):
        factory = WorkflowFactory(
            agents={AGENT_NAME: summary_agent},
            mcp_tool_handler=mcp_handler,
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
