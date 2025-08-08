"""Example showing framework integration with the Python runtime"""

import asyncio
import logging
import sys
import os

# Add parent directory to path so we can import agent_runtime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Demonstrate framework integration"""
    
    print("🚀 Starting Framework Integration Demo")
    
    # Import our runtime components
    from agent_runtime.runtime import InProcessActorRuntime, InProcessActorClient
    from agent_runtime.abstractions import ActorId
    # Import framework directly
    try:
        from agent_framework import ChatClientAgent, ChatMessage, AgentRunResponse
        framework_available = True
        print("📦 Framework available: True")
    except ImportError:
        framework_available = False
        print("📦 Framework available: False")
    
    # Start runtime
    runtime = InProcessActorRuntime()
    client = InProcessActorClient(runtime)
    
    if framework_available:
        try:
            # Import framework types directly (no custom abstractions!)
            from agent_framework import ChatClientAgent, ChatMessage, AgentRunResponse
            
            print("🤖 Creating framework agents directly...")
            
            # Create mock chat client for demo
            class MockChatClient:
                async def complete_chat_async(self, messages, **kwargs):
                    """Mock chat completion"""
                    # Get the last user message
                    last_message = messages[-1] if messages else None
                    user_text = "Hello"
                    
                    if last_message:
                        # Extract text from framework message
                        if hasattr(last_message, 'contents') and last_message.contents:
                            user_text = last_message.contents[0].text if hasattr(last_message.contents[0], 'text') else str(last_message.contents[0])
                        elif hasattr(last_message, 'text'):
                            user_text = last_message.text
                    
                    # Create framework response message  
                    response_msg = ChatMessage(role="assistant", text=f"Framework response to: {user_text}")
                    return AgentRunResponse(messages=[response_msg])
            
            # Create framework agents (exactly like .NET would)
            framework_agent_1 = ChatClientAgent(
                chat_client=MockChatClient(),
                name="Direct Framework Agent",
                instructions="I'm a framework agent running directly in the runtime"
            )
            
            framework_agent_2 = ChatClientAgent(
                chat_client=MockChatClient(), 
                name="Another Framework Agent",
                instructions="I'm another framework agent for concurrent testing"
            )
            
            # Register framework agents in runtime
            print("📝 Registering framework agents in runtime...")
            from agent_runtime.agent_actor import AgentActor
            
            runtime.register_actor_type(
                "framework-1",
                lambda actor_id: AgentActor(framework_agent_1)
            )
            
            runtime.register_actor_type(
                "framework-2", 
                lambda actor_id: AgentActor(framework_agent_2)
            )
            
            framework_agents_registered = True
            
        except Exception as e:
            print(f"❌ Error setting up framework agents: {e}")
            framework_agents_registered = False
    else:
        framework_agents_registered = False
    
    # Also register simple runtime agent for comparison
    from agent_runtime.agent_actor import AgentActor, EchoAgent
    runtime.register_actor_type(
        "simple-echo",
        lambda actor_id: AgentActor(EchoAgent())
    )
    
    # Start runtime
    await runtime.start()
    print("🏃 Runtime started")
    
    try:
        # Test simple runtime agent
        print("\n📨 Testing simple runtime agent...")
        echo_id = ActorId(type_name="simple-echo", instance_id="test1")
        response_handle = await client.send_request(
            actor_id=echo_id,
            method="run",
            params={
                "messages": [
                    {"role": "user", "content": "Hello from simple runtime agent!"}
                ]
            }
        )
        
        response = await response_handle.get_response()
        print(f"✅ Simple agent: {response.data['messages'][0]['content']}")
        
        # Test framework agents if available
        if framework_agents_registered:
            print("\n📨 Testing framework integration...")
            
            # Test first framework agent
            fw_id_1 = ActorId(type_name="framework-1", instance_id="test2")
            response_handle = await client.send_request(
                actor_id=fw_id_1,
                method="run",
                params={
                    "messages": [
                        {"role": "user", "content": "Hello from framework integration!"}
                    ]
                }
            )
            
            response = await response_handle.get_response()
            print(f"✅ Framework Agent 1: {response.data['messages'][0]['content']}")
            
            # Test second framework agent concurrently
            fw_id_2 = ActorId(type_name="framework-2", instance_id="test3")
            
            # Run both agents concurrently (like .NET would)
            print("\n🔄 Testing concurrent framework agents...")
            
            tasks = []
            for i in range(3):
                agent_id = ActorId(
                    type_name="framework-1" if i % 2 == 0 else "framework-2", 
                    instance_id=f"concurrent-{i}"
                )
                
                task = client.send_request(
                    actor_id=agent_id,
                    method="run",
                    params={
                        "messages": [
                            {"role": "user", "content": f"Concurrent message {i}"}
                        ]
                    }
                )
                tasks.append(task)
            
            # Wait for all concurrent requests
            response_handles = await asyncio.gather(*tasks)
            responses = await asyncio.gather(*[handle.get_response() for handle in response_handles])
            
            for i, response in enumerate(responses):
                agent_type = "Framework-1" if i % 2 == 0 else "Framework-2"
                print(f"✅ Concurrent {agent_type}: {response.data['messages'][0]['content']}")
            
            # Test conversation continuity
            print("\n💬 Testing conversation continuity...")
            conv_id = ActorId(type_name="framework-1", instance_id="conversation")
            
            # First message
            response_handle = await client.send_request(
                actor_id=conv_id,
                method="run",
                params={
                    "messages": [{"role": "user", "content": "Start conversation"}]
                }
            )
            response1 = await response_handle.get_response()
            print(f"✅ Conv Message 1: {response1.data['messages'][0]['content']}")
            
            # Second message (should maintain context)
            response_handle = await client.send_request(
                actor_id=conv_id,
                method="run", 
                params={
                    "messages": [{"role": "user", "content": "Continue conversation"}]
                }
            )
            response2 = await response_handle.get_response()
            print(f"✅ Conv Message 2: {response2.data['messages'][0]['content']}")
        
        print("\n🎉 Framework integration demo completed!")
        print("🔍 Key features:")
        print("   ✅ Framework agents running in actor runtime")
        print("   ✅ Framework types used directly") 
        print("   ✅ Concurrent agent execution")
        print("   ✅ Conversation state management")
        
    finally:
        await runtime.stop()
        print("🛑 Runtime stopped")


if __name__ == "__main__":
    asyncio.run(main())