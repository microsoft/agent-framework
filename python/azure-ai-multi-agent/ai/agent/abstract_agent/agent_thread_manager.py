# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import Dict, List, Optional, Union
import uuid

from .agent_thread import AgentThread
from .memory_agent_thread import MemoryAgentThread

class AgentThreadManager:
    """
    A utility class for managing multiple agent threads.
    
    This can be used to keep track of multiple conversations with the same agent
    or to manage threads across multiple agents.
    """
    
    def __init__(self):
        """
        Initialize a new instance of the AgentThreadManager class.
        """
        self._threads: Dict[str, AgentThread] = {}
    
    def create_thread(self, thread_id: Optional[str] = None, thread_type: str = "memory") -> AgentThread:
        """
        Create a new thread and register it with the manager.
        
        Args:
            thread_id (Optional[str]): The ID for the new thread. If None, a random ID will be generated.
            thread_type (str): The type of thread to create. Currently supports "memory" for MemoryAgentThread.
            
        Returns:
            AgentThread: The newly created thread.
            
        Raises:
            ValueError: If the thread_type is not supported or the thread_id already exists.
        """
        # Generate a random ID if none was provided
        if thread_id is None:
            thread_id = str(uuid.uuid4())
            
        # Check if the ID already exists
        if thread_id in self._threads:
            raise ValueError(f"Thread ID '{thread_id}' already exists")
            
        # Create the thread based on the type
        if thread_type.lower() == "memory":
            thread = MemoryAgentThread(thread_id)
        else:
            raise ValueError(f"Unsupported thread type: {thread_type}")
            
        # Register the thread
        self._threads[thread_id] = thread
        
        return thread
    
    def register_thread(self, thread: AgentThread) -> bool:
        """
        Register an existing thread with the manager.
        
        Args:
            thread (AgentThread): The thread to register.
            
        Returns:
            bool: True if the thread was registered successfully, False if the thread's ID already exists.
            
        Raises:
            ValueError: If the thread has no ID.
        """
        if thread.id is None:
            raise ValueError("Thread must have an ID to be registered")
            
        if thread.id in self._threads:
            return False
            
        self._threads[thread.id] = thread
        return True
    
    def get_thread(self, thread_id: str) -> Optional[AgentThread]:
        """
        Get a thread by ID.
        
        Args:
            thread_id (str): The ID of the thread to retrieve.
            
        Returns:
            Optional[AgentThread]: The thread with the specified ID, or None if not found.
        """
        return self._threads.get(thread_id)
    
    def remove_thread(self, thread_id: str) -> bool:
        """
        Remove a thread from the manager.
        
        Args:
            thread_id (str): The ID of the thread to remove.
            
        Returns:
            bool: True if the thread was removed, False if it was not found.
        """
        if thread_id in self._threads:
            del self._threads[thread_id]
            return True
        return False
    
    def clear_threads(self) -> None:
        """
        Remove all threads from the manager.
        """
        self._threads.clear()
    
    @property
    def threads(self) -> List[AgentThread]:
        """
        Get a list of all registered threads.
        
        Returns:
            List[AgentThread]: A list of all registered threads.
        """
        return list(self._threads.values())
    
    @property
    def thread_ids(self) -> List[str]:
        """
        Get a list of all registered thread IDs.
        
        Returns:
            List[str]: A list of all registered thread IDs.
        """
        return list(self._threads.keys())
    
    def count(self) -> int:
        """
        Get the number of registered threads.
        
        Returns:
            int: The number of registered threads.
        """
        return len(self._threads)
