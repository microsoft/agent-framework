# Copyright (c) Microsoft. All rights reserved.
"""Purview policy enforcement sample (Python).

Shows:
1. Creating a basic chat agent
2. Adding Purview policy evaluation via AGENT middleware (agent-level)
3. Adding Purview policy evaluation via CHAT middleware (chat-client level)
4. Implementing a custom cache provider for advanced caching scenarios
5. Running threaded conversations and printing results

Note: Caching is automatic and enabled by default.

Environment variables:
- FOUNDRY_PROJECT_ENDPOINT (required) - Azure AI Foundry project endpoint URL
- FOUNDRY_MODEL (optional, defaults to gpt-4o-mini)
- PURVIEW_CLIENT_APP_ID (required)
- PURVIEW_USE_CERT_AUTH (optional, set to "true" for certificate auth)
- PURVIEW_TENANT_ID (required if certificate auth)
- PURVIEW_CERT_PATH (required if certificate auth)
- PURVIEW_CERT_PASSWORD (optional)
- PURVIEW_DEFAULT_USER_ID (optional, user ID for Purview evaluation)
"""

import asyncio
import os
from typing import Any

from agent_framework import Agent, AgentResponse, Message
from agent_framework.foundry import FoundryChatClient
from agent_framework.microsoft import (
    PurviewChatPolicyMiddleware,
    PurviewPolicyMiddleware,
    PurviewSettings,
)
from azure.identity import (
    AzureCliCredential,
    CertificateCredential,
    InteractiveBrowserCredential,
)
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

JOKER_NAME = "Joker"
JOKER_INSTRUCTIONS = "You are good at telling jokes. Keep responses concise."

# Sequential prompts to demonstrate good -> block -> good orchestration.
# The sensitive prompt contains a Visa test credit card number that matches Purview's
# built-in Credit Card sensitive information type. If the tenant has a DLP policy that
# blocks credit card content for Microsoft 365 Copilot and AI apps, the second message
# will be blocked and the third will verify that subsequent calls still flow normally
# after a block.
GOOD_PROMPT_PRIMARY = "Tell me a joke about a pirate."
SENSITIVE_PROMPT = "My corporate credit card is 4111 1111 1111 1111. Please confirm receipt."
GOOD_PROMPT_FOLLOWUP = "Another light joke please."


async def run_policy_flow(
    label: str,
    agent: Agent,
    user_id: str | None,
    blocked_text: str,
) -> None:
    """Run a good -> block candidate -> good sequence and report each outcome."""
    blocked_marker = blocked_text.lower()
    prompts = [
        ("good (cold cache)", GOOD_PROMPT_PRIMARY),
        ("expected block", SENSITIVE_PROMPT),
        ("good (warm cache)", GOOD_PROMPT_FOLLOWUP),
    ]
    for tag, text in prompts:
        response: AgentResponse = await agent.run(
            Message("user", [text], additional_properties={"user_id": user_id})
        )
        outcome = "BLOCKED" if blocked_marker in str(response).lower() else "ALLOWED"
        print(f"[{label}] {tag}: {outcome}\n{response}\n")


# Custom Cache Provider Implementation
class SimpleDictCacheProvider:
    """A simple custom cache provider that stores everything in a dictionary.

    This example demonstrates how to implement the CacheProvider protocol.
    """

    def __init__(self) -> None:
        """Initialize the simple dictionary cache."""
        self._cache: dict[str, Any] = {}
        self._access_count: dict[str, int] = {}

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found.
        """
        value = self._cache.get(key)
        if value is not None:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            print(f"[CustomCache] Cache HIT for key: {key[:50]}... (accessed {self._access_count[key]} times)")
        else:
            print(f"[CustomCache] Cache MISS for key: {key[:50]}...")
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl_seconds: Time to live in seconds (ignored in this simple implementation).
        """
        self._cache[key] = value
        print(f"[CustomCache] Cached value for key: {key[:50]}... (TTL: {ttl_seconds}s)")

    async def remove(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key.
        """
        if key in self._cache:
            del self._cache[key]
            self._access_count.pop(key, None)
            print(f"[CustomCache] Removed key: {key[:50]}...")


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
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("Skipping run: FOUNDRY_PROJECT_ENDPOINT not set")
        return

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")
    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())

    settings = PurviewSettings(app_name="Agent Framework Sample App")
    purview_agent_middleware = PurviewPolicyMiddleware(build_credential(), settings)

    agent = Agent(
        client=client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
        middleware=[purview_agent_middleware],
    )

    print("-- Agent MiddlewareTypes Path --")
    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("agent middleware", agent, user_id, blocked_text)


async def run_with_chat_middleware() -> None:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("Skipping chat middleware run: FOUNDRY_PROJECT_ENDPOINT not set")
        return

    deployment = os.environ.get("FOUNDRY_MODEL", default="gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")

    settings = PurviewSettings(app_name="Agent Framework Sample App (Chat)")
    client = FoundryChatClient(
        model=deployment,
        project_endpoint=endpoint,
        credential=AzureCliCredential(),
        middleware=[
            PurviewChatPolicyMiddleware(build_credential(), settings)
        ],
    )

    agent = Agent(
        client=client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
    )

    print("-- Chat MiddlewareTypes Path --")
    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("chat middleware", agent, user_id, blocked_text)


async def run_with_custom_cache_provider() -> None:
    """Demonstrate implementing and using a custom cache provider."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("Skipping custom cache provider run: FOUNDRY_PROJECT_ENDPOINT not set")
        return

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")
    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())

    custom_cache = SimpleDictCacheProvider()

    settings = PurviewSettings(app_name="Agent Framework Sample App (Custom Provider)")
    purview_agent_middleware = PurviewPolicyMiddleware(
        build_credential(),
        settings,
        cache_provider=custom_cache,
    )

    agent = Agent(
        client=client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
        middleware=[purview_agent_middleware],
    )

    print("-- Custom Cache Provider Path --")
    print("Using SimpleDictCacheProvider")
    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("custom cache", agent, user_id, blocked_text)


async def run_with_default_cache() -> None:
    """Demonstrate using the default built-in cache."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("Skipping default cache run: FOUNDRY_PROJECT_ENDPOINT not set")
        return

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")
    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())

    # No cache_provider specified - uses default InMemoryCacheProvider
    settings = PurviewSettings(
        app_name="Agent Framework Sample App (Default Cache)",
        cache_ttl_seconds=3600,
        max_cache_size_bytes=100 * 1024 * 1024,  # 100MB
    )
    purview_agent_middleware = PurviewPolicyMiddleware(build_credential(), settings)

    agent = Agent(
        client=client,
        instructions=JOKER_INSTRUCTIONS,
        name=JOKER_NAME,
        middleware=[purview_agent_middleware],
    )

    print("-- Default Cache Path --")
    print("Using default InMemoryCacheProvider with settings-based configuration")
    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("default cache", agent, user_id, blocked_text)


async def main() -> None:
    print("== Purview Agent Sample (MiddlewareTypes with Automatic Caching) ==")

    try:
        await run_with_agent_middleware()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Agent middleware path failed: {ex}")

    try:
        await run_with_chat_middleware()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Chat middleware path failed: {ex}")

    try:
        await run_with_custom_cache_provider()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Custom cache provider path failed: {ex}")

    try:
        await run_with_default_cache()
    except Exception as ex:  # pragma: no cover - demo resilience
        print(f"Default cache path failed: {ex}")


if __name__ == "__main__":
    asyncio.run(main())
