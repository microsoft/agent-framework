# Human-in-the-Loop (HITL) Workflow — Azure Functions

This sample demonstrates a durable workflow with Human-in-the-Loop support hosted in Azure Functions. The workflow pauses at two sequential `RequestPort` nodes and waits for external approval responses sent via HTTP endpoints. This simulates an expense that requires both manager and finance approval.

## Key Concepts Demonstrated

- Using multiple `RequestPort` nodes for sequential human-in-the-loop interactions in a durable workflow
- Auto-generated HTTP endpoints for running workflows, checking status, and sending HITL responses
- Pausing orchestrations via `WaitForExternalEvent` and resuming via `RaiseEventAsync`
- Viewing inputs the workflow is waiting for via the status endpoint

## Workflow

`CreateApprovalRequest` → `ManagerApproval` (HITL pause) → `PrepareFinanceReview` → `FinanceApproval` (HITL pause) → `ExpenseReimburse`

## HTTP Endpoints

The framework auto-generates these endpoints for workflows with `RequestPort` nodes:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workflows/ExpenseReimbursement/run` | Start the workflow |
| GET | `/api/workflows/ExpenseReimbursement/status/{runId}` | Check status and inputs the workflow is waiting for |
| POST | `/api/workflows/ExpenseReimbursement/respond/{runId}` | Send approval response to resume |

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for information on how to configure the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending HTTP requests to the workflow endpoints.

You can use the `demo.http` file to trigger the workflow, or a command line tool like `curl` as shown below:

### Step 1: Start the Workflow

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/run \
    -H "Content-Type: text/plain" -d "EXP-2025-001"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/run `
    -ContentType text/plain `
    -Body "EXP-2025-001"
```

The response will confirm the workflow orchestration has started:

```text
Workflow orchestration started for ExpenseReimbursement. Orchestration runId: abc123def456
```

> **Tip:** You can provide a custom run ID by appending a `runId` query parameter:
>
> ```bash
> curl -X POST "http://localhost:7071/api/workflows/ExpenseReimbursement/run?runId=expense-001" \
>     -H "Content-Type: text/plain" -d "EXP-2025-001"
> ```
>
> If not provided, a unique run ID is auto-generated.

### Step 2: Check Workflow Status

The workflow pauses at the `ManagerApproval` RequestPort. Query the status endpoint to see what input it is waiting for:

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

```json
{
  "runId": "{runId}",
  "status": "Running",
  "waitingForInput": [
    { "eventName": "ManagerApproval", "input": { "ExpenseId": "EXP-2025-001", "Amount": 1500.00, "EmployeeName": "Jerry" } }
  ]
}
```

> **Tip:** You can also verify this in the DTS dashboard at `http://localhost:8082`. Find the orchestration by its `runId` and you will see it is in a "Running" state, paused at a `WaitForExternalEvent` call for the `ManagerApproval` event.

### Step 3: Send Manager Approval Response

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} \
    -H "Content-Type: application/json" \
    -d '{"eventName": "ManagerApproval", "response": {"Approved": true, "Comments": "Approved by manager."}}'
```

```json
{
  "message": "Response sent to workflow.",
  "runId": "{runId}",
  "eventName": "ManagerApproval",
  "validated": true
}
```

### Step 4: Check Workflow Status Again

The workflow now pauses at the `FinanceApproval` RequestPort:

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

```json
{
  "runId": "{runId}",
  "status": "Running",
  "waitingForInput": [
    { "eventName": "FinanceApproval", "input": { "ExpenseId": "EXP-2025-001", "Amount": 1500.00, "EmployeeName": "Jerry" } }
  ]
}
```

### Step 5: Send Finance Approval Response

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} \
    -H "Content-Type: application/json" \
    -d '{"eventName": "FinanceApproval", "response": {"Approved": true, "Comments": "Finance approved."}}'
```

```json
{
  "message": "Response sent to workflow.",
  "runId": "{runId}",
  "eventName": "FinanceApproval",
  "validated": true
}
```

### Step 6: Check Final Status

After both approvals, the workflow completes and the expense is reimbursed:

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

```json
{
  "runId": "{runId}",
  "status": "Completed",
  "waitingForInput": null
}
```

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to visualize the orchestration and inspect its execution history.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.

1. Open the dashboard and look for the orchestration instance matching the `runId` returned in Step 1 (e.g., `abc123def456` or your custom ID like `expense-001`).
2. Click into the instance to see the execution timeline, which shows each executor activity and the two `WaitForExternalEvent` pauses where the workflow waited for human input.
3. Expand individual activity steps to inspect inputs and outputs — for example, the `ManagerApproval` and `FinanceApproval` external events will show the approval request sent and the response received.
