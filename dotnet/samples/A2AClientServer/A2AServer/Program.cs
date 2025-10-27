// Copyright (c) Microsoft. All rights reserved.
using A2A;
using A2A.AspNetCore;
using A2AServer;
using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

string agentId = string.Empty;
string agentType = string.Empty;

for (var i = 0; i < args.Length; i++)
{
    if (args[i].StartsWith("--agentId", StringComparison.InvariantCultureIgnoreCase) && i + 1 < args.Length)
    {
        agentId = args[++i];
    }
    else if (args[i].StartsWith("--agentType", StringComparison.InvariantCultureIgnoreCase) && i + 1 < args.Length)
    {
        agentType = args[++i];
    }
}

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
var app = builder.Build();

var httpClient = app.Services.GetRequiredService<IHttpClientFactory>().CreateClient();
var logger = app.Logger;

IConfigurationRoot configuration = new ConfigurationBuilder()
    .AddEnvironmentVariables()
    .AddUserSecrets<Program>()
    .Build();

string? apiKey = configuration["OPENAI_API_KEY"];
string model = configuration["OPENAI_MODEL"] ?? "gpt-4o-mini";
string? endpoint = configuration["AZURE_FOUNDRY_PROJECT_ENDPOINT"];

var invoiceQueryPlugin = new InvoiceQuery();
IList<AITool> tools =
    [
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryInvoices),
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryByTransactionId),
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryByInvoiceId)
    ];

AIAgent hostA2AAgent;
AgentCard hostA2AAgentCard;

if (!string.IsNullOrEmpty(endpoint) && !string.IsNullOrEmpty(agentId))
{
    (hostA2AAgent, hostA2AAgentCard) = agentType.ToUpperInvariant() switch
    {
        "INVOICE" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentId, tools),
        "POLICY" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentId),
        "LOGISTICS" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentId),
        _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
    };
}
else if (!string.IsNullOrEmpty(apiKey))
{
    (hostA2AAgent, hostA2AAgentCard) = agentType.ToUpperInvariant() switch
    {
        "INVOICE" => await HostAgentFactory.CreateChatCompletionHostAgentAsync(
            agentType, model, apiKey, "InvoiceAgent",
            """
            You specialize in handling queries related to invoices.
            """, tools),
        "POLICY" => await HostAgentFactory.CreateChatCompletionHostAgentAsync(
            agentType, model, apiKey, "PolicyAgent",
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
            """),
        "LOGISTICS" => await HostAgentFactory.CreateChatCompletionHostAgentAsync(
            agentType, model, apiKey, "LogisticsAgent",
            """
            You specialize in handling queries related to logistics.
            
            Always reply with exactly:
            
            Shipment number: SHPMT-SAP-001
            Item: TSHIRT-RED-L
            Quantity: 900
            """),
        _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
    };
}
else
{
    throw new ArgumentException("Either A2AServer:ApiKey or A2AServer:ConnectionString & agentId must be provided");
}

var a2aTaskManager = app.MapA2A(
    hostA2AAgent,
    path: "/",
    agentCard: hostA2AAgentCard,
    taskManager => app.MapWellKnownAgentCard(taskManager, "/"));

await app.RunAsync();
