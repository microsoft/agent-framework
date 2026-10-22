// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides validation shared by protocol hosting integrations that resolve agents for each request.
/// </summary>
internal static class HostedAgentResolution
{
    /// <summary>
    /// Verifies that a keyed <see cref="AIAgent"/> registration exists without resolving it.
    /// </summary>
    /// <param name="services">The application service provider.</param>
    /// <param name="agentName">The name of the keyed agent registration.</param>
    /// <exception cref="InvalidOperationException">No agent is registered with <paramref name="agentName"/>.</exception>
    /// <remarks>
    /// Resolving the agent from the application service provider would capture scoped or transient registrations,
    /// so the check is skipped when the provider cannot report keyed registrations.
    /// </remarks>
    public static void EnsureAgentRegistered(IServiceProvider services, string agentName)
    {
        if (services.GetService<IServiceProviderIsKeyedService>() is { } isKeyedService &&
            !isKeyedService.IsKeyedService(typeof(AIAgent), agentName))
        {
            throw new InvalidOperationException(
                $"No {nameof(AIAgent)} is registered with the name '{agentName}'. " +
                $"Register it with AddAIAgent(\"{agentName}\", ...) before mapping the endpoint.");
        }
    }

    /// <summary>
    /// Gets the stable logical identity of an agent returned by a request-time agent selector.
    /// </summary>
    /// <param name="agent">The selected agent.</param>
    /// <returns>The agent name, which identifies the agent's hosted services and persisted sessions.</returns>
    /// <exception cref="InvalidOperationException">The agent does not have a name.</exception>
    public static string GetSelectedAgentName(AIAgent agent)
    {
        string? agentName = agent.Name;
        if (string.IsNullOrWhiteSpace(agentName))
        {
            throw new InvalidOperationException(
                $"The agent selector returned an {nameof(AIAgent)} without a {nameof(AIAgent.Name)}. " +
                "Selected agents must have a stable name, which identifies their hosted services and persisted sessions across requests.");
        }

        return agentName!;
    }
}
