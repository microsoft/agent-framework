# Copyright (c) Microsoft. All rights reserved.

"""
Valkey Integration Sample — ValkeyChatMessageStore + ValkeyContextProvider

Demonstrates both Valkey-backed components against a local Valkey instance:
  1. ValkeyChatMessageStore — persistent chat history across sessions
  2. ValkeyContextProvider  — long-term memory via text search (no embeddings needed)

Prerequisites:
  - Valkey running locally (9.1+ required for full-text search):
      docker run -d --name valkey -p 6379:6379 valkey/valkey-bundle:9.1.0-rc1
  - AWS credentials configured (for Bedrock)
  - Install: uv pip install agent-framework-valkey agent-framework-bedrock python-dotenv
"""

from __future__ import annotations

import asyncio
import contextlib
import os

from agent_framework import Agent, AgentSession, tool
from agent_framework_bedrock import BedrockChatClient
from agent_framework_valkey import ValkeyChatMessageStore, ValkeyContextProvider
from dotenv import load_dotenv

load_dotenv()

VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-2")
BEDROCK_MODEL = os.getenv("BEDROCK_CHAT_MODEL", "us.anthropic.claude-opus-4-5-20251101-v1:0")


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    from datetime import datetime

    return datetime.now().isoformat()


def make_agent(
    name: str,
    instructions: str,
    context_providers: list,
) -> Agent:
    return Agent(
        client=BedrockChatClient(region=BEDROCK_REGION, model=BEDROCK_MODEL),
        name=name,
        instructions=instructions,
        context_providers=context_providers,
        tools=[get_current_time],
    )


# ---------------------------------------------------------------------------
# Part 1: Chat Message Store — persistent history
# ---------------------------------------------------------------------------
async def demo_chat_message_store() -> None:
    print("=" * 60)
    print("Part 1: ValkeyChatMessageStore — Persistent Chat History")
    print("=" * 60)

    history = ValkeyChatMessageStore(
        source_id="valkey_demo_history",
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        key_prefix="demo_chat",
        max_messages=20,
    )

    agent = make_agent(
        name="HistoryBot",
        instructions="You are a helpful assistant. Be concise.",
        context_providers=[history],
    )

    # --- Session 1: establish facts ---
    session = agent.create_session()
    session_id = session.session_id

    print(f"\n[Session {session_id[:8]}…] Starting conversation")

    for msg in [
        "Hi! My name is [insert name here] and I work on AI agent frameworks.",
        "I really enjoy cycling and live in Seattle.",
    ]:
        print(f"  User: {msg}")
        resp = await agent.run(msg, session=session)
        print(f"  Agent: {resp.text}\n")

    # Serialize session (simulates app restart)
    saved = session.to_dict()

    # --- Session 2: resume and verify recall ---
    print(f"[Session {session_id[:8]}…] Resuming after 'restart'")
    restored = AgentSession.from_dict(saved)

    msg = "What do you remember about me?"
    print(f"  User: {msg}")
    resp = await agent.run(msg, session=restored)
    print(f"  Agent: {resp.text}\n")

    # Verify data in Valkey
    from glide import GlideClient, GlideClientConfiguration, NodeAddress

    client = await GlideClient.create(
        GlideClientConfiguration(addresses=[NodeAddress(host=VALKEY_HOST, port=VALKEY_PORT)])
    )
    key = f"demo_chat:{session_id}"
    count = await client.llen(key)
    print(f"  ✓ Valkey key '{key}' has {count} messages stored")
    await client.close()

    await history.aclose()


# ---------------------------------------------------------------------------
# Part 2: Context Provider — long-term memory via text search
# ---------------------------------------------------------------------------
async def demo_context_provider() -> None:
    print("\n" + "=" * 60)
    print("Part 2: ValkeyContextProvider — Long-Term Memory (Text Search)")
    print("=" * 60)

    context_provider = ValkeyContextProvider(
        source_id="valkey_demo_memory",
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        index_name="demo_memory_idx",
        prefix="demo_mem:",
        agent_id="demo_agent",
    )

    agent = make_agent(
        name="MemoryBot",
        instructions=(
            "You are a helpful assistant with long-term memory. "
            "Use the memories provided to personalize your responses. Be concise."
        ),
        context_providers=[context_provider],
    )

    # --- Conversation 1: teach the agent some facts ---
    session1 = agent.create_session()
    print(f"\n[Conversation 1 — {session1.session_id[:8]}…] Teaching facts")

    for msg in [
        "I'm building a Valkey integration for the Microsoft Agent Framework.",
        "My favorite programming language is Python and I use Bedrock for LLMs.",
    ]:
        print(f"  User: {msg}")
        resp = await agent.run(msg, session=session1)
        print(f"  Agent: {resp.text}\n")

    # --- Conversation 2: new session, agent should recall from Valkey ---
    session2 = agent.create_session()
    print(f"[Conversation 2 — {session2.session_id[:8]}…] Testing recall")

    msg = "What do you know about my projects and preferences?"
    print(f"  User: {msg}")
    resp = await agent.run(msg, session=session2)
    print(f"  Agent: {resp.text}\n")

    # Verify data in Valkey
    from glide import GlideClient, GlideClientConfiguration, NodeAddress

    client = await GlideClient.create(
        GlideClientConfiguration(addresses=[NodeAddress(host=VALKEY_HOST, port=VALKEY_PORT)])
    )
    result = await client.custom_command(["FT.INFO", "demo_memory_idx"])  # noqa: F841
    print("  ✓ Valkey search index 'demo_memory_idx' exists")

    # Count stored documents
    scan_result = await client.scan("0", match="demo_mem:*", count=1000)
    doc_count = len(scan_result[1]) if scan_result[1] else 0
    print(f"  ✓ {doc_count} memory documents stored in Valkey")
    await client.close()

    await context_provider.aclose()


# ---------------------------------------------------------------------------
# Part 3: Both together
# ---------------------------------------------------------------------------
async def demo_combined() -> None:
    print("\n" + "=" * 60)
    print("Part 3: Combined — History + Context Provider")
    print("=" * 60)

    history = ValkeyChatMessageStore(
        source_id="valkey_combined_history",
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        key_prefix="combined_chat",
    )

    context = ValkeyContextProvider(
        source_id="valkey_combined_memory",
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        index_name="combined_mem_idx",
        prefix="combined_mem:",
        agent_id="combined_agent",
    )

    agent = make_agent(
        name="FullBot",
        instructions=(
            "You are a helpful assistant with both conversation history and long-term memory. "
            "Be concise."
        ),
        context_providers=[history, context],
    )

    session = agent.create_session()
    print(f"\n[Session {session.session_id[:8]}…]")

    for msg in [
        "I'm evaluating Valkey for our agent infrastructure.",
        "What are the key advantages of Valkey?",
    ]:
        print(f"  User: {msg}")
        resp = await agent.run(msg, session=session)
        print(f"  Agent: {resp.text}\n")

    await history.aclose()
    await context.aclose()
    print("  ✓ Both providers worked together successfully")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
async def cleanup() -> None:
    """Remove demo keys from Valkey."""
    from glide import GlideClient, GlideClientConfiguration, NodeAddress

    client = await GlideClient.create(
        GlideClientConfiguration(addresses=[NodeAddress(host=VALKEY_HOST, port=VALKEY_PORT)])
    )

    # Drop indexes
    for idx in ["demo_memory_idx", "combined_mem_idx"]:
        with contextlib.suppress(Exception):
            await client.custom_command(["FT.DROPINDEX", idx])

    # Delete keys by pattern
    for pattern in ["demo_chat:*", "demo_mem:*", "combined_chat:*", "combined_mem:*"]:
        cursor: str | bytes = "0"
        while True:
            result = await client.scan(cursor, match=pattern, count=1000)
            cursor = result[0]
            keys = result[1]
            if keys:
                str_keys = [k.decode("utf-8") if isinstance(k, bytes) else str(k) for k in keys]
                await client.delete(str_keys)
            cursor_str = cursor.decode("utf-8") if isinstance(cursor, bytes) else str(cursor)
            if cursor_str == "0":
                break

    await client.close()
    print("\n✓ Cleanup complete — demo keys removed from Valkey")


async def main() -> None:
    print("Valkey Integration Sample")
    print(f"Prerequisites: Valkey on {VALKEY_HOST}:{VALKEY_PORT}, AWS credentials configured\n")

    try:
        await demo_chat_message_store()
        await demo_context_provider()
        await demo_combined()
    finally:
        await cleanup()

    print("\n🎉 All demos completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
