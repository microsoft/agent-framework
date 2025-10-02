# Copyright (c) Microsoft. All rights reserved.
"""Purview policy enforcement sample (Python).

Shows:
1. Creating a basic chat agent
2. Adding Purview policy evaluation via middleware
3. Running a threaded conversation and printing results

Environment variables:
- AZURE_OPENAI_ENDPOINT (required)
- AZURE_OPENAI_DEPLOYMENT_NAME (optional, defaults inside SDK or to gpt-4o-mini)
- PURVIEW_CLIENT_APP_ID (recommended)
- PURVIEW_USE_CERT_AUTH (optional, set to "true" for certificate auth)
- PURVIEW_TENANT_ID (required if certificate auth)
- PURVIEW_CERT_PATH (required if certificate auth)
- PURVIEW_CERT_PASSWORD (optional)
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from agent_framework import AgentRunResponse, ChatAgent, ChatMessage, Role
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import (
    AzureCliCredential,
    CertificateCredential,
    InteractiveBrowserCredential,
)

# Purview integration pieces
from agent_framework_purview import PurviewPolicyMiddleware, PurviewSettings

JOKER_NAME = "Joker"
JOKER_INSTRUCTIONS = "You are good at telling jokes. Keep responses concise."


def _get_env(name: str, *, required: bool = True, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Environment variable {name} is required")
    return val  # type: ignore[return-value]


def build_credential() -> Any:
    """Select an Azure credential for Purview authentication.

    Supported modes ONLY:
    1. CertificateCredential (if PURVIEW_USE_CERT_AUTH=true)
    2. InteractiveBrowserCredential (requires PURVIEW_CLIENT_APP_ID)
    """
    client_id = _get_env("PURVIEW_CLIENT_APP_ID", required=False, default=None)
    use_cert_auth = _get_env("PURVIEW_USE_CERT_AUTH", required=False, default="false").lower() == "true"

    if not client_id:
        raise RuntimeError(
            "PURVIEW_CLIENT_APP_ID is required for interactive browser authentication; "
            "set PURVIEW_USE_CERT_AUTH=true for certificate mode instead."
        )

    if use_cert_auth:
        tenant_id = _get_env("PURVIEW_TENANT_ID")
        cert_path = _get_env("PURVIEW_CERT_PATH")
        cert_password = _get_env("PURVIEW_CERT_PASSWORD", required=False, default=None)
        print(f"Using Certificate Authentication (tenant: {tenant_id}, cert: {cert_path})")
        return CertificateCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            certificate_path=cert_path,
            password=cert_password,
        )

    print(f"Using Interactive Browser Authentication (client_id: {client_id})")
    return InteractiveBrowserCredential(client_id=client_id)


class JokerAgent(ChatAgent):
    """Simple agent used for the Purview sample (middleware injected at construction)."""
    ...


async def run_with_middleware() -> None:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        print("Skipping run: AZURE_OPENAI_ENDPOINT not set")
        return

    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    chat_client = AzureOpenAIChatClient(deployment_name=deployment, endpoint=endpoint, credential=AzureCliCredential())

    purview_middleware = PurviewPolicyMiddleware(
        build_credential(),
        PurviewSettings(
            appName="Agent Framework Sample App",
            defaultUserId=os.environ.get("PURVIEW_DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000000"),
        ),
    )

    agent = JokerAgent(
        chat_client=chat_client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
        middleware=[purview_middleware],
    )

    first: AgentRunResponse = await agent.run(ChatMessage(role=Role.USER, text="Tell me a joke about a pirate."))
    print("First response:\n", first)

    second: AgentRunResponse = await agent.run(
        ChatMessage(role=Role.USER, text="That was funny. Tell me another one.")
    )
    print("Second response:\n", second)


async def main() -> None:
    print("== Purview Agent Sample (Middleware) ==")
    try:
        await run_with_middleware()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Middleware path failed: {ex}")


if __name__ == "__main__":
    asyncio.run(main())
