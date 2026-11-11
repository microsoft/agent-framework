# Copyright (c) Microsoft. All rights reserved.

"""Classify messages from existing history, memory, and context providers.

This sample combines:

1. ``InMemoryHistoryProvider`` for conversation history.
2. ``FileMemoryProvider`` for persistent user memory.
3. ``TodoProvider`` as another message-producing context provider.

``SecureAgentConfig.message_labeler`` receives each provider's authoritative
``source_id`` and returns the complete label that FIDES should use for that
provider message.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT - Microsoft Foundry project endpoint.
    FOUNDRY_MODEL - Model deployment name, for example ``gpt-4o``.
"""

from __future__ import annotations

import asyncio
import os

from agent_framework import (
    Agent,
    FileMemoryProvider,
    InMemoryAgentFileStore,
    InMemoryHistoryProvider,
    Message,
    TodoProvider,
)
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from agent_framework.security import ConfidentialityLabel, ContentLabel, IntegrityLabel, SecureAgentConfig
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

HISTORY_SOURCE_ID = "conversation_history"
MEMORY_SOURCE_ID = "user_memory"
TODO_SOURCE_ID = "planning"

PROVIDER_LABELS = {
    HISTORY_SOURCE_ID: ContentLabel(IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PRIVATE),
    MEMORY_SOURCE_ID: ContentLabel(IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PRIVATE),
    TODO_SOURCE_ID: ContentLabel(IntegrityLabel.TRUSTED, ConfidentialityLabel.PUBLIC),
}


def classify_provider_message(source_id: str, message: Message) -> ContentLabel:
    """Return the application-owned label for one provider message."""
    label = PROVIDER_LABELS[source_id]
    preview = message.text.replace("\n", " ")[:60]
    print(f"Labeling {source_id!r} as {label.integrity.value}/{label.confidentiality.value}: {preview!r}")
    return label


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # 1. Create existing framework providers. No sample-specific provider class is needed.
    history = InMemoryHistoryProvider(source_id=HISTORY_SOURCE_ID)
    memory = FileMemoryProvider(
        InMemoryAgentFileStore(),
        source_id=MEMORY_SOURCE_ID,
        scope="sample-user",
    )
    planning = TodoProvider(source_id=TODO_SOURCE_ID)

    # 2. Configure FIDES before the providers to show that provider order does not control classification.
    security = SecureAgentConfig(
        message_labeler=classify_provider_message,
        allow_untrusted_tools={"file_memory_read", "file_memory_write"},
    )

    async with Agent[FoundryChatOptions](
        client=client,
        instructions="Use the available history, memory, and planning context to answer the user.",
        context_providers=[security, history, memory, planning],
        default_options={"store": False},
    ) as agent:
        session = agent.create_session(session_id="provider-labeling-sample")

        # 3. Seed existing history through the provider's public persistence API.
        await history.save_messages(
            session.session_id,
            [Message(role="assistant", contents=["Earlier note: the user prefers concise travel recommendations."])],
            state=session.state.setdefault(history.source_id, {}),
        )

        # 4. Ask the agent to create a file memory. Its index becomes provider context on the next turn.
        await agent.run(
            "Use file_memory_write to remember that I prefer window seats. Do not modify the todo list.",
            session=session,
        )

        # 5. On this turn the labeler sees history, the file-memory index, and the current todo-list message.
        response = await agent.run(
            "What do you remember about how I like travel recommendations?",
            session=session,
        )
        print(f"\nAgent: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

Labeling 'conversation_history' as untrusted/private: 'Earlier note: the user prefers concise travel recommendations.'
Labeling 'planning' as trusted/public: '### Current todo list...'
Labeling 'user_memory' as untrusted/private: 'The following is your memory index...'

Agent: You prefer concise travel recommendations and window seats.
"""
