// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a Human-in-the-Loop (HITL) workflow using Durable Tasks.
// The workflow creates an expense approval request, waits for manager approval via an external event,
// and then processes the expense reimbursement based on the approval response.
// This sample mirrors the pattern used in the in-process HumanInTheLoopBasic sample.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
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
CreateApprovalRequest createRequest = new();
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
ExpenseReimburse reimburse = new();

Workflow expenseApproval = new WorkflowBuilder(createRequest)
    .WithName("ExpenseReImbursement")
    .WithDescription("Expense ReImbursement")
    .AddEdge(createRequest, managerApproval)
    .AddEdge(managerApproval, reimburse)
    .Build();

IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            options => options.Workflows.AddWorkflow(expenseApproval),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

// Get the IWorkflowClient from DI - no need to manually resolve DurableTaskClient
IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

// Start the workflow with an expense ID as input
string expenseId = "EXP-2025-001";
Console.WriteLine($"Starting expense reimbursement workflow for expense: {expenseId}");

// Start the workflow and get a streaming handle
// Cast to DurableStreamingRun for durable-specific features like InstanceId and SendResponseAsync
await using DurableStreamingRun run = (DurableStreamingRun)await workflowClient.StreamAsync(expenseApproval, expenseId);

Console.WriteLine($"Workflow started with instance ID: {run.InstanceId}");
Console.WriteLine("Watching for workflow events...\n");

// Watch for workflow events - similar pattern to InProcessExecution.StreamAsync
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case DurableRequestInfoEvent requestEvent:
            // Handle request for external input (human-in-the-loop)
            Console.WriteLine($"Workflow is waiting for input at RequestPort: {requestEvent.RequestPortId}");
            Console.WriteLine($"  Input data: {requestEvent.Input}");
            Console.WriteLine($"  Expected response type: {requestEvent.ResponseType}");

            // Simulate manager approval
            ApprovalResponse response = HandleApprovalRequest(requestEvent);
            await run.SendResponseAsync(requestEvent, response);
            Console.WriteLine($"  Response sent: Approved={response.Approved}\n");
            break;

        case DurableWorkflowCompletedEvent completedEvent:
            // The workflow has completed
            Console.WriteLine($"Workflow completed with result: {completedEvent.Result}");
            break;

        case DurableWorkflowFailedEvent failedEvent:
            // The workflow has failed
            Console.WriteLine($"Workflow failed: {failedEvent.ErrorMessage}");
            break;
    }
}

Console.ReadLine();
await host.StopAsync();

// Handler for approval requests - similar to HandleExternalRequest in the in-process sample
static ApprovalResponse HandleApprovalRequest(DurableRequestInfoEvent requestEvent)
{
    // In a real scenario, this would involve human interaction (e.g., a web UI)
    // For this sample, we simulate automatic approval
    ApprovalRequest? request = requestEvent.GetInputAs<ApprovalRequest>();

    if (request is not null)
    {
        Console.WriteLine($"  Approval request for: {request.EmployeeName}, Amount: {request.Amount:C}");
    }

    return new ApprovalResponse(Approved: true, Comments: "Approved by manager. Looks good!");
}
