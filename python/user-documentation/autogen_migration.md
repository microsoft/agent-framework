# Migration from AutoGen to Agent Framework

This is a migration guide for users of [AutoGen](https://github.com/microsoft/autogen) to `Agent Framework`.


## What is Agent Framework?
Agent Framework is an asynchronous, event-driven Agentic framework library which merges the best ideas and features from both `AutoGen` and `Semantic Kernel`. The high level structure of Agent Framework is similar to that of AutoGen, including the components used to build complex workflows. Agent Framework additionally supports the latest client protocols as first class members, including the `OpenAI Responses` and the `Azure AI Foundry` APIs.

This guide will focus on translating the various components from `AutoGen 0.4+` to `Agent Framework`.

## Package structure

AutoGen is broken down into several component packages, including `autogen_agentchat`, `autogen_core`, `autogen_ext`, etc. Objects are also nested into logical subpackages.

The Agent Framework package structure opts toward a flatter structure. The packages are broken into the core package, and several sub-packages; such as `azure`, `openai`, `workflow`, etc. However, each package's contents can and should be accessed through the `agent_framework` namespace and installed using the provided extra to ensure all dependencies are present and have the right versions. However this does mean that for example, `AzureChatClient` can be accessed with either `agent_framework_azure.AzureChatClient` or `agent_framework.azure.AzureChatClient`. Most objects, outside of specific components like exceptions or telemetry functionality, are contained within the top level package.

## Model Client

### Use model client directly

The model clients themselves can be configured nearly identically to AutoGen, with the exception of the occasional parameter name change. Agent Framework has the additional capability of pulling most client configuration options from environment variables. The clients are also similar in usage patterns:

#### AutoGen:
OpenAI:
```python
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

client = OpenAIChatCompletionClient(
    model="gpt-4o",
    api_key="sk-xxx"
)
response = client.create(
    messages=[UserMessage(content="hello world", source="user")]
)
```

Azure OpenAI:
```python
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

client = AzureOpenAIChatCompletionClient(
    azure_deployment="gpt-4o",
    azure_endpoint="https://<your-endpoint>.openai.azure.com/",
    model="gpt-4o",
    api_version="2024-09-01-preview",
    api_key="sk-xxx",
)
response = await client.create(
    messages=[UserMessage(content="hello world", source="user")]
)
```

#### Agent Framework:
OpenAI:
```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    ai_model_id="gpt-4o", # pulled from OPENAI_CHAT_MODEL_ID if parameter is not provided
    api_key="sk-xxx" # pulled from OPENAI_API_KEY if parameter is not provided
)
response = await client.get_response(messages="hello world")
```

Azure OpenAI:
```python
from agent_framework.azure import AzureChatClient

client = AzureChatClient(
    deployment_name="gpt-4o", # pulled from AZURE_OPENAI_CHAT_DEPLOYMENT_NAME if parameter is not provided
    endpoint="https://<your-endpoint>.openai.azure.com/", # pulled from AZURE_OPENAI_ENDPOINT if parameter is not provided
    api_key="sk-xxx" # pulled from AZURE_OPENAI_API_KEY if parameter is not provided
)
response = await client.get_response(messages="hello world")
```

### Client Configuration

In AutoGen, a configuration json is used create its various components. For example:

```python
from autogen_core.models import ChatCompletionClient

config = {
    "provider": "OpenAIChatCompletionClient",
    "config": {
        "model": "gpt-4o",
        "api_key": "sk-xxx" # os.environ["...']
    }
}

client = ChatCompletionClient.load_component(config)
```

Agent Framework currently requires its components to be configured individually with a configuration dictionary, though there may be changes to this in the future for improved developer experience.

```python
from agent_framework.openai import OpenAIChatClient

config = {
    "ai_model_id": "gpt-4o",
    "api_key": "sk-xxx" # os.environ["..."]
}

client = OpenAIChatClient.from_dict(config)
```

## Chat Agent

AutoGen provided a convenience [AssistantAgent](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/tutorial/agents.html#assistant-agent) class with a set of defined functionality. With Agent Framework, a similar chat agent can be created from the model client itself. The functions `run` and `run_streaming` are analogous to autogen's `run` and `run_stream` calls, with both being asynchronous and returning an async iterable for the latter.

#### AutoGen:
```python
from autogen_agentchat.base import TaskResult
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage, ModelClientStreamingChunkEvent
from autogen_ext.models.openai import OpenAIChatCompletionClient

model_client = OpenAIChatCompletionClient(
    model="gpt-4o",
    api_key="sk-xxx",
    seed=42,
    temperature=0
)

agent = AssistantAgent(
    name="assistant",
    system_message="You are a helpful assistant.",
    model_client=model_client,
    model_client_stream=True,
)
# non-streaming responses
response = await agent.run(task="write a story for me.")
print(response.content)

# streaming responses
stream = agent.run_stream(task="write a story for me.")
async for chunk in stream:
    if isinstance(chunk, ModelClientStreamingChunkEvent):
        print(chunk.content, flush=True, end="")
    elif isinstance(chunk, TaskResult):
        # The last response is a TaskResult object with the complete message.
        for message in chunk.messages:
            assert isinstance(message, TextMessage)
            print("\n\n------------\n")
            print("The complete response:", flush=True)
            print(message.content, flush=True)
```

#### Agent Framework:
```python
from agent_framework import AgentRunResponseUpdate, TextContent
from agent_framework.openai import OpenAIChatClient

agent = OpenAIChatClient(
    ai_model_id="gpt-4o",
    api_key="sk-xxx",
    seed=42,
    temperature=0
).create_agent(
    name="assistant",
    instructions="You are a helpful assistant.",
)
# non-streaming responses
response = await agent.run(messages="write a story for me.")
print(response)

# streaming responses
stream = agent.run_streaming(task="write a story for me.")
full_message: str = ""
async for message in response:
    assert message is not None
    assert isinstance(message, AgentRunResponseUpdate)
    for chunk in message.contents:
        if isinstance(chunk, TextContent) and chunk.text:
            full_message += chunk.text
            print(chunk, flush=True, end="")
print("\n\n------------\n")
print("The complete response:", flush=True)
print(full_message, flush=True)
```

Alternatively, the chat agent can be created manually

```python
from agent_framework import ChatClientAgent
from agent_framework.openai import OpenAIChatClient


client = OpenAIChatClient(
    ai_model_id="gpt-4o",
    api_key="sk-xxx",
)

agent = ChatClientAgent(
    client=client,
    instructions="You are a helpful assistant.",
    name="assistant",
)
```


## Message Types

### Union/Inherited Types

#### AutoGen

`LLMMessage`: Union of `SystemMessage`, `UserMessage`, `AssistantMessage`, and `FunctionExecutionResultMessage`.

`BaseChatMessage`: A base class. Default provided child classes are `StructuredMessage`, `TextMessage`, `StopMessage`, `HandoffMessage`, `ToolCallSummaryMessage`, and `MultiModalMessage`.

`BaseAgentEvent`: A base class. Default provided child classes are `ToolCallRequestEvent`, `CodeGenerationEvent`, `CodeExecutionEvent`, `ToolCallExecutionEvent`, `UserInputRequestedEvent`, `MemoryQueryEvent`, `ModelClientStreamingChunkEvent`, `ThoughtEvent`, `SelectSpeakerEvent`, and `SelectorEvent`.

#### Agent Framework

`AIContents`: Union of `TextContent`, `DataContent`, `TextReasoningContent`, `UriContent`, `FunctionCallContent`, `FunctionResultContent`, `ErrorContent`, `UsageContent`, `HostedFileContent`, or `HostedVectorStoreContent`.

### Input Types

AutoGen uses distinct message types between their clients and chat agents. Clients accept a list of `LLMMessage` types. Each message type serves a unique purpose and are not interchangeable. Agents on the other hand accept strings or any object or list of objects inherited from the `BaseChatMessage` type.

Agent Framework on the other hand uses the same type across both clients and chat agents. In both cases, the accepted types are strings, list of strings, `ChatMessage`, or list of `ChatMessage`. `ChatMessage` itself contains a list of `AIContents`.

### Output Types

AutoGen's clients and chat agents similarly produce different output types. These are further split by their streaming and non-streaming calls.

|                   | client                             | agent        |
| ----------------- | ---------------------------------- | ------------ |
| **non-streaming** | `CreateResult`                     | `TaskResult` |
| **streaming**     | stream of string or `CreateResult` | stream of `BaseAgentEvent` or `BaseChatMessage` or `TaskResult` |

`CreateResult` contains a string or a list of `FunctionCall`.
`TastResult` contains a sequence of `BaseAgentEvent` or `BaseChatMessage`.

Agent Framework's outputs follow a similar pattern

|                   | client                         | agent              |
| ----------------- | ------------------------------ | ------------------ |
| **non-streaming** | `ChatResponse`                 | `AgentRunResponse` |
| **streaming**     | stream of `ChatResponseUpdate` | stream of `AgentRunResponseUpdate` |

`ChatResponse` and `AgentRunResponse` contain a list of `ChatMessage`.
`ChatResponseUpdate` and `AgentRunResponseUpdate` contain a list of `AIContents`.
