# Microsoft Agent Framework Workflows Core Concepts: Workflows

This document provides an in-depth look at the **Workflows** component of the Microsoft Agent Framework Workflow system.

## Overview

A Workflow ties everything together and manages execution. It's the orchestrator that coordinates executor execution, message routing, and event streaming.

### Building Workflows

::: zone pivot="programming-language-csharp"

Workflows are constructed using the `WorkflowBuilder` class, which provides a fluent API for defining the workflow structure:

```csharp
// Create executors
var processor = new DataProcessor();
var validator = new Validator();
var formatter = new Formatter();

// Build workflow
WorkflowBuilder builder = new(processor); // Set starting executor
builder.AddEdge(processor, validator);
builder.AddEdge(validator, formatter);
var workflow = builder.Build<string>(); // Specify input message type
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

### Workflow Execution

Workflows support both streaming and non-streaming execution modes:

::: zone pivot="programming-language-csharp"

```csharp
// Streaming execution - get events as they happen
StreamingRun run = await InProcessExecution.StreamAsync(workflow, inputMessage);
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    if (evt is ExecutorCompleteEvent executorComplete)
    {
        Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
    }

    if (evt is WorkflowCompletedEvent completed)
    {
        Console.WriteLine($"Workflow completed: {completed.Data}");
    }
}

// Non-streaming execution - wait for completion
Run result = await InProcessExecution.RunAsync(workflow, inputMessage);
foreach (WorkflowEvent evt in result.NewEvents)
{
    if (evt is WorkflowCompletedEvent completed)
    {
        Console.WriteLine($"Final result: {completed.Data}");
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

### Workflow Validation

The framework performs comprehensive validation when building workflows:

- **Type Compatibility**: Ensures message types are compatible between connected executors
- **Graph Connectivity**: Verifies all executors are reachable from the start executor
- **Executor Binding**: Confirms all executors are properly bound and instantiated
- **Edge Validation**: Checks for duplicate edges and invalid connections

### Execution Model

The framework uses a modified [Pregel](https://kowshik.github.io/JPregel/pregel_paper.pdf) execution model with clear data flow semantics and superstep-based processing.

### Pregel-Style Supersteps

Workflow execution is organized into discrete supersteps, where each superstep processes all available messages in parallel:

```text
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

### Key Execution Characteristics

- **Superstep Isolation**: All executors in a superstep run concurrently without interfering with each other
- **Message Delivery**: Messages are delivered in parallel to all matching edges
- **Event Streaming**: Events are emitted in real-time as executors complete processing
- **Type Safety**: Runtime type validation ensures messages are routed to compatible handlers

## Next Step

- [Learn about events](./events.md) to understand how to monitor and observe workflow execution.
