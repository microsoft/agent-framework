// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using AGUI.WorkflowApproval;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

[Description("Submits an expense report after the user approves the operation.")]
static string SubmitExpense(ExpenseReport report)
    => $"Expense report {report.Id} for {report.Employee} was submitted.";

#pragma warning disable MEAI001 // ApprovalRequiredAIFunction is experimental.
AITool submitExpense = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(SubmitExpense));
#pragma warning restore MEAI001

ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

AIAgent expenseReviewer = chatClient.AsAIAgent(
    name: "ExpenseReviewer",
    instructions: """
        Review the expense report supplied by the user. Perform every check below:
        1. The report has a non-empty business purpose.
        2. A receipt is attached.
        3. The amount is positive and no greater than 500 USD.
        4. The expense is plausibly business-related.

        If any check fails, explain every failed check and do not call SubmitExpense.
        If all checks pass, call SubmitExpense with the complete report. The tool requires user approval.
        """,
    tools: [submitExpense]);

Workflow workflow = ApprovalWorkflow.Create(expenseReviewer);
AIAgent workflowAgent = workflow.AsAIAgent(name: "ApprovalWorkflow");

builder.Services.AddAIAgent("ApprovalWorkflow", (_, _) => workflowAgent)
    .WithInMemorySessionStore(withIsolation: false);

WebApplication app = builder.Build();
app.MapAGUIServer("ApprovalWorkflow", "/");
await app.RunAsync();
