// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Provides extension methods for configuring durable workflow orchestration and activity services within an
/// application's dependency injection container.
/// </summary>
public static class DurableWorkflowServiceCollectionExtensions
{
    /// <summary>
    /// Configures durable workflows, automatically registering orchestrations and activities.
    /// </summary>
    /// <remarks>
    /// This method provides a workflow-focused configuration experience.
    /// If you need to configure both agents and workflows, consider using
    /// <see cref="DurableServiceCollectionExtensions.ConfigureDurableOptions"/> instead.
    /// </remarks>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="configure">A delegate to configure the workflow options.</param>
    /// <param name="workerBuilder">Optional delegate to configure the durable task worker.</param>
    /// <param name="clientBuilder">Optional delegate to configure the durable task client.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection ConfigureDurableWorkflows(
        this IServiceCollection services,
        Action<DurableWorkflowOptions> configure,
        Action<IDurableTaskWorkerBuilder>? workerBuilder = null,
        Action<IDurableTaskClientBuilder>? clientBuilder = null)
    {
        return services.ConfigureDurableOptions(
            options => configure(options.Workflows),
            workerBuilder,
            clientBuilder);
    }
}
