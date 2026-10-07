# Copyright (c) Microsoft. All rights reserved.

"""USER_IDENTITY principal binding with SecureAgentConfig.

This sample shows how an application binds identity-scoped data to an
authenticated tenant/user principal and limits destinations to an authorized
principal set. It demonstrates:

1. Building source and destination tools from host-authenticated identity.
2. Declaring canonical principals with ``PRINCIPAL_METADATA_KEY``.
3. Adding ``SecureAgentConfig`` through ``context_providers``.
4. Allowing a same-principal flow and blocking a cross-principal flow.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_MODEL: Model deployment name.

Before running:
    az login

Run from the ``python`` directory:
    uv run samples/02-agents/security/user_identity_security_example.py

Expected behavior:
    - Saving Alice's profile to Alice's destination is allowed.
    - Sending Alice's profile to Bob's destination is blocked and audited.
"""

import asyncio
import os
from typing import Any

from agent_framework import Agent, AgentSession, FunctionTool, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import PRINCIPAL_METADATA_KEY, SecureAgentConfig
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = "tenant-contoso"
AUTHENTICATED_USER_ID = "alice"
OTHER_USER_ID = "bob"


def principal_set(*, tenant_id: str, user_id: str) -> list[dict[str, str]]:
    """Return the canonical principal-set representation used by FIDES."""
    return [{"tenant_id": tenant_id, "user_id": user_id}]


def create_identity_tools(*, tenant_id: str, authenticated_user_id: str) -> list[FunctionTool]:
    """Create tools whose security metadata comes from authenticated host state.

    In a real application, derive these values from the authenticated request or
    session before constructing the agent's tools. Never accept the principal
    from model-generated tool arguments or remote result metadata.
    """
    authenticated_principals = principal_set(tenant_id=tenant_id, user_id=authenticated_user_id)
    other_principals = principal_set(tenant_id=tenant_id, user_id=OTHER_USER_ID)

    @tool(
        description="Read the authenticated user's profile.",
        additional_properties={
            "source_integrity": "trusted",
            "confidentiality": "user_identity",
            PRINCIPAL_METADATA_KEY: authenticated_principals,
        },
    )
    async def read_my_profile() -> str:
        """Return identity-scoped data for the authenticated user."""
        return f"{authenticated_user_id} profile: preferred language is Python."

    @tool(
        description="Save a note to the authenticated user's profile.",
        additional_properties={
            "max_allowed_confidentiality": "user_identity",
            PRINCIPAL_METADATA_KEY: authenticated_principals,
        },
    )
    async def save_to_my_profile(note: str) -> dict[str, Any]:
        """Save data to a destination authorized for the same principal."""
        print(f"ALLOWED: saved to {authenticated_user_id}: {note}")
        return {"status": "saved", "user_id": authenticated_user_id}

    @tool(
        description="Send a note to another user's account.",
        additional_properties={
            "max_allowed_confidentiality": "user_identity",
            PRINCIPAL_METADATA_KEY: other_principals,
        },
    )
    async def send_to_other_account(note: str) -> dict[str, Any]:
        """Represent a destination authorized for a different principal."""
        print(f"UNEXPECTED: sent to {OTHER_USER_ID}: {note}")
        return {"status": "sent", "user_id": OTHER_USER_ID}

    return [read_my_profile, save_to_my_profile, send_to_other_account]


def create_agent() -> tuple[Agent, SecureAgentConfig]:
    """Create a Foundry agent with identity-aware security enforcement."""
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )
    security = SecureAgentConfig(
        auto_hide_untrusted=True,
        enable_policy_enforcement=True,
        block_on_violation=True,
    )
    agent = Agent(
        client=client,
        name="IdentityScopedAssistant",
        instructions="Follow the user's requested tool sequence exactly.",
        tools=create_identity_tools(
            tenant_id=TENANT_ID,
            authenticated_user_id=AUTHENTICATED_USER_ID,
        ),
        context_providers=[security],
    )
    return agent, security


async def run_scenario(
    agent: Agent,
    security: SecureAgentConfig,
    *,
    title: str,
    prompt: str,
) -> None:
    """Run one isolated scenario and print policy audit entries."""
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")
    session = AgentSession()
    response = await agent.run(prompt, session=session)
    print(f"\nAgent response: {response.text}")

    audit_log = security.get_audit_log(session)
    if audit_log:
        print("\nPolicy audit:")
        for entry in audit_log:
            print(f"- {entry.get('reason', 'Policy violation')}")
    else:
        print("\nPolicy audit: no violations")


async def main() -> None:
    """Run matching-principal and cross-principal flows."""
    agent, security = create_agent()

    await run_scenario(
        agent,
        security,
        title="Allowed: Alice data to Alice destination",
        prompt=(
            "Call read_my_profile. Then call save_to_my_profile with the profile text "
            "as the note. Do not call any other tools."
        ),
    )
    await run_scenario(
        agent,
        security,
        title="Blocked: Alice data to Bob destination",
        prompt=(
            "Call read_my_profile. Then call send_to_other_account with the profile text "
            "as the note. Do not call any other tools."
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
