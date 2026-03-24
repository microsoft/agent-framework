// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

namespace A2AServer;

internal static class HostAgentFactory
{
    internal static async Task<(AIAgent, AgentCard)> CreateFoundryHostAgentAsync(string agentType, string model, string endpoint, string agentName, string[] agentUrls, IList<AITool>? tools = null)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        var aiProjectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());

        AIAgent agent = await aiProjectClient
            .GetAIAgentAsync(agentName, tools: tools);

        AgentCard agentCard = agentType.ToUpperInvariant() switch
        {
            "INVOICE" => GetInvoiceAgentCard(agentUrls),
            "POLICY" => GetPolicyAgentCard(agentUrls),
            "LOGISTICS" => GetLogisticsAgentCard(agentUrls),
            _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
        };

        return new(agent, agentCard);
    }

    internal static async Task<(AIAgent, AgentCard)> CreateChatCompletionHostAgentAsync(string agentType, string model, string apiKey, string name, string instructions, string[] agentUrls, IList<AITool>? tools = null)
    {
        AIAgent agent = new OpenAIClient(apiKey)
             .GetChatClient(model)
             .AsAIAgent(instructions, name, tools: tools);

        AgentCard agentCard = agentType.ToUpperInvariant() switch
        {
            "INVOICE" => GetInvoiceAgentCard(agentUrls),
            "POLICY" => GetPolicyAgentCard(agentUrls),
            "LOGISTICS" => GetLogisticsAgentCard(agentUrls),
            _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
        };

        return new(agent, agentCard);
    }

    #region private
    private static AgentCard GetInvoiceAgentCard(string[] agentUrls)
    {
        var capabilities = new AgentCapabilities()
        {
            Streaming = false,
            PushNotifications = false,
        };

        var invoiceQuery = new AgentSkill()
        {
            Id = "id_invoice_agent",
            Name = "InvoiceQuery",
            Description = "Handles requests relating to invoices.",
            Tags = ["invoice", "semantic-kernel"],
            Examples =
            [
                "List the latest invoices for Contoso.",
            ],
        };

        return new()
        {
            Name = "InvoiceAgent",
            Description = "Handles requests relating to invoices.",
            Version = "1.0.0",
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [invoiceQuery],
            SupportedInterfaces = CreateAgentInterfaces(agentUrls)
        };
    }

    private static AgentCard GetPolicyAgentCard(string[] agentUrls)
    {
        var capabilities = new AgentCapabilities()
        {
            Streaming = false,
            PushNotifications = false,
        };

        var policyQuery = new AgentSkill()
        {
            Id = "id_policy_agent",
            Name = "PolicyAgent",
            Description = "Handles requests relating to policies and customer communications.",
            Tags = ["policy", "semantic-kernel"],
            Examples =
            [
                "What is the policy for short shipments?",
            ],
        };

        return new AgentCard()
        {
            Name = "PolicyAgent",
            Description = "Handles requests relating to policies and customer communications.",
            Version = "1.0.0",
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [policyQuery],
            SupportedInterfaces = CreateAgentInterfaces(agentUrls)
        };
    }

    private static AgentCard GetLogisticsAgentCard(string[] agentUrls)
    {
        var capabilities = new AgentCapabilities()
        {
            Streaming = false,
            PushNotifications = false,
        };

        var logisticsQuery = new AgentSkill()
        {
            Id = "id_logistics_agent",
            Name = "LogisticsQuery",
            Description = "Handles requests relating to logistics.",
            Tags = ["logistics", "semantic-kernel"],
            Examples =
            [
                "What is the status for SHPMT-SAP-001",
            ],
        };

        return new AgentCard()
        {
            Name = "LogisticsAgent",
            Description = "Handles requests relating to logistics.",
            Version = "1.0.0",
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [logisticsQuery],
            SupportedInterfaces = CreateAgentInterfaces(agentUrls)
        };
    }

    private static List<AgentInterface> CreateAgentInterfaces(string[] agentUrls)
    {
        return agentUrls.Select(url => new AgentInterface
        {
            Url = url,
            ProtocolBinding = "JSONRPC",
            ProtocolVersion = "1.0",
        }).ToList();
    }
    #endregion
}
