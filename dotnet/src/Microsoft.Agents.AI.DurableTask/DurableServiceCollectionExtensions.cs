// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Extension methods for configuring durable agents and workflows with dependency injection.
/// </summary>
public static class DurableServiceCollectionExtensions
{
    /// <summary>
    /// Configures durable agents and workflows, automatically registering orchestrations, activities, and agent entities.
    /// </summary>
    /// <remarks>
    /// This is the recommended entry point for configuring durable functionality. It provides unified configuration
    /// for both agents and workflows through a single <see cref="DurableOptions"/> instance, ensuring agents
    /// referenced in workflows are automatically registered.
    /// </remarks>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="configure">A delegate to configure the durable options for both agents and workflows.</param>
    /// <param name="workerBuilder">Optional delegate to configure the durable task worker.</param>
    /// <param name="clientBuilder">Optional delegate to configure the durable task client.</param>
    /// <returns>The service collection for chaining.</returns>
    /// <example>
    /// <code>
    /// services.ConfigureDurableOptions(options =>
    /// {
    ///     // Register agents not part of workflows
    ///     options.Agents.AddAIAgent(standaloneAgent);
    ///
    ///     // Register workflows - agents in workflows are auto-registered
    ///     options.Workflows.AddWorkflow(myWorkflow);
    /// },
    /// workerBuilder: builder => builder.UseDurableTaskScheduler(connectionString),
    /// clientBuilder: builder => builder.UseDurableTaskScheduler(connectionString));
    /// </code>
    /// </example>
    public static IServiceCollection ConfigureDurableOptions(
        this IServiceCollection services,
        Action<DurableOptions> configure,
        Action<IDurableTaskWorkerBuilder>? workerBuilder = null,
        Action<IDurableTaskClientBuilder>? clientBuilder = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(configure);

        DurableOptions durableOptions = new();
        configure(durableOptions);

        return ConfigureDurableOptionsCore(services, durableOptions, workerBuilder, clientBuilder);
    }

    private static IServiceCollection ConfigureDurableOptionsCore(
        IServiceCollection services,
        DurableOptions durableOptions,
        Action<IDurableTaskWorkerBuilder>? workerBuilder,
        Action<IDurableTaskClientBuilder>? clientBuilder)
    {
        services.AddSingleton(durableOptions);
        services.AddSingleton<DurableWorkflowRunner>();

        // Build registrations for all workflows including sub-workflows
        List<WorkflowRegistrationInfo> registrations = [];
        HashSet<string> registeredActivities = [];
        HashSet<string> registeredOrchestrations = [];

        foreach (Workflow workflow in durableOptions.Workflows.Workflows.Values.ToList())
        {
            BuildWorkflowRegistrationRecursive(
                workflow,
                durableOptions.Workflows,
                registrations,
                registeredActivities,
                registeredOrchestrations);
        }

        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agentFactories =
            durableOptions.Agents.GetAgentFactories();

        // Configure Durable Task Worker
        services.AddDurableTaskWorker(builder =>
        {
            workerBuilder?.Invoke(builder);

            builder.AddTasks(registry =>
            {
                foreach (WorkflowRegistrationInfo registration in registrations)
                {
                    registry.AddOrchestratorFunc<string, string>(
                        registration.OrchestrationName,
                        (context, input) => RunWorkflowOrchestrationAsync(context, input, durableOptions));

                    foreach (ActivityRegistrationInfo activity in registration.Activities)
                    {
                        ExecutorBinding binding = activity.Binding;
                        registry.AddActivityFunc<string, string>(
                            activity.ActivityName,
                            (context, input) => DurableActivityExecutor.ExecuteAsync(binding, input));
                    }
                }

                foreach (string agentName in agentFactories.Keys)
                {
                    registry.AddEntity<AgentEntity>(AgentSessionId.ToEntityName(agentName));
                }
            });
        });

        // Register agent-related services if any agents are configured
        if (agentFactories.Count > 0)
        {
            RegisterAgentServices(services, durableOptions.Agents, agentFactories);
        }

        if (clientBuilder is not null)
        {
            services.AddDurableTaskClient(clientBuilder);
        }

        services.TryAddSingleton<DurableWorkflowClient>();
        services.TryAddSingleton<IWorkflowClient>(sp => sp.GetRequiredService<DurableWorkflowClient>());

        return services;
    }

    private static void RegisterAgentServices(
        IServiceCollection services,
        DurableAgentsOptions agentOptions,
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agentFactories)
    {
        // Register agent factories dictionary
        services.AddSingleton(agentFactories);

        // Register DurableAgentsOptions for AgentEntity to access TTL configuration
        services.AddSingleton(agentOptions);

        // Register IDurableAgentClient for agent proxies
        services.TryAddSingleton<IDurableAgentClient, DefaultDurableAgentClient>();

        // Register keyed services for agent proxies
        foreach (KeyValuePair<string, Func<IServiceProvider, AIAgent>> factory in agentFactories)
        {
            services.AddKeyedSingleton(factory.Key, (sp, _) => factory.Value(sp).AsDurableAgentProxy(sp));
        }

        // Register DataConverter for proper JSON serialization
        services.TryAddSingleton<DataConverter, DurableDataConverter>();
    }

    private static void BuildWorkflowRegistrationRecursive(
        Workflow workflow,
        DurableWorkflowOptions workflowOptions,
        List<WorkflowRegistrationInfo> registrations,
        HashSet<string> registeredActivities,
        HashSet<string> registeredOrchestrations)
    {
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name!);

        if (!registeredOrchestrations.Add(orchestrationName))
        {
            return;
        }

        registrations.Add(BuildWorkflowRegistration(workflow, registeredActivities));

        foreach (KeyValuePair<string, ExecutorBinding> entry in workflow.ReflectExecutors())
        {
            if (entry.Value is SubworkflowBinding subworkflowBinding)
            {
                Workflow subWorkflow = subworkflowBinding.WorkflowInstance;
                workflowOptions.AddWorkflow(subWorkflow);

                BuildWorkflowRegistrationRecursive(
                    subWorkflow,
                    workflowOptions,
                    registrations,
                    registeredActivities,
                    registeredOrchestrations);
            }
        }
    }

    private static WorkflowRegistrationInfo BuildWorkflowRegistration(
        Workflow workflow,
        HashSet<string> registeredActivities)
    {
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name!);
        Dictionary<string, ExecutorBinding> executorBindings = workflow.ReflectExecutors();
        List<ActivityRegistrationInfo> activities = [];

        foreach (KeyValuePair<string, ExecutorBinding> entry in executorBindings)
        {
            if (entry.Value is AIAgentBinding or SubworkflowBinding)
            {
                continue;
            }

            string executorName = WorkflowNamingHelper.GetExecutorName(entry.Key);
            string activityName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

            if (registeredActivities.Add(activityName))
            {
                activities.Add(new ActivityRegistrationInfo(activityName, entry.Value));
            }
        }

        return new WorkflowRegistrationInfo(orchestrationName, activities);
    }

    private static async Task<string> RunWorkflowOrchestrationAsync(
        TaskOrchestrationContext context,
        string input,
        DurableOptions durableOptions)
    {
        ILogger logger = context.CreateReplaySafeLogger("DurableWorkflow");
        DurableWorkflowRunner runner = new(durableOptions);

        return await runner.RunWorkflowOrchestrationAsync(context, input, logger).ConfigureAwait(true);
    }

    private sealed record WorkflowRegistrationInfo(string OrchestrationName, List<ActivityRegistrationInfo> Activities);

    private sealed record ActivityRegistrationInfo(string ActivityName, ExecutorBinding Binding);
}
