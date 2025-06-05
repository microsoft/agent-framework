# Memory, RAG, and other Context Providers

Prior to calling a model client, it's often necessary to add information to the client's context window gathered from various sources.
Two prime examples are long-term memory and retrieval-augmented generation (RAG) systems.
The ContextProvider class supports such scenarios through a unified interface for storing and retrieving context data.

## `ContextProvider` base class

```python
class ContextProvider(ABC):
    """
    The base class for context providers like Memory and RAG.
    Subclasses will typically have extra methods and constructor parameters for specific functionality,
    such as clearing memory contents, or adding files to a RAG provider. 
    """

    @abstractmethod
    async def get_relevant_context(self, messages: list["Message"]) -> ProvidedContext | None:
        """Searches for and returns any information relevant to the messages."""
        ...

    @abstractmethod
    async def on_new_messages(self, messages: list["Message"]) -> None:
        """Stores any information derived from the messages that may be useful to retrieve later."""
        ...

    # To close, delete and release any runtime resources, each subclass should override the built-in Python `del` method.    
```

## Usage

As an example, consider the following scenario involving long-term memory as a context provider.

Suppose that an app defines a subclass of `ContextProvider` called `Mem0Wrapper` which implements all required methods.
At runtime the app instantiates the memory provider, passing any necessary parameters to its constructor.
```python
mem = Mem0Wrapper(<params>)
```

In this example, the app then clears memory to ensure that it starts empty.
```python
mem.clear()
```

Then the app creates an agent and passes the memory provider to it through the constructor or some other method.
```python
agent.add_context_provider(mem)
```

After creating the agent, the app calls `agent.run(message, thread, run_config)` as usual,
where the user message assigns a task that requires knowledge the agent doesn't have.
`agent.run()` calls `get_relevant_context(message)` on each of the agent's context providers,
but `None` is returned since memory is empty.
Then `agent.run()` calls the model client as usual, but the LLM can't solve the task.
It may realize the information is missing, and ask the user for it.

The original user message (which assigned the task) is then added to the thread's message history as usual,
which automatically calls the `Agent.on_new_messages(messages)`,
which calls `on_new_messages` on each context provider.
In this case the memory provider fails to find any useful information in the user's message to store.

Suppose then that the user responds by supplying the missing information.
This time the agent will succeed, since the LLM's context window now contains the relevant information.
More importantly for our example, when the second user message is added to the thread's message history,
`mem.on_new_messages()` will extract and store the relevant information for later retrieval.

For this example, suppose the user then initiates a new chat (clearing the message history),
and assigns the original task again, but without providing the missing information.
This time when `mem.get_relevant_context(message)` is called, the memory provider finds the relevant information stored from the previous chat.
Then `agent.run()` attaches the retrieved information to the context window before calling the model client,
which allows the agent to succeed at the task without the user needing to repeat the missing information.

For more advanced memory implementations that have the ability to learn from their own experience
(instead of only from the user), `mem.get_relevant_context(message)` may return useful context
that was not previously extracted by `mem.on_new_messages(messages)`.
