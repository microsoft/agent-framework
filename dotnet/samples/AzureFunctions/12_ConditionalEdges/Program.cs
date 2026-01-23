// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SingleAgent;

OrderIdParserExecutor orderParser = new();
OrderEnrich orderEnrich = new();
PaymentProcesserExecutor paymentProcessor = new();
NotifyFraudExecutor notifyFraud = new();

WorkflowBuilder builder = new(orderParser);
builder
    .AddEdge(orderParser, orderEnrich)
    .AddEdge(orderEnrich, notifyFraud, condition: OrderRouteConditions.WhenBlocked())
    .AddEdge(orderEnrich, paymentProcessor, condition: OrderRouteConditions.WhenNotBlocked());

var workflow = builder.WithName("AuditOrder").Build();

FunctionsApplication.CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(options => options.Workflows.AddWorkflow(workflow))
    .Build()
    .Run();
