# Sequential Workflow Sample

This sample demonstrates how to run a sequential workflow as a durable orchestration from a console application using the Durable Task Framework. It showcases the **durability** aspect - if the process crashes mid-execution, the workflow automatically resumes without re-executing completed activities.

## Key Concepts Demonstrated

- Building a sequential workflow with the `WorkflowBuilder` API
- Using `ConfigureDurableWorkflows` to register workflows with dependency injection
- Running workflows with `IWorkflowClient`
- **Durability**: Automatic resume of interrupted workflows
- **Activity caching**: Completed activities are not re-executed on replay

## Overview

The sample implements an order cancellation workflow with three executors:

```
OrderLookup --> OrderCancel --> SendEmail
```

| Executor | Description |
|----------|-------------|
| OrderLookup | Looks up an order by ID |
| OrderCancel | Marks the order as cancelled |
| SendEmail | Sends a cancellation confirmation email |

## Durability Demonstration

The key feature of Durable Task Framework is **durability**:

- **Activity results are persisted**: When an activity completes, its result is saved
- **Orchestrations replay**: On restart, the orchestration replays from the beginning
- **Completed activities skip execution**: The framework uses cached results
- **Automatic resume**: The worker automatically picks up pending work on startup

### Try It Yourself

> **Tip:** To give yourself more time to stop the application during `OrderCancel`, consider increasing the loop iteration count or `Task.Delay` duration in the `OrderCancel` executor in `OrderCancelExecutors.cs`.

1. Start the application and enter an order ID (e.g., `12345`)
2. Wait for `OrderLookup` to complete, then stop the app (Ctrl+C) during `OrderCancel`
3. Restart the application
4. Observe:
   - `OrderLookup` is **NOT** re-executed (result was cached)
   - `OrderCancel` **restarts** (it didn't complete before the interruption)
   - `SendEmail` runs after `OrderCancel` completes

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/01_SequentialWorkflow
dotnet run --framework net10.0
```

### Sample Output

```text
Durable Workflow Sample
Workflow: OrderLookup -> OrderCancel -> SendEmail

Enter an order ID (or 'exit'):
> 12345
Starting workflow for order: 12345
Run ID: abc123...

[OrderLookup] Looking up order '12345'...
[OrderLookup] Found order for customer 'Jerry'

[OrderCancel] Cancelling order '12345'...
[OrderCancel] Order cancelled successfully

[SendEmail] Sending email to 'jerry@example.com'...
[SendEmail] Email sent successfully

Workflow completed!

> exit
```

