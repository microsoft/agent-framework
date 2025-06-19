# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import pytest
import uuid

from azure.ai.agent.abstract_agent import AgentThreadManager, MemoryAgentThread, AgentThread

def test_agent_thread_manager_initialization():
    """Test that an AgentThreadManager can be initialized."""
    manager = AgentThreadManager()
    assert manager is not None
    assert manager.count() == 0
    assert len(manager.threads) == 0
    assert len(manager.thread_ids) == 0

def test_agent_thread_manager_create_thread():
    """Test creating a thread with the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create a thread with a generated ID
    thread = manager.create_thread()
    assert thread is not None
    assert thread.id is not None
    assert manager.count() == 1
    
    # Create a thread with a specific ID
    thread_id = "test-thread-id"
    thread = manager.create_thread(thread_id)
    assert thread is not None
    assert thread.id == thread_id
    assert manager.count() == 2
    
    # Create a thread with a specific type
    thread = manager.create_thread(thread_type="memory")
    assert thread is not None
    assert isinstance(thread, MemoryAgentThread)
    assert manager.count() == 3
    
    # Test creating a thread with an existing ID raises an error
    with pytest.raises(ValueError):
        manager.create_thread(thread_id)
    
    # Test creating a thread with an unsupported type raises an error
    with pytest.raises(ValueError):
        manager.create_thread(thread_type="unsupported")

def test_agent_thread_manager_register_thread():
    """Test registering an existing thread with the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create a thread
    thread_id = "test-thread-id"
    thread = MemoryAgentThread(thread_id)
    
    # Register the thread
    result = manager.register_thread(thread)
    assert result is True
    assert manager.count() == 1
    assert manager.get_thread(thread_id) == thread
    
    # Test registering a thread with no ID raises an error
    thread_without_id = AgentThread()
    with pytest.raises(ValueError):
        manager.register_thread(thread_without_id)
    
    # Test registering a thread with an existing ID returns False
    duplicate_thread = MemoryAgentThread(thread_id)
    result = manager.register_thread(duplicate_thread)
    assert result is False
    assert manager.count() == 1

def test_agent_thread_manager_get_thread():
    """Test getting a thread by ID from the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create some threads
    thread1_id = "thread-1"
    thread2_id = "thread-2"
    thread1 = manager.create_thread(thread1_id)
    thread2 = manager.create_thread(thread2_id)
    
    # Get the threads
    retrieved_thread1 = manager.get_thread(thread1_id)
    retrieved_thread2 = manager.get_thread(thread2_id)
    assert retrieved_thread1 == thread1
    assert retrieved_thread2 == thread2
    
    # Test getting a non-existent thread returns None
    non_existent_thread = manager.get_thread("non-existent")
    assert non_existent_thread is None

def test_agent_thread_manager_remove_thread():
    """Test removing a thread from the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create some threads
    thread1_id = "thread-1"
    thread2_id = "thread-2"
    thread1 = manager.create_thread(thread1_id)
    thread2 = manager.create_thread(thread2_id)
    
    # Remove a thread
    result = manager.remove_thread(thread1_id)
    assert result is True
    assert manager.count() == 1
    assert manager.get_thread(thread1_id) is None
    assert manager.get_thread(thread2_id) == thread2
    
    # Test removing a non-existent thread returns False
    result = manager.remove_thread("non-existent")
    assert result is False
    assert manager.count() == 1

def test_agent_thread_manager_clear_threads():
    """Test clearing all threads from the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create some threads
    thread1 = manager.create_thread()
    thread2 = manager.create_thread()
    thread3 = manager.create_thread()
    
    assert manager.count() == 3
    
    # Clear all threads
    manager.clear_threads()
    
    assert manager.count() == 0
    assert len(manager.threads) == 0
    assert len(manager.thread_ids) == 0

def test_agent_thread_manager_properties():
    """Test the properties of the AgentThreadManager."""
    manager = AgentThreadManager()
    
    # Create some threads
    thread1_id = "thread-1"
    thread2_id = "thread-2"
    thread1 = manager.create_thread(thread1_id)
    thread2 = manager.create_thread(thread2_id)
    
    # Test the threads property
    threads = manager.threads
    assert len(threads) == 2
    assert thread1 in threads
    assert thread2 in threads
    
    # Test the thread_ids property
    thread_ids = manager.thread_ids
    assert len(thread_ids) == 2
    assert thread1_id in thread_ids
    assert thread2_id in thread_ids
    
    # Test the count property
    assert manager.count() == 2
