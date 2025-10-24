// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Extension methods for converting between model types.
/// </summary>
internal static class AgentReferenceExtensions
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
            : new AgentId(
                type: new AgentIdType(agent.Type),
                name: agent.Name,
                version: agent.Version ?? "latest");
    }
}
