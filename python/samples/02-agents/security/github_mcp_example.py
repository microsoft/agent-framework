# Copyright (c) Microsoft. All rights reserved.

"""GitHub MCP URL + FIDES Example (direct URL connection with local policy enforcement).

This sample connects an agent directly to the remote GitHub MCP URL
(`https://api.githubcopilot.com/mcp/`) while enforcing IFC/FIDES security
locally in your process.

The key idea: wrap the remote MCP URL with `SecureMCPToolProxy(...)` so the MCP
tools run locally. This lets the security middleware inspect tool results, apply
IFC labels, hide untrusted content, and enforce policies before the agent uses
any tool data. The agent is then served through DevUI for interactive use.

Prerequisites (environment variables):
    - GITHUB_PAT: GitHub Personal Access Token (required)
    - FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (required)
    - FOUNDRY_MODEL: Foundry model deployment name (optional, defaults to o4-mini)

Run:
    uv run samples/02-agents/security/github_mcp_example.py
"""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import AsyncExitStack, suppress
from pathlib import Path

import uvicorn
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import SecureAgentConfig, SecureMCPToolProxy
from agent_framework_devui._server import DevServer
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

MCP_URL = "https://api.githubcopilot.com/mcp/"
MCP_HEADERS = {"X-MCP-Features": "ifc_labels"}  # Opt-in to server-side IFC label emission in _meta

_AGENT_INSTRUCTIONS = (
    "You are a helpful GitHub assistant. Use tools to answer accurately. "
    "Never fabricate repository data, pull requests, users, or timestamps. "
    "If tool data is unavailable, explicitly say retrieval failed. "
    "When operations might modify data, explain what action you intend to take."
)


async def main() -> None:
    """Connect to the GitHub MCP URL with FIDES security and serve the agent via DevUI."""
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv()

    github_pat = os.getenv("GITHUB_PAT")
    if not github_pat:
        raise RuntimeError("GITHUB_PAT environment variable is required.")

    foundry_model = os.getenv("FOUNDRY_MODEL", "o4-mini")
    credential = AzureCliCredential()
    main_client = FoundryChatClient(model=foundry_model, credential=credential)
    quarantine_client = FoundryChatClient(model="gpt-4o-mini", credential=credential)

    async with AsyncExitStack() as stack:
        # Wrap the remote MCP URL as local tools so FIDES can label inputs/outputs
        # and enforce policy checks before tool data is used by the agent.
        secure_github = await stack.enter_async_context(
            SecureMCPToolProxy(
                url=MCP_URL,
                headers={"Authorization": f"Bearer {github_pat}", **MCP_HEADERS},
                name="GitHub",
                description="GitHub MCP server over Streamable HTTP",
            )
        )
        print(f"Connected to MCP URL: {MCP_URL} ({len(secure_github.tools)} tools loaded)")

        # SecureAgentConfig is a context provider that applies the IFC/FIDES policy:
        # hide untrusted content, enforce policies, and require approval on violations.
        config = SecureAgentConfig(
            auto_hide_untrusted=True,
            enable_policy_enforcement=True,
            approval_on_violation=True,
            quarantine_chat_client=quarantine_client,
        )

        agent = await stack.enter_async_context(
            Agent(
                client=main_client,
                name="GitHubSecureMcpUrlAgent",
                instructions=_AGENT_INSTRUCTIONS,
                tools=secure_github.tools,
                context_providers=[config],
            )
        )

        # DevUI's serve(...) is synchronous and would spin up its own event loop,
        # orphaning the live MCP session. Drive DevServer via uvicorn directly so
        # it shares this loop with the MCP connection.
        host, port = "127.0.0.1", 8090
        auth_token = os.getenv("DEVUI_AUTH_TOKEN") or secrets.token_urlsafe(32)
        server = DevServer(port=port, host=host, auth_enabled=True, auth_token=auth_token)
        server.set_pending_entities([agent])

        print(f"\nDevUI:        http://{host}:{port}  (entity: agent_{agent.name})")
        print(f"Bearer token: {auth_token}")
        print("Press Ctrl+C to stop.\n")

        uvicorn_server = uvicorn.Server(uvicorn.Config(server.get_app(), host=host, port=port, log_level="info"))
        await uvicorn_server.serve()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
