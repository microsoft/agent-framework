# Copyright (c) Microsoft. All rights reserved.

"""Inspect and label messages added by multiple simple context providers.

``ProviderMessageLabeler`` must run after the providers whose messages it
inspects and immediately before ``SecureAgentConfig``. It replaces the prior
message buckets with one labeled batch that participates in FIDES replay
classification.

This pattern is for simple providers that only add messages during
``before_run``. Use ``provider_labeling_example.py`` for history providers.
Providers with persistence, extra lifecycle hooks, cross-session merges, or
service-side continuation should label messages inside their implementation.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT - Microsoft Foundry project endpoint.
    FOUNDRY_MODEL - Model deployment name, for example ``gpt-4o``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from agent_framework import Agent, AgentSession, ContextProvider, HistoryProvider, Message, SessionContext
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import ConfidentialityLabel, ContentLabel, IntegrityLabel, SecureAgentConfig
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

ProviderMessageClassifier = Callable[[str, Message], ContentLabel]


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
    """Choose restriction labels from host-owned provider policy."""
    confidentiality = ConfidentialityLabel.PRIVATE if source_id == "private_case" else ConfidentialityLabel.PUBLIC
    return ContentLabel(
        integrity=IntegrityLabel.UNTRUSTED,
        confidentiality=confidentiality,
    )


class ProviderMessageLabeler(HistoryProvider):
    """Label every message already added by earlier context providers."""

    def __init__(
        self,
        labeler: ProviderMessageClassifier,
        *,
        source_id: str = "fides_labeled_context",
    ) -> None:
        super().__init__(
            source_id=source_id,
            store_inputs=False,
            store_outputs=False,
        )
        self._labeler = labeler

    @staticmethod
    def _copy_with_label(
        message: Message,
        *,
        original_source_id: str,
        labeled_source_id: str,
        label: ContentLabel,
    ) -> Message:
        labeled = Message.from_dict(message.to_dict())
        properties = dict(labeled.additional_properties)
        attribution = properties.get("_attribution")
        original_attribution = dict(cast(Mapping[str, Any], attribution)) if isinstance(attribution, Mapping) else {}
        properties["_attribution"] = {
            "source_id": labeled_source_id,
            "source_type": "ProviderMessageLabeler",
            "original_source_id": original_attribution.get("source_id", original_source_id),
        }
        properties["security_label"] = label.to_dict()
        labeled.additional_properties = properties
        return labeled

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        del agent, session, state
        labeled_messages: list[Message] = []
        for source_id, messages in list(context.context_messages.items()):
            if source_id == self.source_id:
                continue
            for message in messages:
                labeled_messages.append(
                    self._copy_with_label(
                        message,
                        original_source_id=source_id,
                        labeled_source_id=self.source_id,
                        label=self._labeler(source_id, message),
                    )
                )

        context.context_messages.clear()
        if labeled_messages:
            context.context_messages[self.source_id] = labeled_messages

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        del session_id, state, kwargs
        return []

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del session_id, messages, state, kwargs


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
            PublicSearchContext(),
            PrivateCaseContext(),
            ProviderMessageLabeler(classify_provider_message),
            SecureAgentConfig(),
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
