// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates nested sub-workflows. A sub-workflow can act as an executor
// within another workflow, including multi-level nesting (sub-workflow within sub-workflow).

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SubWorkflows;

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Build the FraudCheck sub-workflow (this will be nested inside the Payment sub-workflow)
AnalyzePatterns analyzePatterns = new();
CalculateRiskScore calculateRiskScore = new();

Workflow fraudCheckWorkflow = new WorkflowBuilder(analyzePatterns)
    .WithName("SubFraudCheck")
    .WithDescription("Analyzes transaction patterns and calculates risk score")
    .AddEdge(analyzePatterns, calculateRiskScore)
    .Build();

// Build the Payment sub-workflow: ValidatePayment -> FraudCheck (sub-workflow) -> ChargePayment
ValidatePayment validatePayment = new();
ExecutorBinding fraudCheckExecutor = fraudCheckWorkflow.BindAsExecutor("FraudCheck");
ChargePayment chargePayment = new();

Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .WithDescription("Validates and processes payment for an order")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// Build the Shipping sub-workflow: SelectCarrier -> CreateShipment
SelectCarrier selectCarrier = new();
CreateShipment createShipment = new();

Workflow shippingWorkflow = new WorkflowBuilder(selectCarrier)
    .WithName("SubShippingArrangement")
    .WithDescription("Selects carrier and creates shipment")
    .AddEdge(selectCarrier, createShipment)
    .Build();

// Build the main workflow using sub-workflows as executors
// OrderReceived -> Payment (sub-workflow) -> Shipping (sub-workflow) -> OrderCompleted
OrderReceived orderReceived = new();
OrderCompleted orderCompleted = new();
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");
ExecutorBinding shippingExecutor = shippingWorkflow.BindAsExecutor("Shipping");

Workflow orderProcessingWorkflow = new WorkflowBuilder(orderReceived)
    .WithName("OrderProcessing")
    .WithDescription("Processes an order through payment and shipping")
    .AddEdge(orderReceived, paymentExecutor)
    .AddEdge(paymentExecutor, shippingExecutor)
    .AddEdge(shippingExecutor, orderCompleted)
    .Build();

// Configure and start the host
// Register only the main workflow - sub-workflows are discovered automatically!
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            workflowOptions => workflowOptions.AddWorkflow(orderProcessingWorkflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Durable Sub-Workflows Sample");
Console.WriteLine("Workflow: OrderReceived -> Payment(sub) -> Shipping(sub) -> OrderCompleted");
Console.WriteLine("  Payment contains nested FraudCheck sub-workflow (Level 2 nesting)");
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
        await StartNewWorkflowAsync(input, orderProcessingWorkflow, workflowClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Start a new workflow using streaming to observe events (including from sub-workflows)
static async Task StartNewWorkflowAsync(string orderId, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"\nStarting order processing for '{orderId}'...");

    IStreamingWorkflowRun run = await client.StreamAsync(workflow, orderId);
    Console.WriteLine($"Run ID: {run.RunId}");
    Console.WriteLine();

    await foreach (WorkflowEvent evt in run.WatchStreamAsync())
    {
        switch (evt)
        {
            // Custom event emitted from the FraudCheck sub-sub-workflow
            case FraudRiskAssessedEvent e:
                Console.ForegroundColor = ConsoleColor.DarkYellow;
                Console.WriteLine($"  [Event from sub-workflow] {e.GetType().Name}: Risk score {e.RiskScore}/100");
                Console.ResetColor();
                break;

            case DurableWorkflowCompletedEvent e:
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine($"✓ Order completed: {e.Result}");
                Console.ResetColor();
                break;

            case DurableWorkflowFailedEvent e:
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"✗ Failed: {e.ErrorMessage}");
                Console.ResetColor();
                break;
        }
    }
}
