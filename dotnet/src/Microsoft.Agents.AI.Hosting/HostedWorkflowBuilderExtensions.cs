// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for <see cref="IHostedWorkflowBuilder"/> to enable additional workflow configuration scenarios.
/// </summary>
public static class HostedWorkflowBuilderExtensions
{
    /// <summary>
    /// Registers the workflow as an AI agent in the dependency injection container.
    /// </summary>
    /// <param name="builder">The <see cref="IHostedWorkflowBuilder"/> instance to extend.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>An <see cref="IHostedAgentBuilder"/> that can be used to further configure the agent.</returns>
    public static IHostedAgentBuilder AddAsAIAgent(this IHostedWorkflowBuilder builder, ServiceLifetime lifetime = ServiceLifetime.Singleton)
        => builder.AddAsAIAgent(name: null, lifetime: lifetime);

    /// <summary>
    /// Registers the workflow as an AI agent in the dependency injection container.
    /// </summary>
    /// <param name="builder">The <see cref="IHostedWorkflowBuilder"/> instance to extend.</param>
    /// <param name="name">The optional name for the AI agent. If not specified, the workflow name is used.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>An <see cref="IHostedAgentBuilder"/> that can be used to further configure the agent.</returns>
    public static IHostedAgentBuilder AddAsAIAgent(this IHostedWorkflowBuilder builder, string? name, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        var workflowName = builder.Name;
        var agentName = name ?? workflowName;

        return builder.HostApplicationBuilder.AddAIAgent(agentName, (sp, key) =>
            sp.GetRequiredKeyedService<Workflow>(workflowName).AsAIAgent(name: key), lifetime);
    }
}
