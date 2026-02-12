// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates conditional edges in a workflow hosted as an Azure Function.
// Orders are routed to different executors based on customer status:
// - Blocked customers → NotifyFraud
// - Valid customers → PaymentProcessor

using ConditionalEdgesFunctionApp;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;

// Create executor instances
OrderIdParser orderParser = new();
OrderEnrich orderEnrich = new();
PaymentProcessor paymentProcessor = new();
NotifyFraud notifyFraud = new();

// Build workflow with conditional edges.
// The condition functions evaluate the Order output from OrderEnrich
// to determine whether to route to NotifyFraud or PaymentProcessor.
Workflow auditOrder = new WorkflowBuilder(orderParser)
    .WithName("AuditOrder")
    .WithDescription("Audits an order and routes based on customer status")
    .AddEdge(orderParser, orderEnrich)
    .AddEdge(orderEnrich, notifyFraud, condition: OrderRouteConditions.WhenBlocked())
    .AddEdge(orderEnrich, paymentProcessor, condition: OrderRouteConditions.WhenNotBlocked())
    .Build();

// Configure the function app to host the workflow.
// This will automatically generate HTTP API endpoints for the workflow.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(durableOption =>
    {
        // Add the workflow.
        durableOption.Workflows.AddWorkflow(auditOrder);
    })
    .Build();
app.Run();
