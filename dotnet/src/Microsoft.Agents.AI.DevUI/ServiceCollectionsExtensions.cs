// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure DevUI.
/// </summary>
public static class MicrosoftAgentAIDevUIServiceCollectionsExtensions
{
    /// <summary>
    /// Adds services required for DevUI integration.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddDevUI(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        // a factory that tries to construct an AIAgent from Workflow,
        // even if workflow was not explicitly registered as an AIAgent.

#pragma warning disable IDE0001 // Simplify Names
        services.AddKeyedSingleton<AIAgent>(KeyedService.AnyKey, (sp, key) =>
        {
            var keyAsStr = key as string;
            Throw.IfNullOrEmpty(keyAsStr);

            var workflow = sp.GetKeyedService<Workflow>(keyAsStr);
            if (workflow is not null)
            {
                return workflow.AsAgent(name: workflow.Name);
            }

            // another thing we can do is resolve a non-keyed workflow.
            // however, we can't rely on anything than key to be equal to the workflow.Name.
            // so we try: if we fail, we return null.
            workflow = sp.GetService<Workflow>();
            if (workflow is not null && workflow.Name?.Equals(keyAsStr, StringComparison.Ordinal) == true)
            {
                return workflow.AsAgent(name: workflow.Name);
            }

            // and it's possible to lookup at the default-registered AIAgent
            // with the condition of same name as the key.
            var agent = sp.GetService<AIAgent>();
            if (agent is not null && agent.Name?.Equals(keyAsStr, StringComparison.Ordinal) == true)
            {
                return agent;
            }

            return null!;
        });
#pragma warning restore IDE0001 // Simplify Names

        return services;
    }
}
