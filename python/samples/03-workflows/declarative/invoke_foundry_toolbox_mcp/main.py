# Copyright (c) Microsoft. All rights reserved.

"""Invoke a Foundry toolbox MCP endpoint from a declarative workflow.

The workflow calls ``microsoft_docs_search`` (the Microsoft Learn Docs
MCP server, bundled into a sample toolbox by ``toolbox_provisioning``)
through the toolbox proxy and asks a Foundry agent to summarise the
result.

Required env vars:
    FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL.

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
from toolbox_provisioning import (  # ty: ignore[unresolved-import]  # pyrefly: ignore[missing-import]
    create_sample_toolbox,
)

AGENT_NAME = "FoundryToolboxMcpAgent"
TOOLBOX_NAME = "declarative_foundry_toolbox_mcp"
DOCS_SERVER_LABEL = "microsoft_docs"

AGENT_INSTRUCTIONS = """\
Answer the user's question using ONLY the Microsoft Learn docs search
result already present in the conversation. Cite document titles or
URLs when available. If the result does not contain an answer, say so
plainly rather than guessing.
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

    print("=" * 60)
    print("Invoke Foundry Toolbox MCP Workflow Demo")
    print("=" * 60)
    print(f"Provisioning toolbox '{TOOLBOX_NAME}' in Foundry...")
    create_sample_toolbox(
        name=TOOLBOX_NAME,
        docs_server_label=DOCS_SERVER_LABEL,
        project_endpoint=project_endpoint,
    )

    toolbox_endpoint = f"{project_endpoint.rstrip('/')}/toolboxes/{TOOLBOX_NAME}/mcp?api-version=v1"
    print(f"Toolbox endpoint: {toolbox_endpoint}")
    print()

    credential = AzureCliCredential()
    chat_client = FoundryChatClient(project_endpoint=project_endpoint, model=model, credential=credential)
    summary_agent = Agent(client=chat_client, name=AGENT_NAME, instructions=AGENT_INSTRUCTIONS)

    # ``timeout=`` matches the MCP-recommended values; httpx's 5s
    # default breaks long-running tool calls.
    http_client = httpx.AsyncClient(
        auth=_BearerAuth(credential),
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
            configuration={
                "FOUNDRY_TOOLBOX_MCP_SERVER_URL": toolbox_endpoint,
                "FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL": DOCS_SERVER_LABEL,
            },
        )
        workflow = factory.create_workflow_from_yaml_path(Path(__file__).parent / "workflow.yaml")

        print("Ask a question that can be answered from the Microsoft Learn docs.")
        print()
        user_input = input("You: ").strip() or "How do I configure logging in the Agent Framework?"  # noqa: ASYNC250

        printed_prefix = False
        async for event in workflow.run({"text": user_input}, stream=True):
            if event.type == "executor_invoked":
                if event.executor_id == "search_docs_with_toolbox":
                    print("[Searching Microsoft Learn docs...]")
                elif event.executor_id == "summarize_toolbox_result":
                    print("[Summarizing results...]")
            elif event.type == "output" and isinstance(event.data, str):
                if not printed_prefix:
                    print("\nAgent: ", end="", flush=True)
                    printed_prefix = True
                print(event.data, end="", flush=True)

        print()


if __name__ == "__main__":
    asyncio.run(main())
