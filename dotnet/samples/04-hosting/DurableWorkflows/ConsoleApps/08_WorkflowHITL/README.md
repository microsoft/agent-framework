# Workflow Human-in-the-Loop (HITL) Sample

This sample demonstrates a **Human-in-the-Loop** pattern in durable workflows using `RequestPort`. The workflow pauses execution at a manager approval point, then fans out to two parallel finance approval points — budget and compliance — before resuming.

## Key Concepts Demonstrated

- Using `RequestPort` to define external input points in a workflow
- Sequential and parallel HITL pause points in a single workflow using fan-out/fan-in
- Streaming workflow events with `IStreamingWorkflowRun`
- Handling `DurableWorkflowWaitingForInputEvent` to detect HITL pauses
- Using `SendResponseAsync` to provide responses and resume the workflow
- **Durability**: The workflow survives process restarts while waiting for human input

## Workflow

This sample implements the following workflow:

```
┌──────────────────────┐   ┌────────────────┐   ┌─────────────────────┐    ┌────────────────────┐
│ CreateApprovalRequest│──►│ManagerApproval │──►│PrepareFinanceReview │──┬►│  BudgetApproval    │──┐
└──────────────────────┘   │ (RequestPort)  │   └─────────────────────┘  │ │  (RequestPort)     │  │
                           └────────────────┘                            │ └────────────────────┘  │  ┌─────────────────┐
                                                                         │                         ├─►│ExpenseReimburse │
                                                                         │ ┌────────────────────┐  │  └─────────────────┘
                                                                         └►│ComplianceApproval  │──┘
                                                                           │  (RequestPort)     │
                                                                           └────────────────────┘
```

| Step | Description |
|------|-------------|
| CreateApprovalRequest | Retrieves expense details and creates an approval request |
| ManagerApproval (RequestPort) | **PAUSES** the workflow and waits for manager approval |
| PrepareFinanceReview | Prepares the request for finance review after manager approval |
| BudgetApproval (RequestPort) | **PAUSES** the workflow and waits for budget approval (parallel) |
| ComplianceApproval (RequestPort) | **PAUSES** the workflow and waits for compliance approval (parallel) |
| ExpenseReimburse | Processes the reimbursement after all approvals pass |

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

See the [README.md](../../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/04-hosting/DurableWorkflows/ConsoleApps/08_WorkflowHITL
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

Workflow paused at RequestPort: BudgetApproval
  Input: {"expenseId":"EXP-2025-001","amount":1500.00,"employeeName":"Jerry"}
  Approval for: Jerry, Amount: $1,500.00
  Response sent: Approved=True

Workflow paused at RequestPort: ComplianceApproval
  Input: {"expenseId":"EXP-2025-001","amount":1500.00,"employeeName":"Jerry"}
  Approval for: Jerry, Amount: $1,500.00
  Response sent: Approved=True

Workflow completed: Expense reimbursed at 2025-01-23T17:30:00.0000000Z
```

### Viewing Workflows in the DTS Dashboard

After running the sample, you can navigate to the Durable Task Scheduler (DTS) dashboard to visualize the completed orchestration and inspect its execution history.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.

1. Open the dashboard and look for the orchestration instance matching the instance ID logged in the console output (e.g., `abc123...`).
2. Click into the instance to see the execution timeline, which shows each executor activity and the `WaitForExternalEvent` pauses where the workflow waited for human input — including the two parallel finance approvals.
3. Expand individual activity steps to inspect inputs and outputs — for example, the `ManagerApproval`, `BudgetApproval`, and `ComplianceApproval` external events will show the approval request sent and the response received.
