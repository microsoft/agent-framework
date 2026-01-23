// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SingleAgent;

// Set up an AI agent following the standard Microsoft Agent Framework pattern.

OrderIdParserExecutor orderParser = new();
PaymentProcesserExecutor paymentProcessor = new();
EmailSenderExecutor emailSender = new();

WorkflowBuilder builder = new(orderParser);
builder.AddEdge(orderParser, paymentProcessor);
builder.AddEdge(paymentProcessor, emailSender).WithOutputFrom(emailSender);
var workflow = builder.WithName("ProcessOrder").Build();

FunctionsApplication.CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(options => options.Workflows.AddWorkflow(workflow))
    .Build().Run();
