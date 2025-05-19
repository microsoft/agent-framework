# Agents

The design goal is a smooth experience to create single agent from
agent components, and to deploy and run the agent through a runtime.

## `Agent` base class

The `Agent` base class is an abstract class that inherits from `Actor` base class
in the `agent_runtime` package. It is the base class for all agents in the framework.

There is the code for the `Agent` base class:

```python
from typing import Generic, TypeVar
from abc import ABC, abstractmethod
from agent_runtime import Actor, ActorInstantiationContext
from agent_framework import RunContext, Message, MessageBatch, ModelClient, Thread, Tool

TInput = TypeVar("TInput", bound=Message)
TOutput = TypeVar("TOutput", bound=Message)

class Agent(Actor, ABC, Generic[TInput, TOutput]):

    @abstractmethod
    async def run(self, messages: MessageBatch[TInput], context: RunContext) -> MessageBatch[TOutput]:
        """The main method to run the agent. This method will be called by the
        `on_messages` method of the `Actor` base class to process incoming messages.

        Each agent will have its own implementation of this method, and specifiy
        the types of the input and output messages it can process.
        
        The input and output types are used by workflow for validation and routing.

        The context provides access to workflow run fixtures such as event channels,
        user input, and shared resources.
        """
        ...
    
    
    @classmethod
    @abstractmethod
    async def create(cls, context: ActorInstantiationContext) -> "Agent":
        """The factory method to create an agent instance from the context provided
        by the runtime: e.g., the user session. Typically, each component will be
        created based on the context provided here. So each component will also
        be associated with the user session.

        The factory method is called by the runtime to create actor instance
        managed by the runtime.

        The `context` varaible provides access to the various components
        that are needed to create the agent instance. The components are
        created by the runtime and passed to the factory method.
        """
        ...
```

## `ToolCallingAgent` example

Here is a simple example of a custom agent that calls a tool and returns the result.
Its input and output message types are custom-defined message types that inherit from the `Message` base class.
The `ToolCallingAgent` class is a subclass of the `Agent` base class. 
It implements the `run` method to process incoming messages and call tools if needed.

```python
from agent_framework import Agent, MessageBatch, Message

class MyMessage(Message):
    ...

class ToolCallingAgent(Agent[MyMessage, MyMessage]):
    def __init__(
        self, 
        name: str,
        model_client: ModelClient,
        thread: Thread,
        tools: list[Tool], 
    ) -> None:
        super().__init__(name=name)
        self.model_client = model_client
        self.tools = tools
        self.thread = thread

    async def run(self, messages: MessageBatch[MyMessage], context: RunContext) -> MessageBatch[MyMessage]:
        # Update the thread with the messages.
        await self.thread.update(messages.to_model_messages())
        # Create a response using the model client.
        create_result = await self.model_client.create(thread=thread)
        # Emit the event to notify the workflow consumer of a model response.
        await context.emit(ModelResponseEvent(create_result))
        # Update the thread with the response.
        await self.thread.update(create_result.to_model_messages())
        if create_result.is_tool_call():
            # Call the tools with the tool calls in the response.
            tool_result = await self.mcp_server.call_tools(create_result.tool_calls)
            # Emit the event to notify the workflow consumer of a tool call.
            await context.emit(ToolCallEvent(tool_result))
            # Update the thread with the tool result.
            await self.thread.update(tool_result.to_model_messages())
            # Return the tool result as the response.
            return MessageBatch(messages=tool_result.messages)
        else: 
            # Return the response as the result.
            return MessageBatch(messages=create_result.messages)
    
    @classmethod
    async def create(cls, context: ActorInstantiationContext) -> "ToolCallingAgent":
        return cls(
            name=context.name,
            model_client=context.get("model_client", type=ModelClient),
            thread=context.get("thread", type=Thread),
            tools=context.get("tools", type=list[Tool]),
        )
```

Things to note in the implementation of the `run` method:
- Orchestration of tools and model is completly customizable.
- Components such as `thread` and `model_client` interacts smoothly with little boilerplate code.
- The `context` parameter provides convenient access to the workflow run fixtures such as event channel.

## Run the agent directly

Developer can instantiate a subclass of `Agent` directly using it's constructor, 
and run it by calling the `run` method.

```python
from agent_framework import Agent, MessageBatch, OpenAIChatCompletionClient, UnboundedThread, RunContext, Tool

@Tool
def my_tool(input: str) -> str:
    return f"Tool result for {input}"

thread = UnboundedThread()
model_client = OpenAIChatCompletionClient("gpt-4.1")
agent = ToolCallingAgent(
    "my_agent", 
    model_client=model_client, 
    thread=thread,
    tools=[my_tool],
)

# Create a task as a message batch.
task = MessageBatch[MyMessage](messages=[MyMessage("Hello")])

# Run the agent with the task and an new context that emits events to the console.
result = await agent.run(task, RunContext(event_channel="console"))
```

## Run the agent through a runtime

When the agent is deployed through a runtime, it is instantiated and run by the runtime
instead of the developer's application.
The runtime can be local or remote, in which case the agent is hosted in a separate process.

```python
# Could be a local or remote runtime.
runtime = AgentRuntime()

# Register the agent class with the runtime, under the type name same as the class name.
# This is the default behavior but can be overridden by specifying a different type name.
# At the same time we also register the components needed to create the agent instance.
# These components are passed to the factory method of the agent class to create
# the agent instance.
runtime.register(ToolCallingAgent, {
    "tools": [my_tool],
    "model_client": OpenAIChatCompletionClient("gpt-4.1"),
    "thread": UnboundedThread(),
})

# For remote runtime, we cannot pass the component objects directly.
# Instead, we pass the component type and the configuration parameters to create 
# the component instance.
# When the runtime creates the agent instance, it will also create the components
# using the parameters provided here.
# The configuration parameters must be serializable to JSON for remote runtime.
runtime.register("model_client", OpenAIChatCompletionClient, {"model": "gpt-4.1"})
runtime.register("thread", UnboundedThread, {})

# NOTE: FunctionTool is tricky to register in a remote runtime.
```

Once the agent and its dependencies are registered with the runtime,
we can then ask the runtime to create an instance of the agent,
and then run it.

```python
# Create an instance of the agent with a unique ID,
# and returns a reference to the agent instance.
stub: AgentStub = runtime.get(ToolCallingAgent, key="123")
# We can also use a full agent identifier with the type name and the key.
stub: AgentStub = runtime.get("ToolCallingAgent/123")

# Create a task as a message batch.
task = MessageBatch[MyMessage](messages=[MyMessage("Hello")])

# Run the agent with the task and an new context that emits events to the console.
result = await stub.run(task, RunContext(event_channel="console"))
```

## Deploying an agent

A agent registered with the runtime can be deployed and exposed as a service.

```python
# When registering the agent, we can specify the service ID to expose the agent as a service,
# and the protocol to use for the service.
# The protocol can be "a2a" for agent-to-agent communication.
runtime.register(ToolCallingAgent, {
    "tools": [my_tool],
    "model_client": OpenAIChatCompletionClient("gpt-4.1"),
    "thread": UnboundedThread(),
}, service_id="my_agent", protocol="a2a")

# Serve the runtime on a port.
await runtime.serve(port=8080)

# The agent can be accessed through this endpoint with a service ID and a key:
# <host_address>:8080/my_agent/123
# The protocol is a2a, the agent card is available at:
# <host_address>:8080/my_agent/123/agent.json
```


## Use Foundry Agent Service