// Copyright (c) Microsoft. All rights reserved.

// ═══════════════════════════════════════════════════════════════════════════════
// SAMPLE: Workflow Events and Streaming
// ═══════════════════════════════════════════════════════════════════════════════
//
// This sample demonstrates how to use IWorkflowContext event methods in executors
// and stream events from the caller side:
//
// 1. AddEventAsync     - Emit custom events that callers can observe in real-time
// 2. StreamAsync       - Start a workflow and obtain a streaming handle
// 3. WatchStreamAsync  - Observe events as they occur (custom, framework, and terminal)
//
// The sample uses IWorkflowClient.StreamAsync to start a workflow and
// WatchStreamAsync to observe events as they occur in real-time.
//
// Workflow: OrderLookup -> OrderCancel -> SendEmail
// ═══════════════════════════════════════════════════════════════════════════════

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using WorkflowEvents;

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
            workflowOptions => workflowOptions.AddWorkflow(cancelOrder),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

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
        await RunWorkflowWithStreamingAsync(input, cancelOrder, workflowClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Runs a workflow and streams events as they occur
static async Task RunWorkflowWithStreamingAsync(string orderId, Workflow workflow, IWorkflowClient client)
{
    // StreamAsync starts the workflow and returns a streaming handle for observing events
    IStreamingWorkflowRun run = await client.StreamAsync(workflow, orderId);
    Console.WriteLine($"Started run: {run.RunId}");

    // WatchStreamAsync yields events as they're emitted by executors
    await foreach (WorkflowEvent evt in run.WatchStreamAsync())
    {
        Console.WriteLine($"  New event received at {DateTime.Now:HH:mm:ss.ffff} ({evt.GetType().Name})");

        switch (evt)
        {
            // Custom domain events (emitted via AddEventAsync)
            case OrderLookupStartedEvent e:
                WriteColored($"    [Lookup] Looking up order {e.OrderId}", ConsoleColor.Cyan);
                break;
            case OrderFoundEvent e:
                WriteColored($"    [Lookup] Found: {e.CustomerName}", ConsoleColor.Cyan);
                break;
            case CancellationProgressEvent e:
                WriteColored($"    [Cancel] {e.PercentComplete}% - {e.Status}", ConsoleColor.Yellow);
                break;
            case OrderCancelledEvent:
                WriteColored("    [Cancel] Done", ConsoleColor.Yellow);
                break;
            case EmailSentEvent e:
                WriteColored($"    [Email] Sent to {e.Email}", ConsoleColor.Magenta);
                break;

            case WorkflowOutputEvent e:
                WriteColored($"    [Output] {e.SourceId}", ConsoleColor.DarkGray);
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

static void WriteColored(string message, ConsoleColor color)
{
    Console.ForegroundColor = color;
    Console.WriteLine(message);
    Console.ResetColor();
}
