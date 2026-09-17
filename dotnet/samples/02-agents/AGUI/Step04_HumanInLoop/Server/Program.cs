// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddAGUIServer();

// A session store is REQUIRED for human-in-the-loop. The framework only honors an approval decision that it
// can match against an approval request it recorded itself when it interrupted the run. Without a session
// store that server-side record is lost between requests, and every approval decision the client sends back
// is rejected. Approval requests present in the inbound message history are deliberately NOT trusted as the
// pairing authority - otherwise any client could forge an approval and execute an approval-required tool.
// In production, use a persistent session store instead of the in-memory one: InMemoryAgentSessionStore keeps
// every session for the lifetime of the process, with no size limit, expiry or eviction, and sessions are keyed
// by a thread id the client chooses. It also has no atomic consume, so two concurrent requests on one thread can
// read the same pending approval before either writes back.
builder.Services.AddKeyedSingleton<AgentSessionStore>("AGUIAssistant", new InMemoryAgentSessionStore());

// WARNING: When session persistence is enabled, in a multi-user deployment you must also register an
// AgentIsolationKeyProvider to scope sessions by principal, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

WebApplication app = builder.Build();

Uri endpoint = AzureOpenAIEndpoint.From(
    builder.Configuration["AZURE_OPENAI_ENDPOINT"])
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Define approval-required tool
[Description("Approve the expense report.")]
static string ApproveExpenseReport(string expenseReportId)
{
    return $"Expense report {expenseReportId} approved";
}

// Wrap the tool in ApprovalRequiredAIFunction so the run interrupts for approval before it executes.
AITool[] tools =
[
    new ApprovalRequiredAIFunction(
        AIFunctionFactory.Create(ApproveExpenseReport, name: "approve_expense_report"))
];

// Create base agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
ChatClient openAIChatClient = new OpenAIClient(
    new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
    new OpenAIClientOptions { Endpoint = endpoint })
    .GetChatClient(deploymentName);

ChatClientAgent baseAgent = openAIChatClient.AsAIAgent(
    name: "AGUIAssistant",
    instructions: "You are a helpful assistant in charge of approving expenses",
    tools: tools);

// No custom approval protocol is required: MapAGUIServer emits the approval interrupt natively when the
// model calls the approval-required tool, and resumes the run when the client sends the decision back.
app.MapAGUIServer("/", baseAgent);
await app.RunAsync();
