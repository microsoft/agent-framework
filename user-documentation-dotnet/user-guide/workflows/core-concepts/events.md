# Microsoft Agent Framework Workflows Core Concepts: Events

This document provides an in-depth look at the **Events** system of Workflows in the Microsoft Agent Framework.

## Overview

There are built-in events that provide observability into the workflow execution.

## Built-in Event Types


```csharp
// Workflow lifecycle events
WorkflowStartedEvent    // Workflow execution begins
WorkflowCompletedEvent  // Workflow reaches completion
WorkflowErrorEvent      // Workflow encounters an error

// Executor events  
ExecutorInvokeEvent     // Executor starts processing
ExecutorCompleteEvent   // Executor finishes processing
ExecutorFailureEvent    // Executor encounters an error

// Superstep events
SuperStepStartedEvent   // Superstep begins
SuperStepCompletedEvent // Superstep completes
```


### Consuming Events


```csharp
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case ExecutorInvokeEvent invoke:
            Console.WriteLine($"Starting {invoke.ExecutorId}");
            break;
            
        case ExecutorCompleteEvent complete:
            Console.WriteLine($"Completed {complete.ExecutorId}: {complete.Data}");
            break;
            
        case WorkflowCompletedEvent finished:
            Console.WriteLine($"Workflow finished: {finished.Data}");
            return;
            
        case WorkflowErrorEvent error:
            Console.WriteLine($"Workflow error: {error.Exception}");
            return;
    }
}
```



## Custom Events

Users can define and emit custom events during workflow execution for enhanced observability.


```csharp
internal sealed class CustomEvent(string message) : WorkflowEvent(message) { }

internal sealed class CustomExecutor() : ReflectingExecutor<CustomExecutor>("CustomExecutor"), IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        await context.AddEventAsync(new CustomEvent($"Processing message: {message}"));
        // Executor logic...
    }
}
```



## Next Steps

- [Learn how to use agents in workflows](./../using-agents.md) to build intelligent workflows.
- [Learn how to handle requests and responses](./../request-and-response.md) in workflows.
- [Learn how to manage state](./../shared-states.md) in workflows.

