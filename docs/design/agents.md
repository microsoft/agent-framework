# Agents

The design goal is a smooth experience to create single agent from
agent components.

## `Agent` base class

The `Agent` base class is an abstract class that inherits from `Actor` base class
in the `agent_runtime` package. It is the base class for all agents in the framework.

There is the code for the `Agent` base class:

```python
from typing import Generic, TypeVar
from abc import ABC, abstractmethod
from agent_runtime import Actor, ActorInstantiationContext
from agent_framework import RunContext, Message, MessageBatch, Memory, ModelClient, Thread, MCPServer, Tool

TInput = TypeVar("TInput", bound=Message)
TOutput = TypeVar("TOutput", bound=Message)

class Agent(Actor, ABC, Generic[TInput, TOutput]):
    def __init__(
        self, 
        name: str,
        model_client: ModelClient,
        memory: Memory,
        thread: Thread,
        mcp_servers: list[MCPServer],
        tools: list[Tool], 
    ) -> None:
        super().__init__(name=name)
        self.memory = memory
        self.model_client = model_client
        self.mcp_servers = mcp_servers
        self.tools = tools
        self.thread = thread

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

        The factory method is called by the runtime to create actor instance.
        """
        ...
```

The experience for creating a custom single agent is shown below.

```python
from agent_framework import Agent, MessageBatch, Message

class MyMessage(Message):
    ...

class ToolCallingAgent(Agent[MyMessage, MyMessage]):
    async def run(self, messages: MessageBatch[MyMessage], context: RunContext) -> MessageBatch[MyMessage]:
        # Update the thread with the messages.
        await thread.update(messages.to_model_messages())
        # Create a response using the model client.
        create_result = await self.model_client.create(thread=thread)
        # Update the thread with the response.
        await thread.update(create_result.to_model_messages())
        if create_result.is_tool_call():
            # Call the tools with the tool calls in the response.
            tool_result = await self.mcp_server.call_tools(create_result.tool_calls)
            # Update the thread with the tool result.
            await thread.update(tool_result.to_model_messages())
            # Return the tool result as the response.
            return MessageBatch(messages=tool_result.messages)
        else: 
            # Return the response as the result.
            return MessageBatch(messages=create_result.messages)
    
    @classmethod
    async def create(cls, context: ActorInstantiationContext) -> "ToolCallingAgent":
        # Create the agent instance from the context.
        return ToolCallingAgent(
            name=context.name,
            model_client=OpenAIChatCompletionClient(
                api_key=context.api_key,
                model=context.model,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                service_id=context.user_id,
            ),
            ...
        )

```
