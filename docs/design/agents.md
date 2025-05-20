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
    """The base class for all agents in the framework.

    Each agent is a subclass of this class, and implements the `run` method
    to process incoming messages.

    Each agent class should specify the input and output message types it can process
    and produce. The input and output types are used by workflow for validation and routing.
    """

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
        model_client: ModelClient
        thread: Thread
        tools: list[Tool]
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
```

Things to note in the implementation of the `run` method:
- Orchestration of tools and model is completly customizable.
- Components such as `thread` and `model_client` interacts smoothly with little boilerplate code.
- The `context` parameter provides convenient access to the workflow run fixtures such as event channel.

## Run agent directly

Developer can instantiate a subclass of `Agent` directly using it's constructor, 
and run it by calling the `run` method.

```python
from agent_framework import Agent, MessageBatch, OpenAIChatCompletionClient, UnboundedThread, RunContext, FunctionTool

@FuntionTool
def my_tool(input: str) -> str:
    return f"Tool result for {input}"

thread = UnboundedThread()
model_client = OpenAIChatCompletionClient("gpt-4.1")
agent = ToolCallingAgent(
    model_client=model_client, 
    thread=thread,
    tools=[my_tool],
)

# Create a task as a message batch.
task = MessageBatch[MyMessage](messages=[MyMessage("Hello")])

# Run the agent with the task and an new context that emits events to the console.
result = await agent.run(task, RunContext(event_channel="console"))
```

## Run agent on a runtime

When the agent is deployed through a runtime, it is instantiated and run by the runtime
instead of the developer's application.
The runtime can be local or remote, in which case the agent is hosted in a separate process.

When creating an instance of the agent, we need to provide the configuration
parameters for the components so that the runtime can create the components
needed to create the agent instance. The configuration parameters must be
JSON serializable as the agent instance may be created in a different process.

```python
# Could be a local or remote runtime.
runtime = AgentRuntime()

# Register the agent class with the runtime, under the type name same as the class name.
# This is the default behavior but can be overridden by specifying a different type name.
# Configuration parameters are provided to the runtime to create the components
runtime.register(ToolCallingAgent, {
    "model_client": {
        "type": "OpenAIChatCompletionClient",
        "model": "gpt-4.1",
    },
    "thread": {
        "type": "UnboundedThread",
    },
    "tools": [my_tool], # NOTE: FunctionTool may be tricky as it's not serializable.
})

# Register the agent class with a different type name "MyAgent", this is useful
# when we want to register the same class to different type names with different configurations.
# In this case, we are using the object directly instead of the config -- only
# works for local runtime.
runtime.register(ToolCallingAgent, {
    "model_client": OpenAIChatCompletionClient("gpt-4.1"),
    "thread": UnboundedThread(),
    "tools": [my_tool],
}, type_name="MyAgent")
```

Once the agent is registered with the runtime,
we can then ask the runtime to create an instance of the agent,
and then run it.

```python
# Get or create an instance of the agent with a unique (type name, key), 
# and returns a stub for the agent instance. 
# The key is optional, if not provided, a unique key for the type name 
# will be generated by the runtime.
stub = runtime.get(ToolCallingAgent, key="123")
# If agent instance with the same (type name, key) already exists,
# the runtime will use the existing instance.

# We can also use the full agent identifier with the type name and the key.
stub = runtime.get("ToolCallingAgent/123")

# Create a task as a message batch.
task = MessageBatch[MyMessage](messages=[MyMessage("Hello")])

# Run the agent with the task and an new context that emits events to the console.
result = await stub.run(task, RunContext(event_channel="console"))

# We can also run the agent with RunContext created by the runtime,
# which will emit events to the event channel configured for the runtime.
# This is useful for remote runtime where the event channel maybe hosted 
# in a different process or using a cloud service.
result = await stub.run(task, runtime.create_run_context())
```

## Scoping the agent instance

In a multi-tenant environment, we may want to scope the agent instance to a user session.
The agent instance can be scoped to a user session by providing a unique key
when creating the agent instance.

```python
session_id = "user_session_id"

# Get an instance of the agent associated with the user session.
stub = runtime.get(ToolCallingAgent, key=session_id)
```

## Reusing or sharing components

If agent instances are created directly by the application, or registered to
the runtime with concrete objects (local only), then the components can be reused
or shared by simply passing the same component instances to different agent instances.

> **Note**: this is just an idea for now. We need to think about the implications.
> Perhaps we should make all components actors as well and let the runtime manage them.
> This also makes it easy to express "agent-as-tool" pattern where the agent is
> hosted on the runtime and can be used as a tool in another agent.

If the agent instances are created by the runtime with configuration parameters,
then the components themselves must be registered with the runtime.

```python
# Register the components with the runtime, so that they can be reused.
runtime.register(OpenAIChatCompletionClient, {
    "model": "gpt-4.1",
}, type_name="my_model_client")
runtime.register(UnboundedThread, {}, type_name="my_thread")

client_stub = runtime.get(OpenAIChatCompletionClient, key="client_123")
thread_stub = runtime.get(UnboundedThread, key="thread_123")

# Register the agent class with the runtime, and use the component stubs.
runtime.register(ToolCallingAgent, {
    "model_client": client_stub,
    "thread": thread_stub,
    "tools": [my_tool],
}, type_name="my_agent_1")
# Register another agent class with the same components.
runtime.register(ToolCallingAgent, {
    "model_client": client_stub,
    "thread": thread_stub,
    "tools": [my_tool],
}, type_name="my_agent_2")
```

The runtime will make sure the components are created only once, and the same component instances
will be used for all agent instances that use the same component stubs.


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

## Using Foundry Agent Service

The framework offers a built-in agent class for users of the Foundry Agent Service.
The agent class essentially acts as a proxy to the agent hosted by the Foundry Agent Service,
whether the agent is running directly or through an agent runtime.

```python
from agent_framework import FoundryAgent, MessageBatch, RunContext

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
task = MessageBatch[Message](messages=[Message("Hello")])

# Run the agent with the task and an new context that emits events to the console.
result = await agent.run(task, RunContext(event_channel="console"))
```

When using agent runtime, the agent class can be registered with the runtime
and then run through the runtime.

```python
runtime = AgentRuntime()
runtime.register(FoundryAgent, {
    "project_client": "ProjectClient",
    "agent_id": "my_agent_id", # If not provided, a new agent will be created.
    "thread_id": "my_thread_id", # If not provided, a new thread will be created.
    "deployment_name": "my_deployment",
    "instruction": "my_instruction",
    ... # Other parameters for the agent creation.
})

# Create an instance of the agent with a unique ID,
# and returns a reference to the agent instance.
stub = runtime.get(FoundryAgent, key="123")

# Create a task as a message batch.
task = MessageBatch[Message](messages=[Message("Hello")])

# Run the agent with the task and a context created by the runtime.
result = await stub.run(task, runtime.create_run_context())
```
