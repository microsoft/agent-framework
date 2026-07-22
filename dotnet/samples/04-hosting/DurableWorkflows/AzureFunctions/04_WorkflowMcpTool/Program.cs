// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to expose a durable workflow as an MCP (Model Context Protocol) tool.
// When using AddWorkflow with exposeMcpToolTrigger: true, the Functions host will automatically
// generate a remote MCP endpoint for the app at /runtime/webhooks/mcp with a workflow-specific
// tool name. MCP-compatible clients can then invoke the workflow as a tool.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using WorkflowMcpTool;

// Define executors
TranslateText translateText = new();
FormatOutput formatOutput = new();
LookupOrder lookupOrder = new();
EnrichOrder enrichOrder = new();

// Build a simple workflow: TranslateText -> FormatOutput
Workflow translateWorkflow = new WorkflowBuilder(translateText)
    .WithName("Translate")
    .WithDescription("Translate text to uppercase and format the result")
    .AddEdge(translateText, formatOutput)
    .Build();

// Build a workflow that returns a POCO: LookupOrder -> EnrichOrder
Workflow orderLookupWorkflow = new WorkflowBuilder(lookupOrder)
    .WithName("OrderLookup")
    .WithDescription("Look up an order by ID and return enriched order details")
    .AddEdge(lookupOrder, enrichOrder)
    .Build();

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows =>
    {
        // Expose both workflows as MCP tool triggers.
        workflows.AddWorkflow(translateWorkflow, exposeStatusEndpoint: false, exposeMcpToolTrigger: true);
        workflows.AddWorkflow(orderLookupWorkflow, exposeStatusEndpoint: false, exposeMcpToolTrigger: true);
    })
    .Build();
app.Run();
