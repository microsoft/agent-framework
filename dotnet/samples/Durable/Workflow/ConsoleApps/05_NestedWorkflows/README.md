# Nested Workflows Sample

This sample demonstrates how to use **nested workflows** (sub-workflows) where one workflow can be used as an executor within another workflow. This enables modular, reusable workflow components with independent checkpointing and replay.

## Key Concepts Demonstrated

- Using `Workflow.BindAsExecutor()` to embed a workflow as an executor in another workflow
- Multi-level nesting (sub-workflow within a sub-workflow)
- Automatic discovery of sub-workflows when registering the main workflow
- Independent orchestration instances for each sub-workflow

## Overview

The sample implements an order processing workflow with three sub-workflows and one sub-sub-workflow:

```
OrderProcessing (Main Workflow)
├── OrderReceived
├── Payment (sub-workflow)
│   ├── ValidatePayment
│   ├── FraudCheck (sub-sub-workflow) ← Level 2 nesting!
│   │   ├── AnalyzePatterns
│   │   └── CalculateRiskScore
│   └── ChargePayment
├── Inventory (sub-workflow)
│   ├── CheckInventory
│   └── ReserveInventory
├── Shipping (sub-workflow)
│   ├── SelectCarrier
│   └── CreateShipment
└── OrderCompleted
```

## How Nested Workflows Work

Sub-workflows are created using `BindAsExecutor()`, which converts a `Workflow` into an `ExecutorBinding` that can be used in another workflow's graph:

```csharp
// Build a sub-workflow
Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// Bind as executor for use in the parent workflow
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");

// Use in the main workflow
Workflow mainWorkflow = new WorkflowBuilder(orderReceived)
    .AddEdge(orderReceived, paymentExecutor)
    .Build();
```

Each sub-workflow runs as a separate orchestration instance in the Durable Task Scheduler, visible in the DTS dashboard Timeline view.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/05_NestedWorkflows
dotnet run --framework net10.0
```

### Sample Output

```text
╔══════════════════════════════════════════════════════════════════╗
║           Nested Workflows Sample                               ║
╠══════════════════════════════════════════════════════════════════╣
║  Main Workflow: OrderProcessing                                  ║
║  ├── Payment (sub-workflow)                                      ║
║  │   ├── ValidatePayment                                         ║
║  │   ├── FraudCheck (sub-sub-workflow) ← Level 2 nesting!        ║
║  │   │   ├── AnalyzePatterns                                     ║
║  │   │   └── CalculateRiskScore                                  ║
║  │   └── ChargePayment                                           ║
║  ├── Inventory (sub-workflow)                                    ║
║  │   ├── CheckInventory                                          ║
║  │   └── ReserveInventory                                        ║
║  └── Shipping (sub-workflow)                                     ║
║      ├── SelectCarrier                                           ║
║      └── CreateShipment                                          ║
╚══════════════════════════════════════════════════════════════════╝

Enter an order ID (or 'exit'):
> ORD-001
Starting order processing for 'ORD-001'...
Run ID: abc123...
Waiting for workflow to complete...
✓ Order completed: Order ORD-001 completed. Tracking: TRACK-1A2B3C4D5E
```
