# Copyright (c) Microsoft. All rights reserved.
"""Purview policy enforcement sample (Python).

Shows:
1. Creating a basic chat agent
2. Adding Purview policy evaluation via AGENT middleware (agent-level)
3. Adding Purview policy evaluation via CHAT middleware (chat-client level)
4. Running a threaded conversation and printing results

Environment variables:
- AZURE_OPENAI_ENDPOINT (required)
- AZURE_OPENAI_DEPLOYMENT_NAME (optional, defaults to gpt-4o-mini)
- PURVIEW_CLIENT_APP_ID (required)
- PURVIEW_USE_CERT_AUTH (optional, set to "true" for certificate auth)
- PURVIEW_TENANT_ID (required if certificate auth)
- PURVIEW_CERT_PATH (required if certificate auth)
- PURVIEW_CERT_PASSWORD (optional)
- PURVIEW_DEFAULT_USER_ID (optional, user ID for Purview evaluation)
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
from agent_framework.microsoft import (
    PurviewPolicyMiddleware,
    PurviewChatPolicyMiddleware,
    PurviewSettings,
)

JOKER_NAME = "Joker"
JOKER_INSTRUCTIONS = "You are good at telling jokes. Keep responses concise."


def _get_env(name: str, *, required: bool = True, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Environment variable {name} is required")
    return val  # type: ignore[return-value]


def build_credential() -> Any:
    """Select an Azure credential for Purview authentication.

    Supported modes:
    1. CertificateCredential (if PURVIEW_USE_CERT_AUTH=true)
    2. InteractiveBrowserCredential (requires PURVIEW_CLIENT_APP_ID)
    """
    client_id = _get_env("PURVIEW_CLIENT_APP_ID", required=True)
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


async def run_with_agent_middleware() -> None:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        print("Skipping run: AZURE_OPENAI_ENDPOINT not set")
        return

    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")
    chat_client = AzureOpenAIChatClient(deployment_name=deployment, endpoint=endpoint, credential=AzureCliCredential())

    purview_agent_middleware = PurviewPolicyMiddleware(
        build_credential(),
        PurviewSettings(
            app_name="Agent Framework Sample App",
        ),
    )

    agent = ChatAgent(
        chat_client=chat_client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
        middleware=purview_agent_middleware,
    )

    print("-- Agent Middleware Path --")
    first: AgentRunResponse = await agent.run(ChatMessage(role=Role.USER, text="Tell me a joke about a pirate.", additional_properties={"user_id": user_id}))
    print("First response (agent middleware):\n", first)

    second: AgentRunResponse = await agent.run(ChatMessage(role=Role.USER, text="That was funny. Tell me another one.", additional_properties={"user_id": user_id}))
    print("Second response (agent middleware):\n", second)


async def run_with_chat_middleware() -> None:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        print("Skipping chat middleware run: AZURE_OPENAI_ENDPOINT not set")
        return

    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", default="gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")
    
    chat_client = AzureOpenAIChatClient(
        deployment_name=deployment,
        endpoint=endpoint,
        credential=AzureCliCredential(),
        middleware=[
            PurviewChatPolicyMiddleware(
                build_credential(),
                PurviewSettings(
                    app_name="Agent Framework Sample App (Chat)",
                ),
            )
        ],
    )

    agent = ChatAgent(
        chat_client=chat_client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
    )

    print("-- Chat Middleware Path --")
    first: AgentRunResponse = await agent.run(
        ChatMessage(
            role=Role.USER,
            text="Give me a short clean joke.",
            additional_properties={"user_id": user_id},
        )
    )
    print("First response (chat middleware):\n", first)

    second: AgentRunResponse = await agent.run(
        ChatMessage(
            role=Role.USER,
            text="One more please.",
            additional_properties={"user_id": user_id},
        )
    )
    print("Second response (chat middleware):\n", second)


async def main() -> None:
    print("== Purview Agent Sample (Agent & Chat Middleware) ==")
    try:
        await run_with_agent_middleware()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Agent middleware path failed: {ex}")

    try:
        await run_with_chat_middleware()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Chat middleware path failed: {ex}")


if __name__ == "__main__":
    asyncio.run(main())
