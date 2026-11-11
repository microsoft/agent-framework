# Copyright (c) Microsoft. All rights reserved.

"""Classify messages added by application-owned context providers.

``SecureAgentConfig.message_labeler`` receives each provider's authoritative
``source_id`` and message. The application returns the complete label that
FIDES should use for that message.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT - Microsoft Foundry project endpoint.
    FOUNDRY_MODEL - Model deployment name, for example ``gpt-4o``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agent_framework import Agent, AgentSession, ContextProvider, Message, SessionContext
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import ConfidentialityLabel, ContentLabel, IntegrityLabel, SecureAgentConfig
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


class PublicSearchContext(ContextProvider):
    """Add public but externally controlled search context."""

    def __init__(self) -> None:
        super().__init__("public_search")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        del agent, session, state
        context.extend_messages(
            self,
            [Message(role="assistant", contents=["Public search result: Contoso announced a new product."])],
        )


class PrivateCaseContext(ContextProvider):
    """Add private case data from an external support system."""

    def __init__(self) -> None:
        super().__init__("private_case")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        del agent, session, state
        context.extend_messages(
            self,
            [Message(role="assistant", contents=["Private case note: customer account 123 needs investigation."])],
        )


def classify_provider_message(source_id: str, _: Message) -> ContentLabel:
    """Choose the authoritative label from host-owned provider policy."""
    confidentiality = ConfidentialityLabel.PRIVATE if source_id == "private_case" else ConfidentialityLabel.PUBLIC
    return ContentLabel(
        integrity=IntegrityLabel.UNTRUSTED,
        confidentiality=confidentiality,
    )


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    async with Agent(
        client=client,
        instructions="Summarize the available context without revealing private details.",
        context_providers=[
            SecureAgentConfig(message_labeler=classify_provider_message),
            PublicSearchContext(),
            PrivateCaseContext(),
        ],
    ) as agent:
        response = await agent.run("What context is available?", session=AgentSession())
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
The public context mentions a Contoso product announcement. Private case
details are available but should not be disclosed.
"""
