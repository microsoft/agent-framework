// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Extension methods for the <see cref="DurableTaskClient"/> class.
/// </summary>
public static class DurableTaskClientExtensions
{
    /// <summary>
    /// Converts a <see cref="DurableTaskClient"/> to a durable agent proxy.
    /// </summary>
    /// <param name="durableClient">The <see cref="DurableTaskClient"/> to convert.</param>
    /// <param name="context">The <see cref="FunctionContext"/> for the current function invocation.</param>
    /// <param name="agentName">The name of the agent.</param>
    /// <returns>A durable agent proxy.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="durableClient"/> or <paramref name="context"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentName"/> is null or empty.</exception>
    public static AIAgent AsDurableAgentProxy(
        this DurableTaskClient durableClient,
        FunctionContext context,
        string agentName)
    {
        ArgumentNullException.ThrowIfNull(durableClient);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentException.ThrowIfNullOrEmpty(agentName);

        DefaultDurableAgentClient agentClient = ActivatorUtilities.CreateInstance<DefaultDurableAgentClient>(
            context.InstanceServices,
            durableClient);

        return new DurableAIAgentProxy(agentName, agentClient);
    }
}
