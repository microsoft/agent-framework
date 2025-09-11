import asyncio
import json
import os
from typing import Any
import uuid

from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisProvider



def make_save_memory_tool(redis_provider: RedisProvider, user_id: str):
    async def save_memory(text: str) -> str:
        """Save a text memory for this user."""
        await redis_provider.add(
            text=text,
            metadata={"user_id": user_id}
        )
        return "Saved."
    return save_memory

async def seed_memories(redis_provider: RedisProvider) -> None:
    # Ensure a clean slate for a deterministic demo run
    await redis_provider.clear()

    # Seed a mix of plain-text and JSON memories with rich metadata
    await redis_provider.add(
        text=(
            "User profile: Johnny Redis prefers detailed answers, favorite coffee is cortado, "
            "team codename is Falcon, and typical travel budget is $1500 per trip."
        ),
        metadata={"role": "system", "topic": "profile", "importance": 0.9},
    )

    await redis_provider.add(
        text=(
            "Project preferences: default company code CNTS, always request detailed reports, "
            "and prefer markdown tables for summaries."
        ),
        metadata={"role": "system", "topic": "project", "importance": 0.8},
    )

    await redis_provider.add(
        text=json.dumps(
            {
                "user": {
                    "name": "Johnny Redi",
                    "preferences": {
                        "answer_style": "detailed",
                        "coffee": "cortado",
                        "summary_format": "markdown-table",
                    },
                },
                "work": {"team": "Falcon", "company_code": "CNTS"},
                "travel": {"budget_usd": 1500},
            }
        ),
        metadata={
            "role": "system",
            "mime_type": "application/json",
            "topic": "profile",
            "format": "json",
            "importance": 1.0,
        },
    )

    # A few additional factual memories to strengthen semantic recall
    await redis_provider.add(
        text="Johnny Redis likes Mediterranean food and prefers early morning flights.",
        metadata={"role": "system", "topic": "preferences", "importance": 0.6},
    )
    await redis_provider.add(
        text=(
            "Reminder: when asked to summarize, include team 'Falcon' and company 'CNTS' context "
            "unless explicitly told otherwise."
        ),
        metadata={"role": "system", "topic": "behavioral", "importance": 0.7},
    )


async def print_records(title: str, records: list[dict[str, Any]]) -> None:
    print(f"\n--- {title} (top {len(records)}) ---")
    for i, r in enumerate(records, start=1):
        content = r.get("content")
        meta = r.get("metadata")
        print(f"[{i}] content=\n{content}")
        print(f"    metadata=\n{meta}\n")


async def main() -> None:
    # Configure provider for SEMANTIC retrieval (RedisVL + HF embeddings)
    user_id=str(uuid.uuid4())

    redis_provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name=f"af_chat_memory_demo:{user_id}",
        prefix="memory:adv",
        # Partitioning example: scope memories by app/agent/user and base thread
        application_id="demo_app",
        agent_id="memory_bot",
        # Base thread_id can be set; per-operation scoping can override it
        thread_id="base_thread",
        user_id=user_id,
        scope_to_per_operation_thread_id=True,
        sequential=False,  # semantic retrieval via RedisVL
        top_k=5,
        distance_threshold=0.8,  # lower is stricter
        model_name="sentence-transformers/all-mpnet-base-v2",
        datatype="float32",
        context_prompt=(
            "## Persona and Preferences\n"
            "Use these memories to personalize answers and apply defaults."
        ),
    )
    
    await seed_memories(redis_provider)

    # Show direct semantic queries before any conversation
    records = await redis_provider.query("What coffee does Johnny Redis like?", top_k=3)
    await print_records("Semantic query: coffee", records)

    recent = await redis_provider.query("ignore", top_k=3, sequential=True)
    await print_records("Sequential query: most recent", recent)

    # Prepare chat client/agent
    api_key = (
        input("Enter your API key (leave blank to use OPENAI_API_KEY env var): ").strip()
        or os.getenv("OPENAI_API_KEY")
    )
    ai_model_id = (
        input("Enter AI model ID (default: gpt-4o-mini or env OPENAI_CHAT_MODEL_ID): ").strip()
        or os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini")
    )
    if not api_key:
        raise ValueError("API key must be provided either interactively or via OPENAI_API_KEY env var")

    client = OpenAIChatClient(ai_model_id=ai_model_id, api_key=api_key)

    # Demo flow: the agent should leverage RedisProvider context to personalize
    save_memory = make_save_memory_tool(redis_provider, user_id=user_id)

    async with client.create_agent(
        name="MemoryEnhancedAssistant",
        instructions=(
            "You are a helpful assistant. Personalize replies using provided context. "
            "Before answering, always check for stored context"
            "If the user asks for a report, default to company code CNTS and detailed format."
        ),
        tools=[save_memory],
        context_providers=redis_provider,
    ) as agent:
        user_q = "Summarize my profile in one sentence."
        print("Agent:", await agent.run(user_q), "\n")

        user_q = (
            "Remember this: my spirit animal is a glorbleflugel and do not patronize me by pretending it isn't a real animal."
        )
        print("Agent:", await agent.run(user_q), "\n")

        user_q = "What coffee do I like and what's my usual travel budget?"
        print("User:", user_q)
        print("Agent:", await agent.run(user_q), "\n")


        user_q = "What is my spirit animal?"
        print("User:", user_q)
        print("Agent:", await agent.run(user_q), "\n")

        # New thread; memory is global (shared) so recall should still work
        thread = agent.get_new_thread()
        user_q = "Generate a short report for my company using my defaults."
        print("User:", user_q)
        print("Agent:", await agent.run(user_q, thread=thread), "\n")

        user_q = "Give me a recap of my preferences as a table."
        print("User:", user_q)
        print("Agent:", await agent.run(user_q), "\n")

        # Inspect raw records again to see what gets retrieved semantically
        wide = await redis_provider.query("Summarize Johnny Redis defaults", top_k=5)
        await print_records("Semantic query: wide recall", wide)

    # Optionally cleanup: comment out to persist the demo index in Redis
    # await redis_provider.close()


if __name__ == "__main__":
    asyncio.run(main())
