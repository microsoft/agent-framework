// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Hosting.Local;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring AI workflows in a host application builder.
/// </summary>
public static class HostApplicationBuilderWorkflowExtensions
{
    /// <summary>
    /// Registers a custom workflow using a factory delegate.
    /// </summary>
    /// <param name="builder">The <see cref="IHostApplicationBuilder"/> to configure.</param>
    /// <param name="name">The unique name for the workflow.</param>
    /// <param name="createWorkflowDelegate">A factory function that creates the <see cref="Workflow"/> instance. The function receives the service provider and workflow name as parameters.</param>
    /// <returns>An <see cref="IHostedWorkflowBuilder"/> that can be used to further configure the workflow.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="createWorkflowDelegate"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the factory delegate returns null or a workflow with a name that doesn't match the expected name.
    /// </exception>
    public static IHostedWorkflowBuilder AddWorkflow(this IHostApplicationBuilder builder, string name, Func<IServiceProvider, string, Workflow> createWorkflowDelegate)
    {
        Throw.IfNull(builder);
        Throw.IfNull(name);
        Throw.IfNull(createWorkflowDelegate);

        builder.Services.AddKeyedSingleton(name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);
            var workflow = createWorkflowDelegate(sp, keyString) ?? throw new InvalidOperationException($"The agent factory did not return a valid {nameof(Workflow)} instance for key '{keyString}'.");
            if (!string.Equals(workflow.Name, keyString, StringComparison.Ordinal))
            {
                throw new InvalidOperationException($"The workflow factory returned workflow with name '{workflow.Name}', but the expected name is '{keyString}'.");
            }

            return workflow;
        });

        // Register the workflow by name for discovery.
        var workflowRegistry = GetWorkflowRegistry(builder);
        workflowRegistry.WorkflowNames.Add(name);

        return new HostedWorkflowBuilder(name, builder);
    }

    private static LocalWorkflowRegistry GetWorkflowRegistry(IHostApplicationBuilder builder)
    {
        var descriptor = builder.Services.FirstOrDefault(s => !s.IsKeyedService && s.ServiceType.Equals(typeof(LocalWorkflowRegistry)));
        if (descriptor?.ImplementationInstance is not LocalWorkflowRegistry instance)
        {
            instance = new LocalWorkflowRegistry();
            ConfigureHostBuilder(builder, instance);
        }

        return instance;
    }

    private static void ConfigureHostBuilder(IHostApplicationBuilder builder, LocalWorkflowRegistry agentHostBuilderContext)
    {
        builder.Services.Add(ServiceDescriptor.Singleton(agentHostBuilderContext));
        builder.Services.AddSingleton<WorkflowCatalog, LocalWorkflowCatalog>();
    }
}
