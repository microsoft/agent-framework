# Sequential Workflow Sample

This sample demonstrates how to use the Microsoft Agent Framework to create an Azure Functions app that hosts durable workflows with sequential executor chains. It showcases two workflows that share a common executor, demonstrating executor reuse across workflows.

## Key Concepts Demonstrated

- Defining workflows with sequential executor chains using `WorkflowBuilder`
- Sharing executors across multiple workflows (the `OrderLookup` executor is used by both workflows)
- Registering workflows with the Function app using `ConfigureDurableWorkflows`
- Durable orchestration ensuring workflows survive process restarts and failures
- Starting workflows via HTTP requests
- Viewing workflow execution history and status in the Durable Task Scheduler (DTS) dashboard

## Workflows

This sample defines two workflows:

1. **CancelOrder**: `OrderLookup` → `OrderCancel` → `SendEmail` — Looks up an order, cancels it, and sends a confirmation email.
2. **OrderStatus**: `OrderLookup` → `StatusReport` — Looks up an order and generates a status report.

Both workflows share the `OrderLookup` executor, which is registered only once by the framework.

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending HTTP requests to the workflow endpoints.

You can use the `demo.http` file to trigger the workflows, or a command line tool like `curl` as shown below:

### Cancel an Order

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/CancelOrder/run \
    -H "Content-Type: text/plain" \
    -d "12345"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/CancelOrder/run `
    -ContentType text/plain `
    -Body "12345"
```

The response will confirm the workflow orchestration has started:

```text
Workflow orchestration started for CancelOrder. Orchestration instanceId: abc123def456
```

In the function app logs, you will see the sequential execution of each executor:

```text
│ [Activity] OrderLookup: Starting lookup for order '12345'
│ [Activity] OrderLookup: Found order '12345' for customer 'Jerry'
│ [Activity] OrderCancel: Starting cancellation for order '12345'
│ [Activity] OrderCancel: ✓ Order '12345' has been cancelled
│ [Activity] SendEmail: Sending email to 'jerry@example.com'...
│ [Activity] SendEmail: ✓ Email sent successfully!
```

### Get Order Status

```bash
curl -X POST http://localhost:7071/api/workflows/OrderStatus/run \
    -H "Content-Type: text/plain" \
    -d "12345"
```

The `OrderStatus` workflow reuses the same `OrderLookup` executor and then generates a status report:

```text
│ [Activity] OrderLookup: Starting lookup for order '12345'
│ [Activity] OrderLookup: Found order '12345' for customer 'Jerry'
│ [Activity] StatusReport: Generating report for order '12345'
│ [Activity] StatusReport: ✓ Order 12345 for Jerry: Status=Active, Date=2025-01-01
```

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to visualize the completed orchestration, inspect inputs/outputs for each step, and view execution history.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.
