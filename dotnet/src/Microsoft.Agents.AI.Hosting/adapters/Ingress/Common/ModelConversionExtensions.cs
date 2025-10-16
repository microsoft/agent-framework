using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Common;

public static class ModelConversionExtensions
{
    public static AgentId? ToAgentId(this AgentReference? agent)
    {
        return agent == null
            ? null
            : AzureAIAgentsModelFactory.AgentId(type: new AgentIdType(agent.Type.ToString()),
                name: agent.Name,
                version: agent.Version);
    }

}
