# Your First Workflow

**Sample:** `dotnet/samples/01-get-started/05_first_workflow/`

Workflows let you connect multiple processing units (executors) into a directed graph. Data flows through edges from one executor to the next.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowExecutorsAndEdgesSample;

/// <summary>
/// This sample introduces the concepts of executors and edges in a workflow.
///
/// Workflows are built from executors (processing units) connected by edges (data flow paths).
/// In this example, we create a simple text processing pipeline that:
/// 1. Takes input text and converts it to uppercase using an UppercaseExecutor
/// 2. Takes the uppercase text and reverses it using a ReverseTextExecutor
///
/// The executors are connected sequentially, so data flows from one to the next in order.
/// For input "Hello, World!", the workflow produces "!DLROW ,OLLEH".
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        ReverseTextExecutor reverse = new();

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.Build();

        // Execute the workflow with input data
        await using Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}

/// <summary>
/// Second executor: reverses the input text and completes the workflow.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // Because we do not suppress it, the returned result will be yielded as an output.
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
```

**Output:**
```
UppercaseExecutor: HELLO, WORLD!
ReverseTextExecutor: !DLROW ,OLLEH
```

## Core Concepts

### Executor

An executor is a processing unit — the node in the workflow graph. Every executor:

- Has a **name** (used in events and routing)
- Takes a strongly-typed **input** and produces a strongly-typed **output**
- Receives an `IWorkflowContext` for accessing services and adding custom events

There are two ways to create executors:

**1. Lambda binding (for simple cases):**
```csharp
Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");
```

**2. Subclass `Executor<TInput, TOutput>` (for complex logic):**
```csharp
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
```

### Edge

An edge connects the output of one executor to the input of another:

```csharp
builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
```

- `AddEdge(from, to)` — data flows from `uppercase` to `reverse`
- `.WithOutputFrom(reverse)` — marks `reverse` as the workflow's output node

### WorkflowBuilder

```csharp
WorkflowBuilder builder = new(uppercase); // first executor = entry point
builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
var workflow = builder.Build();
```

The constructor takes the entry executor. Add edges to connect subsequent executors. Call `Build()` to get an immutable `Workflow`.

### Run and Events

```csharp
await using Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
foreach (WorkflowEvent evt in run.NewEvents)
{
    if (evt is ExecutorCompletedEvent executorComplete)
    {
        Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
    }
}
```

`InProcessExecution.RunAsync` executes the workflow in-process. The `Run` object exposes a stream of `WorkflowEvent` objects. Pattern-match on event types to handle specific transitions:

| Event type | Fires when |
|---|---|
| `ExecutorCompletedEvent` | An executor finishes and produces output |
| `WorkflowCompletedEvent` | The entire workflow finishes |
| `SuperStepStartedEvent` | A new round of executor activations begins |

## Workflow Patterns

Beyond the simple sequential pipeline in this sample, workflows support:

- **Fan-out** — one executor's output feeds multiple executors in parallel
- **Fan-in** — multiple executors' outputs feed one executor
- **Conditional routing** — executors can inspect context and choose which outgoing edges to activate
- **AI agents as executors** — `ChatClientAgent` can be bound as an executor

## Running the Sample

```bash
cd dotnet/samples/01-get-started/05_first_workflow
dotnet run
```

## Key Takeaways

- Executors are strongly-typed processing nodes
- `BindAsExecutor` wraps a lambda; subclass `Executor<TIn, TOut>` for complex logic
- `WorkflowBuilder` connects executors with edges
- `InProcessExecution.RunAsync` runs the workflow and returns a `Run` with an event stream
- `ExecutorCompletedEvent` carries the executor's ID and output data
