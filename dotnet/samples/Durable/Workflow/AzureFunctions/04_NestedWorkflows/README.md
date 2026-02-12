# Nested Workflows - Azure Functions Sample

This sample demonstrates how to build **nested workflows** (sub-workflows) hosted as an Azure Function. One workflow can be used as an executor within another workflow, enabling modular, reusable workflow components.

## Key Concepts Demonstrated

- Building workflows with **sub-workflow executors** using `BindAsExecutor`
- **Multi-level nesting** — a sub-workflow contains its own sub-workflow (FraudCheck inside Payment)
- Hosting nested workflows as an Azure Function using `ConfigureDurableOptions`
- Automatic discovery and registration of sub-workflows

## Overview

The workflow implements an order processing pipeline where each stage is a separate sub-workflow:

```
OrderReceived
    │
    ▼
┌─────────────────────────────────┐
│ Payment (Sub-Workflow)          │
│  ValidatePayment                │
│    ▼                            │
│  ┌────────────────────────────┐ │
│  │ FraudCheck (Sub-Sub)       │ │
│  │  AnalyzePatterns           │ │
│  │    ▼                       │ │
│  │  CalculateRiskScore        │ │
│  └────────────────────────────┘ │
│    ▼                            │
│  ChargePayment                  │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Inventory (Sub-Workflow)        │
│  CheckInventory ──► Reserve     │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Shipping (Sub-Workflow)         │
│  SelectCarrier ──► CreateShip.  │
└─────────────────────────────────┘
    │
    ▼
OrderCompleted
```

| Executor | Sub-Workflow | Description |
|----------|-------------|-------------|
| OrderReceived | Main | Receives order ID and creates OrderInfo |
| ValidatePayment | Payment | Validates payment information |
| AnalyzePatterns | FraudCheck (nested in Payment) | Analyzes transaction patterns |
| CalculateRiskScore | FraudCheck (nested in Payment) | Calculates fraud risk score |
| ChargePayment | Payment | Charges the payment |
| CheckInventory | Inventory | Checks item availability |
| ReserveInventory | Inventory | Reserves inventory items |
| SelectCarrier | Shipping | Selects shipping carrier |
| CreateShipment | Shipping | Creates shipment with tracking |
| OrderCompleted | Main | Outputs completed order summary |

## How Nested Workflows Work

Sub-workflows are created by binding a workflow as an executor:

```csharp
// Build a sub-workflow
Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// Bind it as an executor in the parent workflow
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");

// Use it like any other executor
Workflow mainWorkflow = new WorkflowBuilder(orderReceived)
    .AddEdge(orderReceived, paymentExecutor)
    .Build();
```

Each sub-workflow runs as a separate orchestration instance, providing:
- **Modularity** — workflows can be composed from reusable sub-workflows
- **Independent checkpointing** — each sub-workflow has its own replay history
- **Hierarchical visualization** — view parent-child relationships in the DTS dashboard
- **Failure isolation** — sub-workflow failures don't corrupt parent state

## Environment Setup

This sample requires:

- [.NET 10 SDK](https://dotnet.microsoft.com/download)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-azure-managed-storage) running locally (default: `http://localhost:8080`)
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) for local Azure Storage emulation

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/AzureFunctions/04_NestedWorkflows
func start
```

### Testing

```bash
curl -X POST http://localhost:7071/api/workflows/OrderProcessing/run -H "Content-Type: text/plain" -d "ORD-2026-001"
```

Open the DTS dashboard at `http://localhost:8080` to see the parent-child orchestration hierarchy in the Timeline view.
