// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
    /// todo
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="name"></param>
    /// <param name="agentBuilders"></param>
    /// <returns></returns>
    public static IHostWorkflowBuilder AddConcurrentWorkflow(this IHostApplicationBuilder builder, string name, IEnumerable<IHostAgentBuilder> agentBuilders)
    {
        return builder.AddWorkflow(name, (sp, key) =>
        {
            var agents = agentBuilders.Select(ab => sp.GetRequiredKeyedService<AIAgent>(ab.Name));
            return AgentWorkflowBuilder.PrepareConcurrent(agents: agents).WithName(name).Build();
        });
    }

    /// <summary>
    /// todo
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="name"></param>
    /// <param name="agentBuilders"></param>
    /// <returns></returns>
    public static IHostWorkflowBuilder AddSequentialWorkflow(this IHostApplicationBuilder builder, string name, IEnumerable<IHostAgentBuilder> agentBuilders)
    {
        return builder.AddWorkflow(name, (sp, key) =>
        {
            var agents = agentBuilders.Select(ab => sp.GetRequiredKeyedService<AIAgent>(ab.Name));
            return AgentWorkflowBuilder.PrepareSequential(agents: agents).WithName(name).Build();
        });
    }

    /// <summary>
    /// todo
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="name"></param>
    /// <param name="createWorkflowDelegate"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
    public static IHostWorkflowBuilder AddWorkflow(this IHostApplicationBuilder builder, string name, Func<IServiceProvider, string, Workflow> createWorkflowDelegate)
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

        // Register the agent by name for discovery.
        var workflowRegistry = GetWorkflowRegistry(builder);
        workflowRegistry.WorkflowNames.Add(name);

        return new HostWorkflowBuilder(name, builder);
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
