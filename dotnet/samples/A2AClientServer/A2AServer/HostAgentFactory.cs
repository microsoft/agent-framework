// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;
using OpenAI;

namespace A2AServer;

internal static class HostAgentFactory
{
    internal static async Task<A2AHostAgent> CreateFoundryHostAgentAsync(string agentType, string modelId, string endpoint, string assistantId, IList<AITool>? tools = null)
    {
        var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());
        PersistentAgent persistentAgent = await persistentAgentsClient.Administration.GetAgentAsync(assistantId);

        AIAgent agent = await persistentAgentsClient
            .GetAIAgentAsync(persistentAgent.Id, chatOptions: new() { Tools = tools });

        AgentCard agentCard = agentType.ToUpperInvariant() switch
        {
            "INVOICE" => GetInvoiceAgentCard(),
            "POLICY" => GetPolicyAgentCard(),
            "LOGISTICS" => GetLogisticsAgentCard(),
            _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
        };

        return new A2AHostAgent(agent, agentCard);
    }

    internal static async Task<A2AHostAgent> CreateChatCompletionHostAgentAsync(string agentType, string modelId, string apiKey, string name, string instructions, IList<AITool>? tools = null)
    {
        AIAgent agent = new OpenAIClient(apiKey)
             .GetChatClient(modelId)
             .CreateAIAgent(instructions, name, tools: tools);

        AgentCard agentCard = agentType.ToUpperInvariant() switch
        {
            "INVOICE" => GetInvoiceAgentCard(),
            "POLICY" => GetPolicyAgentCard(),
            "LOGISTICS" => GetLogisticsAgentCard(),
            _ => throw new ArgumentException($"Unsupported agent type: {agentType}"),
        };

        return new A2AHostAgent(agent, agentCard);
    }

    #region private
    private static AgentCard GetInvoiceAgentCard()
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
        };
    }

    private static AgentCard GetPolicyAgentCard()
    {
        var capabilities = new AgentCapabilities()
        {
            Streaming = false,
            PushNotifications = false,
        };

        var invoiceQuery = new AgentSkill()
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
            Skills = [invoiceQuery],
        };
    }

    private static AgentCard GetLogisticsAgentCard()
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
        };
    }
    #endregion
}
