# Copyright (c) Microsoft. All rights reserved.
"""Interactive chat demonstrating CosmosMemoryContextProvider with Agent Framework.

This sample shows:
- Real agent integration with memory persistence
- Custom memory extraction rubric/prompt injection
- Multi-turn conversations with semantic memory
- Memory retrieval across different sessions

Prerequisites:
    Install the package in development mode first:
        pip install -e .

    Then run this sample:
        python samples/interactive_chat.py
"""

import asyncio
import os
import sys
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

# Custom memory extraction rubric - defines WHAT gets remembered and HOW
CUSTOM_EXTRACTION_RUBRIC = """You are a memory extraction specialist analyzing conversation transcripts.

Your task is to identify and extract important information worth remembering long-term.

WHAT TO EXTRACT:
- User preferences and dislikes (food, hobbies, work style, communication preferences)
- Personal facts (job title, location, family, allergies, accessibility needs)
- Decisions made during conversations (chosen solutions, rejected alternatives, rationale)
- Behavioral patterns (how user likes to approach problems, learning style)
- Project context (current projects, goals, deadlines, stakeholders)
- Technical environment (tools used, tech stack, common issues)

WHAT TO IGNORE:
- Transient requests ("book a meeting for tomorrow")
- Small talk and greetings
- Tool output and system messages
- Temporary context that won't be useful later

OUTPUT FORMAT:
Return ONLY valid JSON with this exact structure:
{
  "memories": [
    {
      "type": "fact|procedural|episodic",
      "content": "A single, clear sentence capturing the memory",
      "confidence": 0.0-1.0
    }
  ]
}

MEMORY TYPES:
- fact: Declarative knowledge ("User prefers dark mode", "User is allergic to peanuts")
- procedural: Behavioral rules ("User wants confirmation before deletions", "User prefers concise answers")
- episodic: Past experiences with context ("User struggled with OAuth setup on 2024-03-15")

CONFIDENCE SCORING:
- 0.9-1.0: Explicit statements ("I prefer...", "I always...")
- 0.7-0.9: Strong implications from behavior
- 0.5-0.7: Weak signals, might need confirmation
- Below 0.5: Don't extract

EXAMPLES:

Conversation: "I really dislike verbose explanations. Just give me the code."
Output: {"memories": [{"type": "procedural", "content": "User prefers concise, code-first responses without lengthy explanations", "confidence": 0.95}]}

Conversation: "I'm working on a Python project using FastAPI and PostgreSQL."
Output: {"memories": [{"type": "fact", "content": "User is working on a Python project with FastAPI and PostgreSQL stack", "confidence": 0.9}]}

Conversation: "What's the weather today?"
Output: {"memories": []}

Return {"memories": []} if nothing worth remembering long-term.
"""


class CustomMemoryProcessor:
    """Custom processor that injects our extraction rubric into the memory pipeline.

    The Azure Cosmos DB Agent Memory Toolkit accepts a custom processor that can
    override the default extraction logic. This shows how to inject domain-specific
    extraction rules.
    """

    def __init__(self, extraction_rubric: str):
        """Initialize with custom extraction rubric.

        Args:
            extraction_rubric: System prompt for memory extraction LLM calls
        """
        self.extraction_rubric = extraction_rubric

    async def extract_memories(
        self, user_id: str, thread_id: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Extract memories from conversation using custom rubric.

        This is called by the AsyncCosmosMemoryClient after conversation turns.

        Args:
            user_id: User identifier
            thread_id: Conversation thread identifier
            messages: Recent conversation messages

        Returns:
            List of extracted memory records
        """
        # In a real implementation, this would:
        # 1. Format messages into transcript
        # 2. Call LLM with self.extraction_rubric as system prompt
        # 3. Parse and validate the JSON response
        # 4. Return structured memory records
        #
        # For this sample, we rely on the toolkit's default processor
        # but configure it via environment variables. See processor_config below.
        return []


async def create_agent_with_memory() -> tuple[Agent, CosmosMemoryContextProvider]:
    """Create an agent with Cosmos DB memory integration.

    Returns:
        Tuple of (agent, memory_provider)
    """
    # Load environment variables
    load_dotenv()

    cosmos_endpoint = os.environ.get("COSMOS_DB_ENDPOINT")
    ai_foundry_endpoint = os.environ.get("AI_FOUNDRY_ENDPOINT")
    cosmos_database = os.environ.get("COSMOS_DB_DATABASE", "ai_memory")

    # The SAME AI Foundry endpoint is used for both:
    #   1. The memory provider (embeddings + memory extraction), and
    #   2. The chat agent you talk to (via FoundryChatClient below).
    # The only extra setting is which chat deployment the agent should use.
    chat_deployment = os.environ.get("AI_FOUNDRY_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini")

    if not cosmos_endpoint or not ai_foundry_endpoint:
        print("ERROR: Missing required environment variables:")
        print("  COSMOS_DB_ENDPOINT  - Azure Cosmos DB account endpoint")
        print("  AI_FOUNDRY_ENDPOINT - Azure AI Foundry project endpoint (used by BOTH memory + chat)")
        print("\nOptional:")
        print("  COSMOS_DB_DATABASE - Database name (default: ai_memory)")
        print("  AI_FOUNDRY_CHAT_DEPLOYMENT_NAME - Chat model deployment (default: gpt-4o-mini)")
        print("  AI_FOUNDRY_EMBEDDING_DEPLOYMENT_NAME - Embedding model (default: text-embedding-3-large)")
        sys.exit(1)

    # Create credential (works with az login or managed identity)
    credential = DefaultAzureCredential()

    # Option 1: Use the toolkit's default processor with custom configuration
    # This is the simplest approach - configure extraction via environment variables
    memory_provider = CosmosMemoryContextProvider(
        cosmos_endpoint=cosmos_endpoint,
        cosmos_database=cosmos_database,
        ai_foundry_endpoint=ai_foundry_endpoint,
        credential=credential,
        top_k=5,  # Retrieve top 5 relevant memories
        min_confidence=0.7,  # Only show high-confidence memories
        memory_types=["fact", "procedural", "episodic"],
        context_prompt="## What I Remember About You\nI'll use these memories to personalize my responses:",
        # Configure the extraction processor behavior
        processor_config={
            "FACT_EXTRACTION_EVERY_N": "1",  # Extract after every conversation turn
            "DEDUP_EVERY_N": "3",  # Deduplicate every 3 extractions
            "USER_SUMMARY_EVERY_N": "5",  # Update user profile every 5 turns
            "THREAD_SUMMARY_EVERY_N": "10",  # Summarize thread every 10 turns
        },
    )

    # Option 2: Create a custom memory client with your own processor
    # Uncomment this to use a fully custom extraction rubric:
    #
    # custom_processor = CustomMemoryProcessor(CUSTOM_EXTRACTION_RUBRIC)
    # memory_client = AsyncCosmosMemoryClient(
    #     cosmos_endpoint=cosmos_endpoint,
    #     cosmos_database=cosmos_database,
    #     ai_foundry_endpoint=ai_foundry_endpoint,
    #     use_default_credential=True,
    #     processor=custom_processor,  # Inject custom extraction logic
    # )
    # memory_provider = CosmosMemoryContextProvider(
    #     memory_client=memory_client,
    #     top_k=5,
    #     min_confidence=0.7,
    # )

    # Create the agent with memory.
    #
    # FoundryChatClient talks to your Azure AI Foundry project using the SAME
    # endpoint the memory provider uses (ai_foundry_endpoint). This gives a
    # single-endpoint experience: one AI_FOUNDRY_ENDPOINT powers both the chat
    # agent and the memory pipeline. Auth is via DefaultAzureCredential
    # (az login / managed identity) - no API key required.
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=ai_foundry_endpoint,
            model=chat_deployment,
            credential=DefaultAzureCredential(),
        ),
        name="Memory Assistant",
        instructions=(
            "You are a helpful assistant with long-term memory. "
            "When you remember facts about the user, mention them naturally in conversation. "
            "If you don't remember something, just say so - don't make up information."
        ),
        context_providers=[memory_provider],
    )

    return agent, memory_provider


async def chat_loop(agent: Agent, user_id: str) -> None:
    """Run interactive chat loop.

    Args:
        agent: Agent to chat with
        user_id: User identifier for memory scoping
    """
    print("\n" + "=" * 70)
    print("  Interactive Chat with Cosmos DB Memory")
    print("=" * 70)
    print(f"\nUser ID: {user_id}")
    print("\nCommands:")
    print("  /new    - Start a new conversation thread")
    print("  /user   - Change user ID (to test cross-user isolation)")
    print("  /quit   - Exit")
    print("\nTips:")
    print("  - Tell the assistant your preferences (food, work style, etc.)")
    print("  - Start a new thread and see if it remembers you")
    print("  - Change user ID to see memory isolation")
    print("\n" + "=" * 70 + "\n")

    session = agent.create_session()
    session.state["user_id"] = user_id
    session.state["thread_id"] = f"thread-{session.session_id}"

    print(f"Started conversation thread: {session.state['thread_id']}\n")

    while True:
        try:
            # Read input in a worker thread so the asyncio event loop keeps running while we
            # wait. This lets the toolkit's background memory-extraction tasks (scheduled after
            # each stored turn) make progress between messages instead of being starved by a
            # blocking input() call.
            user_input = (await asyncio.to_thread(input, "You: ")).strip()

            if not user_input:
                continue

            if user_input == "/quit":
                print("\nGoodbye! 👋")
                break

            if user_input == "/new":
                # Start new thread but keep same user (memories carry over)
                session = agent.create_session()
                session.state["user_id"] = user_id
                session.state["thread_id"] = f"thread-{session.session_id}"
                print(f"\n[New conversation thread: {session.state['thread_id']}]")
                print("[Memories from previous conversations will still be available]\n")
                continue

            if user_input == "/user":
                new_user_id = (await asyncio.to_thread(input, "Enter new user ID: ")).strip()
                if new_user_id:
                    user_id = new_user_id
                    session = agent.create_session()
                    session.state["user_id"] = user_id
                    session.state["thread_id"] = f"thread-{session.session_id}"
                    print(f"\n[Switched to user: {user_id}]")
                    print(f"[New conversation thread: {session.state['thread_id']}]\n")
                continue

            # Send message to agent
            response = await agent.run(user_input, session=session)

            print(f"\nAssistant: {response.text}\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback

            traceback.print_exc()


async def main() -> None:
    """Main entry point."""
    try:
        agent, memory_provider = await create_agent_with_memory()

        # Use the async context manager to ensure proper cleanup
        async with memory_provider:
            # Default user ID (can be changed with /user command)
            default_user_id = "demo-user-123"

            try:
                await chat_loop(agent, default_user_id)
            finally:
                # Let any in-flight background memory extraction finish and persist before the
                # client closes (close() cancels still-pending background tasks).
                print("Finalizing memory extraction...")
                await memory_provider.flush()

    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
