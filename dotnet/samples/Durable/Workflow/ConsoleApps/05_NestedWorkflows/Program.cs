// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates nested workflows (sub-workflows) where one workflow
// can be used as an executor within another workflow. This enables modular,
// reusable workflow components with independent checkpointing and replay.
//
// Workflow structure:
//
//  ┌─────────────────────────────────────────────────────────────────────────┐
//  │ OrderProcessing (Main Workflow)                                        │
//  │                                                                        │
//  │  OrderReceived                                                         │
//  │       │                                                                │
//  │       ▼                                                                │
//  │  ┌─────────────────────────────────────────────────────────┐           │
//  │  │ Payment (Sub-Workflow)                                   │           │
//  │  │                                                          │           │
//  │  │  ValidatePayment                                         │           │
//  │  │       │                                                  │           │
//  │  │       ▼                                                  │           │
//  │  │  ┌─────────────────────────────────────────┐            │           │
//  │  │  │ FraudCheck (Sub-Sub-Workflow)            │            │           │
//  │  │  │                                          │            │           │
//  │  │  │  AnalyzePatterns ──► CalculateRiskScore  │            │           │
//  │  │  └─────────────────────────────────────────┘            │           │
//  │  │       │                                                  │           │
//  │  │       ▼                                                  │           │
//  │  │  ChargePayment                                           │           │
//  │  └─────────────────────────────────────────────────────────┘           │
//  │       │                                                                │
//  │       ▼                                                                │
//  │  ┌─────────────────────────────────────────────────────────┐           │
//  │  │ Inventory (Sub-Workflow)                                 │           │
//  │  │                                                          │           │
//  │  │  CheckInventory ──► ReserveInventory                     │           │
//  │  └─────────────────────────────────────────────────────────┘           │
//  │       │                                                                │
//  │       ▼                                                                │
//  │  ┌─────────────────────────────────────────────────────────┐           │
//  │  │ Shipping (Sub-Workflow)                                  │           │
//  │  │                                                          │           │
//  │  │  SelectCarrier ──► CreateShipment                        │           │
//  │  └─────────────────────────────────────────────────────────┘           │
//  │       │                                                                │
//  │       ▼                                                                │
//  │  OrderCompleted                                                        │
//  └─────────────────────────────────────────────────────────────────────────┘
//
// Each sub-workflow runs as a separate orchestration instance, providing:
// - Modular, reusable workflow components
// - Independent checkpointing and replay
// - Hierarchical visualization in the DTS dashboard
// - Failure isolation between parent and child workflows

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using NestedWorkflows;

string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// ============================================
// Step 1: Build the Fraud Check sub-sub-workflow (Level 2 nesting)
// ============================================
AnalyzePatterns analyzePatterns = new();
CalculateRiskScore calculateRiskScore = new();

Workflow fraudCheckWorkflow = new WorkflowBuilder(analyzePatterns)
    .WithName("SubFraudCheck")
    .WithDescription("Analyzes transaction patterns and calculates risk score")
    .AddEdge(analyzePatterns, calculateRiskScore)
    .Build();

// ============================================
// Step 2: Build the Payment Processing sub-workflow (with nested FraudCheck)
// ============================================
ValidatePayment validatePayment = new();
ExecutorBinding fraudCheckExecutor = fraudCheckWorkflow.BindAsExecutor("FraudCheck");
ChargePayment chargePayment = new();

Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .WithDescription("Validates and processes payment for an order")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// ============================================
// Step 3: Build the Inventory Management sub-workflow
// ============================================
CheckInventory checkInventory = new();
ReserveInventory reserveInventory = new();

Workflow inventoryWorkflow = new WorkflowBuilder(checkInventory)
    .WithName("SubInventoryManagement")
    .WithDescription("Checks availability and reserves inventory")
    .AddEdge(checkInventory, reserveInventory)
    .Build();

// ============================================
// Step 4: Build the Shipping Arrangement sub-workflow
// ============================================
SelectCarrier selectCarrier = new();
CreateShipment createShipment = new();

Workflow shippingWorkflow = new WorkflowBuilder(selectCarrier)
    .WithName("SubShippingArrangement")
    .WithDescription("Selects carrier and creates shipment")
    .AddEdge(selectCarrier, createShipment)
    .Build();

// ============================================
// Step 5: Build the Main Order Processing workflow using sub-workflows
// ============================================
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");
ExecutorBinding inventoryExecutor = inventoryWorkflow.BindAsExecutor("Inventory");
ExecutorBinding shippingExecutor = shippingWorkflow.BindAsExecutor("Shipping");

OrderReceived orderReceived = new();
OrderCompleted orderCompleted = new();

// Main workflow: OrderReceived -> Payment -> Inventory -> Shipping -> OrderCompleted
Workflow orderProcessingWorkflow = new WorkflowBuilder(orderReceived)
    .WithName("OrderProcessing")
    .WithDescription("Processes an order through payment, inventory, and shipping")
    .AddEdge(orderReceived, paymentExecutor)
    .AddEdge(paymentExecutor, inventoryExecutor)
    .AddEdge(inventoryExecutor, shippingExecutor)
    .AddEdge(shippingExecutor, orderCompleted)
    .Build();

// ============================================
// Step 6: Configure and start the host
// ============================================
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        // Register only the main workflow - sub-workflows are discovered automatically!
        services.ConfigureDurableWorkflows(
            workflowOptions => workflowOptions.AddWorkflow(orderProcessingWorkflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
Console.WriteLine("║           Nested Workflows Sample                               ║");
Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
Console.WriteLine("║  Main Workflow: OrderProcessing                                  ║");
Console.WriteLine("║  ├── Payment (sub-workflow)                                      ║");
Console.WriteLine("║  │   ├── ValidatePayment                                         ║");
Console.WriteLine("║  │   ├── FraudCheck (sub-sub-workflow) ← Level 2 nesting!        ║");
Console.WriteLine("║  │   │   ├── AnalyzePatterns                                     ║");
Console.WriteLine("║  │   │   └── CalculateRiskScore                                  ║");
Console.WriteLine("║  │   └── ChargePayment                                           ║");
Console.WriteLine("║  ├── Inventory (sub-workflow)                                    ║");
Console.WriteLine("║  │   ├── CheckInventory                                          ║");
Console.WriteLine("║  │   └── ReserveInventory                                        ║");
Console.WriteLine("║  └── Shipping (sub-workflow)                                     ║");
Console.WriteLine("║      ├── SelectCarrier                                           ║");
Console.WriteLine("║      └── CreateShipment                                          ║");
Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
Console.WriteLine();
Console.WriteLine("Open the DTS dashboard at http://localhost:8080 to see the");
Console.WriteLine("parent-child orchestration hierarchy in the Timeline view!");
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

// Start a new workflow and wait for completion
static async Task StartNewWorkflowAsync(string orderId, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"\nStarting order processing for '{orderId}'...");

    IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await client.RunAsync(workflow, orderId);
    Console.WriteLine($"Run ID: {run.RunId}");
    Console.WriteLine("Check the DTS dashboard Timeline tab to see sub-orchestrations!");
    Console.WriteLine();

    try
    {
        Console.WriteLine("Waiting for workflow to complete...");
        string? result = await run.WaitForCompletionAsync<string>();

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"✓ Order completed: {result}");
        Console.ResetColor();
    }
    catch (InvalidOperationException ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"✗ Failed: {ex.Message}");
        Console.ResetColor();
    }
}
