// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates conditional edges in a workflow.
// Orders are routed to different executors based on customer status:
// - Blocked customers → NotifyFraud
// - Valid customers → PaymentProcessor

using ConditionalEdges;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Create executor instances
OrderIdParser orderParser = new();
OrderEnrich orderEnrich = new();
PaymentProcesser paymentProcessor = new();
NotifyFraud notifyFraud = new();

// Build workflow with conditional edges
// The condition functions evaluate the Order output from OrderEnrich
WorkflowBuilder builder = new(orderParser);
builder
    .AddEdge(orderParser, orderEnrich)
    .AddEdge(orderEnrich, notifyFraud, condition: OrderRouteConditions.WhenBlocked())
    .AddEdge(orderEnrich, paymentProcessor, condition: OrderRouteConditions.WhenNotBlocked());

Workflow auditOrder = builder.WithName("AuditOrder").Build();

IHost host = Host.CreateDefaultBuilder(args)
.ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
.ConfigureServices(services =>
{
    services.ConfigureDurableWorkflows(
        workflowOptions => workflowOptions.AddWorkflow(auditOrder),
        workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
        clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
})
.Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Enter an order ID (or 'exit'):");
Console.WriteLine("Tip: Order IDs containing 'B' are flagged as blocked customers.\n");

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
        await StartNewWorkflowAsync(input, auditOrder, workflowClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Start a new workflow and wait for completion
static async Task StartNewWorkflowAsync(string orderId, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"Starting workflow for order '{orderId}'...");

    // Cast to IAwaitableWorkflowRun to access WaitForCompletionAsync
    IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await client.RunAsync(workflow, orderId);
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
