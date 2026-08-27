// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to host a policy agent and expose it through the A2A protocol.

using A2A;
using A2A.AspNetCore;
using A2AServer;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;

// Create the ASP.NET Core host and register the services required by A2A.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();

// Read the Microsoft Foundry project and model configuration.
var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var agentUrl = Environment.GetEnvironmentVariable("A2A_AGENT_URL") ?? "http://localhost:5000";

const string PolicyInstructions =
    """
    You specialize in handling queries related to policies and customer communications.

    Always reply with exactly this text:

    Policy: Short Shipment Dispute Handling Policy V2.1

    Summary: "For short shipments reported by customers, first verify internal shipment records
    (SAP) and physical logistics scan data (BigQuery). If discrepancy is confirmed and logistics data
    shows fewer items packed than invoiced, issue a credit for the missing items. Document the
    resolution in SAP CRM and notify the customer via email within 2 business days, referencing the
    original invoice and the credit memo number. Use the 'Formal Credit Notification' email
    template."
    """;

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent policyAgent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: model,
        instructions: PolicyInstructions,
        name: "PolicyAgent"
    );

// Create the agent card published at the well-known discovery endpoint.
AgentCard policyAgentCard = PolicyAgentCard.Create(agentUrl);

// IMPORTANT: In production, register an AgentIsolationKeyProvider to isolate sessions and tasks by authenticated caller.
// Without this, contextId/taskId alone are the lookup keys — any caller who knows them can access another caller's data.
// Example using claims-based identity:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

// By default, NoopAgentSessionStore is used — sessions are not persisted across requests.
// To enable multi-turn conversations, register a session store explicitly, e.g.:
// builder.Services.AddKeyedSingleton<AgentSessionStore>(policyAgent.Name, new InMemoryAgentSessionStore());

// Register the policy agent with the A2A hosting services.
builder.AddA2AServer(policyAgent);

var app = builder.Build();

// Expose the agent through both supported A2A protocol bindings.
app.MapA2AHttpJson(policyAgent, "/");
app.MapA2AJsonRpc(policyAgent, "/");

// Publish the agent card at the well-known discovery endpoint.
app.MapWellKnownAgentCard(policyAgentCard);

await app.RunAsync();
