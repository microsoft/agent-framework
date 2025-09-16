import asyncio

from agent_framework import ChatMessage, Role
from agent_framework_redis._provider import RedisProvider
from agent_framework.openai import OpenAIChatClient


# Simulated flight-search tool used to demonstrate tool memory
def search_flights(origin_airport_code: str, 
                destination_airport_code: str, 
                detailed: bool = False) -> str:
    """
    Simulated agentic tool masquerading as an airline search interface.
    """
    flights = {
        ("JFK", "LAX"): {"airline": "SkyJet", "duration": "6h 15m", "price": 325, "cabin": "Economy", "baggage": "1 checked bag"},
        ("SFO", "SEA"): {"airline": "Pacific Air", "duration": "2h 5m", "price": 129, "cabin": "Economy", "baggage": "Carry-on only"},
        ("LHR", "DXB"): {"airline": "EuroWings", "duration": "6h 50m", "price": 499, "cabin": "Business", "baggage": "2 bags included"},
    }

    route = (origin_airport_code.upper(), destination_airport_code.upper())
    if route not in flights:
        return f"No flights found between {origin_airport_code} and {destination_airport_code}"

    flight = flights[route]
    if not detailed:
        return f"Flights available from {origin_airport_code} to {destination_airport_code}."

    return (
        f"{flight['airline']} operates flights from {origin_airport_code} to {destination_airport_code}. "
        f"Duration: {flight['duration']}. "
        f"Price: ${flight['price']}. "
        f"Cabin: {flight['cabin']}. "
        f"Baggage policy: {flight['baggage']}."
    )


async def main() -> None:
    """Redis context provider standalone basic usage. 
    
    Initialize the provider with OpenAI vectorizer and API key.
    
    Useful Debug Commands:

    # Print index info
    print(await provider.redis_index.info())

    # Print all data stored in the index 
    print(await provider.search_all())
    """

    # Configure API keys and model IDs (replace placeholders)
    OPENAI_API_KEY = "<API KEY>"
    OPENAI_MODEL_ID = "gpt-4o-mini"

    # Create provider with partition scope and OpenAI embeddings
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics",
        overwrite_redis_index=True,
        drop_redis_index=True,
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        vectorizer_choice="openai",
        vector_field_name="vector",
        vectorizer_api_key=OPENAI_API_KEY
    )
    
    # Build sample chat messages to persist to Redis
    messages = [
        ChatMessage(role=Role.USER, text="A: User Message"),
        ChatMessage(role=Role.ASSISTANT, text="B: Assistant Message"),
        ChatMessage(role=Role.SYSTEM, text="C: System Message"),
    ]

    # Write messages to Redis under thread 'runA'
    await provider.messages_adding(thread_id="runA", new_messages=messages)

    # Retrieve context for model invocation
    ctx = await provider.model_invoking([
        ChatMessage(role=Role.SYSTEM, text="B: Assistant Message")
    ])

    # Inspect retrieved memories injected into instructions
    print(ctx)

    """Redis context provider agent usage. 
    
    Test that agent can store and retrieve context.
    """

    # Fresh provider for agent demo (recreates index)
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics",
        overwrite_redis_index=True,
        drop_redis_index=True,
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        vectorizer_choice="openai",
        vector_field_name="vector",
        vectorizer_api_key=OPENAI_API_KEY
    )

    # Create chat client for the agent
    client = OpenAIChatClient(ai_model_id=OPENAI_MODEL_ID, api_key=OPENAI_API_KEY)
    # Create agent wired to the Redis context provider
    agent = client.create_agent(
            name="MemoryEnhancedAssistant",
            instructions=(
                "You are a helpful assistant. Personalize replies using provided context. "
                "Before answering, always check for stored context"
            ),
            tools=[],
            context_providers=provider)

    # Teach a user preference; it will be persisted
    query = "Remember that I enjoy glugenflorgle"
    print(f"User to Agent: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Ask the agent to recall the stored preference
    query = "What do I enjoy?"
    print(f"User to Agent: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    """Redis context provider agent usage with tool. 
    
    Test that agent can store and retrieve context,
    including context from tool calls.
    """

    # Text-only provider (full-text search only)
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics",
        overwrite_redis_index=True,
        drop_redis_index=True,
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit"
    )

    # Create agent exposing the flight search tool
    client = OpenAIChatClient(ai_model_id=OPENAI_MODEL_ID, api_key=OPENAI_API_KEY)
    agent = client.create_agent(
            name="MemoryEnhancedAssistant",
            instructions=(
                "You are a helpful assistant. Personalize replies using provided context. "
                "Before answering, always check for stored context"
            ),
            tools=search_flights,
            context_providers=provider)
    # Invoke tool; outputs become part of context
    query = "Are there any flights from new york city (jfk) to la? Give me details"
    print(f"User to Agent: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Verify the agent can recall tool-derived context
    query = "Which flight did I ask about?"
    print(f"User to Agent: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


    """AI Derived Context Scoping demo."""
    # --- Scoping demo: static thread_id vs per-operation thread id ---
    # Static scope: uses provider.thread_id regardless of runtime thread
    provider_static = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_scope_demo",
        overwrite_redis_index=True,
        drop_redis_index=True,
        application_id="scope_demo_app",
        agent_id="scope_demo_agent",
        user_id="scope_demo_user",
        thread_id="T_STATIC",
        scope_to_per_operation_thread_id=False
    )
    await provider_static.messages_adding(
        thread_id="T_DYNAMIC_A",
        new_messages=ChatMessage(role=Role.USER, text="STATIC_SCOPE_MSG")
    )
    static_seen = await provider_static.redis_search("STATIC_SCOPE_MSG")
    print("Static-scope found:", len(static_seen))  # expect 1

    # Per-operation scope: uses the runtime-provided thread_id captured per run
    provider_dynamic = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_scope_demo",
        overwrite_redis_index=True,
        drop_redis_index=False,
        application_id="scope_demo_app",
        agent_id="scope_demo_agent",
        user_id="scope_demo_user",
        scope_to_per_operation_thread_id=True
    )
    await provider_dynamic.messages_adding(
        thread_id="T_DYNAMIC_B",
        new_messages=ChatMessage(role=Role.USER, text="PER_OP_SCOPE_MSG")
    )

    # Static provider should not see per-op message (thread filter differs)
    static_view_of_dynamic = await provider_static.redis_search("PER_OP_SCOPE_MSG")
    print("Static-scope sees per-op message:", len(static_view_of_dynamic))  # expect 0

    # Dynamic provider should see its own per-op message
    dynamic_view_of_dynamic = await provider_dynamic.redis_search("PER_OP_SCOPE_MSG")
    print("Per-op scope sees per-op message:", len(dynamic_view_of_dynamic))  # expect 1

    # Dynamic provider should not see static-thread message
    dynamic_view_of_static = await provider_dynamic.redis_search("STATIC_SCOPE_MSG")
    print("Per-op scope sees static message:", len(dynamic_view_of_static))  # expect 0

if __name__ == "__main__":
    asyncio.run(main())
