# Sub-Workflows Console Sample

This sample demonstrates how to compose workflows hierarchically by using sub-workflows within a durable orchestration. Sub-workflows are executed as separate orchestration instances, providing modularity, reusability, and excellent visibility in the Durable Task dashboard.

## Overview

The sample implements an order processing system with three sub-workflows:

```
OrderProcessing (Main Workflow)
??? OrderReceived
??? Payment (Sub-Workflow)
?   ??? ValidatePayment (1s)
?   ??? ChargePayment (2s)
??? Inventory (Sub-Workflow)
?   ??? CheckInventory (1s)
?   ??? ReserveInventory (2s)
??? Shipping (Sub-Workflow)
?   ??? SelectCarrier (1s)
?   ??? CreateShipment (2s)
??? OrderCompleted
```

## Key Concepts

### Sub-Workflow Benefits

1. **Modularity**: Each sub-workflow encapsulates related logic (payment, inventory, shipping)
2. **Reusability**: Sub-workflows can be used in multiple parent workflows
3. **Independent Execution**: Each sub-workflow runs as a separate orchestration instance
4. **Dashboard Visibility**: Sub-workflows appear in the Timeline view with parent-child relationships
5. **Failure Isolation**: A failure in a sub-workflow doesn't corrupt the parent's state

### How Sub-Workflows Work

```csharp
// Step 1: Build a sub-workflow
Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("PaymentProcessing")
    .AddEdge(validatePayment, chargePayment)
    .Build();

// Step 2: Bind it as an executor for use in a parent workflow
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");

// Step 3: Use the sub-workflow executor in the main workflow
Workflow mainWorkflow = new WorkflowBuilder(orderReceived)
    .AddEdge(orderReceived, paymentExecutor)  // Sub-workflow as an edge target
    .AddEdge(paymentExecutor, inventoryExecutor)
    .Build();

// Step 4: Register only the main workflow - sub-workflows are discovered automatically!
services.ConfigureDurableWorkflows(
    options => options.Workflows.AddWorkflow(mainWorkflow),
    ...);
```

### Dashboard Visualization

Open the DTS dashboard at `http://localhost:8080` after running a workflow:

1. Click on the main orchestration instance
2. Switch to the **Timeline** tab
3. You'll see a hierarchical view showing:
   - `OrderProcessing` (parent orchestration)
   - `PaymentProcessing` (sub-orchestration)
   - `InventoryManagement` (sub-orchestration)
   - `ShippingArrangement` (sub-orchestration)

Each sub-orchestration has its own instance ID and can be inspected independently.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on:
- Installing prerequisites (.NET 10+, Docker)
- Starting the Durable Task Scheduler emulator
- Configuring environment variables

## Running the Sample

```bash
# Start the DTS emulator (if not already running)
docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest

# Run the sample
cd dotnet/samples/DurableAgents/ConsoleApps/09_SubWorkflows
dotnet run --framework net10.0
```

### Sample Session

```text
????????????????????????????????????????????????????????????????????
?           Durable Sub-Workflows Sample                           ?
????????????????????????????????????????????????????????????????????
?  Main Workflow: OrderProcessing                                  ?
?  ??? Payment (sub-workflow)                                      ?
?  ?   ??? ValidatePayment (1s)                                    ?
?  ?   ??? ChargePayment (2s)                                      ?
?  ??? Inventory (sub-workflow)                                    ?
?  ?   ??? CheckInventory (1s)                                     ?
?  ?   ??? ReserveInventory (2s)                                   ?
?  ??? Shipping (sub-workflow)                                     ?
?      ??? SelectCarrier (1s)                                      ?
?      ??? CreateShipment (2s)                                     ?
????????????????????????????????????????????????????????????????????

Open the DTS dashboard at http://localhost:8080 to see the
parent-child orchestration hierarchy in the Timeline view!

Enter an order ID (or 'exit'):
> ORD-12345

Starting order processing for 'ORD-12345'...
Instance ID: abc123def456
Check the DTS dashboard Timeline tab to see sub-orchestrations!

[OrderReceived] Processing order 'ORD-12345'
  [Payment/ValidatePayment] Validating payment for order 'ORD-12345'...
  [Payment/ValidatePayment] Payment validated for $99.99
  [Payment/ChargePayment] Charging $99.99 for order 'ORD-12345'...
  [Payment/ChargePayment] ? Payment processed: TXN-A1B2C3D4
  [Inventory/CheckInventory] Checking inventory for order 'ORD-12345'...
  [Inventory/CheckInventory] ? Items available in stock
  [Inventory/ReserveInventory] Reserving items for order 'ORD-12345'...
  [Inventory/ReserveInventory] ? Reserved: RES-E5F6G7H8
  [Shipping/SelectCarrier] Selecting carrier for order 'ORD-12345'...
  [Shipping/SelectCarrier] ? Selected carrier: Express
  [Shipping/CreateShipment] Creating shipment for order 'ORD-12345'...
  [Shipping/CreateShipment] ? Shipment created: TRACK-I9J0K1L2M3
???????????????????????????????????????????????????????????????????
? [OrderCompleted] Order 'ORD-12345' successfully processed!
?   Payment: TXN-A1B2C3D4
?   Inventory: RES-E5F6G7H8
?   Shipping: Express - TRACK-I9J0K1L2M3
???????????????????????????????????????????????????????????????????
? Order completed. Tracking: TRACK-I9J0K1L2M3
```

## Comparison with In-Process Sub-Workflows

| Feature | In-Process | Durable |
|---------|------------|---------|
| Execution | Same process, synchronized supersteps | Separate orchestration instances |
| Visibility | Single workflow view | Hierarchical dashboard view |
| Checkpointing | Parent checkpoints include child state | Independent checkpoints per sub-workflow |
| Failure Recovery | Parent must handle child failures | Automatic retry with state preservation |
| Scalability | Single process | Can scale across workers |

## Related Samples

- [06_SubWorkflows (In-Process)](../../../GettingStarted/Workflows/_Foundational/06_SubWorkflows) - In-process sub-workflow execution
- [08_SingleWorkflow](../08_SingleWorkflow) - Basic durable workflow without sub-workflows
