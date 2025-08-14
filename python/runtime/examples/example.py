"""Example usage of the Python Agent Runtime"""

import asyncio
import logging
import os
import sys

# Add parent directory to path so we can import agent_runtime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.tests.mock_agents import EchoAgent, MockAIAgent

from agent_runtime.agent_actor import ActorId, AgentActor
from agent_runtime.runtime import InProcessActorClient, InProcessActorRuntime

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Demonstrate the agent runtime"""
    print("🚀 Starting Python Agent Runtime Demo")

    # Create the runtime
    runtime = InProcessActorRuntime()
    client = InProcessActorClient(runtime)

    # Register actor types
    runtime.register_actor_type("echo", lambda actor_id: AgentActor(EchoAgent()))
    runtime.register_actor_type("mock", lambda actor_id: AgentActor(MockAIAgent()))

    # Start the runtime
    await runtime.start()

    try:
        # Example 1: Simple echo agent
        print("\n📝 Testing Echo Agent:")
        echo_actor_id = ActorId("echo", "conversation-1")

        response_handle = await client.send_request(
            echo_actor_id, "run", {"messages": [{"role": "user", "content": "Hello, echo agent!"}]}
        )

        response = await response_handle.get_response()
        print(f"✅ Response: {response.data}")

        # Example 2: Mock AI agent with conversation
        print("\n🤖 Testing Mock AI Agent:")
        ai_actor_id = ActorId("mock", "conversation-2")

        conversation_messages = [
            "Hello! What can you do?",
            "Tell me about the weather",
            "What's 2 + 2?",
            "Thank you for your help!",
        ]

        for msg in conversation_messages:
            print(f"👤 User: {msg}")

            response_handle = await client.send_request(
                ai_actor_id, "run", {"messages": [{"role": "user", "content": msg}]}
            )

            response = await response_handle.get_response()

            if response.data and "messages" in response.data:
                for response_msg in response.data["messages"]:
                    print(f"🤖 Agent: {response_msg['content']}")

            # Small delay between messages
            await asyncio.sleep(0.5)

        # Example 3: Multiple concurrent conversations
        print("\n🔄 Testing Concurrent Conversations:")

        tasks = []
        for i in range(3):
            actor_id = ActorId("mock", f"concurrent-{i}")
            task = asyncio.create_task(send_test_message(client, actor_id, f"Hello from conversation {i}"))
            tasks.append(task)

        # Wait for all concurrent requests
        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            print(f"✅ Conversation {i}: {result}")

        # Example 4: State persistence test
        print("\n💾 Testing State Persistence:")

        persistent_actor_id = ActorId("echo", "persistent-conversation")

        # Send first message
        await send_test_message(client, persistent_actor_id, "First message")

        # Send second message - should remember conversation
        await send_test_message(client, persistent_actor_id, "Second message")

        print("✅ State persistence test completed")

    finally:
        # Stop the runtime
        await runtime.stop()
        print("🏁 Runtime stopped")


async def send_test_message(client, actor_id, message_content):
    """Helper function to send a test message"""
    response_handle = await client.send_request(
        actor_id, "run", {"messages": [{"role": "user", "content": message_content}]}
    )

    response = await response_handle.get_response()

    if response.data and "messages" in response.data:
        return response.data["messages"][0]["content"]
    return "No response"


if __name__ == "__main__":
    asyncio.run(main())
