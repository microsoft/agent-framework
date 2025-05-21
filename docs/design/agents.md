# Agents

The design goal is a smooth experience to create single agent from
agent components, and to deploy and run the agent through a runtime.

## Design Choices

There are two main design choices for an agent abstraction:
1. **Stateful Agent**: Agent is a class that implements a `run` method while
    maintaining a state. For some use cases, the agent is ephemeral and created
    with a task and an externalized state for the task. For other use cases, 
    the agent maintains a state across different tasks.
2. **Stateless Agent**: Agent is a configuration (i.e., a data class
    or a Pydantic base model) with model client, tools, MCP servers, and other
    components). The agent itself is stateless and a separate function or runner
    class is used to run the agent with a task and an externalized state.

The table below provides breakdown of the two design choices:

| Aspect | Stateful Agent | Stateless Agent |
|--------|----------------|-----------------|
| Task  | Handles task directly and updates its state | Runs task with a runner and exporting the state as the output |
| Statefulness | Allowed to maintains state depending on implementation | Stateless |
| State management | State is managed by the agent class, can be exported, imported, and reseted through methods | State is temporarily managed by the runner during a run, and completely exported as part of the output |
| State serialization | State is custom and up to the implementation, while built-in states are serializable | State is defined by the framework and must be serializable |
| Components | Interacts with components directly within itself | Interacts with components through the runner |
| Parameters | Parameters are passed to the constructor | Parameters are passed to the constructor |
| Customization | Customizable by subclassing the agent class | Customizable by creating a new runner function or class |
| Workflow behavior | A stateful node in a workflow -- depending on implementation it could be stateless | A stateless node in a workflow and an externalized state passes through the nodes in the workflow |
| Workflow topology | Workflow can be defined either by the control flow (execution order) or the data flow (message delivery), or both together | Control flow and data flow are the same, similar to an ETL pipeline |

For **stateful agents**, see the [Stateful Agent](#stateful-agent) section below.
For **stateless agents**, see the [Stateless Agent](#stateless-agent) section below.

## Stateful Agent

### `Agent` base class

The `Agent` base class is an abstract class all agents in the framework
must inherit from. 

There is the code for the `Agent` base class:

```python
TInput = TypeVar("TInput", bound=Message)
TOutput = TypeVar("TOutput", bound=Message)

class Agent(ABC, Generic[TInput, TOutput]):
    """The base class for all agents in the framework.

    Each agent is a subclass of this class, and implements the `run` method
    to process incoming messages.

    Each agent class should specify the input and output message types it can process
    and produce. The input and output types are used by workflow for validation and routing.
    """

    @abstractmethod
    async def run(self, messages: Sequence[TInput], context: RunContext) -> Sequence[TOutput]:
        """The main method to run the agent.

        Each agent will have its own implementation of this method, and specifiy
        the types of the input and output messages it can process.
        
        The input and output types are used by workflow for validation and routing.

        The context provides access to fixtures such as event channels,
        user input, and shared resources.
        """
        ...
    
```

### `ToolCallingAgent` example

Here is a simple example of a custom agent that calls a tool and returns the result.
Its input and output message types are custom-defined message types that inherit from the `Message` base class.
The `ToolCallingAgent` class is a subclass of the `Agent` base class. 
It implements the `run` method to process incoming messages and call tools if needed.

```python
class MyMessage(Message):
    ...

class ToolCallingAgent(Agent[MyMessage, MyMessage]):
    def __init__(
        self, 
        model_client: ModelClient,
        thread: Thread,
        tools: list[Tool],
        input_guardrails: list[InputGuardrails[MyMessage]],
    ) -> None:
        super().__init__(name=name)
        self.model_client = model_client
        self.tools = tools
        self.thread = thread
        self.input_guardrails = input_guardrails

    async def run(self, messages: Sequence[MyMessage], context: RunContext) -> Sequence[MyMessage]:
        # Raise exception if the guardrail is triggered.
        await self.input_guardrails.trip_wire(messages)
        # Update the thread with the messages.
        await self.thread.update(messages)
        # Create a response using the model client.
        create_result = await self.model_client.create(thread=thread)
        # Emit the event to notify the workflow consumer of a model response.
        await context.emit(ModelResponseEvent(create_result))
        # Update the thread with the response.
        await self.thread.update(create_result.to_model_messages())
        if create_result.is_tool_call():
            # Get user approval for the tool call.
            approval = await context.get_user_approval(create_result.tool_calls)
            if not approval:
                # ... return a canned response.
            # Call the tools with the tool calls in the response.
            tool_result = await self.mcp_server.call_tools(create_result.tool_calls)
            # Emit the event to notify the workflow consumer of a tool call.
            await context.emit(ToolCallEvent(tool_result))
            # Update the thread with the tool result.
            await self.thread.update(tool_result.to_model_messages())
            # Return the tool result as the response.
            return list(tool_result.messages)
        else: 
            # Return the response as the result.
            return list(create_result.messages)
```

Things to note in the implementation of the `run` method:
- Orchestration of tools and model is completly customizable.
- Components such as `thread` and `model_client` interacts smoothly with little boilerplate code.
- The `context` parameter provides convenient access to the workflow run fixtures such as event channel.

### Run agent directly

Developer can instantiate a subclass of `Agent` directly using it's constructor, 
and run it by calling the `run` method.

```python
@FuntionTool
def my_tool(input: str) -> str:
    return f"Tool result for {input}"

thread = UnboundedThread()
model_client = OpenAIChatCompletionClient("gpt-4.1")
agent = ToolCallingAgent(
    model_client=model_client, 
    thread=thread,
    tools=[my_tool],
    guardrails=[JailbreakGuardrail()]
)

# Create a task as a message batch.
task = [MyMessage("Hello")]

# Run the agent with the task and an new context that emits events to the console.
result = await agent.run(task, ConsoleRunContext())
```

### Using Foundry Agent Service

The framework offers a built-in agent class for users of the Foundry Agent Service.
The agent class essentially acts as a proxy to the agent hosted by the Foundry Agent Service.

```python
agent = FoundryAgent(
    name="my_foundry_agent",
    project_client="ProjectClient",
    agent_id="my_agent_id", # If not provided, a new agent will be created.
    thread_id="my_thread_id", # If not provided, a new thread will be created.
    deployment_name="my_deployment",
    instruction="my_instruction",
    ... # Other parameters for the agent creation.
)

# Create a task as a message batch.
task = [Message("Hello")]

# Run the agent with the task and an new context that emits events to the console.
result = await agent.run(task, RunContext(event_channel="console"))
```
