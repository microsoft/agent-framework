# Workflow Human-in-the-Loop (HITL) Sample

This sample demonstrates a **Human-in-the-Loop** pattern in durable workflows using `RequestPort`. The workflow pauses execution at two sequential approval points — manager and finance — and resumes when each response is provided.

## Key Concepts Demonstrated

- Using `RequestPort` to define external input points in a workflow
- Multiple sequential HITL pause points in a single workflow
- Streaming workflow events with `IStreamingWorkflowRun`
- Handling `DurableWorkflowWaitingForInputEvent` to detect HITL pauses
- Using `SendResponseAsync` to provide responses and resume the workflow
- **Durability**: The workflow survives process restarts while waiting for human input

## Workflow

```
CreateApprovalRequest -> ManagerApproval (RequestPort) -> PrepareFinanceReview -> FinanceApproval (RequestPort) -> ExpenseReimburse
```

| Step | Description |
|------|-------------|
| CreateApprovalRequest | Retrieves expense details and creates an approval request |
| ManagerApproval (RequestPort) | **PAUSES** the workflow and waits for manager approval |
| PrepareFinanceReview | Prepares the request for finance review after manager approval |
| FinanceApproval (RequestPort) | **PAUSES** the workflow and waits for finance approval |
| ExpenseReimburse | Processes the reimbursement based on the final approval |

## How It Works

A `RequestPort` defines a typed external input point in the workflow:

```csharp
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval =
    RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
```

Use `WatchStreamAsync` to observe events. When the workflow reaches a `RequestPort`, a `DurableWorkflowWaitingForInputEvent` is emitted. Call `SendResponseAsync` to provide the response and resume the workflow:

```csharp
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case DurableWorkflowWaitingForInputEvent requestEvent:
            ApprovalRequest? request = requestEvent.GetInputAs<ApprovalRequest>();
            await run.SendResponseAsync(requestEvent, new ApprovalResponse(Approved: true, Comments: "Approved."));
            break;
    }
}
```

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/08_WorkflowHITL
dotnet run --framework net10.0
```

### Sample Output

```text
Starting expense reimbursement workflow for expense: EXP-2025-001
Workflow started with instance ID: abc123...

Workflow paused at RequestPort: ManagerApproval
  Input: {"expenseId":"EXP-2025-001","amount":1500.00,"employeeName":"Jerry"}
  Approval for: Jerry, Amount: $1,500.00
  Response sent: Approved=True

Workflow paused at RequestPort: FinanceApproval
  Input: {"expenseId":"EXP-2025-001","amount":1500.00,"employeeName":"Jerry"}
  Approval for: Jerry, Amount: $1,500.00
  Response sent: Approved=True

Workflow completed: Expense reimbursed at 2025-01-23T17:30:00.0000000Z
```
