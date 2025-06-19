# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
import logging
import argparse
import uuid
import json
import os
import sys
from typing import Dict, List, Optional, Any

from azure.ai.agent.abstract_agent import AgentThreadManager, Agent, AgentThread
from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.common import ChatMessage, ChatRole

class ConversationManager:
    """
    A manager for multiple conversations with agents.
    
    This class demonstrates using the AgentThreadManager to maintain multiple
    conversations across different users and agents.
    """
    
    def __init__(self, agents_dict=None, logger=None):
        """
        Initialize a new instance of the ConversationManager class.
        
        Args:
            agents_dict (dict): A dictionary of agent names to agent instances.
            logger: Optional logger to use for logging.
        """
        self.agents = agents_dict or {}
        self.thread_manager = AgentThreadManager()
        self.logger = logger or logging.getLogger(__name__)
        self.user_sessions: Dict[str, Dict[str, Any]] = {}
        
    def register_agent(self, name: str, agent: Agent) -> None:
        """
        Register an agent with the conversation manager.
        
        Args:
            name (str): The name to register the agent under.
            agent (Agent): The agent to register.
        """
        self.agents[name] = agent
        
    def get_available_agents(self) -> List[str]:
        """
        Get the names of available agents.
        
        Returns:
            List[str]: A list of agent names.
        """
        return list(self.agents.keys())
    
    def create_user_session(self, user_id: Optional[str] = None) -> str:
        """
        Create a new session for a user.
        
        Args:
            user_id (Optional[str]): The ID of the user. If None, a random ID will be generated.
            
        Returns:
            str: The user ID.
        """
        if user_id is None:
            user_id = str(uuid.uuid4())
            
        if user_id in self.user_sessions:
            self.logger.warning(f"User session '{user_id}' already exists. Overwriting.")
            
        # Create a new session
        self.user_sessions[user_id] = {
            "current_agent": None,
            "conversations": {}  # agent_name -> thread_id mapping
        }
        
        return user_id
    
    def get_or_create_conversation(self, user_id: str, agent_name: str) -> AgentThread:
        """
        Get or create a conversation thread for a user with a specific agent.
        
        Args:
            user_id (str): The ID of the user.
            agent_name (str): The name of the agent.
            
        Returns:
            AgentThread: The conversation thread.
            
        Raises:
            ValueError: If the user ID or agent name is invalid.
        """
        if user_id not in self.user_sessions:
            raise ValueError(f"User session '{user_id}' not found.")
            
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not found. Available agents: {self.get_available_agents()}")
            
        # Check if the user already has a conversation with this agent
        user_session = self.user_sessions[user_id]
        conversations = user_session["conversations"]
        
        if agent_name in conversations:
            thread_id = conversations[agent_name]
            thread = self.thread_manager.get_thread(thread_id)
            if thread is not None:
                return thread
                
        # Create a new thread for this conversation
        thread_id = f"{user_id}_{agent_name}_{str(uuid.uuid4())}"
        thread = self.thread_manager.create_thread(thread_id)
        
        # Store the thread ID in the user session
        conversations[agent_name] = thread_id
        
        # Add a system message to initialize the conversation
        system_message = ChatMessage(
            ChatRole.SYSTEM,
            f"This is a conversation between a user and the {agent_name} agent."
        )
        
        # If we're using a memory agent thread, we can add the system message directly
        if hasattr(thread, 'add_message'):
            thread.add_message(system_message)
            
        return thread
    
    def set_current_agent(self, user_id: str, agent_name: str) -> None:
        """
        Set the current agent for a user session.
        
        Args:
            user_id (str): The ID of the user.
            agent_name (str): The name of the agent.
            
        Raises:
            ValueError: If the user ID or agent name is invalid.
        """
        if user_id not in self.user_sessions:
            raise ValueError(f"User session '{user_id}' not found.")
            
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not found. Available agents: {self.get_available_agents()}")
            
        self.user_sessions[user_id]["current_agent"] = agent_name
    
    def get_current_agent(self, user_id: str) -> Optional[str]:
        """
        Get the current agent for a user session.
        
        Args:
            user_id (str): The ID of the user.
            
        Returns:
            Optional[str]: The name of the current agent or None.
            
        Raises:
            ValueError: If the user ID is invalid.
        """
        if user_id not in self.user_sessions:
            raise ValueError(f"User session '{user_id}' not found.")
            
        return self.user_sessions[user_id]["current_agent"]
    
    async def process_message(self, user_id: str, message: str, agent_name: Optional[str] = None, streaming: bool = False) -> Dict[str, Any]:
        """
        Process a message from a user.
        
        Args:
            user_id (str): The ID of the user.
            message (str): The message to process.
            agent_name (Optional[str]): The name of the agent to use. If None, uses the current agent for the session.
            streaming (bool): Whether to use streaming mode for responses.
            
        Returns:
            Dict[str, Any]: A dictionary with the response information.
            
        Raises:
            ValueError: If the user ID or agent name is invalid.
        """
        if user_id not in self.user_sessions:
            raise ValueError(f"User session '{user_id}' not found.")
            
        # Get the agent name to use
        if agent_name is None:
            agent_name = self.get_current_agent(user_id)
            if agent_name is None:
                raise ValueError("No agent specified and no current agent set for the session.")
                
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not found. Available agents: {self.get_available_agents()}")
            
        # Get the agent and thread
        agent = self.agents[agent_name]
        thread = self.get_or_create_conversation(user_id, agent_name)
        
        # Create the chat message
        chat_message = ChatMessage(ChatRole.USER, message)
        
        # Process with the agent
        response_content = ""
        if streaming:
            async for update in agent.run_streaming_async_with_messages([chat_message], thread):
                if update.message and update.message.content:
                    response_content = update.message.content
        else:
            response = await agent.run_async_with_messages([chat_message], thread)
            if response.messages and len(response.messages) > 0:
                response_content = response.messages[0].content
        
        # Create the response information
        response_info = {
            "user_id": user_id,
            "agent": agent_name,
            "response": response_content,
            "thread_id": thread.id
        }
        
        return response_info
    
    def save_state(self, file_path: str) -> None:
        """
        Save the conversation manager state to a file.
        
        Args:
            file_path (str): The path to save the state to.
        """
        state = {
            "user_sessions": self.user_sessions
        }
        
        with open(file_path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, file_path: str) -> None:
        """
        Load the conversation manager state from a file.
        
        Args:
            file_path (str): The path to load the state from.
        """
        if not os.path.exists(file_path):
            self.logger.warning(f"State file '{file_path}' not found.")
            return
            
        with open(file_path, 'r') as f:
            state = json.load(f)
            
        if "user_sessions" in state:
            self.user_sessions = state["user_sessions"]
        
        # Re-create threads for all conversations
        for user_id, user_session in self.user_sessions.items():
            for agent_name, thread_id in user_session["conversations"].items():
                # Create the thread if it doesn't exist
                if self.thread_manager.get_thread(thread_id) is None:
                    self.thread_manager.create_thread(thread_id)

async def main(args):
    """
    Main function to demonstrate the ConversationManager.
    """
    # Configure logging
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=logging_level, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("conversation_manager_sample")
    
    # Create agents
    agents = {
        "greeter": SimpleAgent(
            response_text="Hello there! How can I assist you today?",
            name="Greeter",
            description="A friendly greeter agent",
            instructions="Greet the user in a friendly manner",
            logger=logger
        ),
        "helper": SimpleAgent(
            response_text="I'm here to help with any questions you might have.",
            name="Helper",
            description="A helpful assistant agent",
            instructions="Help the user with their questions",
            logger=logger
        ),
        "farewell": SimpleAgent(
            response_text="Thank you for chatting. Have a wonderful day!",
            name="Farewell",
            description="An agent that says goodbye",
            instructions="Say farewell to the user",
            logger=logger
        )
    }
    
    # Create the conversation manager
    conversation_manager = ConversationManager(agents, logger)
    
    # Load state if requested
    if args.state_file and os.path.exists(args.state_file):
        logger.info(f"Loading state from {args.state_file}")
        conversation_manager.load_state(args.state_file)
    
    print(f"Available agents: {conversation_manager.get_available_agents()}")
    
    # Create or get user session
    user_id = args.user_id or str(uuid.uuid4())
    if user_id not in conversation_manager.user_sessions:
        user_id = conversation_manager.create_user_session(user_id)
        print(f"Created new user session with ID: {user_id}")
    else:
        print(f"Using existing user session with ID: {user_id}")
    
    # Set initial agent if specified
    if args.agent:
        if args.agent in conversation_manager.get_available_agents():
            conversation_manager.set_current_agent(user_id, args.agent)
            print(f"Set current agent to: {args.agent}")
        else:
            print(f"Agent '{args.agent}' not found. Available agents: {conversation_manager.get_available_agents()}")
    
    # Interactive loop
    print("\nType 'exit' to quit, 'switch <agent>' to use a specific agent, or 'save' to save the conversation state.")
    
    current_agent = conversation_manager.get_current_agent(user_id)
    if current_agent:
        print(f"Currently using the '{current_agent}' agent.")
    else:
        print("No agent selected. Use 'switch <agent>' to select an agent.")
    
    while True:
        # Get user input
        try:
            user_input = input("\nYou: ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break
            
        if user_input.lower() == "exit":
            break
            
        if user_input.lower() == "save":
            if args.state_file:
                conversation_manager.save_state(args.state_file)
                print(f"Saved state to {args.state_file}")
            else:
                print("No state file specified. Use --state-file to specify a file.")
            continue
            
        if user_input.lower().startswith("switch "):
            parts = user_input.split(" ", 1)
            if len(parts) > 1:
                agent_name = parts[1].strip()
                if agent_name in conversation_manager.get_available_agents():
                    conversation_manager.set_current_agent(user_id, agent_name)
                    print(f"Now using the '{agent_name}' agent.")
                else:
                    print(f"Agent '{agent_name}' not found. Available agents: {conversation_manager.get_available_agents()}")
            continue
        
        # Check if we have a current agent
        current_agent = conversation_manager.get_current_agent(user_id)
        if current_agent is None:
            print("No agent selected. Use 'switch <agent>' to select an agent.")
            continue
            
        try:
            # Process the message
            response_info = await conversation_manager.process_message(
                user_id, user_input, streaming=args.streaming
            )
            
            # Print the response
            agent_name = response_info["agent"]
            response = response_info["response"]
            
            if args.streaming:
                print(f"\n{agent_name}: {response}")
            else:
                print(f"\n{agent_name}: {response}")
                
        except ValueError as e:
            print(f"Error: {e}")
    
    # Save state if requested
    if args.state_file:
        conversation_manager.save_state(args.state_file)
        print(f"Saved state to {args.state_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversation Manager Demo")
    parser.add_argument("--streaming", action="store_true", help="Use streaming mode for responses")
    parser.add_argument("--debug", action="store_true", help="Show debug information")
    parser.add_argument("--user-id", type=str, help="The user ID to use for the session")
    parser.add_argument("--agent", type=str, help="The initial agent to use")
    parser.add_argument("--state-file", type=str, help="The file to save/load the conversation state")
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
