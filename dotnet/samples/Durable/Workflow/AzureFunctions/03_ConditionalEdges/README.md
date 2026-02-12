# Conditional Edges Workflow - Azure Functions Sample

This sample demonstrates how to build a workflow with **conditional edges** hosted as an Azure Function. Orders are routed to different executors based on customer status.

## Key Concepts Demonstrated

- Building workflows with **conditional edges** using `AddEdge` with a `condition` parameter
- Hosting a conditional workflow as an Azure Function using `ConfigureDurableOptions`
- Defining reusable condition functions for routing logic
- Branching workflow execution based on data-driven decisions

## Overview

The workflow implements an order audit that routes orders differently based on whether the customer is blocked (flagged for fraud):

```
OrderIdParser --> OrderEnrich --[IsBlocked]--> NotifyFraud
                              |
                              +--[NotBlocked]--> PaymentProcessor
```

| Executor | Description |
|----------|-------------|
| OrderIdParser | Parses the order ID and retrieves order details |
| OrderEnrich | Enriches the order with customer information |
| PaymentProcessor | Processes payment for valid orders |
| NotifyFraud | Notifies the fraud team for blocked customers |

## How Conditional Edges Work

Conditional edges allow you to specify a condition function that determines whether the edge should be traversed:

```csharp
builder
    .AddEdge(orderParser, orderEnrich)
    .AddEdge(orderEnrich, notifyFraud, condition: OrderRouteConditions.WhenBlocked())
    .AddEdge(orderEnrich, paymentProcessor, condition: OrderRouteConditions.WhenNotBlocked());
```

The condition functions receive the output of the source executor and return a boolean:

```csharp
internal static class OrderRouteConditions
{
    internal static Func<Order?, bool> WhenBlocked() =>
        order => order?.Customer?.IsBlocked == true;

    internal static Func<Order?, bool> WhenNotBlocked() =>
        order => order?.Customer?.IsBlocked == false;
}
```

### Routing Logic

- Order IDs containing the letter **'B'** are associated with blocked customers → routed to `NotifyFraud`
- All other order IDs are associated with valid customers → routed to `PaymentProcessor`

## Environment Setup

This sample requires:

- [.NET 10 SDK](https://dotnet.microsoft.com/download)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-azure-managed-storage) running locally (default: `http://localhost:8080`)
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) for local Azure Storage emulation

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/AzureFunctions/03_ConditionalEdges
func start
```

### Testing

**Valid order (routes to PaymentProcessor):**
```bash
curl -X POST http://localhost:7071/api/workflows/AuditOrder/run -H "Content-Type: text/plain" -d "12345"
```

**Blocked order (routes to NotifyFraud):**
```bash
curl -X POST http://localhost:7071/api/workflows/AuditOrder/run -H "Content-Type: text/plain" -d "12345B"
```
