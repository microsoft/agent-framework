# Agent Framework: Overview

What values does the framework provide?

- A set of configurable, extensible and high-quality components (e.g., model clients, tools, MCP servers and memory).
- An easy path for deploying, securing and scaling applications, both locally and in the cloud.
- Integration with tools for monitoring, debugging, evaluation and optimization, both locally and in the cloud.
- A community of developers and users for support, ideas, and contributions, benefiting everyone in the ecosystem.

What is this document?

- An overview of the new framework.
- Defining the major elements of the framework and their relationships.
- Detailed design of each element and its implementation will be in a separate document.

Table of Contents

- [Agent Framework: Overview](#agent-framework-overview)
  - [Core Data Types](#core-data-types)
  - [Component](#component)
  - [Agent Components](#agent-components)
    - [Model Client](#model-client)
    - [Vector Store and Embedding Client](#vector-store-and-embedding-client)
    - [Tool](#tool)
    - [MCP Server](#mcp-server)
    - [Memory](#memory)
    - [Thread](#thread)
    - [Guardrail](#guardrail)
  - [Actor Components](#actor-components)
    - [Agent](#agent)
    - [Workflow](#workflow)
  - [Deployment and Scaling](#deployment-and-scaling)
  - [Monitoring](#monitoring)
  - [Evaluation](#evaluation)
    - [Core Evaluation Concepts](#core-evaluation-concepts)
    - [Evaluation Components](#evaluation-components)
    - [Metrics](#metrics)
      - [Computation-based Metrics](#computation-based-metrics)
      - [Model-based Metrics](#model-based-metrics)
    - [Example Metrics](#example-metrics)
    - [Sample Developer Experience](#sample-developer-experience)
    - [Integration with Cloud Services](#integration-with-cloud-services)
  - [Debugging](#debugging)
  - [Optimization](#optimization)

## Core Data Types

To unify the interaction between components, we define a set of core
data types.

For example, text, images, function calls, tool schema are
all examples of such data types.
These data types are used to interact with agent components (model clients, tools, MCP, threads, and memory),
forming the connective tissue between those components.

In AutoGen, these are the data types mostly defined in `autogen_core.models` module,
and others like `autogen_core.Image` and `autogen_core.FunctionCall`. This is just
an example as AutoGen has no formal definition of model context.

A design goal of the new framework to simplify the interaction between agent components
through a common set of data types, minimizing boilerplate code
in the application for transforming data between components.

We can start with a set of data types based on Microsoft.Extension.AI and MCP.

## Component

A component is a class that provides a specific functionality and can be used
independently by applications.

Components can be composed to create complex components. For example,
an agent can be composed from model clients, tools and memory,
and a tool can be composed from an agent or a workflow.
It is the responsibility of the framework to validate components
and their composition.

A component can be created from a set of serializable configuration parameters,
with the help of dependency injection to resolve non-serializable dependencies.
For example, a model client can be created from a set of parameters like temperature and model names,
but the actual underlying client can be instantiated as an object.

The following diagram shows the component relationship of the framework:

```mermaid
graph TD
    Component[Component] --> |extends| Actor[Actor]
    Actor --> |extends| Agent[Agent]
    Actor --> |extends| Workflow[Workflow]

    Component --> |extends| ModelClient[Model Client]
    Component --> |extends| VectorStore[Vector Store]
    Component --> |extends| EmbeddingClient[Embedding Client]
    Component --> |extends| Tool[Tool]
    Component --> |extends| MCPServer[MCP Server]
    Component --> |extends| Memory[Memory]
    Component --> |extends| Thread[Thread]
    Component --> |extends| Guardrail[Guardrail]

    Agent --> |uses| uses1[Model Client]
    Agent --> |uses| uses2[Thread]
    Agent --> |uses| uses3[Tools and MCP Servers]
    Agent --> |uses| uses4[Memory]
    Agent --> |uses| uses5[Guardrail]

    Workflow --> |contains| contains[Child Actors]

    Memory --> |uses| uses5[Vector Store]
    VectorStore --> |uses| uses6[Embedding Client]
```

Some components are implemented using the [Agent Runtime](https://github.com/microsoft/agent-runtime):

- Thread as a state object
- Memory as a state object
- Agent as an actor
- Guardrail as an actor
- Workflow as an actor that orchestrates other actors.

## Agent Components

Agent components are components that are used to build an agent.

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
and returns a well-defined result type to the caller.

The result type should indicate the success or failure of the invocation,
as well as the output of the invocation in terms of the core data types.
There may be other fields in the result type for things like
side effects, etc.. We should address this when designing the
tool interface.

A tool may have arguments for invocation.
The arguments must be defined using JSON schema that language model supports.

A tool may have dependencies such as tokens, credentials,
or output message channels that will be provided by the framework
through dependency injection.

A tool may also have an action guard that is used to ensure the
tool is invoked with proper arguments, or that the agent has the
right context such as human approval to invoke the tool.

The framework provides a set of pre-built tools:

- `FunctionTool`: a tool that wraps a function.
- `AzureAISearchTool`: a tool that is backed by Azure AI Search Service.
- `OpenAPITool`: a tool that is backed by a service that defines an OpenAPI spec.
- Other tools backed by Foundry.

### MCP Server

(Exact name to be determined)

An MCP server is a component that wraps a session to an
[Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server.

The tools provided by MCP server should match the tool interface to ensure
minimal boilerplate code when dealing with both tools and MCP servers.

Other features like sampling and resources, should be accessible through
the MCP server interface as well.

### Memory

A memory is a component that stores arbitrary data types while providing
an interface for retrieving model context from the stored data for language models.
For example, a memory can store multi-media documents, and provide an interface
for synthesizing model context from snippets of the documents.
In another example, a memory can store the past interactions with a language model,
and provide an interface for synthesizing summaries of the interactions.

Some memory may implement tool or MCP server interfaces to allow models to
operate on them.

The framework provides a set of pre-built memories:

- `ListMemory`: a memory that synthesizes model context formatted from all data it stores as a list.
- `VectorMemory`: a memory that synthesize model context from data retrieved from a vector store.
  This may be a base class for vendor-specific implementations.
- `AzureAISearchMemory`: a memory that synthesizes model context from data retrieved from Azure AI Search.
- `Mem0Memory`: a memory that is backed by Mem0.

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

### Guardrail

A guardrail is an agent component that enforces constraints on
the input and output of other agent components.
For example, a guardrail can be used to ensure the input messages to a model
does not contain jailbreaks or malicious instructions, or that the
output of a tool call does not contain sensitive information or harmful content.

The framework provides a set of pre-built guardrails as reference implementation:

- `JailbreakGuardrail`: a guardrail that uses a language model to detect malicious instructions
  and jailbreaks in the input messages.
- `SecretGuardrail`: a guardrail that uses a configurable set of rules to detect
  sensitive data such as passwords, credit card numbers, tokens, etc. in model or tool outputs.
- `PIIGuardrail`: a guardrail that uses a configurable set of rules to detect
  personally identifiable information (PII) such as email addresses, phone numbers,
  social security numbers, etc. in model or tool outputs.

A teaser of the experience of using a built-in guardrail:

```python
from agent_framework import PIIGuardrail, MCPServer

guardrail = PIIGuardrail(
    config={
        "rules": [
            {
                "type": "email",
                "action": "block"
            },
            {
                "type": "phone",
                "action": "block"
            }
        ]
    }
)

mcp_server = MCPServer(...)
mcp_server.add_output_guardrail(guardrail)
```

## Actor Components

An actor is a component that takes a sequence of messages and produces a stream
of messages. The data types of the messages can be built-in or defined by the application,
but they must be serializable and defined for each actor.
These data types are not necessarily the same ones in model context.

The actor class is inherited from the actor base class in the agent runtime,
so it holds state managed by the agent runtime through the state API, including
the thread and memory components.

_NOTE: we need to align the actor definition in the agent runtime with this one,
so we are using the actor class directly from the agent runtime._

_NOTE: we need to design the agent runtime to make sure the state API can
be used to implement the components in the agent framework._

_NOTE: Instead of "Agent", in the runtime, we should use "Actor" to refer to the
current agent base class `agent_runtime.Agent`. We want to reserve the term "Agent"
to refer to entities that use language models. This aligns with the usage in the
AI community, where people often refer to "Agent" as an entity that can perceive, plan
and act._

### Agent

An agent is an actor that uses a language model.
During its handling of messages, the agent:

- Uses model client to process messages,
- Uses thread to keep track of the interaction with the model,
- Invokes tools or MCP servers, and
- Retrieves and stores data through memory.

An agent base class has access to a set of well-known states through the state API provided by its actor base class. These well-known states are:

- `Thread`: the thread component.
- `Memory`: the memory component.

It is up to the implementation of the agent class to decide how these states and
components are used.

**An important design goal of the framework is to ensure the developer experience
of creating custom agent is as easy as possible.** Existing frameworks
have made "kitchen-sink" agents that are hard to understand and maintain.

A teaser of the experience for creating a custom agent is shown below.

```python
from agent_framework import Agent, MessageBatch, Thread

class ToolCallingAgent(Agent):
    async def run(self, messages: MessageBatch, thread: Thread) -> MessageBatch:
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
```

An agent might not use the components provided by the framework to implement
the actor interface.
Azure AI Agent is an example of such agent: its implementation is
backed by the Azure AI Agent Service.

The framework provides a set of pre-built agents:

- `ChatCompletionAgent`: an agent that uses a chat-completion model to process messages
  and use thread, memory, tools and MCP servers in a configurable way. **If we can make
  custom agents easy to implement, we can remove this agent.**
- `AzureAIAgent`: an agent that is backed by Azure AI Agent Service.
- `ResponsesAgent`: an agent that is backed by OpenAI's Responses API.
- `A2AAgent`: an agent that is backed by the [A2A Protocol](https://google.github.io/A2A/documentation/).

### Workflow

A workflow is an actor consists of multiple child actors, some of which may be
actors, and some may be other workflows.
During its handling of messages, it invokes its child actors
in some order (could be concurrent or sequential), collects the messages
produced by the child actors, and create the output messages.

The composition of actors can be declaratively defined using a directed graph, or can
emerge from the type-based message routing defined for each actor.

The workflow should understand the agent and guardrail interfaces, and knows
how to compose them appropriately to achieve functionality like trip-wiring
and retry.

The workflow should cover all the use cases of current AutoGen's
AgentChat, Semantic Kernel's Agent Framework and Process Framework.

The framework provides a set of pre-built workflows:

- `GraphWorkflow`: a workflow that specifies the order of invocation as a directed graph.
- `RoutedWorkflow`: a workflow that routes messages to its child actors based on the
  message type and the message content. Swarm is an example of such workflow (details TBD).

Pesudo Python code for creating a `GraphWorkflow`.

```python
from agent_framework import GraphWorkflow, GraphBuilder, ChatCompletionAgent, Any, All

agent1 = ChatCompletionAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_servers=["MCPServer1", "MCPServer2"],
    memory="ListMemory",
)

agent2 = ChatCompletionAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_servers=["MCPServer3", "MCPServer4"],
    memory="ListMemory",
)

graph = GraphBuilder() \
    .add_agent(agent1) \
    .add_agent(agent2) \
    .add_loop(agent1, agent1, conditions=Any(...)) \
    .add_transition(agent1, agent2, conditions=Any(..., All(...))]) \
    .build()

workflow = GraphWorkflow(graph=graph)

# This is just a teaser, we still need to define how the actual API looks like.
events = workflow.run_stream(
    input_message="Hello, world!",
    context={
        "user_id": "123456",
        "session_id": "abcdefg"
    },
    mcp_servers=["MCPServer1", "MCPServer2", "MCPServer3", "MCPServer4"],
)
```

## Deployment and Scaling

Agents and workflows created using this framework can be deloyed through
the [Agent Runtime](https://github.com/microsoft/agent-runtime).

Details TBD.

## Monitoring

Traces should follow the [OTEL GenAI Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

Details TBD.

## Evaluation

The framework provides a comprehensive evaluation system for assessing agent performance, enabling developers to measure both the quality of agent responses and the efficiency of their decision-making processes.

### Core Evaluation Concepts

- **Trajectory Evaluation**: Analyze the path (sequence of tool calls, reasoning steps) an agent takes to reach its final response.
- **Response Evaluation**: Assess the final output of an agent against quality criteria.
- **Standardized Trajectory Format**: A unified representation of agent interactions (messages, tool calls, events) enabling consistent evaluation across different agent implementations.

### Evaluation Components

The framework provides these key evaluation components:

- **Trajectory Converter**: Transforms agent runs from various frameworks into a standardized format for evaluation.
- **Metrics Library**:
  - Computation-based metrics: Direct algorithms that calculate objective measures without requiring a model
  - Model-based metrics: Evaluation criteria that require a model to assess subjective qualities
- **Judge**: For model-based metrics, a judge is the LLM responsible for applying evaluation criteria. Different judge models can be selected based on evaluation needs.
- **Evaluator**: Coordinates the evaluation process by running computation-based metrics directly and applying judges to model-based metrics.
- **Integration**: Connect with cloud evaluation services including Azure AI Evaluation.

### Metrics

#### Computation-based Metrics

- **Tool Match**: Measures tool call sequence matching in various ways:
  - Exact Match: Perfect match with reference sequence
  - In-Order Match: Required tools called in correct order (extra steps allowed)
  - Any-Order Match: All required tools called regardless of order
- **Precision**: Proportion of agent's tool calls that match reference tool calls.
- **Recall**: Proportion of reference tool calls included in the agent's tool calls.
- **Single Tool Usage**: Checks if a specific tool was used during the trajectory.
- **Tool Call Errors**: Measures rate of tool call failures or errors.
- **Latency**: Time required for agent to complete its task.

#### Model-based Metrics

- **Task Adherence**: Evaluates how well the agent's response addresses the assigned task.
- **Coherence**: Assesses logical flow and internal consistency of the response.
- **Safety**: Detects potential harmful content in responses.
- **Follows Trajectory**: Evaluates if the response logically follows from the tools used.
- **Efficiency**: Measures if the agent took an optimal path to reach the solution.

### Example Metrics

The framework provides both computation-based metrics that run directly and model-based metrics that require a judge:

```python
# Example of computation-based metric (runs direct calculations, no judge needed)
trajectory_match = ExactTrajectoryMatch()

# Example of model-based metric (requires a judge model to evaluate)
task_adherence_metric = PointwiseMetric(
    metric="task_adherence",
    metric_prompt_template=PointwiseMetricPromptTemplate(
        criteria={
            "Task adherence": (
                "Evaluate whether the agent's response appropriately addresses the assigned task. "
                "Consider these sub-points:\n"
                "  - Does the response directly address the user's request?\n"
                "  - Does the response incorporate information gathered from tool calls?\n"
                "  - Is the response complete without missing important aspects of the task?\n"
            )
        },
        rating_rubric={
            "5": "Excellent - Completely addresses all aspects of the task with thorough detail",
            "4": "Good - Addresses most aspects of the task effectively",
            "3": "Adequate - Addresses the core of the task but may miss minor details",
            "2": "Poor - Only partially addresses the task with significant gaps",
            "1": "Inadequate - Fails to address the task or contains major inaccuracies",
        },
    ),
)

# Evaluator combines both types of metrics
evaluator = Evaluator(
    computation_metrics=[trajectory_match],  # Run directly
    model_metrics=[task_adherence_metric],   # Require a judge
    judge=JudgeModel(model="o3-mini", temperature=0)  # Judge for model-based metrics
)
```

### Sample Developer Experience

1. **Prepare Dataset**: Create a dataset with tasks, expected responses, and optional reference trajectories.
2. **Configure Metrics**: Select from pre-built metrics or define custom metrics based on evaluation needs.
3. **Select Judges**: Choose appropriate judge models for model-based metrics, optimizing for evaluation quality.
4. **Run Evaluation**: Execute the evaluation against agent runs or existing trajectory data.
5. **Analyze Results**: Review metrics, identify areas for improvement, and compare different agent configurations.

### Integration with Cloud Services

The framework supports evaluation through:

- **Local Evaluation**: Run evaluations directly within the framework.
- **Azure AI Evaluation**: Connect to Azure AI Evaluation Service for comprehensive agent assessment.

By standardizing trajectory representation, the framework simplifies evaluation across different agent architectures and enables seamless integration with both local and cloud-based evaluation systems.

## Debugging

Future work, a placeholder here for our mind.

## Optimization

Future work, a placeholder here for our mind.
