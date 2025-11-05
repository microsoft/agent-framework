// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Extension methods for the <see cref="AIAgent"/> class.
/// </summary>
public static class AIAgentExtensions
{
    /// <summary>
    /// Converts an AIAgent to a durable agent proxy.
    /// </summary>
    /// <param name="agent">The agent to convert.</param>
    /// <param name="services">The service provider.</param>
    /// <returns>The durable agent proxy.</returns>
    /// <exception cref="ArgumentException">
    /// Thrown when the agent is a DurableAIAgent instance or if the agent has no name.
    /// </exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown if <paramref name="services"/> does not contain an <see cref="IDurableAgentClient"/>.
    /// </exception>
    public static AIAgent AsDurableAgentProxy(this AIAgent agent, IServiceProvider services)
    {
        // Don't allow this method to be used on DurableAIAgent instances.
        if (agent is DurableAIAgent)
        {
            throw new ArgumentException(
                $"{nameof(DurableAIAgent)} instances cannot be converted to a durable agent proxy.",
                nameof(agent));
        }

        string agentName = agent.Name ?? throw new ArgumentException("Agent must have a name.", nameof(agent));
        IDurableAgentClient agentClient = services.GetRequiredService<IDurableAgentClient>();
        return new DurableAIAgentProxy(agentName, agentClient);
    }
}
