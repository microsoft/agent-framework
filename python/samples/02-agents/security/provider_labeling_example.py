# Copyright (c) Microsoft. All rights reserved.

"""Label messages from ordinary history and context providers before FIDES consumes them.

This sample shows two small opt-in adapters:

- ``LabeledHistoryProvider`` wraps a standard ``HistoryProvider`` that uses the
  base get/save lifecycle.
- ``LabeledContextProvider`` wraps a simple ``ContextProvider`` that adds
  messages from its own ``source_id`` during ``before_run``.

The adapters do not make arbitrary provider behavior FIDES-aware. Providers
that rewrite history, use additional lifecycle hooks, merge sessions, or own
service-side continuation should implement their FIDES labeling at the source.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT - Microsoft Foundry project endpoint.
    FOUNDRY_MODEL - Model deployment name, for example ``gpt-4o``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from typing import Any

from agent_framework import Agent, AgentSession, ContextProvider, HistoryProvider, Message, SessionContext
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import ConfidentialityLabel, ContentLabel, IntegrityLabel, SecureAgentConfig
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

MessageLabeler = Callable[[Message], ContentLabel]


def labeled_copy(message: Message, labeler: MessageLabeler) -> Message:
    """Copy one message and attach an application-owned restriction label."""
    labeled = Message.from_dict(message.to_dict())
    labeled.additional_properties = dict(labeled.additional_properties)
    labeled.additional_properties["security_label"] = labeler(message).to_dict()
    return labeled


class LabeledHistoryProvider(HistoryProvider):
    """Add labels when loading messages from a standard history provider."""

    def __init__(self, inner: HistoryProvider, labeler: MessageLabeler) -> None:
        super().__init__(
            source_id=inner.source_id,
            load_messages=inner.load_messages,
            store_inputs=inner.store_inputs,
            store_context_messages=inner.store_context_messages,
            store_context_from=set(inner.store_context_from) if inner.store_context_from is not None else None,
            store_outputs=inner.store_outputs,
        )
        self._inner = inner
        self._labeler = labeler

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        messages = await self._inner.get_messages(session_id, state=state, **kwargs)
        return [labeled_copy(message, self._labeler) for message in messages]

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        await self._inner.save_messages(session_id, messages, state=state, **kwargs)


class LabeledContextProvider(HistoryProvider):
    """Adapt a simple message-producing ContextProvider into FIDES replay classification."""

    def __init__(self, inner: ContextProvider, labeler: MessageLabeler) -> None:
        super().__init__(
            source_id=inner.source_id,
            store_inputs=False,
            store_outputs=False,
        )
        self._inner = inner
        self._labeler = labeler

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        existing_count = len(context.context_messages.get(self.source_id, ()))
        await self._inner.before_run(
            agent=agent,
            session=session,
            context=context,
            state=state,
        )
        source_messages = context.context_messages.get(self.source_id, [])
        source_messages[existing_count:] = [
            labeled_copy(message, self._labeler) for message in source_messages[existing_count:]
        ]

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        await self._inner.after_run(
            agent=agent,
            session=session,
            context=context,
            state=state,
        )

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


class ImportedHistoryProvider(HistoryProvider):
    """Read-only history imported from a system that does not emit FIDES labels."""

    def __init__(self) -> None:
        super().__init__(
            source_id="imported_history",
            store_inputs=False,
            store_outputs=False,
        )

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        del session_id, state, kwargs
        return [Message(role="assistant", contents=["Imported support transcript: customer account is private."])]

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del session_id, messages, state, kwargs


class ExternalNotesProvider(ContextProvider):
    """Add one note retrieved from an external system."""

    def __init__(self) -> None:
        super().__init__("external_notes")

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
            [Message(role="assistant", contents=["External note: do not disclose the internal case identifier."])],
        )


def external_private_label(_: Message) -> ContentLabel:
    """Restrict imported provider data according to the host application's policy."""
    return ContentLabel(
        integrity=IntegrityLabel.UNTRUSTED,
        confidentiality=ConfidentialityLabel.PRIVATE,
    )


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )
    security = SecureAgentConfig()

    async with Agent(
        client=client,
        instructions="Summarize available background context without exposing private details.",
        context_providers=[
            LabeledHistoryProvider(ImportedHistoryProvider(), external_private_label),
            LabeledContextProvider(ExternalNotesProvider(), external_private_label),
            security,
        ],
    ) as agent:
        response = await agent.run("What background information is available?", session=AgentSession())
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
The available background information is private and came from external sources,
so I will not repeat the sensitive account or case details.
"""
