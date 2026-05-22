# Copyright (c) Microsoft. All rights reserved.

"""Invoke a Foundry toolbox MCP endpoint from a declarative workflow.

The workflow lists the toolbox's tools, queries Microsoft Learn Docs
and ``web_search`` through the toolbox, and summarises the combined
results with a Foundry agent. The reserved ``tools/list`` tool name is
intercepted natively by ``DefaultMCPToolHandler``.

Required env vars:
    FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL.

Optional env vars:
    FOUNDRY_TOOLBOX_NAME, FOUNDRY_TOOLBOX_API_VERSION,
    FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL,
    FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME, FOUNDRY_TOOLBOX_ENDPOINT.

Run with:
    python samples/03-workflows/declarative/invoke_foundry_toolbox_mcp/main.py
"""

import asyncio
import os
from collections.abc import Generator
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
    FOUNDRY_FEATURES_HEADERS,
    build_toolbox_mcp_server_url,
    create_sample_toolbox,
)

AGENT_NAME = "FoundryToolboxMcpAgent"

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
    """Inject a fresh Azure AD bearer token on every request."""

    def __init__(self, credential: TokenCredential) -> None:
        self._get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def main() -> None:
    """Run the Foundry toolbox MCP workflow."""
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]
    toolbox_name = os.environ.get("FOUNDRY_TOOLBOX_NAME", "declarative_foundry_toolbox_mcp")
    toolbox_api_version = os.environ.get("FOUNDRY_TOOLBOX_API_VERSION", "v1")
    docs_server_label = os.environ.get("FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL", "microsoft_docs")
    web_search_tool_name = os.environ.get("FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME", "web_search")

    print("=" * 60)
    print("Invoke Foundry Toolbox MCP Workflow Demo")
    print("=" * 60)
    print(f"Provisioning toolbox '{toolbox_name}' in Foundry...")
    create_sample_toolbox(
        name=toolbox_name,
        docs_server_label=docs_server_label,
        project_endpoint=project_endpoint,
    )

    toolbox_endpoint = os.environ.get("FOUNDRY_TOOLBOX_ENDPOINT") or build_toolbox_mcp_server_url(
        project_endpoint=project_endpoint,
        name=toolbox_name,
        api_version=toolbox_api_version,
    )
    # Values exposed to ``=Env.*`` in workflow.yaml. Passing them via
    # ``configuration`` keeps the symbol table scoped to this workflow.
    workflow_configuration = {
        "FOUNDRY_TOOLBOX_MCP_SERVER_URL": toolbox_endpoint,
        "FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL": docs_server_label,
        "FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME": web_search_tool_name,
    }
    print(f"Toolbox endpoint: {toolbox_endpoint}")
    print()

    credential = AzureCliCredential()
    chat_client = FoundryChatClient(project_endpoint=project_endpoint, model=model, credential=credential)
    summary_agent = Agent(client=chat_client, name=AGENT_NAME, instructions=AGENT_INSTRUCTIONS)

    # ``headers=`` attaches the Foundry-Features preview flag on every
    # request, including the MCP ``initialize`` handshake (the YAML's
    # per-action ``headers`` only takes effect during ``call_tool``).
    # ``timeout=`` matches the MCP-recommended values; httpx's 5s
    # default breaks long-running tool calls like ``web_search``.
    http_client = httpx.AsyncClient(
        auth=_BearerAuth(credential),
        headers=FOUNDRY_FEATURES_HEADERS,
        timeout=httpx.Timeout(30.0, read=300.0),
        follow_redirects=True,
    )

    async def _client_provider(invocation: MCPToolInvocation) -> httpx.AsyncClient | None:
        # Fail closed when the YAML resolves a different ``serverUrl``
        # so the bearer-bound client cannot be reused against an
        # unexpected endpoint and ``DefaultMCPToolHandler`` cannot
        # silently fall back to an unauthenticated client.
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
            configuration=workflow_configuration,
        )
        workflow = factory.create_workflow_from_yaml_path(Path(__file__).parent / "workflow.yaml")

        print("Ask one question that benefits from both Microsoft Learn docs and a web search.")
        print()
        user_input = input("You: ").strip() or "How do I configure logging in the Agent Framework?"  # noqa: ASYNC250

        # Progress markers per YAML action so slow MCP calls or agent
        # invocations don't look like a hang. Action ids mirror
        # workflow.yaml.
        progress_labels = {
            "list_toolbox_tools": "Listing toolbox tools...",
            "search_docs_with_toolbox": "Searching Microsoft Learn docs...",
            "search_web_with_toolbox": "Searching the web...",
            "summarize_toolbox_result": "Summarizing results...",
        }
        printed_prefix = False
        produced_output = False
        async for event in workflow.run({"text": user_input}, stream=True):
            if event.type == "executor_invoked":
                label = progress_labels.get(event.executor_id or "")
                if label is not None:
                    print(f"[{label}]")
                continue
            if event.type == "output" and isinstance(event.data, str):
                # Only the summarising agent emits ``output``; the three
                # MCP actions use ``autoSend: false`` in the YAML.
                if event.executor_id and event.executor_id != "summarize_toolbox_result":
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
