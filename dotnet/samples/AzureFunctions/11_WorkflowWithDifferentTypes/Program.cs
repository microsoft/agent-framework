// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a workflow with different input/output types:
// - OrderIdParserExecutor: string → int
// - OrderLookupExecutor: int → OrderDetails (custom POCO)
// - OrderSummaryExecutor: OrderDetails → string
//
// Workflow: HTTP Request (string) → Parse Order ID → Lookup Order → Generate Summary

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SingleAgent;

// Create the executors with different input/output types
OrderIdParserExecutor orderIdParser = new();      // string → int
OrderLookupExecutor orderLookup = new();          // int → OrderDetails POCO
OrderSummaryExecutor orderSummary = new();        // OrderDetails → string

// Build the workflow: Parse → Lookup → Summarize
Workflow workflow = new WorkflowBuilder(orderIdParser)
    .WithName("OrderLookupWorkflow")
    .WithDescription("Looks up an order by ID and returns a formatted summary")
    .AddEdge(orderIdParser, orderLookup)          // string → int → OrderDetails
    .AddEdge(orderLookup, orderSummary)           // OrderDetails → string
    .WithOutputFrom(orderSummary)
    .Build();

// Configure the function app to host workflows.
// This will automatically generate HTTP API endpoints for the workflow.
FunctionsApplicationBuilder functionBuilder = FunctionsApplication.CreateBuilder(args);
functionBuilder.ConfigureFunctionsWebApplication().ConfigureDurableOptions(options =>
{
    // Register the workflow
    options.Workflows.AddWorkflow(workflow);
});
functionBuilder.Build().Run();
