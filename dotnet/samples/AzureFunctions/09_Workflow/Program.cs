// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using SingleAgent;

Func<string, string> orderParserFunc = input =>
{
    // We accept both short ordereId(Ex:12345) and long order reference number(MSFT12345)
    // OrderId is the last 5 digigs of order reference number.
    const int OrderIdPartLength = 5;
    if (input.Length > OrderIdPartLength)
    {
        return input[^OrderIdPartLength..];
    }

    return input;
};
var orderParserExecutor = orderParserFunc.BindAsExecutor("OrderParser");

Func<string, string> cancelOrderFunc = input => $"Cancelled order:{input}";
var orderArchiver = orderParserFunc.BindAsExecutor("OrderArchiver");

OrderLookupExecutor orderLookupExecutor = new();
OrderEnricherExecutor orderEnricherExeecutor = new();
PaymentProcessorExecutor paymentProcessorExecutor = new();

Workflow processOrder = new WorkflowBuilder(orderParserExecutor)
    .WithName("FulfillOrder")
    .WithDescription("Looks up an order by ID and run payment processing")
    .AddEdge(orderParserExecutor, orderLookupExecutor)
    .AddEdge(orderLookupExecutor, orderEnricherExeecutor)
    .AddEdge(orderEnricherExeecutor, paymentProcessorExecutor)
    .Build();

Workflow cancelOrder = new WorkflowBuilder(orderParserExecutor)
    .WithName("CancelOrder")
    .WithDescription("Cancel an order")
    .AddEdge(orderParserExecutor, orderLookupExecutor)
    .AddEdge(orderLookupExecutor, orderArchiver)
    .Build();

var host = FunctionsApplication.CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(options => options.Workflows.AddWorkflow([processOrder, cancelOrder]))
    .Build();

host.Run();
