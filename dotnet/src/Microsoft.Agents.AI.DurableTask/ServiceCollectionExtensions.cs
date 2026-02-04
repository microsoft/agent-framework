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
public static class ServiceCollectionExtensions
{
    /// <summary>
    /// Gets a durable agent proxy by name.
    /// </summary>
    /// <param name="services">The service provider.</param>
    /// <param name="name">The name of the agent.</param>
    /// <returns>The durable agent proxy.</returns>
    /// <exception cref="KeyNotFoundException">Thrown if the agent proxy is not found.</exception>
    public static AIAgent GetDurableAgentProxy(this IServiceProvider services, string name)
    {
        return services.GetKeyedService<AIAgent>(name)
            ?? throw new KeyNotFoundException($"A durable agent with name '{name}' has not been registered.");
    }

    /// <summary>
    /// Configures durable agents, automatically registering agent entities.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method provides an agent-focused configuration experience.
    /// If you need to configure both agents and workflows, consider using
    /// <see cref="ConfigureDurableOptions"/> instead.
    /// </para>
    /// <para>
    /// Multiple calls to this method are supported and configurations are composed additively.
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="configure">A delegate to configure the durable agents.</param>
    /// <param name="workerBuilder">Optional delegate to configure the Durable Task worker.</param>
    /// <param name="clientBuilder">Optional delegate to configure the Durable Task client.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection ConfigureDurableAgents(
        this IServiceCollection services,
        Action<DurableAgentsOptions> configure,
        Action<IDurableTaskWorkerBuilder>? workerBuilder = null,
        Action<IDurableTaskClientBuilder>? clientBuilder = null)
    {
        return services.ConfigureDurableOptions(
            options => configure(options.Agents),
            workerBuilder,
            clientBuilder);
    }

    /// <summary>
    /// Configures durable workflows, automatically registering orchestrations and activities.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method provides a workflow-focused configuration experience.
    /// If you need to configure both agents and workflows, consider using
    /// <see cref="ConfigureDurableOptions"/> instead.
    /// </para>
    /// <para>
    /// Multiple calls to this method are supported and configurations are composed additively.
    /// </para>
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

    /// <summary>
    /// Configures durable agents and workflows, automatically registering orchestrations, activities, and agent entities.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is the recommended entry point for configuring durable functionality. It provides unified configuration
    /// for both agents and workflows through a single <see cref="DurableOptions"/> instance, ensuring agents
    /// referenced in workflows are automatically registered.
    /// </para>
    /// <para>
    /// Multiple calls to this method (or to <see cref="ConfigureDurableAgents"/>
    /// and <see cref="ConfigureDurableWorkflows"/>) are supported and configurations are composed additively.
    /// </para>
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

        // Get or create the shared DurableOptions instance for configuration
        DurableOptions sharedOptions = GetOrCreateSharedOptions(services);

        // Apply the configuration immediately to capture agent names for keyed service registration
        configure(sharedOptions);

        // Register keyed services for any new agents
        RegisterAgentKeyedServices(services, sharedOptions);

        // Register core services only once
        EnsureDurableServicesRegistered(services, sharedOptions, workerBuilder, clientBuilder);

        return services;
    }

    private static DurableOptions GetOrCreateSharedOptions(IServiceCollection services)
    {
        // Look for an existing DurableOptions registration
        ServiceDescriptor? existingDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(DurableOptions) && d.ImplementationInstance is not null);

        if (existingDescriptor?.ImplementationInstance is DurableOptions existing)
        {
            return existing;
        }

        // Create a new shared options instance
        DurableOptions options = new();
        services.AddSingleton(options);
        return options;
    }

    private static void RegisterAgentKeyedServices(IServiceCollection services, DurableOptions options)
    {
        foreach (KeyValuePair<string, Func<IServiceProvider, AIAgent>> factory in options.Agents.GetAgentFactories())
        {
            // Only add if not already registered (to support multiple Configure* calls)
            if (!services.Any(d => d.ServiceType == typeof(AIAgent) && d.IsKeyedService && Equals(d.ServiceKey, factory.Key)))
            {
                services.AddKeyedSingleton(factory.Key, (sp, _) => factory.Value(sp).AsDurableAgentProxy(sp));
            }
        }
    }

    /// <summary>
    /// Ensures that the core durable services are registered only once, regardless of how many
    /// times the configuration methods are called.
    /// </summary>
    private static void EnsureDurableServicesRegistered(
        IServiceCollection services,
        DurableOptions sharedOptions,
        Action<IDurableTaskWorkerBuilder>? workerBuilder,
        Action<IDurableTaskClientBuilder>? clientBuilder)
    {
        // Use a marker to ensure we only register core services once
        if (services.Any(d => d.ServiceType == typeof(DurableServicesMarker)))
        {
            return;
        }

        services.AddSingleton<DurableServicesMarker>();

        services.TryAddSingleton<DurableWorkflowRunner>();

        // Configure Durable Task Worker - capture sharedOptions reference in closure.
        // The options object is populated by all Configure* calls before the worker starts.
        services.AddDurableTaskWorker(builder =>
        {
            workerBuilder?.Invoke(builder);

            builder.AddTasks(registry => RegisterTasksFromOptions(registry, sharedOptions));
        });

        // Configure Durable Task Client
        if (clientBuilder is not null)
        {
            services.AddDurableTaskClient(clientBuilder);
        }

        // Register workflow and agent services
        services.TryAddSingleton<DurableWorkflowClient>();
        services.TryAddSingleton<IWorkflowClient>(sp => sp.GetRequiredService<DurableWorkflowClient>());
        services.TryAddSingleton<DataConverter, DurableDataConverter>();
        services.TryAddSingleton<IDurableAgentClient, DefaultDurableAgentClient>();

        // Register agent factories resolver - returns factories from the shared options
        services.TryAddSingleton(
            sp => sp.GetRequiredService<DurableOptions>().Agents.GetAgentFactories());

        // Register DurableAgentsOptions resolver
        services.TryAddSingleton(sp => sp.GetRequiredService<DurableOptions>().Agents);
    }

    private static void RegisterTasksFromOptions(DurableTaskRegistry registry, DurableOptions durableOptions)
    {
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

            // Register orchestrations and activities
            foreach (WorkflowRegistrationInfo registration in registrations)
            {
                // Register with DurableWorkflowInput<object> - the DataConverter handles serialization/deserialization
                registry.AddOrchestratorFunc<DurableWorkflowInput<object>, string>(
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

        // Register agent entities
        foreach (string agentName in agentFactories.Keys)
        {
            registry.AddEntity<AgentEntity>(AgentSessionId.ToEntityName(agentName));
        }
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

        // Process subworkflows recursively to register them as separate orchestrations
        foreach (SubworkflowBinding subworkflowBinding in workflow.ReflectExecutors()
            .Select(e => e.Value)
            .OfType<SubworkflowBinding>())
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

    private static WorkflowRegistrationInfo BuildWorkflowRegistration(
        Workflow workflow,
        HashSet<string> registeredActivities)
    {
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name!);
        Dictionary<string, ExecutorBinding> executorBindings = workflow.ReflectExecutors();
        List<ActivityRegistrationInfo> activities = [];

        // Filter out AI agents and subworkflows - they are not registered as activities.
        // AI agents use Durable Entities for stateful execution, and subworkflows are
        // registered as separate orchestrations via BuildWorkflowRegistrationRecursive.
        foreach (KeyValuePair<string, ExecutorBinding> entry in executorBindings
                    .Where(e => e.Value is not AIAgentBinding and not SubworkflowBinding))
                {
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
                DurableWorkflowInput<object> workflowInput,
                DurableOptions durableOptions)
            {
                ILogger logger = context.CreateReplaySafeLogger("DurableWorkflow");
                DurableWorkflowRunner runner = new(durableOptions);

                // ConfigureAwait(true) is required in orchestration code for deterministic replay.
                return await runner.RunWorkflowOrchestrationAsync(context, workflowInput, logger).ConfigureAwait(true);
            }

            private sealed record WorkflowRegistrationInfo(string OrchestrationName, List<ActivityRegistrationInfo> Activities);

            private sealed record ActivityRegistrationInfo(string ActivityName, ExecutorBinding Binding);

            /// <summary>
            /// Validates that an agent with the specified name has been registered.
            /// </summary>
            /// <param name="services">The service provider.</param>
            /// <param name="agentName">The name of the agent to validate.</param>
            /// <exception cref="InvalidOperationException">
            /// Thrown when the agent dictionary is not registered in the service provider.
            /// </exception>
            /// <exception cref="AgentNotRegisteredException">
            /// Thrown when the agent with the specified name has not been registered.
            /// </exception>
            internal static void ValidateAgentIsRegistered(IServiceProvider services, string agentName)
            {
                IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>>? agents =
                    services.GetService<IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>>>()
                    ?? throw new InvalidOperationException(
                        $"Durable agents have not been configured. Ensure {nameof(ConfigureDurableAgents)} has been called on the service collection.");

                if (!agents.ContainsKey(agentName))
                {
                    throw new AgentNotRegisteredException(agentName);
                }
            }
        }
