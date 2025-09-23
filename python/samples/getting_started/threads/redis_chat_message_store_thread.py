# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from uuid import uuid4

from agent_framework import AgentThread
from agent_framework._threads import deserialize_thread_state
from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisChatMessageStore


async def example_basic_redis_store() -> None:
    """Basic example of using Redis chat message store."""
    print("=== Basic Redis Chat Message Store Example ===")
    
    # Create Redis store with auto-generated thread ID
    redis_store = RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        # thread_id will be auto-generated if not provided
    )
    
    print(f"Created store with thread ID: {redis_store.thread_id}")
    
    # Create thread with Redis store
    thread = AgentThread(message_store=redis_store)
    
    # Create agent
    agent = OpenAIChatClient().create_agent(
        name="RedisBot",
        instructions="You are a helpful assistant that remembers our conversation using Redis.",
    )
    
    # Have a conversation
    print("\n--- Starting conversation ---")
    query1 = "Hello! My name is Alice and I love pizza."
    print(f"User: {query1}")
    response1 = await agent.run(query1, thread=thread)
    print(f"Agent: {response1.text}")
    
    query2 = "What do you remember about me?"
    print(f"User: {query2}")
    response2 = await agent.run(query2, thread=thread)
    print(f"Agent: {response2.text}")
    
    # Show messages are stored in Redis
    messages = await redis_store.list_messages()
    print(f"\nTotal messages in Redis: {len(messages)}")
    
    # Cleanup
    await redis_store.clear()
    await redis_store.aclose()
    print("Cleaned up Redis data\n")


async def example_user_session_management() -> None:
    """Example of managing user sessions with Redis."""
    print("=== User Session Management Example ===")
    
    user_id = "alice_123"
    session_id = f"session_{uuid4()}"
    
    # Create Redis store for specific user session
    def create_user_session_store():
        return RedisChatMessageStore(
            redis_url="redis://localhost:6379",
            thread_id=f"user_{user_id}_{session_id}",
            max_messages=10  # Keep only last 10 messages
        )
    
    # Create agent with factory pattern
    agent = OpenAIChatClient().create_agent(
        name="SessionBot",
        instructions="You are a helpful assistant. Keep track of user preferences.",
        chat_message_store_factory=create_user_session_store,
    )
    
    # Start conversation
    thread = agent.get_new_thread()
    
    print(f"Started session for user {user_id}")
    if hasattr(thread.message_store, 'thread_id'):
        print(f"Thread ID: {thread.message_store.thread_id}")  # type: ignore[union-attr]
    
    # Simulate conversation
    queries = [
        "Hi, I'm Alice and I prefer vegetarian food.",
        "What restaurants would you recommend?",
        "I also love Italian cuisine.",
        "Can you remember my food preferences?"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n--- Message {i} ---")
        print(f"User: {query}")
        response = await agent.run(query, thread=thread)
        print(f"Agent: {response.text}")
    
    # Show persistent storage
    if thread.message_store:
        messages = await thread.message_store.list_messages()  # type: ignore[union-attr]
        print(f"\nMessages stored for user {user_id}: {len(messages)}")
    
    # Cleanup
    if thread.message_store:
        await thread.message_store.clear()  # type: ignore[union-attr]
        await thread.message_store.aclose()  # type: ignore[union-attr]
    print("Cleaned up session data\n")


async def example_conversation_persistence() -> None:
    """Example of conversation persistence across application restarts."""
    print("=== Conversation Persistence Example ===")
    
    conversation_id = "persistent_chat_001"
    
    # Phase 1: Start conversation
    print("--- Phase 1: Starting conversation ---")
    store1 = RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        thread_id=conversation_id,
    )
    
    thread1 = AgentThread(message_store=store1)
    agent = OpenAIChatClient().create_agent(
        name="PersistentBot",
        instructions="You are a helpful assistant. Remember our conversation history.",
    )
    
    # Start conversation
    query1 = "Hello! I'm working on a Python project about machine learning."
    print(f"User: {query1}")
    response1 = await agent.run(query1, thread=thread1)
    print(f"Agent: {response1.text}")
    
    query2 = "I'm specifically interested in neural networks."
    print(f"User: {query2}")
    response2 = await agent.run(query2, thread=thread1)
    print(f"Agent: {response2.text}")
    
    print(f"Stored {len(await store1.list_messages())} messages in Redis")
    await store1.aclose()
    
    # Phase 2: Resume conversation (simulating app restart)
    print("\n--- Phase 2: Resuming conversation (after 'restart') ---")
    store2 = RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        thread_id=conversation_id,  # Same thread ID
    )
    
    thread2 = AgentThread(message_store=store2)
    
    # Continue conversation - agent should remember context
    query3 = "What was I working on before?"
    print(f"User: {query3}")
    response3 = await agent.run(query3, thread=thread2)
    print(f"Agent: {response3.text}")
    
    query4 = "Can you suggest some Python libraries for neural networks?"
    print(f"User: {query4}")
    response4 = await agent.run(query4, thread=thread2)
    print(f"Agent: {response4.text}")
    
    print(f"Total messages after resuming: {len(await store2.list_messages())}")
    
    # Cleanup
    await store2.clear()
    await store2.aclose()
    print("Cleaned up persistent data\n")


async def example_thread_serialization() -> None:
    """Example of thread state serialization and deserialization."""
    print("=== Thread Serialization Example ===")
    
    # Create initial thread with Redis store
    original_store = RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        thread_id="serialization_test",
        max_messages=50,
    )
    
    original_thread = AgentThread(message_store=original_store)
    
    agent = OpenAIChatClient().create_agent(
        name="SerializationBot",
        instructions="You are a helpful assistant.",
    )
    
    # Have initial conversation
    print("--- Initial conversation ---")
    query1 = "Hello! I'm testing serialization."
    print(f"User: {query1}")
    response1 = await agent.run(query1, thread=original_thread)
    print(f"Agent: {response1.text}")
    
    # Serialize thread state
    serialized_thread = await original_thread.serialize()
    print(f"\nSerialized thread state: {serialized_thread}")
    
    # Close original connection
    await original_store.aclose()
    
    # Deserialize thread state (simulating loading from database/file)
    print("\n--- Deserializing thread state ---")
    
    # Create a new thread with the same Redis store type
    # This ensures the correct store type is used for deserialization
    restored_store = RedisChatMessageStore(redis_url="redis://localhost:6379")
    restored_thread = AgentThread(message_store=restored_store)
    
    # Deserialize the thread state into the properly typed thread
    await deserialize_thread_state(restored_thread, serialized_thread)
    
    # Continue conversation with restored thread
    query2 = "Do you remember what I said about testing?"
    print(f"User: {query2}")
    response2 = await agent.run(query2, thread=restored_thread)
    print(f"Agent: {response2.text}")
    
    # Cleanup
    if restored_thread.message_store:
        await restored_thread.message_store.clear()  # type: ignore[union-attr]
        await restored_thread.message_store.aclose()  # type: ignore[union-attr]
    print("Cleaned up serialization test data\n")


async def example_message_limits() -> None:
    """Example of automatic message trimming with limits."""
    print("=== Message Limits Example ===")
    
    # Create store with small message limit
    store = RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        thread_id="limits_test",
        max_messages=3,  # Keep only 3 most recent messages
    )
    
    thread = AgentThread(message_store=store)
    agent = OpenAIChatClient().create_agent(
        name="LimitBot",
        instructions="You are a helpful assistant with limited memory.",
    )
    
    # Send multiple messages to test trimming
    messages = [
        "Message 1: Hello!",
        "Message 2: How are you?",
        "Message 3: What's the weather?",
        "Message 4: Tell me a joke.",
        "Message 5: This should trigger trimming.",
    ]
    
    for i, query in enumerate(messages, 1):
        print(f"\n--- Sending message {i} ---")
        print(f"User: {query}")
        response = await agent.run(query, thread=thread)
        print(f"Agent: {response.text}")
        
        stored_messages = await store.list_messages()
        print(f"Messages in store: {len(stored_messages)}")
        if len(stored_messages) > 0:
            print(f"Oldest message: {stored_messages[0].text[:30]}...")
    
    # Final check
    final_messages = await store.list_messages()
    print(f"\nFinal message count: {len(final_messages)} (should be <= 6: 3 messages × 2 per exchange)")
    
    # Cleanup
    await store.clear()
    await store.aclose()
    print("Cleaned up limits test data\n")


async def main() -> None:
    """Run all Redis chat message store examples."""
    print("Redis Chat Message Store Examples")
    print("=" * 50)
    print("Prerequisites:")
    print("- Redis server running on localhost:6379")
    print("- OPENAI_API_KEY environment variable set")
    print("=" * 50)
    
    # Check prerequisites
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        return
    
    try:
        # Test Redis connection
        test_store = RedisChatMessageStore(redis_url="redis://localhost:6379")
        connection_ok = await test_store.ping()
        await test_store.aclose()
        if not connection_ok:
            raise Exception("Redis ping failed")
        print("✓ Redis connection successful\n")
    except Exception as e:
        print(f"ERROR: Cannot connect to Redis: {e}")
        print("Please ensure Redis is running on localhost:6379")
        return
    
    try:
        # Run all examples
        await example_basic_redis_store()
        await example_user_session_management()
        await example_conversation_persistence()
        await example_thread_serialization()
        await example_message_limits()
        
        print("All examples completed successfully!")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
