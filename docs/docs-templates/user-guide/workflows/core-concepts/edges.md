# Microsoft Agent Framework Workflows Core Concepts: Edges

This document provides an in-depth look at the **Edges** component of the Microsoft Agent Framework Workflow system.

## Overview

Edges define how messages flow between executors with optional conditions. They represent the connections in the workflow graph and determine the data flow paths.

### Types of Edges

The framework supports several edge patterns:

1. **Direct Edges**: Simple one-to-one connections between executors
2. **Conditional Edges**: Edges with conditions that determine when messages should flow
3. **Fan-out Edges**: One executor sending messages to multiple targets
4. **Fan-in Edges**: Multiple executors sending messages to a single target

#### Direct Edges

The simplest form of connection between two executors:

::: zone pivot="programming-language-csharp"

```csharp
WorkflowBuilder builder = new(sourceExecutor);
builder.AddEdge(sourceExecutor, targetExecutor);
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

#### Conditional Edges

Edges that only activate when certain conditions are met:

::: zone pivot="programming-language-csharp"

```csharp
// Route based on message content
builder.AddEdge(
    source: spamDetector, 
    target: emailProcessor, 
    condition: result => result is SpamResult spam && !spam.IsSpam
);

builder.AddEdge(
    source: spamDetector,
    target: spamHandler,
    condition: result => result is SpamResult spam && spam.IsSpam
);
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

#### Fan-out Edges

Distribute messages from one executor to multiple targets:

::: zone pivot="programming-language-csharp"

```csharp
// Send to all targets
builder.AddFanOutEdge(splitterExecutor, targets: [worker1, worker2, worker3]);

// Send to specific targets based on partitioner function
builder.AddFanOutEdge(
    source: routerExecutor,
    partitioner: (message, targetCount) => message.Priority switch
    {
        Priority.High => [0], // Route to first worker only
        Priority.Normal => [1, 2], // Route to workers 2 and 3
        _ => Enumerable.Range(0, targetCount) // Route to all workers
    },
    targets: [highPriorityWorker, normalWorker1, normalWorker2]
);
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

#### Fan-in Edges

Collect messages from multiple sources into a single target:

::: zone pivot="programming-language-csharp"

```csharp
// Aggregate results from multiple workers
builder.AddFanInEdge(aggregatorExecutor, sources: [worker1, worker2, worker3]);
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Next Step

- [Learn about Workflows](../workflows.md) to understand how to build and execute workflows.