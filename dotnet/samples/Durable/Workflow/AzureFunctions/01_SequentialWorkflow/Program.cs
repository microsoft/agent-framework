// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Extensions.Hosting;
using SequentialWorkflow;

OrderLookup orderLookupExecutor = new();
OrderEnrich orderEnricherExeecutor = new();
PaymentProcessor paymentProcessorExecutor = new();

Workflow fulfillOrder = new WorkflowBuilder(orderLookupExecutor)
    .WithName("FulfillOrder")
    .WithDescription("Looks up an order by ID and run payment processing")
    .AddEdge(orderLookupExecutor, orderEnricherExeecutor)
    .AddEdge(orderEnricherExeecutor, paymentProcessorExecutor)
    .Build();

// Configure the function app to host the AI agent.
// This will automatically generate HTTP API endpoints for the agent.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(durableOption =>
    {
        // Add a workflow.
        durableOption.Workflows.AddWorkflow(fulfillOrder);
    })
    .Build();
app.Run();
