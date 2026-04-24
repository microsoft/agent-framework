// Copyright (c) Microsoft. All rights reserved.
using A2A;
using A2A.AspNetCore;
using A2AServer;
using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

string agentName = string.Empty;
string agentType = string.Empty;

for (var i = 0; i < args.Length; i++)
{
    if (args[i].Equals("--agentName", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
    {
        agentName = args[++i];
    }
    else if (args[i].Equals("--agentType", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
    {
        agentType = args[++i];
    }
}

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();

IConfigurationRoot configuration = new ConfigurationBuilder()
    .AddEnvironmentVariables()
    .AddUserSecrets<Program>()
    .Build();

string? apiKey = configuration["OPENAI_API_KEY"];
string model = configuration["OPENAI_CHAT_MODEL_NAME"] ?? "gpt-5.4-mini";
string? endpoint = configuration["AZURE_AI_PROJECT_ENDPOINT"];
string[] agentUrls = (builder.Configuration["urls"] ?? "http://localhost:5000").Split(';');

var invoiceQueryPlugin = new InvoiceQuery();
IList<AITool> tools =
[
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryInvoices),
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryByTransactionId),
    AIFunctionFactory.Create(invoiceQueryPlugin.QueryByInvoiceId)
];

AIAgent hostA2AAgent;
AgentCard hostA2AAgentCard;

if (!string.IsNullOrEmpty(endpoint) && !string.IsNullOrEmpty(agentName))
{
    (hostA2AAgent, hostA2AAgentCard) = agentType.ToUpperInvariant() switch
    {
        "INVOICE" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentName, agentUrls, tools),
        "POLICY" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentName, agentUrls),
        "LOGISTICS" => await HostAgentFactory.CreateFoundryHostAgentAsync(agentType, model, endpoint, agentName, agentUrls),
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
            """, agentUrls, tools),
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
            """, agentUrls),
        "LOGISTICS" => await HostAgentFactory.CreateChatCompletionHostAgentAsync(
            agentType, model, apiKey, "LogisticsAgent",
            """
            You specialize in handling queries related to logistics.
            
            Always reply with exactly:
            
            Shipment number: SHPMT-SAP-001
            Item: TSHIRT-RED-L
            Quantity: 900
            """, agentUrls),
        _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
    };
}
else
{
    throw new ArgumentException("Either A2AServer:ApiKey or A2AServer:ConnectionString & agentName must be provided");
}

builder.AddA2AServer(hostA2AAgent);

var app = builder.Build();
app.MapA2AHttpJson(hostA2AAgent, "/");
app.MapA2AJsonRpc(hostA2AAgent, "/");

app.MapWellKnownAgentCard(hostA2AAgentCard);

await app.RunAsync();
