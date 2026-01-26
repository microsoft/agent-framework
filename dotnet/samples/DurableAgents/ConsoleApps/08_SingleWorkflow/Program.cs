// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to run a workflow as a durable orchestration from a console application.
// The workflow consists of three executors: OrderLookup -> OrderCancel -> SendEmail.
// It uses the DurableExecution API similar to InProcessExecution for in-process workflows.
//
// DURABILITY DEMONSTRATION:
// - Each activity has artificial delays to simulate real-world operations
// - Stop the app (Ctrl+C or stop debugging) during the OrderCancel activity (5 seconds)
// - Restart the application - the workflow will automatically resume!
// - The Durable Task Framework will skip already-completed activities (OrderLookup)
//   and continue from where it left off (OrderCancel)

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SingleAgent;

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
            options => options.Workflows.AddWorkflow(cancelOrder),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableClient = host.Services.GetRequiredService<DurableTaskClient>();

Console.WriteLine("Durable Workflow Sample");
Console.WriteLine("Workflow: OrderLookup (2s) -> OrderCancel (5s) -> SendEmail (1s)");
Console.WriteLine();
Console.WriteLine("TIP: Stop the app during OrderCancel to test durability.");
Console.WriteLine("     Restart - it will resume from where it left off.");
Console.WriteLine();
Console.WriteLine("Checking for pending workflows...");
await Task.Delay(TimeSpan.FromSeconds(2));
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
        await StartNewWorkflowAsync(input, cancelOrder, durableClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Start a new workflow
async Task StartNewWorkflowAsync(string orderId, Workflow workflow, DurableTaskClient client)
{
    Console.WriteLine($"Starting workflow for order '{orderId}'...");

    await using DurableRun run = await DurableWorkflow.RunAsync(workflow, orderId, client);
    Console.WriteLine($"Instance ID: {run.InstanceId}");

    try
    {
        string? result = await run.WaitForCompletionAsync();
        Console.WriteLine($"Completed: {result}");
    }
    catch (InvalidOperationException ex)
    {
        Console.WriteLine($"Failed: {ex.Message}");
    }
}
