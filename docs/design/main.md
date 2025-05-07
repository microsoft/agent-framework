# Agent Framework Design Doc (Draft)


What values does the framework provide?
- A set of configurable, extensible and high-quality components (e.g., model clients, tools, MCP workbenches and memory).
- An easy path for deploying, securing and scaling applications, both locally and in the cloud.
- A set of tools for monitoring, debugging, evaluation and optimization.
- A community of developers and users for support, ideas, and contributions, benefiting everyone in the ecosystem.

Table of Contents
- [Main Components](#main-components)
    - [Model Client](#model-client-class)
    - [Model Context](#model-context-term)
    - [Model Context Provider](#model-context-provider-term)
    - [Tool](#tool-class)
    - [Workbench](#workbench-class)
    - [Memory](#memory-class)
    - [Thread](#thread-class)
    - [Actor](#actor-class)
    - [Agent](#agent-term)
    - [Guardrails](#guardrails-term)
    - [Workflow](#workflow-class)

## Main Components

A component is a class that provides a specific functionality and can be used
independently by applications.

Components can be composed to create complex components. For example,
an agent can be composed from model clients, tools and memory,
and a tool can be composed from an agent or a workflow.
It is the responsibility of the framework to validate components
and their composition,
and ensure the lifecycle of the components are managed correctly.

Subsections with label __(class)__ describes the main components that are part of the framework,
those with label __(term)__ are logical concepts that we use to describe components.
There will be other minor components such as conditions, messages, etc., that are 
part of implementation of the main components. Those are not described here.

We do not discuss the implementation details of the components, as some of them
such as actors will be backed by the [agent runtime](https://github.com/microsoft/agent-runtime).

_Question: should components be serializable?_

### Model Client (class)

A model client is a component that implements a unified interface for
interacting with different language models. It exposes a standardized metadata
about the model it provides (e.g., model name, tool call and vision capabilities, etc.)
to support validation and composition with other components.

### Model Context (term)

Model context (or simply "context") refers to data types that are produced by
or consumed by language models. For example, Chat Completion messages,
text, images, audio, etc.

### Model Context Provider (term)

A model context provider refers to components that provides context to
language models and may be invoked using data in the context.

[Model Context Protocol](https://modelcontextprotocol.io/introduction) (MCP)
is a standard protocol that defines a model context provider.

### Tool (class)

A tool is a model context provider that can be used to invoke procedure code
and returns the result as context to the language model.
Tool can have arguments for invocation. 
The arguments must be defined using JSON schema that language model supports.

A tool may come with 

### Workbench (class)

A workbench is a model context provider that provides a set of tools sharing
common state and resource. 

_Question: should we make Workbench an extension of MCP?_

### Memory (class)

A memory is a model context provider that stores arbitrary data types while providing
an interface for retrieving context from the stored data for language models.
For example, a memory can store multi-media documents, and provide an interface
for synthesizing context from snippets of the documents.
In another example, a memory can store the past interactions with a language model,
and provide an interface for synthesizing summaries of the interactions.

Some memory may implement tool or workbench interfaces to allow models to
operate on them.

### Thread (class)

A thread is a model context provider that stores the message history
used with a chat-based language model.

### Actor (class)

An actor is a component that takes a sequence of messages and produces a stream
of messages. The data types of the messages can be built-in or defined by the application,
but they must be serializable and defined for each actor.

### Agent (term)

Agent refers to a category of actors that uses a language model to process and produce messages.
During its handling of messages, it may use thread to keep track of the interaction
with the model, invoke tools and workbenches, and store and retrieve data through memory.

A agent may not use the components provided by the framework to implement
the actor interface.
Azure AI Agent is an example of such agent: its implementation is
backed by the Azure AI Agent Service.

The framework provides a set of pre-built agents:
- ChatCompletionAgent: an agent that uses a chat-completion model to process messages
and use thread, memory, tools and workbenches in a configurable way.
- AzureAIAgent: an agent that is backed by Azure AI Agent Service.
- OpenAIAgent: an agent that is backed by OpenAI's response API.

### Guardrail (term)

Guardrail refers to a category of actors that enforce constraints on
the messages sent to or produced by other actors.
For example, a guardrail can be used to ensure the input messages to an agent
does not contain jailbreaks or malicious instructions, or that the
output messages of an agent does not contain sensitive information or harmful content.
In another example, a guardrail can be used to review code produced by an agent
is safe and following the security guidelines.

A guardrail may also be an agent, they are not mutually exclusive.

The implementaiton of some tools or agents may also uses components similar to
guardrails but that's not what being discussed here.

### Workflow (class)

A workflow is an actor consists of multiple child actors, some of which may be
agents, some of which may be guardrails, and some may be other workflows.
During its handling of messages, it invokes its child actors
in some order (could be concurrent or sequential), collects the messages
produced by the child actors, and create the output messages.

The composition of actors can be declaratively defined using a directed graph, or can
emerge from the type-based message routing defined for each actor.

## Deployment and Scaling

Agents and workflows created using this framework can be deloyed through
the [Agent Runtime](https://github.com/microsoft/agent-runtime).

## Monitoring and Debugging

## Evaluation and Optimization