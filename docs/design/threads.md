# Threads

Threads are stateful objects to manage the conversation context of an agent or a workflow.
They are meant to be shown to the user as part of a user interface.
They can be persisted to a database or a file system, and used to
resume a previous user session.

Thread should use message and content types as defined in [Core Data Types](types.md).

For workflows, a thread can contain sub-threads as a dictionary of threads. 
This is to ensure agents in a workflow can run concurrently on different threads.
The default thread has the key `main` and the sub-threads having keys that are usually
corresponding to the agents in a workflow.

For workflows, a thread should also support the concept of execution state, which includes:
- The history of steps taken.
- The current step in the workflow.
- The next steps to be taken.
This is to ensure the workflow can be resumed from where it left off, without losing
the state of execution.

The framework should provides default implementations of a thread class that:
- Can be backed by a database (i.e., Redis) or a file system (i.e., JSON file).
- Can be backed by the Foundry Agent Service.
- Can be copied and forked.
- Can be serialized and deserialized to/from JSON.
- Can support checkpointing, rollback, and time travel, for both agent and workflow.
- Can automantically export truncated views to be used by model clients to keep the context size within limits.

## `Thread` base class

```python
class Thread(ABC):
    """The base class for all threads defining the minimum interface."""

    # ---------- Message-handling ----------
    @abstractmethod
    async def on_new_message(self, message: "Message") -> None:
        """Handle a new message added to the thread."""
        ...
    
    # ---------- State management ----------
    @abstractmethod
    async def fork(self, message_id: str | None = None) -> "Thread":
        """Create a fork of the thread starting from the given message ID.
        
        If no message ID is provided, the fork will start from the latest message."""
        ...
    
    @abstractmethod
    async def reset(self) -> None:
        """Reset the thread to its initial state."""
        ...
    
    @abstractmethod
    async def save_state(self) -> Mapping[str, Any]:
        """Save the current state of the thread as a serializable dictionary."""
        ...
    
    @abstractmethod
    async def load_state(self, state: Mapping[str, Any]) -> None:
        """Load the state of the thread from a serializable dictionary."""
        ...
    

    # ---------- Lifecycle management ----------
    @classmethod
    @abstractmethod
    async def create(self) -> "Thread":
        """Create a new thread of the same type."""
        ...
    
    @abstractmethod
    async def delete(self) -> None:
        """Delete the thread. It will not be recoverable."""
        ...    
```

## `ChatHistoryThread` class

The most common thread type is going to be the `ChatHistoryThread`, which is a thread that stores the messages in a list. This thread type works well with `ChatCompletionAgent` and its subclasses.

```python
class ChatHistoryThread(Thread):
    """A thread that stores the messages in a list."""

    def __init__(self):
        self_messages = []  # List to store messages in the thread

    async def on_new_message(self, message: "Message") -> None:
        """Handle a new message added to the thread."""
        self._messages.append(message)
    
    async def fork(self, message_id: str | None = None) -> "ChatHistoryThread":
        """Create a fork of the thread starting from the given message ID.
        
        If no message ID is provided, the fork will start from the latest message."""
        new_thread = ChatHistoryThread()
        if message_id is None:
            new_thread._messages = self._messages.copy()
        else:
            index = next((i for i, msg in enumerate(self._messages) if msg.id == message_id), -1)
            new_thread._messages = self._messages[index + 1:] if index != -1 else []
        return new_thread
    
    async def reset(self) -> None:
        """Reset the thread to its initial state."""
        self._messages.clear()
    
    async def save_state(self) -> Mapping[str, Any]:
        """Save the current state of the thread as a serializable dictionary."""
        return {
            "messages": [msg.to_dict() for msg in self._messages],
        }
    
    async def load_state(self, state: Mapping[str, Any]) -> None:
        """Load the state of the thread from a serializable dictionary."""
        self._messages = [Message.from_dict(msg) for msg in state.get("messages", [])]

    @classmethod
    async def create(cls) -> "ChatHistoryThread":
        """Create a new chat history thread."""
        return cls()

    async def delete(self) -> None:
        """Delete the thread. It will not be recoverable."""
        self._messages.clear()
```

## `WorkflowThread` class

The `WorkflowThread` is a specialized thread that manages the execution state of a workflow. It extends the base `Thread` class and provides additional functionality to handle the workflow's execution steps and sub-threads.

```python

class WorkflowThread(Thread):
    """A thread that manages the execution state of a workflow."""

    # ----------- Execution state management -----------
    # TBD

    # ----------- Lifecycle management -----------
    async def create_sub_thread(self, agent: Agent, key: str) -> "Thread":
        """Create a sub-thread for the given agent with the given key."""
        pass
    
    async def delete_sub_thread(self, key: str) -> None:
        """Delete the sub-thread with the given key."""
        pass
    
    async def get_sub_thread(self, key: str) -> "Thread":
        """Get the sub-thread with the given key."""
        pass
