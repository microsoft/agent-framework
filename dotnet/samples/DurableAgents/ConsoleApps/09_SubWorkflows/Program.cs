// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use sub-workflows within a durable orchestration.
// Sub-workflows allow you to compose complex workflows from simpler, reusable components.
//
// The sample implements an order processing workflow with three sub-workflows:
// 1. PaymentProcessing - Validates and processes payment
// 2. InventoryManagement - Checks and reserves inventory
// 3. ShippingArrangement - Arranges shipping and generates tracking
//
// Each sub-workflow runs as a separate orchestration instance, visible in the DTS dashboard.
// This provides:
// - Modular, reusable workflow components
// - Independent checkpointing and replay
// - Hierarchical visualization in the dashboard
// - Failure isolation between parent and child workflows

using Microsoft.Agents.AI.DurableTask;
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

// ============================================
// Step 1: Build the Payment Processing sub-workflow
// ============================================
ValidatePayment validatePayment = new();
ChargePayment chargePayment = new();

Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .WithDescription("Validates and processes payment for an order")
    .AddEdge(validatePayment, chargePayment)
    .Build();

// ============================================
// Step 2: Build the Inventory Management sub-workflow
// ============================================
CheckInventory checkInventory = new();
ReserveInventory reserveInventory = new();

Workflow inventoryWorkflow = new WorkflowBuilder(checkInventory)
    .WithName("SubInventoryManagement")
    .WithDescription("Checks availability and reserves inventory")
    .AddEdge(checkInventory, reserveInventory)
    .Build();

// ============================================
// Step 3: Build the Shipping Arrangement sub-workflow
// ============================================
SelectCarrier selectCarrier = new();
CreateShipment createShipment = new();

Workflow shippingWorkflow = new WorkflowBuilder(selectCarrier)
    .WithName("SubShippingArrangement")
    .WithDescription("Selects carrier and creates shipment")
    .AddEdge(selectCarrier, createShipment)
    .Build();

// ============================================
// Step 4: Build the Main Order Processing workflow using sub-workflows
// ============================================
// Bind sub-workflows as executors for use in the main workflow
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");
ExecutorBinding inventoryExecutor = inventoryWorkflow.BindAsExecutor("Inventory");
ExecutorBinding shippingExecutor = shippingWorkflow.BindAsExecutor("Shipping");

// Create entry and exit executors for the main workflow
OrderReceived orderReceived = new();
OrderCompleted orderCompleted = new();

// Build the main workflow: OrderReceived -> Payment -> Inventory -> Shipping -> OrderCompleted
Workflow orderProcessingWorkflow = new WorkflowBuilder(orderReceived)
    .WithName("OrderProcessing")
    .WithDescription("Processes an order through payment, inventory, and shipping")
    .AddEdge(orderReceived, paymentExecutor)
    .AddEdge(paymentExecutor, inventoryExecutor)
    .AddEdge(inventoryExecutor, shippingExecutor)
    .AddEdge(shippingExecutor, orderCompleted)
    .Build();

// ============================================
// Step 5: Configure and start the host
// ============================================
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        // Register only the main workflow - sub-workflows are discovered automatically!
        services.ConfigureDurableWorkflows(
            options => options.Workflows.AddWorkflow(orderProcessingWorkflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

// Get the IWorkflowClient from DI
IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
Console.WriteLine("║           Durable Sub-Workflows Sample                           ║");
Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
Console.WriteLine("║  Main Workflow: OrderProcessing                                  ║");
Console.WriteLine("║  ├── Payment (sub-workflow)                                      ║");
Console.WriteLine("║  │   ├── ValidatePayment (1s)                                    ║");
Console.WriteLine("║  │   └── ChargePayment (2s)                                      ║");
Console.WriteLine("║  ├── Inventory (sub-workflow)                                    ║");
Console.WriteLine("║  │   ├── CheckInventory (1s)                                     ║");
Console.WriteLine("║  │   └── ReserveInventory (2s)                                   ║");
Console.WriteLine("║  └── Shipping (sub-workflow)                                     ║");
Console.WriteLine("║      ├── SelectCarrier (1s)                                      ║");
Console.WriteLine("║      └── CreateShipment (2s)                                     ║");
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

// Start a new workflow using IWorkflowClient
async Task StartNewWorkflowAsync(string orderId, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"\nStarting order processing for '{orderId}'...");

    await using DurableRun run = (DurableRun)await client.RunAsync(workflow, orderId);
    Console.WriteLine($"Instance ID: {run.InstanceId}");
    Console.WriteLine("Check the DTS dashboard Timeline tab to see sub-orchestrations!");
    Console.WriteLine();

    try
    {
        string? result = await run.WaitForCompletionAsync();
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
