// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates nested workflows (sub-workflows) hosted as an Azure Function.
// One workflow can be used as an executor within another workflow, enabling modular,
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

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using NestedWorkflowsFunctionApp;

// Create executor instances for the Fraud Check sub-sub-workflow (Level 2 nesting)
AnalyzePatterns analyzePatterns = new();
CalculateRiskScore calculateRiskScore = new();

Workflow fraudCheckWorkflow = new WorkflowBuilder(analyzePatterns)
    .WithName("SubFraudCheck")
    .WithDescription("Analyzes transaction patterns and calculates risk score")
    .AddEdge(analyzePatterns, calculateRiskScore)
    .Build();

// Create executor instances for the Payment Processing sub-workflow
ValidatePayment validatePayment = new();
ExecutorBinding fraudCheckExecutor = fraudCheckWorkflow.BindAsExecutor("FraudCheck");
ChargePayment chargePayment = new();

Workflow paymentWorkflow = new WorkflowBuilder(validatePayment)
    .WithName("SubPaymentProcessing")
    .WithDescription("Validates and processes payment for an order")
    .AddEdge(validatePayment, fraudCheckExecutor)
    .AddEdge(fraudCheckExecutor, chargePayment)
    .Build();

// Create executor instances for the Inventory Management sub-workflow
CheckInventory checkInventory = new();
ReserveInventory reserveInventory = new();

Workflow inventoryWorkflow = new WorkflowBuilder(checkInventory)
    .WithName("SubInventoryManagement")
    .WithDescription("Checks availability and reserves inventory")
    .AddEdge(checkInventory, reserveInventory)
    .Build();

// Create executor instances for the Shipping Arrangement sub-workflow
SelectCarrier selectCarrier = new();
CreateShipment createShipment = new();

Workflow shippingWorkflow = new WorkflowBuilder(selectCarrier)
    .WithName("SubShippingArrangement")
    .WithDescription("Selects carrier and creates shipment")
    .AddEdge(selectCarrier, createShipment)
    .Build();

// Build the main Order Processing workflow using sub-workflows as executors
ExecutorBinding paymentExecutor = paymentWorkflow.BindAsExecutor("Payment");
ExecutorBinding inventoryExecutor = inventoryWorkflow.BindAsExecutor("Inventory");
ExecutorBinding shippingExecutor = shippingWorkflow.BindAsExecutor("Shipping");

OrderReceived orderReceived = new();
OrderCompleted orderCompleted = new();

Workflow orderProcessingWorkflow = new WorkflowBuilder(orderReceived)
    .WithName("OrderProcessing")
    .WithDescription("Processes an order through payment, inventory, and shipping")
    .AddEdge(orderReceived, paymentExecutor)
    .AddEdge(paymentExecutor, inventoryExecutor)
    .AddEdge(inventoryExecutor, shippingExecutor)
    .AddEdge(shippingExecutor, orderCompleted)
    .Build();

// Configure the function app to host the workflow.
// Sub-workflows are discovered and registered automatically.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(durableOption =>
        durableOption.Workflows.AddWorkflow(orderProcessingWorkflow))
    .Build();
app.Run();
