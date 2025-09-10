# Microsoft Agent Framework Workflows Core Concepts: Executors

This document provides an in-depth look at the **Executors** component of the Microsoft Agent Framework Workflow system.

## Overview

Executors are the fundamental building blocks that process messages in a workflow. They are autonomous processing units that receive typed messages, perform operations, and can produce output messages or events.

::: zone pivot="programming-language-csharp"

Executors implement the `IMessageHandler<TInput>` or `IMessageHandler<TInput, TOutput>` interfaces and inherit from the `ReflectingExecutor<T>` base class. Each executor has a unique identifier and can handle specific message types.

### Basic Executor Structure

```csharp
internal sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor"), 
    IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = message.ToUpperInvariant();
        return result; // Return value is automatically sent to connected executors
    }
}
```

It is possible to send messages manually without returning a value:

```csharp
internal sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor"), 
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        string result = message.ToUpperInvariant();
        await context.SendMessageAsync(result); // Manually send messages to connected executors
    }
}
```

It is also possible to handle multiple input types by implementing multiple interfaces:

```csharp
internal sealed class SampleExecutor() : ReflectingExecutor<SampleExecutor>("SampleExecutor"), 
    IMessageHandler<string, string>, IMessageHandler<int, int>
{
    /// <summary>
    /// Converts input string to uppercase
    /// </summary>
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = message.ToUpperInvariant();
        return result;
    }

    /// <summary>
    /// Doubles the input integer
    /// </summary>
    public async ValueTask<int> HandleAsync(int message, IWorkflowContext context)
    {
        int result = message * 2;
        return result;
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Next Step

- [Learn about Edges](./edges.md) to understand how executors are connected in a workflow.