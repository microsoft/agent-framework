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

## `Agent` protocol

```python
class Agent(Protocol):
    """The protocol for all agents in the framework."""

    async def run(
        self, 
        thread: Thread,
        context: Context,
    ) -> Result:
        """The method to run the agent on a thread of messages, and return the result.

        Args:
            thread: The thread of messages to process: it may be a local thread
                or a stub thread that is backed by a remote service.
            context: The context for the current invocation of the agent, providing
                access to the event channel, and human-in-the-loop (HITL) features.
        
        Returns:
            The result of running the agent, which includes the final response
            and the updated thread.
        """
        ...


@dataclass
class Context:
    """The context for the current invocation of the agent."""
    event_handler: EventHandler
    """The event consumer for handling events emitted by the agent."""
    user_input_source: UserInputSource
    """The user input source for requesting for user input during the agent run."""
    ... # Other fields, could be extended to include more for application-specific needs.


@dataclass
class Result:
    """The result of running an agent."""
    thread: Thread
    final_response: Message
    ... # Other fields, could be extended to include more for application-specific needs.
```

## `ToolCallingAgent` example

Here is an example of a custom agent that calls a tool and returns the result.
The `ToolCallingAgent` implements the `Agent` base class and
it implements the `run` method to process incoming messages and call tools if needed.

```python
class ToolCallingAgent(Agent):
    def __init__(
        self, 
        model_client: ModelClient,
        tools: list[Tool],
    ) -> None:
        self.model_client = model_client
        self.tools = tools

    async def run(self, thread: Thread, context: Context) -> Result:
        # Create a response using the model client, passing the thread and context.
        create_result = await self.model_client.create(thread, context, tools=self.tools)
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
            await thread.append(tool_result.to_messages())
            # Return the tool result as the response.
            return Result(
                thread=thread,
                final_response=tool_result,
            )
        else: 
            # Return the response as the result.
            return Result(
                thread=thread,
                final_response=create_result,
            )
```

Things to note in the implementation of the `run` method:
- Orchestration of tools and model is completly customizable.
- Components such as `thread` and `model_client` interacts smoothly with little boilerplate code.
- The `context` parameter provides convenient access to the workflow run fixtures such as event channel.

An agent doesn't need to use components provided by the framework to implement the agent interface.

For example, in a multi-agent workflow, we may need a verification agent in a using deterministic
logic to critic another agent's response.

```python
class CriticAgent(Agent):
    def __init__(self) -> None:
        self.verification_logic = ... # Some verification logic, e.g. a set of rules.

    async def run(self, thread: Thread, context: Context) -> Result:
        # Use the verification logic to verify the last message in the thread.
        response = thread.get_last_message()
        is_verified = self.verification_logic.verify(response)
        if is_verified:
            final_response = Message("The response is verified.")
        else:
            final_response = Message("The response is not verified.")
        
        return Result(
            thread=thread,
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
thread = [
    Message("Hello"),
    Message("Can you find the file 'foo.txt' for me?"),
]

# Create a context that uses a handler that prints emitted events to the console, 
# and a user input source that reads from the console.
context = Context(event_handler=ConsoleEventHandler(), user_input_source=ConsoleUserInputSource())

# Run the agent with the thread and context.
result = await agent.run(thread, context)
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
Whereas the memory is can be set through the constructor of the agent.

See the [Memory](memory.md) design document for more details on how memory
is used in the framework.

It is up to the application to decide whether to reuse state across different
user sessions. The framework should provide the necessary methods and storage layer integration
for persisting and retrieving state, but the application should decide how to use them.

## Run agent concurrently

If the agent just call models and tools that are stateless, 
we can run the same instance of the agent concurrently.

```python
# Create threads for concurrent tasks.
thread1 = [
    Message("Hello"),
    Message("Can you find the file 'foo.txt' for me?"),
]
thread2 = [
    Message("Hello"),
    Message("Can you find the file 'bar.txt' for me?"),
]

# Run the agent concurrently on multiple threads.
results = await asyncio.gather(
    agent.run(thread1, context),
    agent.run(thread2, context),
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
result = await agent.run(thread, RunContext(event_channel="console"))
```
