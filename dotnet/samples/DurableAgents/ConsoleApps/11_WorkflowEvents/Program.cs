// Copyright (c) Microsoft. All rights reserved.

// ═══════════════════════════════════════════════════════════════════════════════
// SAMPLE: Workflow Events and IWorkflowContext Features
// ═══════════════════════════════════════════════════════════════════════════════
//
// This sample demonstrates how to use IWorkflowContext methods in executors:
//
// 1. AddEventAsync     - Emit custom events that callers can observe in real-time
// 2. YieldOutputAsync  - Stream intermediate outputs during long-running operations
//
// The sample uses DurableWorkflow.StreamAsync to observe events as they occur,
// showing how callers can receive real-time updates from the workflow.
//
// Workflow: OrderLookup -> OrderCancel -> SendEmail
// ═══════════════════════════════════════════════════════════════════════════════

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

// Define executors and build workflow
OrderLookup orderLookup = new();
OrderCancel orderCancel = new();
SendEmail sendEmail = new();

Workflow cancelOrder = new WorkflowBuilder(orderLookup)
    .WithName("CancelOrder")
    .WithDescription("Cancel an order and notify the customer")
    .AddEdge(orderLookup, orderCancel)
    .AddEdge(orderCancel, sendEmail)
    .Build();

// Configure host with durable workflow support
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

Console.WriteLine("Workflow Events Demo - Enter order ID (or 'exit'):");

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
        await RunWorkflowWithStreamingAsync(input, cancelOrder, durableClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Runs a workflow and streams events as they occur
async Task RunWorkflowWithStreamingAsync(string orderId, Workflow workflow, DurableTaskClient client)
{
    // StreamAsync starts the workflow and returns a handle for observing events
    await using DurableStreamingRun run = await DurableWorkflow.StreamAsync(workflow, orderId, client);
    Console.WriteLine($"Started: {run.InstanceId}");

    // WatchStreamAsync yields events as they're emitted by executors
    await foreach (WorkflowEvent evt in run.WatchStreamAsync())
    {
        // Always print the event type name
        Console.WriteLine($"  Event: {evt.GetType().Name}");

        switch (evt)
        {
            // Custom domain events (emitted via AddEventAsync)
            case OrderLookupStartedEvent e:
                WriteColored($"    [Lookup] Looking up order {e.OrderId}", ConsoleColor.Cyan);
                break;
            case OrderFoundEvent e:
                WriteColored($"    [Lookup] Found: {e.Order.Customer.Name}", ConsoleColor.Cyan);
                break;
            case CancellationProgressEvent e:
                WriteColored($"    [Cancel] {e.PercentComplete}% - {e.Status}", ConsoleColor.Yellow);
                break;
            case OrderCancelledEvent e:
                WriteColored("    [Cancel] Done", ConsoleColor.Yellow);
                break;
            case EmailSentEvent e:
                WriteColored($"    [Email] Sent to {e.Email}", ConsoleColor.Magenta);
                break;

            // Yielded outputs (emitted via YieldOutputAsync)
            case DurableYieldedOutputEvent e:
                WriteColored($"    [Output] {e.ExecutorId}", ConsoleColor.DarkGray);
                break;

            // Workflow completion
            case DurableWorkflowCompletedEvent e:
                WriteColored($"  Completed: {e.Result}", ConsoleColor.Green);
                break;
            case DurableWorkflowFailedEvent e:
                WriteColored($"  Failed: {e.ErrorMessage}", ConsoleColor.Red);
                break;
        }
    }
}

void WriteColored(string message, ConsoleColor color)
{
    Console.ForegroundColor = color;
    Console.WriteLine(message);
    Console.ResetColor();
}
