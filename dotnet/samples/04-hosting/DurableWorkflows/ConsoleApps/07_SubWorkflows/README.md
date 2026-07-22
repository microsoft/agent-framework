# Sub-Workflows Sample (Nested Workflows)

This sample demonstrates how to compose complex workflows from simpler, reusable sub-workflows. Sub-workflows are built using `WorkflowBuilder` and embedded as executors via `BindAsExecutor()`. Unlike the in-process workflow runner, the durable workflow backend persists execution state across process restarts — each sub-workflow runs as a separate orchestration instance on the Durable Task Scheduler, providing independent checkpointing, fault tolerance, and hierarchical visualization in the DTS dashboard.

## Key Concepts Demonstrated

- **Sub-workflows**: Using `Workflow.BindAsExecutor()` to embed a workflow as an executor in another workflow
- **Multi-level nesting**: Sub-workflows within sub-workflows (Level 2 nesting)
- **Automatic discovery**: Registering only the main workflow; sub-workflows are discovered automatically
- **Failure isolation**: Each sub-workflow runs as a separate orchestration instance on the DTS backend
- **Hierarchical visualization**: Parent-child orchestration hierarchy visible in the DTS dashboard
- **Event propagation**: Custom workflow events (`FraudRiskAssessedEvent`) bubble up from nested sub-workflows to the streaming client
- **Message passing**: Using `Executor<TInput>` (void return) with `SendMessageAsync` to forward typed messages to connected executors (`SelectCarrier`)
- **Shared state within sub-workflows**: Using `QueueStateUpdateAsync`/`ReadStateAsync` to share data between executors within a sub-workflow (`AnalyzePatterns` → `CalculateRiskScore`)

## Overview

The sample implements an order processing workflow composed of two sub-workflows, one of which contains its own nested sub-workflow:

```
OrderProcessing (main workflow)
├── OrderReceived
├── Payment (sub-workflow)
│   ├── ValidatePayment
│   ├── FraudCheck (sub-sub-workflow) ← Level 2 nesting!
│   │   ├── AnalyzePatterns
│   │   └── CalculateRiskScore
│   └── ChargePayment
├── Shipping (sub-workflow)
│   ├── SelectCarrier ← Uses SendMessageAsync (void-return executor)
│   └── CreateShipment
└── OrderCompleted
```

| Executor | Sub-Workflow | Description |
|----------|-------------|-------------|
| OrderReceived | Main | Receives order ID and creates order info |
| ValidatePayment | Payment | Validates payment information |
| AnalyzePatterns | FraudCheck (nested in Payment) | Analyzes transaction patterns, stores results in shared state |
| CalculateRiskScore | FraudCheck (nested in Payment) | Reads shared state, calculates risk score, emits `FraudRiskAssessedEvent` |
| ChargePayment | Payment | Charges payment amount |
| SelectCarrier | Shipping | Selects carrier using `SendMessageAsync` (void-return executor) |
| CreateShipment | Shipping | Creates shipment with tracking |
| OrderCompleted | Main | Outputs completed order summary |

## How Sub-Workflows Work

For an introduction to sub-workflows and the `BindAsExecutor()` API, see the [Sub-Workflows foundational sample](../../../../03-workflows/_StartHere/05_SubWorkflows).

This durable sample extends the same pattern — the key difference is that each sub-workflow runs as a **separate orchestration instance** on the Durable Task Scheduler, providing independent checkpointing, fault tolerance, and hierarchical visualization in the DTS dashboard.

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/04-hosting/DurableWorkflows/ConsoleApps/07_SubWorkflows
dotnet run --framework net10.0
```

### Sample Output

```text
Durable Sub-Workflows Sample
Workflow: OrderReceived -> Payment(sub) -> Shipping(sub) -> OrderCompleted
  Payment contains nested FraudCheck sub-workflow (Level 2 nesting)

Enter an order ID (or 'exit'):
> ORD-001
Starting order processing for 'ORD-001'...
Run ID: abc123...

[OrderReceived] Processing order 'ORD-001'
  [Payment/ValidatePayment] Validating payment for order 'ORD-001'...
  [Payment/ValidatePayment] Payment validated for $99.99
    [Payment/FraudCheck/AnalyzePatterns] Analyzing patterns for order 'ORD-001'...
    [Payment/FraudCheck/AnalyzePatterns] ✓ Pattern analysis complete (2 suspicious patterns)
    [Payment/FraudCheck/CalculateRiskScore] Calculating risk score for order 'ORD-001'...
    [Payment/FraudCheck/CalculateRiskScore] ✓ Risk score: 53/100 (based on 2 patterns)
  [Event from sub-workflow] FraudRiskAssessedEvent: Risk score 53/100
  [Payment/ChargePayment] Charging $99.99 for order 'ORD-001'...
  [Payment/ChargePayment] ✓ Payment processed: TXN-A1B2C3D4
  [Shipping/SelectCarrier] Selecting carrier for order 'ORD-001'...
  [Shipping/SelectCarrier] ✓ Selected carrier: Express
  [Shipping/CreateShipment] Creating shipment for order 'ORD-001'...
  [Shipping/CreateShipment] ✓ Shipment created: TRACK-I9J0K1L2M3
┌─────────────────────────────────────────────────────────────────┐
│ [OrderCompleted] Order 'ORD-001' successfully processed!
│   Payment: TXN-A1B2C3D4
│   Shipping: Express - TRACK-I9J0K1L2M3
└─────────────────────────────────────────────────────────────────┘
✓ Order completed: Order ORD-001 completed. Tracking: TRACK-I9J0K1L2M3

> exit
```

### Viewing Workflows in the DTS Dashboard

After running the workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to inspect the orchestration hierarchy, including sub-orchestrations.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.

Because each sub-workflow runs as a separate orchestration instance, the dashboard shows a parent-child hierarchy: the top-level `OrderProcessing` orchestration with `Payment` and `Shipping` as child orchestrations, and `FraudCheck` nested under `Payment`. You can click into each orchestration to inspect its executor inputs/outputs, events, and execution timeline independently.
