# Human-in-the-Loop (HITL) Workflow — Azure Functions

This sample demonstrates a durable workflow with Human-in-the-Loop support hosted in Azure Functions. The workflow pauses at three `RequestPort` nodes — one sequential manager approval, then two parallel finance approvals (budget and compliance) via fan-out/fan-in. Approval responses are sent via HTTP endpoints.

## Key Concepts Demonstrated

- Using multiple `RequestPort` nodes for sequential and parallel human-in-the-loop interactions in a durable workflow
- Fan-out/fan-in pattern for parallel approval steps
- Auto-generated HTTP endpoints for running workflows, checking status, and sending HITL responses
- Pausing orchestrations via `WaitForExternalEvent` and resuming via `RaiseEventAsync`
- Viewing inputs the workflow is waiting for via the status endpoint

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

> [!TIP]
> You can provide a custom run ID by appending a `runId` query parameter:
>
> Bash (Linux/macOS/WSL):
>
> ```bash
> curl -X POST "http://localhost:7071/api/workflows/ExpenseReimbursement/run?runId=expense-001" \
>     -H "Content-Type: text/plain" -d "EXP-2025-001"
> ```
>
> PowerShell:
>
> ```powershell
> Invoke-RestMethod -Method Post `
>     -Uri "http://localhost:7071/api/workflows/ExpenseReimbursement/run?runId=expense-001" `
>     -ContentType text/plain `
>     -Body "EXP-2025-001"
> ```
>
> If not provided, a unique run ID is auto-generated.

### Step 2: Check Workflow Status

The workflow pauses at the `ManagerApproval` RequestPort. Query the status endpoint to see what input it is waiting for:

Bash (Linux/macOS/WSL):

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
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

> [!TIP]
> You can also verify this in the DTS dashboard at `http://localhost:8082`. Find the orchestration by its `runId` and you will see it is in a "Running" state, paused at a `WaitForExternalEvent` call for the `ManagerApproval` event.

### Step 3: Send Manager Approval Response

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} \
    -H "Content-Type: application/json" \
    -d '{"eventName": "ManagerApproval", "response": {"Approved": true, "Comments": "Approved by manager."}}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} `
    -ContentType application/json `
    -Body '{"eventName": "ManagerApproval", "response": {"Approved": true, "Comments": "Approved by manager."}}'
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

The workflow now pauses at both the `BudgetApproval` and `ComplianceApproval` RequestPorts in parallel:

Bash (Linux/macOS/WSL):

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

```json
{
  "runId": "{runId}",
  "status": "Running",
  "waitingForInput": [
    { "eventName": "BudgetApproval", "input": { "ExpenseId": "EXP-2025-001", "Amount": 1500.00, "EmployeeName": "Jerry" } },
    { "eventName": "ComplianceApproval", "input": { "ExpenseId": "EXP-2025-001", "Amount": 1500.00, "EmployeeName": "Jerry" } }
  ]
}
```

### Step 5a: Send Budget Approval Response

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} \
    -H "Content-Type: application/json" \
    -d '{"eventName": "BudgetApproval", "response": {"Approved": true, "Comments": "Budget approved."}}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} `
    -ContentType application/json `
    -Body '{"eventName": "BudgetApproval", "response": {"Approved": true, "Comments": "Budget approved."}}'
```

```json
{
  "message": "Response sent to workflow.",
  "runId": "{runId}",
  "eventName": "BudgetApproval",
  "validated": true
}
```

### Step 5b: Send Compliance Approval Response

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} \
    -H "Content-Type: application/json" \
    -d '{"eventName": "ComplianceApproval", "response": {"Approved": true, "Comments": "Compliance approved."}}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/respond/{runId} `
    -ContentType application/json `
    -Body '{"eventName": "ComplianceApproval", "response": {"Approved": true, "Comments": "Compliance approved."}}'
```

```json
{
  "message": "Response sent to workflow.",
  "runId": "{runId}",
  "eventName": "ComplianceApproval",
  "validated": true
}
```

### Step 6: Check Final Status

After all approvals, the workflow completes and the expense is reimbursed:

Bash (Linux/macOS/WSL):

```bash
curl http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:7071/api/workflows/ExpenseReimbursement/status/{runId}
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
2. Click into the instance to see the execution timeline, which shows each executor activity and the `WaitForExternalEvent` pauses where the workflow waited for human input — including the two parallel finance approvals.
3. Expand individual activity steps to inspect inputs and outputs — for example, the `ManagerApproval`, `BudgetApproval`, and `ComplianceApproval` external events will show the approval request sent and the response received.
