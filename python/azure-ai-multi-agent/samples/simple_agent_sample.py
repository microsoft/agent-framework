# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
import logging
import argparse

from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.common import ChatMessage, ChatRole

async def main(args):
    """
    Main function to demonstrate the SimpleAgent.
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("simple_agent_sample")
    
    # Create the agent
    agent = SimpleAgent(
        response_text=args.response,
        name=args.name,
        description="A simple demonstration agent",
        instructions="Respond with a fixed message to any user message",
        logger=logger
    )
    
    # Create a thread
    thread = agent.get_new_thread()
    
    while True:
        # Get user input
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
            
        # Create a message
        message = ChatMessage(ChatRole.USER, user_input)
        
        # Run the agent in streaming mode if requested, otherwise run normally
        if args.streaming:
            print(f"{agent.name or 'Agent'}: ", end="", flush=True)
            async for update in agent.run_streaming_async_with_messages([message], thread):
                # For streaming, just print the latest character
                latest_content = update.message.content
                if len(latest_content) > 0:
                    print(latest_content[-1], end="", flush=True)
            print()  # Add a newline at the end
        else:
            # Run the agent
            response = await agent.run_async_with_messages([message], thread)
            
            # Print the response
            print(f"{agent.name or 'Agent'}: {response.messages[0].content}")
        
        # Print thread history if debug is enabled
        if args.debug:
            print("\nThread history:")
            for i, msg in enumerate(thread.messages):
                speaker = msg.author_name or ("You" if msg.role == ChatRole.USER else "Agent")
                print(f"{i+1}. {speaker}: {msg.content}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple Agent Demo")
    parser.add_argument("--response", type=str, default="I am a simple agent that responds with this message to any input.", 
                        help="The response message the agent will use")
    parser.add_argument("--name", type=str, default="SimpleAgent", help="Name for the agent")
    parser.add_argument("--streaming", action="store_true", help="Use streaming mode for responses")
    parser.add_argument("--debug", action="store_true", help="Show debug information including thread history")
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
