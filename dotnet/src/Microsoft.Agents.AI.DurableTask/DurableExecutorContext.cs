// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.Entities;
using Microsoft.DurableTask.Entities;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// An implementation of <see cref="IWorkflowContext"/> for workflow executors running as durable activities.
/// Provides durable state management using Durable Entities. State is scoped to the orchestration instance
/// and shared between executors running on potentially different compute instances.
/// </summary>
/// <remarks>
/// State operations use GetEntityAsync for reads (fetches current entity state) and SignalEntityAsync
/// for writes. Since activities run sequentially in the orchestration and entity signals are processed
/// in order, state consistency is maintained across executors.
/// </remarks>
[RequiresUnreferencedCode("State serialization uses reflection-based JSON serialization.")]
[RequiresDynamicCode("State serialization uses reflection-based JSON serialization.")]
public sealed class DurableExecutorContext : IWorkflowContext
{
    private readonly string _instanceId;
    private readonly DurableTaskClient _client;
    private readonly Dictionary<string, string?> _pendingUpdates = [];
    private readonly HashSet<string> _clearedScopes = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableExecutorContext"/> class.
    /// </summary>
    /// <param name="instanceId">The orchestration instance ID used to scope the state entity.</param>
    /// <param name="client">The durable task client for entity operations.</param>
    public DurableExecutorContext(string instanceId, DurableTaskClient client)
    {
        this._instanceId = instanceId;
        this._client = client;
    }

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
    {
        // In activity context, events are not propagated to the workflow
        return default;
    }

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
    {
        // In activity context, messages cannot be routed to other executors
        return default;
    }

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
    {
        // In activity context, outputs are not yielded to the workflow
        return default;
    }

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync()
    {
        // Halt requests are not supported in activity context
        return default;
    }

    /// <inheritdoc/>
    public async ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string scopeKey = GetScopeKey(scopeName, key);

        // 1. Check pending updates first (read-your-writes within this activity)
        if (this._pendingUpdates.TryGetValue(scopeKey, out string? pendingValue))
        {
            return pendingValue is null ? default : JsonSerializer.Deserialize<T>(pendingValue);
        }

        // 2. Check if the scope was cleared in this activity
        string normalizedScope = scopeName ?? "__default__";
        if (this._clearedScopes.Contains(normalizedScope))
        {
            return default;
        }

        // 3. Read from the durable entity
        EntityInstanceId entityId = this.GetStateEntityId();

        EntityMetadata? metadata = await this._client.Entities
            .GetEntityAsync(entityId, includeState: true, cancellation: cancellationToken)
            .ConfigureAwait(false);

        if (metadata?.IncludesState != true)
        {
            return default;
        }

        WorkflowStateData? stateData = metadata.State.ReadAs<WorkflowStateData>();
        if (stateData?.Values is null)
        {
            return default;
        }

        if (stateData.Values.TryGetValue(scopeKey, out string? serializedValue) && serializedValue is not null)
        {
            return JsonSerializer.Deserialize<T>(serializedValue);
        }

        return default;
    }

    /// <inheritdoc/>
    public async ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        T? value = await this.ReadStateAsync<T>(key, scopeName, cancellationToken).ConfigureAwait(false);

        if (value is not null)
        {
            return value;
        }

        // Initialize with factory value and write to entity
        T initialValue = initialStateFactory();
        await this.QueueStateUpdateAsync(key, initialValue, scopeName, cancellationToken).ConfigureAwait(false);
        return initialValue;
    }

    /// <inheritdoc/>
    public async ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string normalizedScope = scopeName ?? "__default__";
        string scopePrefix = GetScopePrefix(scopeName);
        HashSet<string> keys = [];

        // If scope was cleared, only return keys from pending updates
        if (this._clearedScopes.Contains(normalizedScope))
        {
            return this.GetPendingKeysForScope(scopeName);
        }

        // Read keys from the durable entity
        EntityInstanceId entityId = this.GetStateEntityId();

        EntityMetadata? metadata = await this._client.Entities
            .GetEntityAsync(entityId, includeState: true, cancellation: cancellationToken)
            .ConfigureAwait(false);

        if (metadata?.IncludesState == true)
        {
            WorkflowStateData? stateData = metadata.State.ReadAs<WorkflowStateData>();
            if (stateData?.Values is not null)
            {
                foreach (string scopeKey in stateData.Values.Keys)
                {
                    if (scopeKey.StartsWith(scopePrefix, StringComparison.Ordinal))
                    {
                        string foundKey = scopeKey[scopePrefix.Length..];
                        keys.Add(foundKey);
                    }
                }
            }
        }

        // Merge with pending updates
        foreach (KeyValuePair<string, string?> pending in this._pendingUpdates)
        {
            if (pending.Key.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                string foundKey = pending.Key[scopePrefix.Length..];
                if (pending.Value is not null)
                {
                    keys.Add(foundKey);
                }
                else
                {
                    keys.Remove(foundKey);
                }
            }
        }

        return keys;
    }

    /// <inheritdoc/>
    public async ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string scopeKey = GetScopeKey(scopeName, key);
        string? serializedValue = value is null ? null : JsonSerializer.Serialize(value);

        // Store locally for read-your-writes within this activity
        this._pendingUpdates[scopeKey] = serializedValue;

        // Write to the durable entity via signal
        // Since activities run sequentially and signals are processed in order,
        // the next activity will see this update when it reads from the entity
        EntityInstanceId entityId = this.GetStateEntityId();
        WorkflowStateWriteRequest request = new() { Key = key, ScopeName = scopeName, Value = serializedValue };

        await this._client.Entities
            .SignalEntityAsync(entityId, nameof(WorkflowSharedStateEntity.WriteState), request, cancellation: cancellationToken)
            .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string normalizedScope = scopeName ?? "__default__";
        this._clearedScopes.Add(normalizedScope);

        // Remove pending updates in this scope
        string scopePrefix = GetScopePrefix(scopeName);
        List<string> keysToRemove = this._pendingUpdates.Keys
            .Where(k => k.StartsWith(scopePrefix, StringComparison.Ordinal))
            .ToList();

        foreach (string key in keysToRemove)
        {
            this._pendingUpdates.Remove(key);
        }

        // Clear in the durable entity via signal
        EntityInstanceId entityId = this.GetStateEntityId();

        await this._client.Entities
            .SignalEntityAsync(entityId, nameof(WorkflowSharedStateEntity.ClearScope), scopeName, cancellation: cancellationToken)
            .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public IReadOnlyDictionary<string, string>? TraceContext => null;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => false;

    private EntityInstanceId GetStateEntityId()
    {
        // Entity is keyed by orchestration instance ID for isolation between runs
        return new EntityInstanceId(WorkflowSharedStateEntity.EntityName, this._instanceId);
    }

    private HashSet<string> GetPendingKeysForScope(string? scopeName)
    {
        string scopePrefix = GetScopePrefix(scopeName);
        HashSet<string> keys = [];

        foreach (KeyValuePair<string, string?> pending in this._pendingUpdates)
        {
            if (pending.Key.StartsWith(scopePrefix, StringComparison.Ordinal) && pending.Value is not null)
            {
                string key = pending.Key[scopePrefix.Length..];
                keys.Add(key);
            }
        }

        return keys;
    }

    private static string GetScopeKey(string? scopeName, string key)
    {
        return $"{GetScopePrefix(scopeName)}{key}";
    }

    private static string GetScopePrefix(string? scopeName)
    {
        return scopeName is null ? "__default__:" : $"{scopeName}:";
    }
}
