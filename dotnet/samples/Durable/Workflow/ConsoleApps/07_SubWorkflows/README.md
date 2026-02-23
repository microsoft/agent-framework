# Sub-Workflows Sample (Nested Workflows)

This sample demonstrates how to compose complex workflows from simpler, reusable sub-workflows using the Durable Task Framework. Sub-workflows run as separate orchestration instances, providing modular design, independent checkpointing, and hierarchical visualization in the DTS dashboard.

## Key Concepts Demonstrated

- **Sub-workflows**: Using `Workflow.BindAsExecutor()` to embed a workflow as an executor in another workflow
- **Multi-level nesting**: Sub-workflows within sub-workflows (Level 2 nesting)
- **Automatic discovery**: Registering only the main workflow; sub-workflows are discovered automatically
- **Failure isolation**: Each sub-workflow runs as a separate orchestration instance
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

1. **Build** each sub-workflow as a standalone `Workflow` using `WorkflowBuilder`
2. **Bind** a workflow as an executor using `workflow.BindAsExecutor("name")`
3. **Add** the bound executor as a node in the parent workflow's graph
4. **Register** only the top-level workflow — sub-workflows are discovered and registered automatically

```csharp
// Build a sub-workflow
Workflow fraudCheckWorkflow = new WorkflowBuilder(analyzePatterns)
    .WithName("SubFraudCheck")
    .AddEdge(analyzePatterns, calculateRiskScore)
    .Build();

// Nest it inside another sub-workflow using BindAsExecutor
ExecutorBinding fraudCheckExecutor = fraudCheckWorkflow.BindAsExecutor("FraudCheck");

Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// Use the Payment sub-workflow in the main workflow
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");

Workflow mainWorkflow = new WorkflowBuilder(orderReceived)
    .AddEdge(orderReceived, paymentExecutor)
    .AddEdge(paymentExecutor, orderCompleted)
    .Build();
```

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/07_SubWorkflows
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
