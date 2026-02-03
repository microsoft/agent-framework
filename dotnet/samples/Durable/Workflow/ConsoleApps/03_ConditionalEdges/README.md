# Conditional Edges Workflow Sample

This sample demonstrates how to build a workflow with **conditional edges** that route execution to different paths based on runtime conditions. The workflow evaluates conditions on the output of an executor to determine which downstream executor to run.

## Key Concepts Demonstrated

- Building workflows with **conditional edges** using `AddEdge` with a `condition` parameter
- Defining reusable condition functions for routing logic
- Branching workflow execution based on data-driven decisions
- Using `ConfigureDurableWorkflows` to register workflows with dependency injection

## Overview

The sample implements an order audit workflow that routes orders differently based on whether the customer is blocked (flagged for fraud):

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
    // Routes to NotifyFraud when customer is blocked
    internal static Func<Order?, bool> WhenBlocked() => 
        order => order?.Customer?.IsBlocked == true;

    // Routes to PaymentProcessor when customer is not blocked
    internal static Func<Order?, bool> WhenNotBlocked() => 
        order => order?.Customer?.IsBlocked == false;
}
```

### Routing Logic

In this sample, the routing is based on the order ID:
- Order IDs containing the letter **'B'** are associated with blocked customers ? routed to `NotifyFraud`
- All other order IDs are associated with valid customers ? routed to `PaymentProcessor`

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/03_ConditionalEdges
dotnet run --framework net10.0
```

### Sample Output

**Valid order (routes to PaymentProcessor):**
```text
Enter an order ID (or 'exit'):
> 12345
Starting workflow for order '12345'...
Run ID: abc123...
Waiting for workflow to complete...
Workflow completed. {"Id":"12345","Amount":100.0,"Customer":{"Id":201,"Name":"Jerry","IsBlocked":false},"PaymentReferenceNumber":"a1b2"}
```

**Blocked order (routes to NotifyFraud):**
```text
Enter an order ID (or 'exit'):
> 12345B
Starting workflow for order '12345B'...
Run ID: def456...
Waiting for workflow to complete...
Workflow completed. Order 12345B flagged as fraudulent for customer George.
```
