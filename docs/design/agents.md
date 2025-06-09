# Agents

An agent is a component that processes messages in a thread and returns a result.

During its handling of messages, an agent may:

- Use model client to process messages,
- Use thread to keep track of the interaction with the model,
- Invoke tools or MCP servers, and
- Retrieve and store data through memory.

It is up to the implementation of the agent class to decide how these components are used.

__An important design goal of the framework is to ensure the developer experience
of creating custom agent is as easy as possible.__ Existing frameworks
have made "kitchen-sink" agents that are hard to understand and maintain.

An agent might not use the components provided by the framework to implement
the agent interface.
Azure AI Agent is an example of such agent: its implementation is
backed by the Azure AI Agent Service.

The framework provides a set of pre-built agents:

- `ChatCompletionAgent`: an agent that uses a chat-completion model to process messages
and use thread, memory, tools and MCP servers in a configurable way. __If we can make
custom agents easy to implement, we can remove this agent.__
- `AzureAIAgent`: an agent that is backed by Azure AI Agent Service.
- `ResponsesAgent`: an agent that is backed by OpenAI's Responses API.
- `A2AAgent`: an agent that is backed by the [A2A Protocol](https://google.github.io/A2A/documentation/).

## `Agent` base class

```python
TInThread = TypeVar("TInThread", bound="AgentThread", contravariant=True)
TNewThread = TypeVar("TOutThread", bound="AgentThread", covariant=True)

class Agent(ABC, Generic[TInThread, TNewThread]):
    """The base class for all agents in the framework."""

    @abstractmethod
    async def run(
        self, 
        messages: list[Message],
        thread: TInThread,
        context: RunContext,
    ) -> Result:
        """The method to run the agent on a thread of messages, and return the result.

        Args:
            messages: The list of new messages to process that have not been added
                to the thread yet. The agent may use these messages and append
                new messages to the thread as part of its processing.
            thread: The thread of messages to process: it may be a local thread
                or a stub thread that is backed by a remote service.
            context: The context for the current invocation of the agent, providing
                access to the event channel, and human-in-the-loop (HITL) features.
        
        Returns:
            The result of running the agent, which includes the final response.
        """
        ...
    
    @classmethod
    @abstractmethod
    async def create_thread(self) -> TNewThread:
        """Create a new thread for the agent to use.

        Returns:
            A new thread that is compatible with the agent.
        """
        ...


@dataclass
class RunContext:
    """The context for the current invocation of the agent."""

    event_handler: EventHandler | Callable[[Message], Awaitable[None]]
    """The event consumer for handling events emitted by the agent. Could be
    a callable that takes a message and returns an awaitable, or an instance of
    `EventHandler` that handles events emitted by the agent."""

    user_input_source: UserInputSource
    """The user input source for requesting for user input during the agent run."""

    ... # Other fields, could be extended to include more for application-specific needs.


@dataclass
class Result:
    """The result of running an agent."""
    final_response: Message
    ... # Other fields, could be extended to include more for application-specific needs.
```

## `ToolCallingAgent` example

Here is an example of a custom agent that calls a tool and returns the result.
The `ToolCallingAgent` implements the `Agent` base class and
it implements the `run` method to process incoming messages and call tools if needed.

```python

TInThread = TypeVar("TInThread", bound="ChatMessageThread", contravariant=True)
TNewThread = TypeVar("TOuthread", bound="ChatMessageThread", covariant=True)

class ToolCallingAgent(Agent[TInThread, TNewThread]):
    def __init__(
        self, 
        model_client: ModelClient,
        tools: list[Tool],
    ) -> None:
        self.model_client = model_client
        self.tools = tools

    async def run(self, messages: list[Message], thread: TInThread, context: RunContext) -> Result:
        # Apply the messages to the thread.
        await thread.on_new_messages(messages)
        # Create a response using the model client, passing the thread and context.
        create_result = await self.model_client.create(thread.messages, context, tools=self.tools)
        # Emit the event to notify the workflow consumer of a model response.
        await context.emit(ModelResponseEvent(create_result))
        if create_result.is_tool_call():
            # Get user approval for the tool call through the context.
            approval = await context.get_user_approval(create_result.tool_calls)
            if not approval:
                # ... return a canned response.
            # Call the tools with the tool calls in the response.
            tools = ... # Find the tool by name in the tools list.
            tool_results = ... # Call the tool with the tool call arguments.
            # Emit the event to notify the workflow consumer of a tool call.
            await context.emit(ToolCallEvent(tool_result))
            # Update the thread with the tool result.
            await thread.on_new_messages(tool_result.to_messages())
            # Return the tool result as the response.
            return Result(
                final_response=tool_result,
            )
        else: 
            # Return the response as the result.
            return Result(
                final_response=create_result,
            )
    
    @classmethod
    async def create_thread(self) -> TNewThread:
        """Create a new thread for the agent to use.
        
        NOTE: this could be part of a new base class for this type of agent.
        """
        return await ChatMessageThread.create()
```

Things to note in the implementation of the `run` method:
- Orchestration of tools and model is completly customizable.
- Components such as `thread` and `model_client` interacts smoothly with little boilerplate code.
- The `context` parameter provides convenient access to the workflow run fixtures such as event channel.

In practice, the developer likely will inherit from `ChatAgent` to
customize the `run` method, so they don't need to implement the boilerplate code
for creating a thread.

An agent doesn't need to use components provided by the framework to implement the agent interface.

For example, in a multi-agent workflow, we may need a verification agent in a using deterministic
logic to critic another agent's response.

```python
class CriticAgent(ChatAgent):
    def __init__(self) -> None:
        self.verification_logic = ... # Some verification logic, e.g. a set of rules.

    async def run(self, messages: list[Message], thread: ChatMessageThread, context: RunContext) -> Result:
        # Use the verification logic to verify the messages.
        is_verified = self.verification_logic.verify(messages)
        if is_verified:
            final_response = Message("The response is verified.")
        else:
            final_response = Message("The response is not verified.")
        
        return Result(
            final_response=final_response,
        )
```

## Run

A _run_ is a single invocation of the agent or a workflow given a thread of messages.

## Run agent

Developer can instantiate a subclass of `Agent` directly using it's constructor, 
and run it by calling the `run` method.

```python
@FunctionTool
def my_tool(input: str) -> str:
    return f"Tool result for {input}"

model_client = OpenAIChatCompletionClient("gpt-4.1")
agent = ToolCallingAgent(
    model_client=model_client, 
    tools=[my_tool],
)

# Create a thread for the current task.
thread = await ChatMessageThread.create()

# Create a context that uses a handler that prints emitted events to the console, 
# and a user input source that reads from the console.
context = RunContext(event_handler=ConsoleEventHandler(), user_input_source=ConsoleUserInputSource())

# Run the agent with the thread and context.
result = await agent.run([Message("Can you find the file 'foo.txt' for me?")], thread, context)
```

## User session

A user session is a logical concept which involves a sequence of messages exchanged between the user and the agent.
Consider the following examples:

- A chat session in ChatGPT.
- A delegation of task to a workflow agent from a user, with data exchanged between the user
    and the workflow such as occassional feedbacks from the user and status updates from the workflow.

A user session may involve multiple runs.


## User session state

Rather than classifying agents as stateless or stateful, we focus on how state is managed during a user session.

There are several states that an application may maintain during a user session:
- **Conversation or workflow state**. This is the conversation history or execution 
    history in a workflow. This state is typically owned and managed by the thread object.
- **Long-term memory**. This can be information relevant to the user, 
    such as user preferences, past interactions, or other relevant data.
    This can also be information relevant to the task, such as past trajectories,
    past results, or other task-related data. These states are typically
    owned and managed by a memory object.

The thread is always passed through the agent's `run` method.
Memory may be attached to the thread or passed to the agent's constructor.

See the [Context Providers](context_providers.md) design document for more details on how memory
and other context providers like RAG are used in the framework.

It is up to the application to decide whether to reuse state across different
user sessions. The framework should provide the necessary methods and storage layer integration
for persisting and retrieving state, but the application should decide how to use them.

## Run agent concurrently

If the agent just call models and tools that are stateless, 
we can run the same instance of the agent concurrently.

```python
# Create threads for concurrent tasks.
thread1 = ChatMessageThread.create()
thread2 = ChatMessageThread.create()

# Run the agent concurrently on multiple threads.
results = await asyncio.gather(
    agent.run([Message(...)], thread1, context),
    agent.run([Message(...)], thread2, context),
)
# The `context`'s event handlers will emit events from both runs.
```

This is not always the right way to run concurrent agents, as some tools
or memory associated with the agent may not be concurrent-safe.

It is up the application to decide if an agent can run concurrently,
or multiple instances should be created for each thread.


## Using Foundry Agent Service

The framework offers a built-in agent class for users of the Foundry Agent Service.
The agent class essentially acts as a proxy to the agent hosted by the Foundry Agent Service.

```python
agent = FoundryAgent(
    name="my_foundry_agent",
    project_client="ProjectClient",
    agent_id="my_agent_id", # If not provided, a new agent will be created.
    deployment_name="my_deployment",
    instruction="my_instruction",
    ... # Other parameters for the agent creation.
)

# Create a thread that is backed by the Foundry Agent Service.
thread = FoundryThread(thread_id="my_thread_id")

# Run the agent on the thread and an new context that emits events to the console.
result = await agent.run([Message(...)], thread, RunRunContext(event_channel="console"))
```

## Alternative agent abstractions

There are two alternatives:

1. **Agent with private conversation state**: The agent manages its own conversation state,
    either by using a thread or other custom logics. The conversation state is 
    not shared with other agents or workflows. It is up to the agent to decide how
    to manage the conversation state.
2. **Agent without conversation state**: The conversation state is externalized
    and managed by a thread abstraction. The agent is invoked with a thread on
    every run. While it can still use the thread to append messages etc., it loses
    control over the conversation state the moment the run method returns.

### Protocol comparison

For agent with private conversation state, agent is invoked with new messages
and the agent is responsible for managing the conversation state while exposing
public methods for the orchestration code to manipulate its conversation state
indirectly.

```python
class Agent(ABC):

    async def run(
        self, 
        messages: list[Message],
        context: RunContext,
    ) -> Result:
        """The method to run the agent and return the result.

        Args:
            messages: The list of new messages to process.
            context: The context for the current invocation of the agent, providing
                access to the event channel, and human-in-the-loop (HITL) features.

        Returns:
            The result of running the agent, which includes the final response.
        """
        ...
    
    async def reset() -> None:
        """Reset the conversation state of the agent."""
        ...
    
    # And other methods for managing the conversation state.
```

For agent without conversation state, the agent is invoked with a thread
and the agent is responsible for processing the messages in the thread.

```python
class Agent(ABC, Generic[TThread]):

    async def run(
        self, 
        messages: list[Message],
        thread: TThread,
        context: RunContext,
    ) -> Result:
        """The method to run the agent on a thread of messages, and return the result.

        Args:
            messages: The list of new messages to process.
            thread: The current conversation state.
            context: The context for the current invocation of the agent, providing
                access to the event channel, and human-in-the-loop (HITL) features.
        Returns:
            The result of running the agent, which includes the final response.
        """
        ...
```

### Constructor comparison

For agent with private conversation state, the agent is initialized with
the a state in addition to components like model client and tools, which could be a thread passed to the constructor,
or a custom state object that the agent uses to manage its conversation state.

```python
class CustomAgent(Agent[ChatMessageThread]):
    def __init__(self, 
        model_client: ModelClient,
        tools: list[Tool],
        state: CustomState, # Could be a thread or a custom state object, or nothing at all.
    ) -> None:
        self.model_client = model_client
        self.tools = tools
        self.state = state # Could be created by the agent within the constructor.

```

For agent without conversation state, the agent is initialized with
the components it needs to process messages, such as a model client and tools.

```python
class CustomAgent(Agent[ChatMessageThread]):
    def __init__(
        self, 
        model_client: ModelClient,
        tools: list[Tool],
    ) -> None:
        self.model_client = model_client
        self.tools = tools
```

### Thread-Agent compatibility considerations

For agent with private conversation state, compatibility with thread is not a concern,
as this is completely managed by the agent itself.

For agent without conversation state, the thread must be compatible with the agent's
`run` method. For example, a `FoundryAgent` must work with a `FoundryThread`
because the thread is backed by the Foundry Agent Service, and the implementation
requires the thread to be compatible with the service's API.

Compatibility constraints:
- `FoundryAgent` must work with `FoundryThread`.
- `OpenAIAssistantAgent` must work with `OpenAIAssistantThread`.
- `ResponsesAgent` must work with `ResponsesThread`, when using the stateful mode of the Responses API.

### Workflow-Agent compatibility considerations

For agent with private conversation state, the orchestration code cannot directly
modifies the conversation state of every agent in the workflow.
This means that for resetting the conversation state, branching a conversation,
or other orchestration logic, the agent must provides public
methods for the orchestration code to manipulate its conversation state.

Potential methods (just initial ideas):
- `reset()` to reset the conversation state.
- `branch()` to create a new branch of the conversation state from an existing state.

Example: AutoGen's MagenticOne orchestration requires the agents to be able to
reset their conversation states during re-planning. It is reasonable to expect
other types of orchestration logic will require behavior like branching
or backtracking.

For agent without conversation state, the orchestration code can directly
manipulate the thread that is passed to the agent's `run` method. So the orchestration code
can clone, fork, or reset the thread as needed.
This also means that the agent's converstion state must be abstracted as a thread.

### Extensibility considerations

For agent with private conversation state, the management of the conversation state
is completely up to the agent implementation. This means that custom agents can
be created with different conversation state management strategies, such as:
- Using a custom thread implementation that provides additional features.
- Using a custom state object that provides additional features.
When using a custom state object, the developer must also implement
methods for exporting and importing the state.

For agent without conversation state, the thread abstraction is required to
encapsulate the conversation state and ensure that the agent's `run` method
can use it without any issues. This puts a constraint on the agent implementation,
and also what can be represented as state in the thread.
Though, if the thread abstraction is designed well, it relieves the developer
from implementing the conversation state management logic themselves.
The developer only needs to come up with custom thread when the built-in thread
abstraction does not work with their custom agent.

### Discussion

- Either agent or thread must manage the conversation state.
- The class that manages the conversation state must provide a way to manipulate
    it for orchestration purposes.
- Isolate thread as a separate required abstraction may introduce compatibility
    issues.
- A thread abstraction with methods for manipulating the conversation state
    should always be provided by the framework, whether it is exposed again
    through the agent or not.

In a scenario with built-in agents and built-in threads, the developer experience
is nearly identical except for agent without conversation state the developer
must ensure the thread is compatible with the agent's `run` method.

In a scenario with custom agents and built-in threads, the developer experience
is simpler for agent without conversation state, as the thread abstraction
is already provided by the framework and the agent can use it directly. Plus,
the developer doesn't need to implement the conversation state management logic
through the agent's other methods, which will mostly likely be boilerplate code.

In a scenario with built-in agents and custom threads, the developer experience
is nearly identical, as in either case the developer must ensure
the agent's `run` method is compatible with the thread or general state object.

In a scenario with custom agents and custom threads, the developer experience
is nearly identical, as in either case the developer must ensure
the agent's `run` method is compatible with the thread or general state object,
and that the state management logic is implemented in the agent or the thread.

| Scenario | Agent with Conversation State | Agent without Conversation State |
|----------|------------------------------------------|---------------------------------------------|
| Built-in Agents, Built-in Threads | Simpler -- it should just work as there is no compatibility issue at runtime | Developer must ensure thread compatibility with agent's `run` method at runtime |
| Custom Agents, Built-in Threads | Developer must implement state management methods on the agent. | Simpler, as thread abstraction is provided by the framework and agent can use it directly |
| Built-in Agents, Custom Threads | Developer must ensure compatibility of the custom thread or state with agent's `run` method | Developer must ensure compatibility of the custom thread with agent's `run` method |
| Custom Agents, Custom Threads | Developer is fully responsible for implementing state management. | Developer is fully responsible for implementing state management. |

Overall, the agent without conversation state abstraction
provides a simpler and more consistent developer experience, as it relies on
the thread abstraction provided by the framework. The downside is that 
developer must ensure the thread used is compatible with the agent's `run` method
-- this can be mitigated by enforcing strong types and validation, as well as
built-in factory methods for creating new threads given the agent type.

Another factor to consider is that Semantic Kernel already has agent abstraction
that passes a thread per invocation, so it is easier for us to migrate to the
new interface. 

**Decision**: We will use the agent abstraction without conversation state 
as the interface for agents in the framework.

> **We should continue to question this decision as we implement more agents and workflows, and revisit the design.**