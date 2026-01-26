# Workflow Human-in-the-Loop (HITL) Sample

This sample demonstrates a **Human-in-the-Loop** pattern in durable workflows using `RequestPort`. The workflow pauses execution to wait for external input (e.g., manager approval) and resumes when the response is provided.

## Overview

The sample implements an expense approval workflow:

1. **CreateApprovalRequest** - Retrieves expense details and creates an approval request
2. **ManagerApproval** (RequestPort) - Pauses workflow to wait for manager approval
3. **ExpenseReimburse** - Processes the reimbursement based on approval response

## Workflow Flow

```
User Input (Expense ID)
       |
       v
+---------------------+
| CreateApprovalRequest|  Creates ApprovalRequest with expense details
+---------------------+
       |
       v
+---------------------+
|  ManagerApproval    |  RequestPort - PAUSES here waiting for external input
|   (RequestPort)     |  Workflow is durable while waiting
+---------------------+
       |
       v  (ApprovalResponse)
+---------------------+
|  ExpenseReimburse   |  Processes reimbursement if approved
+---------------------+
       |
       v
    Result
```

## Key Concepts

- **RequestPort** - A special executor that pauses the workflow and waits for external input
- **DurableRequestInfoEvent** - Event emitted when the workflow reaches a RequestPort
- **SendResponseAsync** - Method to provide the response and resume the workflow
- **Durability** - The workflow can survive process restarts while waiting for human input

## Code Highlights

### Defining the RequestPort

```csharp
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval = 
    RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
```

### Handling the Request Event

```csharp
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case DurableRequestInfoEvent requestEvent:
            // Workflow is waiting for input
            ApprovalResponse response = HandleApprovalRequest(requestEvent);
            await run.SendResponseAsync(requestEvent, response);
            break;
        // ... other events
    }
}
```

## Environment Setup

See the [README.md](../README.md) file in the parent directory for environment configuration.

## Running the Sample

```bash
cd dotnet/samples/DurableAgents/ConsoleApps/10_Workflow_HITL
dotnet run --framework net10.0
```

### Sample Output

```
Starting expense reimbursement workflow for expense: EXP-2025-001
Workflow started with instance ID: abc123...
Watching for workflow events...

Workflow is waiting for input at RequestPort: ManagerApproval
  Input data: {"ExpenseId":"EXP-2025-001","Amount":1500.00,"EmployeeName":"Jerry"}
  Expected response type: SingleAgent.ApprovalResponse
  Approval request for: Jerry, Amount: $1,500.00
  Response sent: Approved=True

Workflow completed with result: Expense reimbursed at 1/23/2025 5:30:00 PM
```
