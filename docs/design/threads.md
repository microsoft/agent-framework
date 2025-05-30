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

## `AgentThread` base class

```python
class AgentThread(ABC):
    """The base class for all threads defining the minimum interface."""

    # ---------- Message-handling ----------
    @abstractmethod
    async def on_new_messages(self, messages: list["Message"]) -> None:
        """Handle a new message added to the thread."""
        ...

    # ---------- Lifecycle management ----------
    @classmethod
    @abstractmethod
    async def create(self) -> "AgentThread":
        """Create a new thread of the same type."""
        ...

    # For delete and release resources, subclass should override built-in Python `del` method.    
```

## `ChatMessageThread` class

The most common thread type is going to be the `ChatMessageThread`, which is a thread that stores the messages in a list. This thread type works well with `ChatCompletionAgent` and its subclasses.

```python
class ChatMessageThread(AgentThread):
    """A thread that stores the messages in a list."""

    def __init__(self):
        # NOTE: We should have some way to prevent direct calling of the constructor from the base class
        # and enforce using the `create` class method.
        if ThreadCreationContext.is_active:
            raise RuntimeError("Cannot instantiate ChatMessageThread directly. Use ChatMessageThread.create() instead.")
        self._messages: list["Message"] = []
    
    @property
    def messages(self) -> list["Message"]:
        """Get the list of messages in the thread."""
        return self._messages

    async def on_new_messages(self, messages: list["Message"]) -> None:
        """Handle a list of new messages added to the thread."""
        self._messages.extend(messages)
    
    async def fork(self, message_id: str | None = None) -> "ChatMessageThread":
        """Create a fork of the thread starting from the given message ID.

        NOTE: we may need to create a new base class / protocol for this behavior.
        
        If no message ID is provided, the fork will start from the latest message."""
        new_thread = ChatMessageThread()
        if message_id is None:
            new_thread._messages = self._messages.copy()
        else:
            index = next((i for i, msg in enumerate(self._messages) if msg.id == message_id), -1)
            new_thread._messages = self._messages[index + 1:] if index != -1 else []
        return new_thread

    @classmethod
    async def create(cls) -> "ChatMessageThread":
        """Create a new chat history thread."""
        with ThreadCreationContext.activate():
            return cls()

    async def delete(self) -> None:
        """Delete the thread. It will not be recoverable."""
        self._messages.clear()
```

## `WorkflowThread` class

The `WorkflowThread` is a specialized thread that manages the execution state of a workflow. It extends the base `Thread` class and provides additional functionality to handle the workflow's execution steps and sub-threads.

```python

class WorkflowThread(AgentThread):
    """A thread that manages the execution state of a workflow."""

    # ----------- Execution state management -----------
    # TBD

    # ----------- Lifecycle management -----------
    async def create_sub_thread(self, agent: Agent, key: str) -> "AgentThread":
        """Create a sub-thread for the given agent with the given key."""
        pass
    
    async def delete_sub_thread(self, key: str) -> None:
        """Delete the sub-thread with the given key."""
        pass
    
    async def get_sub_thread(self, key: str) -> "AgentThread":
        """Get the sub-thread with the given key."""
        pass
