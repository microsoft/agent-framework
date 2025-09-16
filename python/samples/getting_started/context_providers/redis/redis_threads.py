import asyncio
import os
import uuid

from agent_framework_redis._provider import RedisProvider
from agent_framework.openai import OpenAIChatClient


OPENAI_API_KEY = "<API KEY>"
OPENAI_MODEL_ID = "gpt-4o-mini"

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
os.environ["OPENAI_CHAT_MODEL_ID"] = OPENAI_MODEL_ID

async def example_global_thread_scope() -> None:
    """Example 1: Global thread_id scope (memories shared across all operations)."""
    print("1. Global Thread Scope Example:")
    print("-" * 40)

    global_thread_id = str(uuid.uuid4())

    client = OpenAIChatClient(
        ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    provider = RedisProvider(
                    redis_url="redis://localhost:6379",
                    index_name="redis_threads_global",
                    overwrite_redis_index=True,
                    drop_redis_index=True,
                    application_id="threads_demo_app",
                    agent_id="threads_demo_agent",
                    user_id="threads_demo_user",
                    thread_id=global_thread_id,
                    scope_to_per_operation_thread_id=False,  # Share memories across all threads
                )

    agent = client.create_agent(
        name="GlobalMemoryAssistant",
        instructions=(
            "You are a helpful assistant. Personalize replies using provided context. "
            "Before answering, always check for stored context containing information"
        ),
        tools=[],
        context_providers=provider)

    # Store a preference in the global scope
    query = "Remember that I prefer technical responses with code examples when discussing programming."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Create a new thread - memories should still be accessible due to global scope
    new_thread = agent.get_new_thread()
    query = "What technical responses do I prefer?"
    print(f"User (new thread): {query}")
    result = await agent.run(query, thread=new_thread)
    print(f"Agent: {result}\n")


async def example_per_operation_thread_scope() -> None:
    """Example 2: Per-operation thread scope (memories isolated per thread).

    Note: When scope_to_per_operation_thread_id=True, the provider is bound to a single thread
    throughout its lifetime. Use the same thread object for all operations with that provider.
    """
    print("2. Per-Operation Thread Scope Example:")
    print("-" * 40)

    client = OpenAIChatClient(
        ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    agent = client.create_agent(
        name="ScopedMemoryAssistant",
        instructions="You are an assistant with thread-scoped memory.",
        context_providers=RedisProvider(
            redis_url="redis://localhost:6379",
            index_name="redis_threads_dynamic",
            overwrite_redis_index=True,
            drop_redis_index=True,
            application_id="threads_demo_app",
            agent_id="threads_demo_agent",
            user_id="threads_demo_user",
            scope_to_per_operation_thread_id=True,  # Isolate memories per thread
        ),
    )

    # Create a specific thread for this scoped provider
    dedicated_thread = agent.get_new_thread()

    # Store some information in the dedicated thread
    query = "Remember that for this conversation, I'm working on a Python project about data analysis."
    print(f"User (dedicated thread): {query}")
    result = await agent.run(query, thread=dedicated_thread)
    print(f"Agent: {result}\n")

    # Test memory retrieval in the same dedicated thread
    query = "What project am I working on?"
    print(f"User (same dedicated thread): {query}")
    result = await agent.run(query, thread=dedicated_thread)
    print(f"Agent: {result}\n")

    # Store more information in the same thread
    query = "Also remember that I prefer using pandas and matplotlib for this project."
    print(f"User (same dedicated thread): {query}")
    result = await agent.run(query, thread=dedicated_thread)
    print(f"Agent: {result}\n")

    # Test comprehensive memory retrieval
    query = "What do you know about my current project and preferences?"
    print(f"User (same dedicated thread): {query}")
    result = await agent.run(query, thread=dedicated_thread)
    print(f"Agent: {result}\n")


async def example_multiple_agents() -> None:
    """Example 3: Multiple agents with different thread configurations (isolated via agent_id)."""
    print("3. Multiple Agents with Different Thread Configurations:")
    print("-" * 40)

    client = OpenAIChatClient(
        ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    personal_agent = client.create_agent(
        name="PersonalAssistant",
        instructions="You are a personal assistant that helps with personal tasks.",
        context_providers=RedisProvider(
            redis_url="redis://localhost:6379",
            index_name="redis_threads_agents",
            overwrite_redis_index=True,
            drop_redis_index=True,
            application_id="threads_demo_app",
            agent_id="agent_personal",
            user_id="threads_demo_user",
        ),
    )
    work_agent = client.create_agent(
        name="WorkAssistant",
        instructions="You are a work assistant that helps with professional tasks.",
        context_providers=RedisProvider(
            redis_url="redis://localhost:6379",
            index_name="redis_threads_agents",
            overwrite_redis_index=True,
            drop_redis_index=False,
            application_id="threads_demo_app",
            agent_id="agent_work",
            user_id="threads_demo_user",
        ),
    )

    # Store personal information
    query = "Remember that I like to exercise at 6 AM and prefer outdoor activities."
    print(f"User to Personal Agent: {query}")
    result = await personal_agent.run(query)
    print(f"Personal Agent: {result}\n")

    # Store work information
    query = "Remember that I have team meetings every Tuesday at 2 PM."
    print(f"User to Work Agent: {query}")
    result = await work_agent.run(query)
    print(f"Work Agent: {result}\n")

    # Test memory isolation
    query = "What do you know about my schedule?"
    print(f"User to Personal Agent: {query}")
    result = await personal_agent.run(query)
    print(f"Personal Agent: {result}\n")

    print(f"User to Work Agent: {query}")
    result = await work_agent.run(query)
    print(f"Work Agent: {result}\n")


async def main() -> None:
    print("=== Redis Thread Scoping Examples ===\n")
    await example_global_thread_scope()
    await example_per_operation_thread_scope()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
