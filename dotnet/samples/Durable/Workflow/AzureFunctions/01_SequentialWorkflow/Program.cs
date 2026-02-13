// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates two workflows that share an executor (OrderLookup).
// The CancelOrder workflow cancels an order and notifies the customer.
// The OrderStatus workflow looks up an order and generates a status report.
// Both workflows reuse the same OrderLookup executor, demonstrating executor sharing.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SequentialWorkflow;

// Define executors for both workflows
OrderLookup orderLookup = new();
OrderCancel orderCancel = new();
SendEmail sendEmail = new();
StatusReport statusReport = new();

// Build the CancelOrder workflow: OrderLookup -> OrderCancel -> SendEmail
Workflow cancelOrder = new WorkflowBuilder(orderLookup)
    .WithName("CancelOrder")
    .WithDescription("Cancel an order and notify the customer")
    .AddEdge(orderLookup, orderCancel)
    .AddEdge(orderCancel, sendEmail)
    .Build();

// Build the OrderStatus workflow: OrderLookup -> StatusReport
// This workflow shares the OrderLookup executor with the CancelOrder workflow.
Workflow orderStatus = new WorkflowBuilder(orderLookup)
    .WithName("OrderStatus")
    .WithDescription("Look up an order and generate a status report")
    .AddEdge(orderLookup, statusReport)
    .Build();

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows => workflows.AddWorkflows(cancelOrder, orderStatus))
    .Build();
app.Run();
