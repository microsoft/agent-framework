# Agent Framework: Overview


What values does the framework provide?
- A set of configurable, extensible and high-quality components (e.g., model clients, tools, MCP workbenches and memory).
- An easy path for deploying, securing and scaling applications, both locally and in the cloud.
- A set of tools for monitoring, debugging, evaluation and optimization, both locally and in the cloud.
- A community of developers and users for support, ideas, and contributions, benefiting everyone in the ecosystem.

What is this document?
- An overview of the new framework.
- Defining the major elements of the framework and their relationships.
- Detailed design of each element and its implementation will be in a separate document.

Table of Contents
- [Main Components](#main-components)
    - [Concepts](#concepts)
        - [Component](#component)
        - [Model Context](#model-context)
        - [Actor](#actor)
    - [Component Relationships](#component-relationships)
    - [Model Client](#model-client)
    - [Vector Store and Embedding Client](#vector-store-and-embedding-client)
    - [Tool](#tool)
    - [Workbench](#workbench)
    - [Memory](#memory)
    - [Thread](#thread)
    - [Agent](#agent)
    - [Guardrail](#guardrail)
    - [Workflow](#workflow)
- [Deployment and Scaling](#deployment-and-scaling)
- [Monitoring](#monitoring)
- [Evaluation](#evaluation)
- [Debugging](#debugging)

## Main Components

### Concepts

#### Component

A component is a class that provides a specific functionality and can be used
independently by applications.

Components can be composed to create complex components. For example,
an agent can be composed from model clients, tools and memory,
and a tool can be composed from an agent or a workflow.
It is the responsibility of the framework to validate components
and their composition,
and ensure the lifecycle of the components are managed correctly.

We do not discuss the implementation details of the components, as some of them
such as actors will be backed by the [agent runtime](https://github.com/microsoft/agent-runtime).

_Question: should components be serializable?_


#### Model Context

Model context refers to content produced by or consumed by language models.
For example, text, images, function calls, tool schema are 
all examples of such data types.
These data types are used to interact with model clients, tools, workbenches, threads, and memory,
forming the connective tissue between the components.

In AutoGen, these are the data types mostly defined in `autogen_core.models` module,
and others like `autogen_core.Image` and `autogen_core.FunctionCall`. This is just
an example as AutoGen has no formal definition of model context.

A design goal of the new framework to simplify the interaction between components
through a common set of model context data types, minimizing boilerplate code
in the application for transforming data between components.

_TODO: define a set of model context data types based on MEAI and MCP._

#### Actor

An actor is a component that takes a sequence of messages and produces a stream
of messages. The data types of the messages can be built-in or defined by the application,
but they must be serializable and defined for each actor.
These data types are not necessarily the same ones in model context.

An actor holds state managed by the agent runtime through the state API,
which supports stateful components such as threads, workbenches, and memory.

_NOTE: we need to align the actor definition in the agent runtime with this one,
so we are using the actor class directly from the agent runtime._

_NOTE: we need to design the agent runtime to make sure the state API can
be used to implement the components in the agent framework._

_NOTE: Instead of "Agent", in the runtime, we should use "Actor" to refer to the
current agent base class `autogen_core.Agent`. We want to reserve the term "Agent"
to refer to entities that use language models. This aligns with the usage in the
AI community, where people often refer to "Agent" as an entity that can perceive, plan
and act._

### Component Relationships

The following diagram shows the component relationship of the framework:

```mermaid
graph TD
    Component[Component] --> |extends| Actor[Actor]
    Actor --> |extends| Agent[Agent]
    Actor --> |extends| Guardrail[Guardrail]
    Actor --> |extends| Workflow[Workflow]
    
    Component --> |extends| ModelClient[Model Client]
    Component --> |extends| VectorStore[Vector Store]
    Component --> |extends| EmbeddingClient[Embedding Client]
    Component --> |extends| Tool[Tool]
    Component --> |extends| Workbench[Workbench]
    Component --> |extends| Memory[Memory]
    Component --> |extends| Thread[Thread]
    
    Agent --> |uses| uses1[Model Client]
    Agent --> |uses| uses2[Thread]
    Agent --> |uses| uses3[Tools/Workbenches]
    Agent --> |uses| uses4[Memory]
    
    Workflow --> |contains| contains[Child Actors]

    Memory --> |uses| uses5[Vector Store]
    VectorStore --> |uses| uses6[Embedding Client]
```


### Model Client

A model client is a component that implements a unified interface for
interacting with different language models. It exposes a standardized metadata
about the model it provides (e.g., model name, tool call and vision capabilities, etc.)
to support validation and composition with other components.

The framework provides a set of pre-built model clients:
- `OpenAIChatCompletionClient`
- `AzureOpenAIChatCompletionClient`
- `AzureOpenAIResponseClient`
- `AzureAIClient`
- `AnthropicClient`
- `GeminiClient`
- `HuggingFaceClient`
- `OllamaClient`
- `VLLMClient`
- `ONNXRuntimeClient`
- `BedrockClient`
- `NIMClient`

Prompt template is a component that is used by model clients to generate prompts with parameters set based on some injected context.
prompts with parameters set based on some injected context.
This gets into the actual interface and implementation detail of model clients,
so we just mention it here.

### Vector Store and Embedding Client

A vector store is component that provides a unified interface for
interacting with different vector databases, similar to model clients.
It exposes indexing and querying methods, including vector, text-based
and hybrid queries.

The details can be filled in based on the existing vector abstraction
in Semantic Kernel.

The framework provides pre-built vector stores (already exist in
Semantic Kernel):
- Azure AI Search
- Cosmos DB
- Chroma
- Couchbase
- Elasticsearch
- Faiss
- In-memory
- JDBC
- MongoDB
- Pinecone
- Postgres
- Qdrant
- Redis
- SQL Server
- SQLite
- Volatile
- Weaviate

Many vector store implementations will require embedding clients
to function. An embedding client is a component that implements a unified interface
to interact with different embedding models.

The framework provides a set of pre-built embedding clients:
- TBD.

### Tool

A tool is a component that can be used to invoke procedure code
and returns the result as context to the language model.
A tool may have arguments for invocation. 
The arguments must be defined using JSON schema that language model supports.

A tool may have dependencies such as tokens, credentials,
or output message channels that will be provided by the framework.

The framework provides a set of pre-built tools:
- `FunctionTool`: a tool that wraps a function.
- `AzureAISearchTool`: a tool that is backed by Azure AI Search Service.

### Workbench

A workbench is a component that provides a set of tools sharing
common state and resource.
For example, a workbench can be used by multiple agents to edit the same document,
work on the same code repository, or operatng on a common database.

The framework provides a set of pre-built workbenches:
- `MCPWorkbench`: a workbench that is backed by a Model Context Protocol (MCP) server.

_Question: should we just use MCP as a component, forget about workbench? It looks like
there isn't going to be another workbench class._

### Memory

A memory is a component that stores arbitrary data types while providing
an interface for retrieving model context from the stored data for language models.
For example, a memory can store multi-media documents, and provide an interface
for synthesizing model context from snippets of the documents.
In another example, a memory can store the past interactions with a language model,
and provide an interface for synthesizing summaries of the interactions.

Some memory may implement tool or workbench interfaces to allow models to
operate on them.

The framework provides a set of pre-built memories:
- `ListMemory`: a memory that synthesizes model context formatted from all data it stores as a list.
- `VectorMemory`: a memory that synthesize model context from data retrieved from a vector store.
This may be a base class for vendor-specific implementations.

### Thread

A thread is a component that stores message history 
and provides a view of the message history to the language model.

The framework provides a set of pre-built threads:
- `UnboundedThread`: a thread that provides view for all of the message history
- `TruncatedThread`: a thread that provides a view of a message history from the last N messages.
- `TokenLimitedThread`: a thread that provides a view of a message history up to
a certain number of tokens.
- `TimeLimitedThread`: a thread that provides a view of a message history up to
a certain time limit.

### Agent

An agent is an actor that uses a language model. 
During its handling of messages, the agent:
- Uses model client to process messages,
- Uses thread to keep track of the interaction with the model,
- Invokes tools or workbenches, and
- Retrieves and stores data through memory.

An agent base class has access to a set of well-known states through the state API provided by its actor base class. These well-known states are:
- `Thread`: the thread component.
- `Memory`: the memory component.

It is up to the implementation of the agent class to decide how these states and
components are used.
An agent may not use the components provided by the framework to implement
the actor interface.
Azure AI Agent is an example of such agent: its implementation is
backed by the Azure AI Agent Service.

The framework provides a set of pre-built agents:
- `ChatCompletionAgent`: an agent that uses a chat-completion model to process messages
and use thread, memory, tools and workbenches in a configurable way.
- `AzureAIAgent`: an agent that is backed by Azure AI Agent Service.
- `ResponsesAgent`: an agent that is backed by OpenAI's Responses API.
- `A2AAgent`: an agent that is backed by the [A2A Protocol](https://google.github.io/A2A/documentation/).


### Guardrail

A guardrail is an actor that enforces constraints on
the messages sent to or produced by other actors.
For example, a guardrail can be used to ensure the input messages to an agent
does not contain jailbreaks or malicious instructions, or that the
output messages of an agent does not contain sensitive information or harmful content.
In another example, a guardrail can be used to review code produced by an agent
is safe and following the security guidelines.

The implementaiton of some tools or agents may also uses components similar to
guardrails but that's not what being discussed here.

The framework provides a set of pre-built guardrails as reference implementation:
- `JailbreakGuardrail`: a guardrail that uses a language model to detect malicious instructions
and jailbreaks in the input messages.
- `SecretGuardrail`: a guardrail that uses a configurable set of rules to detect
sensitive data such as passwords, credit card numbers, tokens, etc. in the output messages.
- `PIIGuardrail`: a guardrail that uses a configurable set of rules to detect
personally identifiable information (PII) such as email addresses, phone numbers,
social security numbers, etc. in the output messages.
- `PythonCodeReviewGuardrail`: a guardrail that uses Python linting tools and a language
model to review code in the output messages.


### Workflow

A workflow is an actor consists of multiple child actors, some of which may be
agents, some of which may be guardrails, and some may be other workflows.
During its handling of messages, it invokes its child actors
in some order (could be concurrent or sequential), collects the messages
produced by the child actors, and create the output messages.

The composition of actors can be declaratively defined using a directed graph, or can
emerge from the type-based message routing defined for each actor.

The design goal of workflow is to cover all the use cases of current AutoGen's
AgentChat, Semantic Kernel's Agent Framework and Process Framework.

_Question: should we consider this a replacement for the Process Framework?_

The framework provides a set of pre-built workflows:
- `GraphWorkflow`: a workflow that specifies the order of invocation as a directed graph.
- `RoutedWorkflow`: a workflow that routes messages to its child actors based on the
message type and the message content. Swarm is an example of such workflow.

## Deployment and Scaling

Agents and workflows created using this framework can be deloyed through
the [Agent Runtime](https://github.com/microsoft/agent-runtime).

Details TBD.

## Monitoring

Traces should follow the [OTEL GenAI Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

Details TBD.

## Evaluation

Integrate with Azure AI Evaluation Service.

Details TBD.

## Debugging

Future work, a placeholder here for our mind.

## Optimization

Future work, a placeholder here for our mind.