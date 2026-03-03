// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SequentialWorkflow;

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Define executors for the workflow
OrderLookup orderLookup = new();
OrderCancel orderCancel = new();
SendEmail sendEmail = new();

// Build the CancelOrder workflow: OrderLookup -> OrderCancel -> SendEmail
Workflow cancelOrder = new WorkflowBuilder(orderLookup)
    .WithName("CancelOrder")
    .WithDescription("Cancel an order and notify the customer")
    .AddEdge(orderLookup, orderCancel)
    .AddEdge(orderCancel, sendEmail)
    .Build();

IHost host = Host.CreateDefaultBuilder(args)
.ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
.ConfigureServices(services =>
{
    services.ConfigureDurableWorkflows(
        workflowOptions => workflowOptions.AddWorkflow(cancelOrder),
        workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
        clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
})
.Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Durable Workflow Sample");
Console.WriteLine("Workflow: OrderLookup -> OrderCancel -> SendEmail");
Console.WriteLine();
Console.WriteLine("Enter an order ID (or 'exit'):");

while (true)
{
    Console.Write("> ");
    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        OrderCancelRequest request = new(OrderId: input, Reason: "Customer requested cancellation");
        await StartNewWorkflowAsync(request, cancelOrder, workflowClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Start a new workflow using IWorkflowClient with typed input
static async Task StartNewWorkflowAsync(OrderCancelRequest request, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"Starting workflow for order '{request.OrderId}' (Reason: {request.Reason})...");

    // RunAsync returns IWorkflowRun, cast to IAwaitableWorkflowRun for completion waiting
    IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await client.RunAsync(workflow, request);
    Console.WriteLine($"Run ID: {run.RunId}");

    try
    {
        Console.WriteLine("Waiting for workflow to complete...");
        string? result = await run.WaitForCompletionAsync<string>();
        Console.WriteLine($"Workflow completed. {result}");
    }
    catch (InvalidOperationException ex)
    {
        Console.WriteLine($"Failed: {ex.Message}");
    }
}
