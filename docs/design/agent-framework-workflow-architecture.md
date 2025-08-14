# Agent Framework Workflows - Technical Design Document

## Table of Contents

1. [Introduction](#introduction)
2. [Core Components](#core-components)
3. [Foundation Patterns](#foundation-patterns)
4. [Request & Response Pattern](#request--response-pattern)
5. [Execution Model](#execution-model)
6. [API Design](#api-design)
7. [Security Considerations](#security-considerations)
8. [Future Enhancements](#future-enhancements)
9. [Conclusion](#conclusion)

## Introduction

### Purpose

The Agent Framework Workflow system is a sophisticated orchestration framework designed to manage complex multi-agent workflows with advanced type safety and polymorphic execution patterns. Built on a graph-based architecture using [Pregel-style](https://kowshik.github.io/JPregel/pregel_paper.pdf) execution, the framework provides a flexible and extensible foundation for building AI-powered applications.

### Architecture Overview

The framework follows a graph-based architecture where:

- **Executors** are processing units that handle messages
- **Edges** define the flow of data between executors
- **Messages** carry typed data through the graph
- **Events** provide observability into the workflow execution

## Core Components

The workflow framework consists of three core layers that work together to create a flexible, type-safe execution environment:

```txt
┌───────────────────────────────────────────────────────────────────┐
│                        Workflow System                            │
├─────────────────┬───────────────┬─────────────────────────────────┤
│                 │               │                                 │
│   Executors     │     Edges     │           Workflow              │
│  (Processing)   │   (Routing)   │       (Orchestration)           │
│                 │               │                                 │
│ ┌─────────────┐ │ ┌───────────┐ │ ┌─────────────────────────────┐ │
│ │@handler     │ │ │Conditional│ │ │ • Manages execution flow    │ │
│ │┌───────────┐│ │ │  Routing  │ │ │ • Coordinates executors     │ │
│ ││Handler A  ││ │ └─────┬─────┘ │ │ • Streams events            │ │
│ │├───────────┤│ │       │       │ └─────────────┬───────────────┘ │
│ ││Handler B  ││◄├───────┴───────┤►              │                 │
│ │├───────────┤│ │               │               ▼                 │
│ ││Handler C  ││ │  Type-based   │        WorkflowContext          │
│ │└───────────┘│ │   Routing     │    (Shared State & Events)      │
│ └─────────────┘ │               │                                 │
└─────────────────┴───────────────┴─────────────────────────────────┘
```

### 1. Executor

Executors are the fundamental building blocks that process messages in a workflow:

```
┌─────────────────────────────────────────┐
│             Executor                    │
├─────────────────────────────────────────┤
│ Name: "data_processor"                  │
├─────────────────────────────────────────┤
│ Message Handlers:                       │
│  • handle_text(TextData) → ProcessedText│
│  • handle_image(ImageData) → Thumbnail  │
└─────────────────────────────────────────┘
```

Messages will be automatically routed to the appropriate handler based on their type. An executor cannot have multiple handlers for the same message type, ensuring type safety and clarity in message processing.

### 2. Edge

Edges define how messages flow between executors with optional conditions:

```
┌─────────────┐                    ┌─────────────┐
│  Executor A │                    │  Executor B │
│             │                    │             │
│   Output:   │                    │   Input:    │
│   UserData  │                    │   UserData  │
│             │                    │             │
└──────┬──────┘                    └──────▲──────┘
       │                                  │
       │         ┌──────────────┐         │
       └────────►│     Edge     │─────────┘
                 │              │
                 │ if user.age  │
                 │    >= 18     │
                 └──────────────┘
```

### 3. Workflow

The Workflow ties everything together and manages execution:

```
┌─────────────────────────────────────────────────────┐
│                    Workflow                         │
├─────────────────────────────────────────────────────┤
│  Components:                                        │
│  • Executors: [A, B, C, D]                          │
│  • Edges: [A→B, A→C, B→D, C→D]                      │
│  • Start: A                                         │
│  • Runner: Pregel-style superstep execution         │
├─────────────────────────────────────────────────────┤
│  Execution Flow:                                    │
│  1. run_streaming(message) ──► Start at executor A  │
│  2. Superstep 1: A processes, sends to B & C        │
│  3. Superstep 2: B & C process in parallel          │
│  4. Superstep 3: D processes results from B & C     │
│  5. Stream events throughout execution              │
│  6. Complete when no messages remain                │
└─────────────────────────────────────────────────────┘
```

## Foundation Patterns

```
┌─────────────────────────────────────────────────────┐
│(1) Direct-messaging: A ──► B                        │
│                                                     │
│  .add_edge(A, B)                                    │
│                                                     │
│(2) Sequential:     A ──► B ──► C                    │
│                                                     │
│  .add_chain([A, B, C])                              │
│  (*Cycles are not allowed in a chain)               │
│                                                     │
│(3) Fan-out:                                         │
|                   ┌──► B                            │
│                A ─┼──► C                            │
│                   └──► D                            │
│  .add_fan_out_edges(A, [B, C, D])                   │
│  (*Messages from A are sent to all B, C, D)         │
│  (*With an optional selection function,             │
│     messages can be sent to only a subset of        │
│     recipients based on custom logic)               │
│                                                     │
│(4) Switch-case:   ┌─[case: x>0]─► B                 │
│                A ─┤                                 │
│                   └─[default]─► C                   │
│  .add_switch_case_edge_group(                       │
│     source=A,                                       │
│     case=[                                          │
│       Case(B, condition=lambda x, state: x > 0),    │
│       Default(C),                                   │
│     ],                                              │
│   )                                                 │
│                                                     │
│(5) Fan-in:    A ─┐                                  │
│               B ─┼──► D                             │
│               C ─┘                                  │
│  .add_fan_in_edges([A, B, C], D)                    │
│  (*Messages from A, B, C are collected and          │
│     sent to D as a list when all are ready)         │
└─────────────────────────────────────────────────────┘
```

## Request & Response Pattern

A special built-in executor for handling external interactions:

```
┌─────────────────────────────────────────────────────────────┐
│  Executor A                       External World            │
│     │                                    ▲                  │
│     │  Request                           │                  │
│     ▼                                    │                  │
│  ┌──────────────┐      RequestInfoEvent  │                  │
│  │ RequestInfo  │ ─────────────────────► │                  │
│  │  Executor    │      (request_id: 123) │                  │
│  │              │                        │                  │
│  │              │◄───────────────────────┘                  │
│  └──────────────┘send_responses_streaming({123: response})  │
│     │                                                       │
│     │  Response                                             │
│     ▼                                                       │
│  Executor A                                                 │
└─────────────────────────────────────────────────────────────┘
```

**How it works:**

1. **Intercepts Requests**: Catches any `RequestMessage` subclass
2. **Generates Correlation ID**: Creates unique request_id
3. **Emits Event**: Sends RequestInfoEvent for external handling
4. **Waits for Response**: Application sends responses back with the same request_id
5. **Continues Flow**: Response routed back to the original executor

**Use Cases:**

- Human approval workflows
- External API calls
- Database lookups
- Any async external integration

## Execution Model

### Pregel-Style Supersteps

The framework uses a modified Pregel execution model with clear data flow semantics:

```
Superstep N:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Collect All    │───▶│  Route Messages │───▶│  Execute All    │
│  Pending        │    │  Based on Type  │    │  Target         │
│  Messages       │    │  & Conditions   │    │  Executors      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
┌─────────────────┐    ┌─────────────────┐             │
│  Start Next     │◀───│  Emit Events &  │◀────────────┘
│  Superstep      │    │  New Messages   │
└─────────────────┘    └─────────────────┘
```

- **Superstep Isolation**: All executors in a superstep run concurrently
- **Message Delivery**: Parallel delivery to all matching edges

#### Check Points

Checkpoints can be saved between superstep boundaries to allow for recovery in case of failures. The following information will be stored:

- Executor states
- Workflow states
- Pending messages

A checkpoint will be automatically created when the workflow converges (no more messages to process). A workflow can be resumed from a checkpoint, allowing for fault tolerance and long-running workflows.

#### Transactions (Planned)

If an executor fails during a superstep, messages processed during that superstep will be rolled back. Updates to shared state will not be committed. This ensures that the workflow remains consistent and avoids partial updates.

## API Design

### Creating Executors

```python
class SampleExecutor(Executor):

    @handler(output_types=[str])
    async def reverse_string(self, data: str, ctx: WorkflowContext) -> None:
        """Handler that handles a string and sends a string."""
        await ctx.send_message(data[::-1])

    @handler(output_types=[int, float])
    async def handle_int(self, data: int, ctx: WorkflowContext) -> None:
        """Handler that handles an integer and sends an integer and a float."""
        await ctx.send_message(int(data * 2))
        await ctx.send_message(float(data / 2))

    @handler
    async def handle(self, data: str, ctx: WorkflowContext) -> None:
        """Handler that handles a string and emits an event."""
        await ctx.add_event(WorkflowCompletedEvent(data))
```

### Building Workflows with a WorkflowBuilder

```python
# Sequential workflow
workflow = (
    WorkflowBuilder()
    .add_chain([executor_a, executor_b, executor_c])
    .set_start_executor(executor_a)
    .build()
)

# Conditional routing
workflow = (
    WorkflowBuilder()
    .add_edge(router, executor_a, lambda msg, workflow_state: msg.type == "A")
    .add_edge(router, executor_b, lambda msg, workflow_state: msg.type == "B")
    .set_start_executor(router)
    .build()
)

# Fan-out/Fan-in pattern
workflow = (
    WorkflowBuilder()
    .set_start_executor(splitter)
    .add_fan_out_edges(splitter, [worker1, worker2, worker3])
    .add_fan_in_edges([worker1, worker2, worker3], aggregator)
    .build()
)
```

### Workflow Validation

Upon building the workflow, the framework performs comprehensive validation:

- **EDGE_DUPLICATION**: Checks for duplicate edges between the same pair of executors.
- **TYPE_COMPATIBILITY**: Ensures that message types are compatible between connected executors. This is done by checking the output types of the source executor against the input types of the target executor using type annotations and type information added by the decorator.
- **GRAPH_CONNECTIVITY**: Ensures that all executors are reachable from the start executor.

### Running Workflows

```python
# Streaming
async for event in workflow.run_streaming(initial_message):
    if isinstance(event, WorkflowCompletedEvent):
        print(f"Workflow completed with result: {event.data}")

# Non-streaming
result = await workflow.run(initial_message)
print(f"Workflow completed with result: {result.get_completed_event().data}")
```

### Built-in Event Types

```python
# Workflow lifecycle events
WorkflowStartedEvent    # Workflow execution begins
WorkflowCompletedEvent  # Workflow reaches completion

# Executor events
ExecutorInvokeEvent     # Executor starts processing
ExecutorCompleteEvent   # Executor finishes processing

# Request/Response events
RequestInfoEvent       # Request received with correlation ID
```

### State Management

Thread-safe key-value store accessible to all executors.

```python
class StatefulExecutor(Executor):
    @handler
    async def process_data(self, data: str, ctx: WorkflowContext) -> None:
        # Read from shared state
        counter = await ctx.get_shared_state("counter") or 0

        # Update shared state
        await ctx.set_shared_state("counter", counter + 1)

        # Atomic multi-operation update
        async with ctx._shared_state.hold():
            value1 = await ctx.get_shared_state("key1")
            value2 = await ctx.get_shared_state("key2")
            await ctx.set_shared_state("combined", value1 + value2)
```

### Request & Response

```python
request_info_event: RequestInfoEvent | None = None
async for event in workflow.run_streaming(initial_message):
    if isinstance(event, RequestInfoEvent):
        request_info_event = event

async for event in workflow.send_responses_stream({request_info_event.request_id: "response_data"}):
    if isinstance(event, WorkflowCompletedEvent):
        result = event.data

print(f"Workflow completed with result: {result}")
```

## Security Considerations

### 1. Type Safety

- Strong typing prevents type confusion attacks
- Runtime type validation catches mismatched messages
- Generic type parameters enforce compile-time safety

### 2. State Isolation

- Executors cannot directly access each other's state
- Shared state requires explicit key-based access
- No global mutable state outside controlled interfaces

### 3. Message Validation

- All messages are validated against executor input types
- Conditional routing provides additional filtering
- Malformed messages are rejected at edge boundaries

### 4. Resource Limits

- Maximum iteration count prevents infinite loops
- Timeout support for long-running executors (planned)
- Memory usage bounded by message queue size (planned)

## Future Enhancements

### 1. Templatized Workflows

- Support for reusable workflow templates
- High-level workflow definitions with parameterization and templatized WorkflowBuilder to allow for easy instantiation of common patterns

### 2. Declarative Workflow Definitions

- CSDL (Copilot Studio Definition Language) support for defining workflows

### 3. Crossed-platform & Distributed Execution

- Support for executor distribution across nodes
- Message passing via message queues
- Distributed shared state with consistency guarantees

### 4. Enhanced Observability

- OpenTelemetry integration
- Structured logging with correlation IDs
- Performance metrics and profiling
- Visual workflow debugging tools

### 5. Advanced Error Handling

- Configurable retry policies per executor
- Dead letter queues for failed messages
- Circuit breaker pattern support
- Graceful degradation strategies

## Conclusion

The Agent Framework Workflow system provides a powerful, type-safe foundation for building complex AI-powered workflows. Its multi-handler executor pattern, built-in request/response support, and comprehensive type validation make it suitable for a wide range of applications from simple sequential processing to complex multi-agent orchestrations with external integrations.

**Key Strengths:**

- **Polymorphic Design**: Single executors handle multiple message types with automatic routing
- **Type Safety**: Comprehensive validation prevents runtime conflicts and ensures correct message flow
- **External Integration**: Built-in request/response correlation for APIs and human-in-the-loop workflows
- **Developer Experience**: Clean, intuitive API with extensive validation and helpful error reporting
- **Extensibility**: Easy to add new handler types and message patterns
