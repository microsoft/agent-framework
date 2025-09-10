# Microsoft Agent Framework Multi-Turn Conversations and Threading

The Microsoft Agent Framework provides built-in support for managing multi-turn conversations with AI agents. This includes maintaining context across multiple interactions. Different agent types and underlying services that are used to build agents may support different threading types, and the agent framework abstracts these differences away, providing a consistent interface for developers.

For example, when using a ChatClientAgent based on a foundry agent, the conversation history is persisted in the service. While, when using a ChatClientAgent based on chat completion with gpt-4.1 the conversation history is in-memory and managed by the agent.

The differences between the underlying threading models are abstracted away via the `AgentThread` type.

## AgentThread lifecycle

### AgentThread Creation

`AgentThread` instances can be created in two ways:

1. By calling `GetNewThread` on the agent.
1. By running the agent and not providing an `AgentThread`. In this case the agent will create a throwaway `AgentThread` with an underlying thread which will only be used for the duration of the run.

Some underlying threads may be persistently created in an underlying service, where the service requires this, e.g. Foundry Agents or OpenAI Responses. Any cleanup or deletion of these threads is the responsibility of the user.


### AgentThread Storage

`AgentThread` instances can be serialized and stored for later use. This allows for the preservation of conversation context across different sessions or service calls.

For cases where the conversation history is stored in a service, the serialized `AgentThread` will contain an
id of the thread in the service.
For cases where the conversation history is managed in-memory, the serialized `AgentThread` will contain the messages
themselves.


## Agent/AgentThread relationship

`AIAgent` instances are stateless and the same agent instance can be used with multiple `AgentThread` instances.

Not all agents support all thread types though. For example if you are using a `ChatClientAgent` with the responses service, `AgentThread` instances created by this agent, will not work with a `ChatClientAgent` using the Foundry Agent service.
This is because these services both support saving the conversation history in the service, and the `AgentThread`
only has a reference to this service managed thread.

It is therefore considered unsafe to use an `AgentThread` instance that was created by one agent with a different agent instance, unless you are aware of the underlying threading model and its implications.

## Threading support by service / protocol

| Service | Threading Support |
|---------|--------------------|
| Foundry Agents | Service managed persistent threads |
| OpenAI Responses | Service managed persistent threads OR in-memory threads |
| OpenAI ChatCompletion | In-memory threads |
| OpenAI Assistants | Service managed threads |
| A2A | Service managed threads |

