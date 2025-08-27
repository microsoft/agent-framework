# Migration from Autogen to Agent Framework

This is a migration guide for users of [Autogen](https://microsoft.github.io/autogen/stable/) to `Agent Framework`.


## What is Agent Framework?
Agent Framework is an asynchronous, event-driven Agentic framework library which merges the best ideas and features from both `Autogen` and `Semantic Kernel`. The high level structure of Agent Framework is similar to that of Autogen, including the components used to build complex workflows.

This guide will focus on translating the various components from `Autogen 0.4+` to `Agent Framework`

## Package structure

Autogen is broken down into several component packages, including `autogen_agentchat`, `autogen_core`, `autogen_ext`, etc. Objects are also nested into logical subpackages.

The Agent Framework package stucture opts toward a flatter structure. The packages are broken into the core package, and model-specific packages; including `agent-framework`, `agent-framework-azure`, `agent-framework-openai`, etc. However, each package's contents can be accessed through the `agent_framework` namespace as well. For example, `OpenAIChatClient` can be accessed with either `agent-framework-openai.OpenAIChatClient` or `agent_framework.openai.OpenAIChatClient`. Most objects, outside of specific components like errors or telemetry functionality, are contained within the top level package.

## Model Client

### Client Configuration

In Autogen, a self-describing configuration was used create its various components. For example:

```python
from autogen_core.models import ChatCompletionClient

config = {
    "provider": "OpenAIChatCompletionClient",
    "config": {
        "model": "gpt-4o",
        "api_key": "sk-xxx" # os.environ["...']
    }
}

model_client = ChatCompletionClient.load_component(config)
```

Agent Framework currently requires its components to be configured individually with a configuration dictionary, though in the future we will be implementing Copilot Studio Declarative Language (CPSDL) our official the declarative specification.

```python
from agent_framework.openai import OpenAIChatClient

config = {
    "ai_model_id": "gpt-4o",
    "api_key": "sk-xxx" # os.environ["..."]
}

chat_client = OpenAIChatClient.from_dict(config)
```

### Use model client directly

The model clients themselves can be configured nearly identically to Autogen, with the exception of the occasional parameter name change

OpenAI:
```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    ai_model_id="gpt-4o",
    api_key="sk-xxx"
)
```

Azure OpenAI:
```python
from agent_framework.azure import AzureChatClient

client = AzureChatClient(
    deployment_name="gpt-4o",
    endpoint="https://<your-endpoint>.openai.azure.com/",
    api_key="sk-xxx"
)
```

## Chat Agent

In Autogen, a specialized agent implementation was created for use as an assistant agent. With Agent Framework, a chat agent can be created from the model client itself.

```python
from agent_framework.openai import OpenAIChatClient

agent = OpenAIChatClient(
    ai_model_id="gpt-4o",
    api_key="sk-xxx",
).create_agent(
    name="assistant",
    instructions="You are a helpful assistant.",
)
```

The functions `run` and `run_streaming` are analogous to autogen's `run` and `run_stream` calls, with both being asynchronous and returning an async iterable for the latter.

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