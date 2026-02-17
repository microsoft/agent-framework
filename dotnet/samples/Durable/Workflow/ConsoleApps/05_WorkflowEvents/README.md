# Workflow Events Sample

This sample demonstrates how to use workflow events and streaming in durable workflows.

## What it demonstrates

1. **Custom Events** (`AddEventAsync`) — Executors emit domain-specific events during execution
2. **Event Streaming** (`StreamAsync` / `WatchStreamAsync`) — Callers observe events in real-time as the workflow progresses
3. **Framework Events** — Automatic `ExecutorInvokedEvent`, `ExecutorCompletedEvent`, and `WorkflowOutputEvent` events emitted by the framework

## Emitting Custom Events

Executors can emit custom domain events during execution using the `IWorkflowContext` instance passed to `HandleAsync`. These events are streamed to callers in real-time via `WatchStreamAsync`.

### Defining a custom event

Create a class that inherits from `WorkflowEvent`. Pass any data payload to the base constructor:

```csharp
public class CancellationProgressEvent(int percentComplete, string status) : WorkflowEvent(status)
{
    public int PercentComplete { get; } = percentComplete;
    public string Status { get; } = status;
}
```

### Emitting the event from an executor

Call `AddEventAsync` on the `IWorkflowContext` inside your executor's `HandleAsync` method:

```csharp
public override async ValueTask<Order> HandleAsync(
    Order message,
    IWorkflowContext context,
    CancellationToken cancellationToken = default)
{
    await context.AddEventAsync(new CancellationProgressEvent(33, "Processing refund"), cancellationToken);
    // ... rest of the executor logic
}
```

### Observing events from the caller

Use `StreamAsync` to start the workflow and `WatchStreamAsync` to observe events. Pattern match on your custom event types:

```csharp
IStreamingWorkflowRun run = await workflowClient.StreamAsync(workflow, input);

await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case CancellationProgressEvent e:
            Console.WriteLine($"{e.PercentComplete}% - {e.Status}");
            break;
    }
}
```

## Workflow Structure

```
OrderLookup → OrderCancel → SendEmail
```

Each executor emits custom events during execution:
- `OrderLookup` emits `OrderLookupStartedEvent` and `OrderFoundEvent`
- `OrderCancel` emits `CancellationProgressEvent` (with percentage) and `OrderCancelledEvent`
- `SendEmail` emits `EmailSentEvent`

## Prerequisites

- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler) running locally or in Azure
- Set the `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` environment variable (defaults to local emulator)

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the sample

```bash
dotnet run
```

Enter an order ID at the prompt to start a workflow and watch events stream in real-time:

```text
> order-42
Started run: b6ba4d19...
  New event received at 13:27:41.4956 (ExecutorInvokedEvent)
  New event received at 13:27:41.5019 (OrderLookupStartedEvent)
    [Lookup] Looking up order order-42
  New event received at 13:27:41.5025 (OrderFoundEvent)
    [Lookup] Found: Jerry
  New event received at 13:27:41.5026 (ExecutorCompletedEvent)
  New event received at 13:27:41.5026 (WorkflowOutputEvent)
    [Output] OrderLookup
  New event received at 13:27:43.0772 (ExecutorInvokedEvent)
  New event received at 13:27:43.0773 (CancellationProgressEvent)
    [Cancel] 0% - Starting cancellation
  New event received at 13:27:43.0775 (CancellationProgressEvent)
    [Cancel] 33% - Contacting payment provider
  New event received at 13:27:43.0776 (CancellationProgressEvent)
    [Cancel] 66% - Processing refund
  New event received at 13:27:43.0777 (CancellationProgressEvent)
    [Cancel] 100% - Complete
  New event received at 13:27:43.0779 (OrderCancelledEvent)
    [Cancel] Done
  New event received at 13:27:43.0780 (ExecutorCompletedEvent)
  New event received at 13:27:43.0780 (WorkflowOutputEvent)
    [Output] OrderCancel
  New event received at 13:27:43.6610 (ExecutorInvokedEvent)
  New event received at 13:27:43.6611 (EmailSentEvent)
    [Email] Sent to jerry@example.com
  New event received at 13:27:43.6613 (ExecutorCompletedEvent)
  New event received at 13:27:43.6613 (WorkflowOutputEvent)
    [Output] SendEmail
  New event received at 13:27:43.6619 (DurableWorkflowCompletedEvent)
  Completed: Cancellation email sent for order order-42 to jerry@example.com.
```

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to inspect the workflow execution and events.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.
