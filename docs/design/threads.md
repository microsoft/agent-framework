# Threads

Threads are stateful objects to manage the conversation context of an agent or a workflow.
They are meant to be shown to the user as part of a user interface.
They can be persisted to a database or a file system, and used to
resume a previous user session.

Thread should use message and content types as defined in [Core Data Types](types.md).

A thread can contain sub-threads as a dictionary of threads. 
This is to ensure agents in a workflow can run concurrently on different threads.
The default thread has the key `main` and the sub-threads having keys that are usually
corresponding to the agents in a workflow.

For workflows, thread should also support the concept of execution state, which includes:
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
