# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, AgentSession, FileMemoryProvider, FileSystemAgentFileStore
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load python/.env (python-dotenv walks up from this file by default). Pass
# override=True so values from .env take precedence over any pre-existing OS
# environment variables — without this, OS-level values silently win.
load_dotenv(override=True)

"""
Sample: give an agent file-based memory with ``FileMemoryProvider``.

This sample shows how to attach :class:`FileMemoryProvider` directly to a plain
``Agent`` via ``context_providers``, and how to control the *scope* of the
memories so they persist and can be recalled across separate sessions.

``FileMemoryProvider`` is a :class:`~agent_framework.ContextProvider` that
exposes a set of ``file_memory_*`` tools (write, read, delete, ls, grep,
replace, replace_lines) to the agent, letting the model decide what to remember
and when to recall it. Each memory is stored as an individual file in an
:class:`~agent_framework.AgentFileStore`; here we use a
:class:`~agent_framework.FileSystemAgentFileStore` so the memories are written
to real files on disk. Because the files live outside the conversation, the
agent can recall them in a later session, even after the original chat history
is gone.

Controlling scope:
    The provider isolates memories per session by default (the working folder is
    derived from the session id). Passing an explicit ``scope`` (for example a
    user id) instead groups memories under a stable working folder that every
    session for that user shares — which is what lets the second conversation
    below recall what the user said in the first.

Prerequisites:
    - ``FOUNDRY_PROJECT_ENDPOINT``: Your Microsoft Foundry project endpoint.
    - ``FOUNDRY_MODEL``: Chat model deployment name.
    - Run ``az login`` before executing the sample.
"""

# The id of the user we are storing memories for. It is used below as the
# provider's scope so that each user gets their own memory folder.
USER_ID = "UID1"


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # <create_file_memory_provider>
    # 1. Create the file store the provider will use to persist memory files.
    #    Here we use a file-system backed store rooted at a local
    #    ``agent-file-memory`` folder, but any AgentFileStore implementation can
    #    be used, e.g. InMemoryAgentFileStore or a custom blob-backed store.
    memory_root = Path(__file__).parent / "agent-file-memory"
    store = FileSystemAgentFileStore(memory_root)

    # 2. Create the FileMemoryProvider over that store.
    #    The ``scope`` determines the scope and lifetime of the memories:
    #    - A stable scope, like the per-user one below, gives durable memories
    #      shared by every session for that user. That is what allows the second
    #      conversation further down to recall what the user said in the first.
    #    - Omitting ``scope`` (the default) isolates memories to a single session
    #      (the working folder is derived from the session id).
    file_memory_provider = FileMemoryProvider(store, scope=f"users/{USER_ID}")

    # 3. Attach the provider to the agent so it gets the file_memory_* tools.
    agent = Agent(
        client=client,
        name="TravelAssistant",
        instructions=(
            "You are a helpful travel assistant. Remember what the user tells you about "
            "themselves so that you can give better recommendations later."
        ),
        context_providers=[file_memory_provider],
    )
    # </create_file_memory_provider>

    working_folder = memory_root / "users" / USER_ID
    print(f"Memory files will be written to: {working_folder}\n")

    # 4. First conversation: tell the agent something worth remembering. The
    #    agent should call file_memory_write to store it as a file in the scope.
    first_session: AgentSession = agent.create_session()
    print("=== First conversation ===")
    print(
        await agent.run(
            "I'm vegetarian and I always travel with my dog. Please remember this for future trips.",
            session=first_session,
        )
    )
    print()

    # 5. Show the memory files the agent created on disk.
    print("=== Memory files on disk ===")
    if working_folder.exists():
        for file in sorted(working_folder.iterdir()):
            if file.is_file():
                print(file.name)
    print()

    # 6. Second conversation: a brand new session with no chat history from the
    #    first. The provider injects the memory index (memories.md) into the
    #    agent's context, and the agent calls file_memory_read to recall the
    #    user's preferences with no shared chat history.
    second_session: AgentSession = agent.create_session()
    print("=== Second conversation (new session) ===")
    print(
        await agent.run(
            "Suggest a hotel and a restaurant for my trip to Paris next week.",
            session=second_session,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

Memory files will be written to: .../context_providers/agent-file-memory/users/UID1

=== First conversation ===
Got it — I'll remember that you're vegetarian and always travel with your dog. I've saved
this so I can tailor future recommendations for you.

=== Memory files on disk ===
userpreferences.md

=== Second conversation (new session) ===
Since you're vegetarian and travel with your dog, here are some dog-friendly options in Paris:
- Hotel: ... (pet-friendly, central) ...
- Restaurant: ... (excellent vegetarian menu, welcomes dogs) ...
"""
