# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
import logging
import argparse

from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.abstract_agent import MemoryAgentThread, Agent
from azure.ai.agent.common import ChatMessage, ChatRole

class MultiAgentOrchestrator:
    """
    A simple orchestrator for demonstrating how to use multiple agents with a shared thread.
    """
    
    def __init__(self, agents_dict, logger=None):
        """
        Initialize a new instance of the MultiAgentOrchestrator class.
        
        Args:
            agents_dict (dict): A dictionary of agent names to agent instances.
            logger: Optional logger to use for logging.
        """
        self.agents = agents_dict
        self.thread = MemoryAgentThread()
        self.logger = logger or logging.getLogger(__name__)
        
        # Add a system message to set the context
        system_message = ChatMessage(
            ChatRole.SYSTEM,
            "This is a conversation with multiple specialized agents. " +
            "Each agent serves a different purpose and responds differently to your messages."
        )
        self.thread.add_message(system_message)
        
    def get_available_agents(self):
        """
        Get the names of available agents.
        
        Returns:
            list: A list of agent names.
        """
        return list(self.agents.keys())
    
    async def process_message(self, message, agent_name=None, streaming=False):
        """
        Process a message using a specific agent or all agents.
        
        Args:
            message (str): The message to process.
            agent_name (str, optional): The name of the agent to use, if None, all agents will respond.
            streaming (bool): Whether to use streaming mode for responses.
            
        Returns:
            dict: A dictionary mapping agent names to their responses.
        """
        chat_message = ChatMessage(ChatRole.USER, message)
        self.thread.add_message(chat_message)
        
        responses = {}
        
        if agent_name:
            if agent_name in self.agents:
                agent = self.agents[agent_name]
                if streaming:
                    responses[agent_name] = await self._get_streaming_response(agent, chat_message)
                else:
                    responses[agent_name] = await self._get_response(agent, chat_message)
            else:
                self.logger.warning(f"Agent '{agent_name}' not found. Available agents: {self.get_available_agents()}")
        else:
            # Process with all agents
            tasks = []
            for name, agent in self.agents.items():
                if streaming:
                    task = asyncio.create_task(self._get_streaming_response(agent, chat_message))
                else:
                    task = asyncio.create_task(self._get_response(agent, chat_message))
                tasks.append((name, task))
                
            for name, task in tasks:
                responses[name] = await task
                
        return responses
    
    async def _get_response(self, agent, message):
        """
        Get a response from an agent.
        
        Args:
            agent (Agent): The agent to use.
            message (ChatMessage): The message to process.
            
        Returns:
            str: The agent's response.
        """
        # Run the agent (note that we don't pass the thread here because the message is already in the thread,
        # and we don't want to add it again)
        response = await agent.run_async_with_messages([], self.thread)
        return response.messages[0].content
    
    async def _get_streaming_response(self, agent, message):
        """
        Get a streaming response from an agent.
        
        Args:
            agent (Agent): The agent to use.
            message (ChatMessage): The message to process.
            
        Returns:
            str: The agent's response.
        """
        # Run the agent in streaming mode
        response_text = ""
        async for update in agent.run_streaming_async_with_messages([], self.thread):
            if update.message and update.message.content:
                response_text = update.message.content
        return response_text
    
    def get_thread_history(self):
        """
        Get the history of the thread.
        
        Returns:
            list: A list of chat messages.
        """
        return self.thread.messages

async def main(args):
    """
    Main function to demonstrate the MultiAgentOrchestrator.
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("multi_agent_sample")
    
    # Create agents
    agents = {
        "greeter": SimpleAgent(
            response_text="Hello there! How can I assist you today?",
            name="Greeter",
            description="A friendly greeter agent",
            instructions="Greet the user in a friendly manner",
            logger=logger
        ),
        "farewell": SimpleAgent(
            response_text="Thank you for chatting. Have a wonderful day!",
            name="Farewell",
            description="An agent that says goodbye",
            instructions="Say farewell to the user",
            logger=logger
        ),
        "echo": SimpleAgent(
            response_text="You said: '{0}'",
            name="Echo",
            description="An agent that echoes the user's message",
            instructions="Echo the user's message back to them",
            logger=logger
        )
    }
    
    # Create the orchestrator
    orchestrator = MultiAgentOrchestrator(agents, logger)
    
    print(f"Available agents: {orchestrator.get_available_agents()}")
    print("Type 'exit' to quit, or 'switch <agent>' to use a specific agent.")
    print("Currently using all agents.")
    
    current_agent = None
    
    while True:
        # Get user input
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
            
        if user_input.lower().startswith("switch "):
            parts = user_input.split(" ", 1)
            if len(parts) > 1:
                agent_name = parts[1].strip()
                if agent_name == "all":
                    current_agent = None
                    print("Now using all agents.")
                elif agent_name in orchestrator.get_available_agents():
                    current_agent = agent_name
                    print(f"Now using the '{current_agent}' agent.")
                else:
                    print(f"Agent '{agent_name}' not found. Available agents: {orchestrator.get_available_agents()}")
            continue
            
        # Process the message
        responses = await orchestrator.process_message(user_input, current_agent, args.streaming)
        
        # Print the responses
        for agent_name, response in responses.items():
            print(f"{agent_name}: {response}")
        
        # Print thread history if debug is enabled
        if args.debug:
            print("\nThread history:")
            for i, msg in enumerate(orchestrator.get_thread_history()):
                if msg.role == ChatRole.SYSTEM:
                    speaker = "System"
                elif msg.role == ChatRole.USER:
                    speaker = "You"
                else:
                    speaker = msg.author_name or "Agent"
                print(f"{i+1}. {speaker}: {msg.content}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Demo")
    parser.add_argument("--streaming", action="store_true", help="Use streaming mode for responses")
    parser.add_argument("--debug", action="store_true", help="Show debug information including thread history")
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
