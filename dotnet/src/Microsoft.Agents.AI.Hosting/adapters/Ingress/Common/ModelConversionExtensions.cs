using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Common;

/// <summary>
/// Extension methods for converting between model types.
/// </summary>
public static class ModelConversionExtensions
{
    /// <summary>
    /// Converts an AgentReference to an AgentId.
    /// </summary>
    /// <param name="agent">The agent reference to convert.</param>
    /// <returns>An AgentId, or null if the agent reference is null.</returns>
    public static AgentId? ToAgentId(this AgentReference? agent)
    {
        return agent == null
            ? null
            : AzureAIAgentsModelFactory.AgentId(type: new AgentIdType(agent.Type.ToString()),
                name: agent.Name,
                version: agent.Version);
    }
}
