// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a Human-in-the-Loop (HITL) workflow hosted in Azure Functions.
// Workflow: CreateApprovalRequest -> ManagerApproval (RequestPort/HITL pause) -> ExpenseReimburse
//
// The workflow pauses at a RequestPort and waits for an external approval response via HTTP.
// The framework auto-generates three HTTP endpoints for each workflow:
//   POST /api/workflows/{name}/run          - Start the workflow
//   GET  /api/workflows/{name}/status/{id}  - Check status and pending approvals
//   POST /api/workflows/{name}/respond/{id} - Send approval response to resume

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using WorkflowHITLFunctions;

// Define executors and a RequestPort for the HITL pause point
CreateApprovalRequest createRequest = new();
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
ExpenseReimburse reimburse = new();

// Build the workflow: CreateApprovalRequest -> ManagerApproval (HITL) -> ExpenseReimburse
Workflow expenseApproval = new WorkflowBuilder(createRequest)
    .WithName("ExpenseReimbursement")
    .WithDescription("Expense reimbursement with manager approval")
    .AddEdge(createRequest, managerApproval)
    .AddEdge(managerApproval, reimburse)
    .Build();

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows => workflows.AddWorkflow(expenseApproval, exposeStatusEndpoint: true))
    .Build();
app.Run();
