"""Debug test to isolate the hanging issue"""

import asyncio
import logging
from agent_runtime.runtime import InProcessActorRuntime, InProcessActorClient
from agent_runtime.runtime_abstractions import (
    ActorId, ActorRequestMessage, ActorResponseMessage, 
    ActorMessageType, RequestStatus, IActor
)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

class SimpleActor(IActor):
    """Simple actor for debugging"""
    
    def __init__(self, context):
        self.context = context
        print(f"SimpleActor created for {context.actor_id}")
    
    async def run(self, context):
        print(f"SimpleActor.run() started for {context.actor_id}")
        try:
            message_count = 0
            async for message in context.watch_messages():
                message_count += 1
                print(f"SimpleActor received message #{message_count}: {message}")
                
                if isinstance(message, ActorRequestMessage):
                    print(f"Processing request: {message.method}")
                    response = ActorResponseMessage(
                        message_id=message.message_id,
                        message_type=ActorMessageType.RESPONSE,
                        sender_id=context.actor_id,
                        status=RequestStatus.COMPLETED,
                        data={"result": f"processed {message.method}"}
                    )
                    print(f"Sending response: {response}")
                    context.complete_request(message.message_id, response)
                    print(f"Response sent for {message.message_id}")
                    
                if message_count >= 1:  # Exit after processing one message
                    print("Exiting actor loop")
                    break
        except Exception as e:
            print(f"Error in actor.run(): {e}")
            raise
        print(f"SimpleActor.run() finished for {context.actor_id}")


async def test_simple_actor():
    print("=== Starting debug test ===")
    
    # Create runtime
    runtime = InProcessActorRuntime()
    runtime.register_actor_type("simple", lambda context: SimpleActor(context))
    await runtime.start()
    print("Runtime started")
    
    try:
        # Create client
        client = InProcessActorClient(runtime)
        print("Client created")
        
        # Create actor
        actor_id = ActorId(type_name="simple", instance_id="test1")
        print(f"Sending request to {actor_id}")
        
        # Send request
        response_handle = await client.send_request(
            actor_id=actor_id,
            method="test",
            params={"data": "hello"}
        )
        print("Request sent, waiting for response...")
        
        # Get response with timeout
        try:
            response = await asyncio.wait_for(response_handle.get_response(), timeout=5.0)
            print(f"Got response: {response}")
        except asyncio.TimeoutError:
            print("TIMEOUT: No response received within 5 seconds")
            return
            
    finally:
        print("Stopping runtime...")
        await runtime.stop()
        print("Runtime stopped")
    
    print("=== Debug test completed ===")


if __name__ == "__main__":
    asyncio.run(test_simple_actor())
