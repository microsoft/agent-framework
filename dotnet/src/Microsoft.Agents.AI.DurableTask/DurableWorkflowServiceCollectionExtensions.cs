// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Extension methods for configuring durable workflows with the service collection.
/// </summary>
public static class DurableWorkflowServiceCollectionExtensions
{
    /// <summary>
    /// Configures durable workflows with the service collection, automatically registering
    /// orchestrations and activities for each workflow.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="configure">A delegate to configure the durable options.</param>
    /// <param name="workerBuilder">An optional delegate to configure the durable task worker.</param>
    /// <param name="clientBuilder">An optional delegate to configure the durable task client.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection ConfigureDurableWorkflows(
        this IServiceCollection services,
        Action<DurableOptions> configure,
        Action<IDurableTaskWorkerBuilder>? workerBuilder = null,
        Action<IDurableTaskClientBuilder>? clientBuilder = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(configure);

        // Create and configure durable options
        DurableOptions durableOptions = new();
        configure(durableOptions);

        // Register DurableOptions as a singleton
        services.AddSingleton(durableOptions);

        // Register the workflow runner
        services.AddSingleton<DurableWorkflowRunner>();

        // Build registration info for all workflows (including sub-workflows)
        List<WorkflowRegistrationInfo> registrations = [];
        HashSet<string> registeredActivities = [];
        HashSet<string> registeredOrchestrations = [];

        // Take a snapshot of the workflows to avoid collection modified during enumeration
        // (sub-workflows are added to the collection during recursive registration)
        foreach (Workflow workflow in durableOptions.Workflows.Workflows.Values.ToList())
        {
            BuildWorkflowRegistrationRecursive(
                workflow,
                durableOptions.Workflows,
                registrations,
                registeredActivities,
                registeredOrchestrations);
        }

        // Get any AI agents that were auto-registered from workflows
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agentFactories = durableOptions.Agents.GetAgentFactories();

        // Configure Durable Task Worker with orchestrations and activities
        services.AddDurableTaskWorker(builder =>
        {
            workerBuilder?.Invoke(builder);

            builder.AddTasks(registry =>
            {
                // Register all workflow tasks
                foreach (WorkflowRegistrationInfo registration in registrations)
                {
                    // Register orchestration
                    registry.AddOrchestratorFunc<string, string>(
                        registration.OrchestrationName,
                        (context, input) => RunWorkflowOrchestrationAsync(context, input, durableOptions));

                    // Register activities
                    foreach (ActivityRegistrationInfo activity in registration.Activities)
                    {
                        ExecutorBinding binding = activity.Binding;
                        registry.AddActivityFunc<string, string>(
                            activity.ActivityName,
                            (context, input) => ExecuteActivityAsync(binding, input));
                    }
                }

                // Register agent entities for any AI agents used in workflows
                foreach (string agentName in agentFactories.Keys)
                {
                    registry.AddEntity<AgentEntity>(AgentSessionId.ToEntityName(agentName));
                }
            });
        });

        // Register DurableAgentsOptions and agent factories for entity resolution
        if (agentFactories.Count > 0)
        {
            services.AddSingleton(durableOptions.Agents);

            // Register the agent factories dictionary for backward compatibility
            services.TryAddSingleton(
                sp => sp.GetRequiredService<DurableAgentsOptions>().GetAgentFactories());

            // A custom data converter is needed for proper JSON serialization
            services.TryAddSingleton<DataConverter, WorkflowDataConverter>();
        }

        // Configure Durable Task Client if a builder is provided
        if (clientBuilder is not null)
        {
            services.AddDurableTaskClient(clientBuilder);
        }

        // Register the DurableWorkflowClient for DI-friendly workflow execution
        // Register both the concrete type and the interface
        services.TryAddSingleton<DurableWorkflowClient>();
        services.TryAddSingleton<IWorkflowClient>(sp => sp.GetRequiredService<DurableWorkflowClient>());

        return services;
    }

    /// <summary>
    /// Recursively builds workflow registrations, including any sub-workflows.
    /// Also adds sub-workflows to the workflow options so they can be looked up at runtime.
    /// </summary>
    /// <param name="workflow">The workflow to register.</param>
    /// <param name="workflowOptions">The workflow options to add sub-workflows to.</param>
    /// <param name="registrations">The list to add registrations to.</param>
    /// <param name="registeredActivities">Set of already registered activity names to avoid duplicates.</param>
    /// <param name="registeredOrchestrations">Set of already registered orchestration names to avoid duplicates.</param>
    private static void BuildWorkflowRegistrationRecursive(
        Workflow workflow,
        DurableWorkflowOptions workflowOptions,
        List<WorkflowRegistrationInfo> registrations,
        HashSet<string> registeredActivities,
        HashSet<string> registeredOrchestrations)
    {
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name!);

        // Skip if this workflow is already registered (handles circular references)
        if (!registeredOrchestrations.Add(orchestrationName))
        {
            return;
        }

        // Build registration for this workflow
        registrations.Add(BuildWorkflowRegistration(workflow, registeredActivities));

        // Recursively register any sub-workflows
        foreach (KeyValuePair<string, ExecutorBinding> entry in workflow.ReflectExecutors())
        {
            if (entry.Value is SubworkflowBinding subworkflowBinding)
            {
                Workflow subWorkflow = subworkflowBinding.WorkflowInstance;

                // Add sub-workflow to options so it can be looked up by the runner at runtime
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
        string workflowName = workflow.Name!;
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);
        Dictionary<string, ExecutorBinding> executorBindings = workflow.ReflectExecutors();

        List<ActivityRegistrationInfo> activities = [];

        foreach (KeyValuePair<string, ExecutorBinding> entry in executorBindings)
        {
            // Skip agent executors - they're handled differently
            if (entry.Value is AIAgentBinding)
            {
                continue;
            }

            // Skip sub-workflow executors - they're handled as sub-orchestrations
            if (entry.Value is SubworkflowBinding)
            {
                continue;
            }

            string executorName = WorkflowNamingHelper.GetExecutorName(entry.Key);
            string activityName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

            // Skip if already registered (same executor used in multiple workflows)
            if (!registeredActivities.Add(activityName))
            {
                continue;
            }

            activities.Add(new ActivityRegistrationInfo(activityName, entry.Value));
        }

        return new WorkflowRegistrationInfo(orchestrationName, activities);
    }

    private static async Task<string> RunWorkflowOrchestrationAsync(
        TaskOrchestrationContext context,
        string input,
        DurableOptions durableOptions)
    {
        ILogger logger = context.CreateReplaySafeLogger("WorkflowOrchestration");
        DurableWorkflowRunner runner = new(
            NullLoggerFactory.Instance.CreateLogger<DurableWorkflowRunner>(),
            durableOptions);

        return await runner.RunWorkflowOrchestrationAsync(context, input, logger).ConfigureAwait(true);
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Executor types are registered at startup.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Executor types are registered at startup.")]
    private static async Task<string> ExecuteActivityAsync(ExecutorBinding binding, string input)
    {
        DurableActivityInput? inputWithState = TryDeserializeActivityInput(input);
        string executorInput = inputWithState?.Input ?? input;
        Dictionary<string, string> sharedState = inputWithState?.State ?? [];

        Executor executor = await binding.FactoryAsync!("activity-run").ConfigureAwait(false);
        Type inputType = ResolveInputType(inputWithState?.InputTypeName, executor.InputTypes);
        object typedInput = DeserializeInput(executorInput, inputType);

        PipelineActivityContext workflowContext = new(sharedState, executor);
        object? result = await executor.ExecuteAsync(
            typedInput,
            new TypeId(inputType),
            workflowContext,
            CancellationToken.None).ConfigureAwait(false);

        return SerializeActivityOutput(result, workflowContext);
    }

    /// <summary>
    /// Serializes the activity output using source-generated serialization.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "SerializeResult uses reflection for user types.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "SerializeResult uses reflection for user types.")]
    private static string SerializeActivityOutput(object? result, PipelineActivityContext context)
    {
        DurableActivityOutput output = new()
        {
            Result = SerializeResult(result),
            StateUpdates = context.StateUpdates,
            ClearedScopes = [.. context.ClearedScopes],
            Events = context.Events.ConvertAll(SerializeEvent),
            SentMessages = context.SentMessages.ConvertAll(m => new SentMessageInfo
            {
                Message = m.Message,
                TypeName = m.TypeName
            })
        };

        return JsonSerializer.Serialize(output, DurableWorkflowJsonContext.Default.DurableActivityOutput);
    }

    /// <summary>
    /// Resolves the input type from the provided type name, or falls back to the first supported type.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Type resolution for registered executor types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2057:TypeGetType", Justification = "Type resolution for registered executor types.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Type resolution for registered executor types.")]
    private static Type ResolveInputType(string? inputTypeName, ISet<Type> supportedTypes)
    {
        if (string.IsNullOrEmpty(inputTypeName))
        {
            return supportedTypes.FirstOrDefault() ?? typeof(string);
        }

        // Try to find a matching type in the supported types
        Type? matchedType = supportedTypes.FirstOrDefault(t =>
            t.AssemblyQualifiedName == inputTypeName ||
            t.FullName == inputTypeName ||
            t.Name == inputTypeName);

        if (matchedType is not null)
        {
            return matchedType;
        }

        // Try to load the type directly (for types not in supported types)
        Type? loadedType = Type.GetType(inputTypeName);

        // If the loaded type is string but the executor doesn't support string,
        // fall back to the first supported type. This handles the case where
        // serialized JSON objects are passed with type "System.String" but need
        // to be deserialized to the actual expected type (e.g., OrderInfo).
        if (loadedType == typeof(string) && !supportedTypes.Contains(typeof(string)))
        {
            return supportedTypes.FirstOrDefault() ?? typeof(string);
        }

        return loadedType ?? supportedTypes.FirstOrDefault() ?? typeof(string);
    }

    /// <summary>
    /// Attempts to deserialize activity input using source-generated serialization.
    /// </summary>
    private static DurableActivityInput? TryDeserializeActivityInput(string input)
    {
        try
        {
            return JsonSerializer.Deserialize(input, DurableWorkflowJsonContext.Default.DurableActivityInput);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>
    /// Serializes a workflow event with type information.
    /// </summary>
    /// <remarks>
    /// The event data itself uses reflection-based serialization since event types
    /// are user-defined, but the wrapper uses source generation.
    /// </remarks>
    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Event data uses reflection for user types.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Event data uses reflection for user types.")]
    private static string SerializeEvent(WorkflowEvent evt)
    {
        // Serialize with type information so we can deserialize to the correct type later
        SerializedWorkflowEvent wrapper = new()
        {
            TypeName = evt.GetType().AssemblyQualifiedName,
            Data = JsonSerializer.Serialize(evt, evt.GetType())
        };
        return JsonSerializer.Serialize(wrapper, DurableWorkflowJsonContext.Default.SerializedWorkflowEvent);
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Deserializing workflow types registered at startup.")]
    private static object DeserializeInput(string input, Type targetType)
    {
        if (targetType == typeof(string))
        {
            return input;
        }

        return JsonSerializer.Deserialize(input, targetType)
            ?? throw new InvalidOperationException($"Failed to deserialize input to type '{targetType.Name}'.");
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Serializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Serializing workflow types registered at startup.")]
    private static string SerializeResult(object? result)
    {
        if (result is null)
        {
            return string.Empty;
        }

        if (result is string str)
        {
            return str;
        }

        return JsonSerializer.Serialize(result, result.GetType());
    }

    private sealed record WorkflowRegistrationInfo(string OrchestrationName, List<ActivityRegistrationInfo> Activities);

    private sealed record ActivityRegistrationInfo(string ActivityName, ExecutorBinding Binding);

    /// <summary>
    /// Custom data converter for workflow execution with AI agents.
    /// </summary>
    private sealed class WorkflowDataConverter : DataConverter
    {
        private static readonly JsonSerializerOptions s_options = new(DurableAgentJsonUtilities.DefaultOptions)
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            PropertyNameCaseInsensitive = true,
        };

        [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Fallback path uses reflection when metadata unavailable.")]
        [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050", Justification = "Fallback path uses reflection when metadata unavailable.")]
        public override object? Deserialize(string? data, Type targetType)
        {
            if (data is null)
            {
                return null;
            }

            if (targetType == typeof(DurableAgentState))
            {
                return JsonSerializer.Deserialize(data, DurableAgentStateJsonContext.Default.DurableAgentState);
            }

            return TryDeserializeWithTypeInfo(data, targetType)
                ?? JsonSerializer.Deserialize(data, targetType, s_options);
        }

        [return: NotNullIfNotNull(nameof(value))]
        [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Fallback path uses reflection when metadata unavailable.")]
        [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050", Justification = "Fallback path uses reflection when metadata unavailable.")]
        public override string? Serialize(object? value)
        {
            if (value is null)
            {
                return null;
            }

            if (value is DurableAgentState durableAgentState)
            {
                return JsonSerializer.Serialize(durableAgentState, DurableAgentStateJsonContext.Default.DurableAgentState);
            }

            return TrySerializeWithTypeInfo(value)
                ?? JsonSerializer.Serialize(value, s_options);
        }

        private static object? TryDeserializeWithTypeInfo(string data, Type targetType)
        {
            JsonTypeInfo? typeInfo = s_options.GetTypeInfo(targetType);
            return typeInfo is not null ? JsonSerializer.Deserialize(data, typeInfo) : null;
        }

        private static string? TrySerializeWithTypeInfo(object value)
        {
            JsonTypeInfo? typeInfo = s_options.GetTypeInfo(value.GetType());
            return typeInfo is not null ? JsonSerializer.Serialize(value, typeInfo) : null;
        }
    }
}

/// <summary>
/// Input payload for activity execution, containing the executor input and shared workflow state.
/// </summary>
internal sealed class DurableActivityInput
{
    /// <summary>
    /// Gets or sets the serialized executor input.
    /// </summary>
    public string? Input { get; set; }

    /// <summary>
    /// Gets or sets the assembly-qualified type name of the input, used for proper deserialization.
    /// </summary>
    public string? InputTypeName { get; set; }

    /// <summary>
    /// Gets or sets the shared state dictionary (scope-prefixed key -> serialized value).
    /// </summary>
    public Dictionary<string, string> State { get; set; } = [];
}

/// <summary>
/// Output payload from activity execution, containing the result, state updates, and emitted events.
/// </summary>
internal sealed class DurableActivityOutput
{
    /// <summary>
    /// Gets or sets the serialized result of the activity.
    /// </summary>
    public string? Result { get; set; }

    /// <summary>
    /// Gets or sets state updates made during activity execution (scope-prefixed key -> serialized value, null = delete).
    /// </summary>
    public Dictionary<string, string?> StateUpdates { get; set; } = [];

    /// <summary>
    /// Gets or sets scopes that were cleared during activity execution.
    /// </summary>
    public List<string> ClearedScopes { get; set; } = [];

    /// <summary>
    /// Gets or sets the serialized workflow events emitted during activity execution.
    /// </summary>
    public List<string> Events { get; set; } = [];

    /// <summary>
    /// Gets or sets messages sent via SendMessageAsync during activity execution.
    /// Each entry is a tuple of (serializedMessage, typeName).
    /// </summary>
    public List<SentMessageInfo> SentMessages { get; set; } = [];
}

/// <summary>
/// Information about a message sent via SendMessageAsync.
/// </summary>
internal sealed class SentMessageInfo
{
    /// <summary>
    /// Gets or sets the serialized message content.
    /// </summary>
    public string? Message { get; set; }

    /// <summary>
    /// Gets or sets the full type name of the message.
    /// </summary>
    public string? TypeName { get; set; }
}
