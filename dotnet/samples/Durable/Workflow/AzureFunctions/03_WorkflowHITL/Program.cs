// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a Human-in-the-Loop (HITL) workflow hosted in Azure Functions.
// Workflow: CreateApprovalRequest -> ManagerApproval (HITL) -> PrepareFinanceReview -> FinanceApproval (HITL) -> ExpenseReimburse
//
// The workflow pauses at two sequential RequestPorts and waits for external approval responses via HTTP.
// This simulates an expense that requires both manager and finance approval.
// The framework auto-generates three HTTP endpoints for each workflow:
//   POST /api/workflows/{name}/run          - Start the workflow
//   GET  /api/workflows/{name}/status/{id}  - Check status and pending approvals
//   POST /api/workflows/{name}/respond/{id} - Send approval response to resume

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using WorkflowHITLFunctions;

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

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows => workflows.AddWorkflow(expenseApproval, exposeStatusEndpoint: true))
    .Build();
app.Run();
