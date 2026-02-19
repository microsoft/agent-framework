// Copyright (c) Microsoft. All rights reserved.

// ═══════════════════════════════════════════════════════════════════════════════
// SAMPLE: Shared State During Workflow Execution
// ═══════════════════════════════════════════════════════════════════════════════
//
// This sample demonstrates how executors in a durable workflow can share state
// via IWorkflowContext. State is persisted across supersteps and survives
// process restarts because the orchestration passes it to each activity.
//
// Key concepts:
//   1. QueueStateUpdateAsync  - Write a value to shared state
//   2. ReadStateAsync         - Read a value written by a previous executor
//   3. ReadOrInitStateAsync   - Read or lazily initialize a state value
//   4. QueueClearScopeAsync   - Clear all entries under a scope
//   5. RequestHaltAsync       - Stop the workflow early (e.g., validation failure)
//
// Workflow: ValidateOrder -> EnrichOrder -> ProcessPayment -> GenerateInvoice
//
// Return values carry primary business data through the pipeline (OrderDetails,
// payment ref). Shared state carries side-channel data that doesn't belong in
// the message chain: a tax rate (set by ValidateOrder, read by ProcessPayment)
// and an audit trail (each executor appends its own entry).
// ═══════════════════════════════════════════════════════════════════════════════

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using WorkflowSharedState;

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Define executors
ValidateOrder validateOrder = new();
EnrichOrder enrichOrder = new();
ProcessPayment processPayment = new();
GenerateInvoice generateInvoice = new();

// Build the workflow: ValidateOrder -> EnrichOrder -> ProcessPayment -> GenerateInvoice
Workflow orderPipeline = new WorkflowBuilder(validateOrder)
    .WithName("OrderPipeline")
    .WithDescription("Order processing pipeline with shared state across executors")
    .AddEdge(validateOrder, enrichOrder)
    .AddEdge(enrichOrder, processPayment)
    .AddEdge(processPayment, generateInvoice)
    .Build();

// Configure host with durable workflow support
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            workflowOptions => workflowOptions.AddWorkflow(orderPipeline),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Shared State Workflow Demo");
Console.WriteLine("Workflow: ValidateOrder -> EnrichOrder -> ProcessPayment -> GenerateInvoice");
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
        // Start the workflow and stream events to see shared state in action
        IStreamingWorkflowRun run = await workflowClient.StreamAsync(orderPipeline, input);
        Console.WriteLine($"Started run: {run.RunId}");

        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            switch (evt)
            {
                case WorkflowOutputEvent e:
                    Console.WriteLine($"  [Output] {e.SourceId}: {e.Data}");
                    break;

                case DurableWorkflowCompletedEvent e:
                    Console.WriteLine($"  Completed: {e.Result}");
                    break;

                case DurableWorkflowFailedEvent e:
                    Console.WriteLine($"  Failed: {e.ErrorMessage}");
                    break;
            }
        }
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();
