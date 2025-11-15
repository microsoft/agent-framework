// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// A context for durable agents that provides access to orchestration capabilities.
/// This class provides thread-static access to the current agent context.
/// </summary>
public class DurableAgentContext
{
    private static readonly AsyncLocal<DurableAgentContext?> s_currentContext = new();
    private readonly IServiceProvider _services;
    private readonly CancellationToken _cancellationToken;

    internal DurableAgentContext(
        TaskEntityContext entityContext,
        DurableTaskClient client,
        IHostApplicationLifetime lifetime,
        IServiceProvider services)
    {
        this.EntityContext = entityContext;
        this.CurrentThread = new DurableAgentThread(entityContext.Id);
        this.Client = client;
        this._services = services;
        this._cancellationToken = lifetime.ApplicationStopping;
    }

    /// <summary>
    /// Gets the current durable agent context instance.
    /// </summary>
    /// <exception cref="InvalidOperationException">Thrown when no agent context is available.</exception>
    public static DurableAgentContext Current => s_currentContext.Value ??
        throw new InvalidOperationException("No agent context found!");

    /// <summary>
    /// Gets the entity context for this agent.
    /// </summary>
    public TaskEntityContext EntityContext { get; }

    /// <summary>
    /// Gets the durable task client for this agent.
    /// </summary>
    public DurableTaskClient Client { get; }

    /// <summary>
    /// Gets the current agent thread.
    /// </summary>
    public DurableAgentThread CurrentThread { get; }

    /// <summary>
    /// Sets the current durable agent context instance.
    /// This is called internally by the agent entity during execution.
    /// </summary>
    /// <param name="context">The context instance to set.</param>
    internal static void SetCurrent(DurableAgentContext context)
    {
        if (s_currentContext.Value is not null)
        {
            throw new InvalidOperationException("A DurableAgentContext has already been set for this AsyncLocal context.");
        }

        s_currentContext.Value = context;
    }

    /// <summary>
    /// Clears the current durable agent context instance.
    /// This is called internally by the agent entity after execution.
    /// </summary>
    internal static void ClearCurrent()
    {
        s_currentContext.Value = null;
    }

    /// <summary>
    /// Schedules a new orchestration instance.
    /// </summary>
    /// <remarks>
    /// When run in the context of a durable agent tool, the actual scheduling of the orchestration
    /// occurs after the completion of the tool call. This allows the durable scheduling of the orchestration
    /// and the agent state update to be committed atomically in a single transaction.
    /// </remarks>
    /// <param name="name">The name of the orchestration to schedule.</param>
    /// <param name="input">The input to the orchestration.</param>
    /// <param name="options">The options for the orchestration.</param>
    /// <returns>The instance ID of the scheduled orchestration.</returns>
    public string ScheduleNewOrchestration(
        TaskName name,
        object? input = null,
        StartOrchestrationOptions? options = null)
    {
        return this.EntityContext.ScheduleNewOrchestration(name, input, options);
    }

    /// <summary>
    /// Gets the status of an orchestration instance.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to get the status of.</param>
    /// <param name="includeDetails">Whether to include detailed information about the orchestration.</param>
    /// <returns>The status of the orchestration.</returns>
    public Task<OrchestrationMetadata?> GetOrchestrationStatusAsync(string instanceId, bool includeDetails = false)
    {
        return this.Client.GetInstanceAsync(instanceId, includeDetails, this._cancellationToken);
    }

    /// <summary>
    /// Raises an event on an orchestration instance.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to raise the event on.</param>
    /// <param name="eventName">The name of the event to raise.</param>
    /// <param name="eventData">The data to send with the event.</param>
#pragma warning disable CA1030 // Use events where appropriate
    public Task RaiseOrchestrationEventAsync(string instanceId, string eventName, object? eventData = null)
#pragma warning restore CA1030 // Use events where appropriate
    {
        return this.Client.RaiseEventAsync(instanceId, eventName, eventData, this._cancellationToken);
    }

    /// <summary>
    /// Asks the <see cref="DurableAgentContext"/> for an object of the specified type, <typeparamref name="TService"/>.
    /// </summary>
    /// <typeparam name="TService">The type of the object being requested.</typeparam>
    /// <param name="serviceKey">An optional key to identify the service instance.</param>
    /// <returns>The service instance, or <see langword="null"/> if the service is not found.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when <paramref name="serviceKey"/> is not <see langword="null"/> and the service provider does not support keyed services.
    /// </exception>
    public TService? GetService<TService>(object? serviceKey = null)
    {
        return this.GetService(typeof(TService), serviceKey) is TService service ? service : default;
    }

    /// <summary>
    /// Asks the <see cref="DurableAgentContext"/> for an object of the specified type, <paramref name="serviceType"/>.
    /// </summary>
    /// <param name="serviceType">The type of the object being requested.</param>
    /// <param name="serviceKey">An optional key to identify the service instance.</param>
    /// <returns>The service instance, or <see langword="null"/> if the service is not found.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when <paramref name="serviceKey"/> is not <see langword="null"/> and the service provider does not support keyed services.
    /// </exception>
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceKey is not null)
        {
            if (this._services is not IKeyedServiceProvider keyedServiceProvider)
            {
                throw new InvalidOperationException("The service provider does not support keyed services.");
            }

            return keyedServiceProvider.GetKeyedService(serviceType, serviceKey);
        }

        return this._services.GetService(serviceType);
    }
}
