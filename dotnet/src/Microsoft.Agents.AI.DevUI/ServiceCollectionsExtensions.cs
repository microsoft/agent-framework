// Copyright (c) Microsoft. All rights reserved.

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
        services.AddKeyedSingleton(KeyedService.AnyKey, (sp, key) =>
        {
            var keyAsStr = key as string;
            Throw.IfNullOrEmpty(keyAsStr);

            var workflow = sp.GetKeyedService<Workflow>(keyAsStr);
            if (workflow is null)
            {
                return null!;
            }

            return workflow.AsAgent(name: workflow.Name);
        });

        return services;
    }
}
