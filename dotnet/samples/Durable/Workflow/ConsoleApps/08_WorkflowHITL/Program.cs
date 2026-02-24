// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a Human-in-the-Loop (HITL) workflow using Durable Tasks.
// Workflow: CreateApprovalRequest -> ManagerApproval -> PrepareFinanceReview -> FinanceApproval -> ExpenseReimburse
//
// The workflow pauses at two sequential RequestPorts, emitting a DurableWorkflowWaitingForInputEvent at each.
// This simulates an expense that requires both manager and finance approval.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using WorkflowHITL;

string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Define executors and RequestPorts for the two HITL pause points
CreateApprovalRequest createRequest = new();
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
PrepareFinanceReview prepareFinanceReview = new();
RequestPort<ApprovalRequest, ApprovalResponse> financeApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("FinanceApproval");
ExpenseReimburse reimburse = new();

// Build the workflow: CreateApprovalRequest -> ManagerApproval -> PrepareFinanceReview -> FinanceApproval -> ExpenseReimburse
Workflow expenseApproval = new WorkflowBuilder(createRequest)
    .WithName("ExpenseReimbursement")
    .WithDescription("Expense reimbursement with manager and finance approval")
    .AddEdge(createRequest, managerApproval)
    .AddEdge(managerApproval, prepareFinanceReview)
    .AddEdge(prepareFinanceReview, financeApproval)
    .AddEdge(financeApproval, reimburse)
    .Build();

IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            options => options.AddWorkflow(expenseApproval),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

// Start the workflow with streaming to observe events including HITL pauses
string expenseId = "EXP-2025-001";
Console.WriteLine($"Starting expense reimbursement workflow for expense: {expenseId}");
IStreamingWorkflowRun run = await workflowClient.StreamAsync(expenseApproval, expenseId);
Console.WriteLine($"Workflow started with instance ID: {run.RunId}\n");

// Watch for workflow events — handle HITL requests as they arrive
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case DurableWorkflowWaitingForInputEvent requestEvent:
            Console.WriteLine($"Workflow paused at RequestPort: {requestEvent.RequestPort.Id}");
            Console.WriteLine($"  Input: {requestEvent.Input}");

            // In a real scenario, this would involve human interaction (UI, email, Teams, etc.)
            ApprovalRequest? request = requestEvent.GetInputAs<ApprovalRequest>();
            Console.WriteLine($"  Approval for: {request?.EmployeeName}, Amount: {request?.Amount:C}");

            ApprovalResponse approvalResponse = new(Approved: true, Comments: "Approved by manager.");
            await run.SendResponseAsync(requestEvent, approvalResponse);
            Console.WriteLine($"  Response sent: Approved={approvalResponse.Approved}\n");
            break;

        case DurableWorkflowCompletedEvent completedEvent:
            Console.WriteLine($"Workflow completed: {completedEvent.Result}");
            break;

        case DurableWorkflowFailedEvent failedEvent:
            Console.WriteLine($"Workflow failed: {failedEvent.ErrorMessage}");
            break;
    }
}

await host.StopAsync();
