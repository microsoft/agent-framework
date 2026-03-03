// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates three workflows that share executors.
// The CancelOrder workflow cancels an order and notifies the customer.
// The OrderStatus workflow looks up an order and generates a status report.
// The BatchCancelOrders workflow accepts a complex JSON input to cancel multiple orders.
// Both CancelOrder and OrderStatus reuse the same OrderLookup executor, demonstrating executor sharing.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SequentialWorkflow;

// Define executors for all workflows
OrderLookup orderLookup = new();
OrderCancel orderCancel = new();
SendEmail sendEmail = new();
StatusReport statusReport = new();
BatchCancelProcessor batchCancelProcessor = new();
BatchCancelSummary batchCancelSummary = new();

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

// Build the BatchCancelOrders workflow: BatchCancelProcessor -> BatchCancelSummary
// This workflow demonstrates using a complex JSON object as the workflow input.
Workflow batchCancelOrders = new WorkflowBuilder(batchCancelProcessor)
    .WithName("BatchCancelOrders")
    .WithDescription("Cancel multiple orders in a batch using a complex JSON input")
    .AddEdge(batchCancelProcessor, batchCancelSummary)
    .Build();

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows => workflows.AddWorkflows(cancelOrder, orderStatus, batchCancelOrders))
    .Build();
app.Run();
