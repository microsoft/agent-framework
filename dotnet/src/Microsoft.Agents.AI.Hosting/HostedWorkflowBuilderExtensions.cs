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
    /// <returns>An <see cref="IHostedAgentBuilder"/> that can be used to further configure the agent.</returns>
    public static IHostedAgentBuilder AddAsAIAgent(this IHostedWorkflowBuilder builder)
        => builder.AddAsAIAgent(name: null);

    /// <summary>
    /// Registers the workflow as an AI agent in the dependency injection container.
    /// </summary>
    /// <param name="builder">The <see cref="IHostedWorkflowBuilder"/> instance to extend.</param>
    /// <param name="name">The optional name for the AI agent. If not specified, the workflow name is used.</param>
    /// <returns>An <see cref="IHostedAgentBuilder"/> that can be used to further configure the agent.</returns>
    public static IHostedAgentBuilder AddAsAIAgent(this IHostedWorkflowBuilder builder, string? name)
    {
        var agentName = name ?? builder.Name;
        return builder.HostApplicationBuilder.AddAIAgent(agentName, (sp, key) =>
        {
            var workflow = sp.GetRequiredKeyedService<Workflow>(key);
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
            return workflow.AsAgentAsync(name: key).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
        });
    }
}
