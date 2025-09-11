import asyncio
import os
from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisProvider

def retrieve_company_report(company_code: str, detailed: bool) -> str:
    if company_code != "CNTS":
        raise ValueError("Company code not found")
    if not detailed:
        return "CNTS is a company that specializes in technology."
    return "CNTS is a company that specializes in technology. It had a revenue of $10 million in 2022. It has 100 employees."

async def main() -> None:

    # Use sequential=True to avoid embedding model download during first test.
    redis_provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="chat_history",
        prefix="memory",
        sequential=True,  # set False to enable semantic retrieval via redisvl + HF embeddings
    )

    api_key = input("Enter your API key (leave blank to use OPENAI_API_KEY env var): ").strip() \
            or os.getenv("OPENAI_API_KEY")

    ai_model_id = input("Enter AI model ID (default: gpt-4o-mini or env OPENAI_CHAT_MODEL_ID): ").strip() \
                or os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini")

    if not api_key:
        raise ValueError("API key must be provided either interactively or via OPENAI_API_KEY env var")

    client = OpenAIChatClient(
        ai_model_id=ai_model_id,
        api_key=api_key,
    )

    async with client.create_agent(
        name="FriendlyAssistant",
        instructions="You are a friendly assistant.",
        tools=retrieve_company_report,
        context_providers=redis_provider,
    ) as agent:
        print("=== Redis Context Provider with OpenAI ===")

        query = "Please retrieve my company report"
        print(f"User: {query}")
        print("Agent:", await agent.run(query), "\n")

        query = ("I always work with CNTS and I always want a detailed report format. "
                 "Please remember and retrieve it.")
        print(f"User: {query}")
        print("Agent:", await agent.run(query), "\n")

        print("\nRequest within a new thread:")
        thread = agent.get_new_thread()
        query = "Please retrieve my company report"
        print(f"User: {query}")
        print("Agent:", await agent.run(query, thread=thread), "\n")

if __name__ == "__main__":
    asyncio.run(main())
