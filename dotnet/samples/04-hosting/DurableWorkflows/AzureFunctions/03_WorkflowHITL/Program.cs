// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a Human-in-the-Loop (HITL) workflow hosted in Azure Functions.
//
// ┌──────────────────────┐   ┌────────────────┐   ┌─────────────────────┐    ┌────────────────────┐
// │ CreateApprovalRequest│──►│ManagerApproval │──►│PrepareFinanceReview │──┬►│  BudgetApproval    │──┐
// └──────────────────────┘   │ (RequestPort)  │   └─────────────────────┘  │ │  (RequestPort)     │  │
//                            └────────────────┘                            │ └────────────────────┘  │  ┌─────────────────┐
//                                                                          │                         ├─►│ExpenseReimburse │
//                                                                          │ ┌────────────────────┐  │  └─────────────────┘
//                                                                          └►│ComplianceApproval  │──┘
//                                                                            │  (RequestPort)     │
//                                                                            └────────────────────┘
//
// The workflow pauses at three RequestPorts — one for the manager, then two in parallel for finance.
// After manager approval, BudgetApproval and ComplianceApproval run concurrently via fan-out/fan-in.
// The framework auto-generates three HTTP endpoints for each workflow:
//   POST /api/workflows/{name}/run          - Start the workflow
//   GET  /api/workflows/{name}/status/{id}  - Check status and pending approvals
//   POST /api/workflows/{name}/respond/{id} - Send approval response to resume

using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using WorkflowHITLFunctions;

// Define executors and RequestPorts for the three HITL pause points
CreateApprovalRequest createRequest = new();
RequestPort<ApprovalRequest, ApprovalResponse> managerApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("ManagerApproval");
PrepareFinanceReview prepareFinanceReview = new();
RequestPort<ApprovalRequest, ApprovalResponse> budgetApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("BudgetApproval");
RequestPort<ApprovalRequest, ApprovalResponse> complianceApproval = RequestPort.Create<ApprovalRequest, ApprovalResponse>("ComplianceApproval");
ExpenseReimburse reimburse = new();

// Build the workflow: CreateApprovalRequest -> ManagerApproval -> PrepareFinanceReview -> [BudgetApproval AND ComplianceApproval] -> ExpenseReimburse
Workflow expenseApproval = new WorkflowBuilder(createRequest)
    .WithName("ExpenseReimbursement")
    .WithDescription("Expense reimbursement with manager and parallel finance approvals")
    .AddEdge(createRequest, managerApproval)
    .AddEdge(managerApproval, prepareFinanceReview)
    .AddFanOutEdge(prepareFinanceReview, [budgetApproval, complianceApproval])
    .AddFanInBarrierEdge([budgetApproval, complianceApproval], reimburse)
    .Build();

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableWorkflows(workflows => workflows.AddWorkflow(expenseApproval, exposeStatusEndpoint: true))
    .Build();
app.Run();
