// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Agent-specific extension methods for the <see cref="IServiceCollection"/> class.
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
    /// Configures the Durable Agents services via the service collection.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <param name="configure">A delegate to configure the durable agents.</param>
    /// <param name="workerBuilder">A delegate to configure the Durable Task worker.</param>
    /// <param name="clientBuilder">A delegate to configure the Durable Task client.</param>
    /// <returns>The service collection.</returns>
    public static IServiceCollection ConfigureDurableAgents(
        this IServiceCollection services,
        Action<DurableAgentsOptions> configure,
        Action<IDurableTaskWorkerBuilder>? workerBuilder = null,
        Action<IDurableTaskClientBuilder>? clientBuilder = null)
    {
        ArgumentNullException.ThrowIfNull(configure);

        DurableAgentsOptions options = services.ConfigureDurableAgents(configure);

        // A worker is required to run the agent entities
        services.AddDurableTaskWorker(builder =>
        {
            workerBuilder?.Invoke(builder);

            builder.AddTasks(registry =>
            {
                foreach (string name in options.GetAgentFactories().Keys)
                {
                    registry.AddEntity<AgentEntity>(AgentSessionId.ToEntityName(name));
                }
            });
        });

        // The client is needed to send notifications to the agent entities from non-orchestrator code
        if (clientBuilder != null)
        {
            services.AddDurableTaskClient(clientBuilder);
        }

        services.AddSingleton<IDurableAgentClient, DefaultDurableAgentClient>();

        return services;
    }

    // This is internal because it's also used by Microsoft.Azure.Functions.DurableAgents, which is a friend assembly project.
    internal static DurableAgentsOptions ConfigureDurableAgents(
        this IServiceCollection services,
        Action<DurableAgentsOptions> configure)
    {
        DurableAgentsOptions options = new();
        configure(options);

        var agents = options.GetAgentFactories();

        // The agent dictionary contains the real agent factories, which is used by the agent entities.
        services.AddSingleton(agents);

        // The keyed services are used to resolve durable agent *proxy* instances for external clients.
        foreach (var factory in agents)
        {
            services.AddKeyedSingleton(factory.Key, (sp, _) => factory.Value(sp).AsDurableAgentProxy(sp));
        }

        // A custom data converter is needed because the default chat client uses camel case for JSON properties,
        // which is not the default behavior for the Durable Task SDK.
        services.AddSingleton<DataConverter, DefaultDataConverter>();

        return options;
    }

    private sealed class DefaultDataConverter : DataConverter
    {
        // Use durable agent options (web defaults + camel case by default) with case-insensitive matching.
        // We clone to apply naming/casing tweaks while retaining source-generated metadata where available.
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

            JsonTypeInfo? typeInfo = s_options.GetTypeInfo(targetType);
            if (typeInfo is JsonTypeInfo typedInfo)
            {
                return JsonSerializer.Deserialize(data, typedInfo);
            }

            // Fallback (may trigger trimming/AOT warnings for unsupported dynamic types).
            return JsonSerializer.Deserialize(data, targetType, s_options);
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

            JsonTypeInfo? typeInfo = s_options.GetTypeInfo(value.GetType());
            if (typeInfo is JsonTypeInfo typedInfo)
            {
                return JsonSerializer.Serialize(value, typedInfo);
            }

            return JsonSerializer.Serialize(value, s_options);
        }
    }
}
