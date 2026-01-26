// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// A workflow context for activity execution that uses pipeline-based state management.
/// State is passed in from the orchestration and updates are collected for return.
/// </summary>
internal sealed class PipelineActivityContext : IWorkflowContext
{
    private readonly Dictionary<string, string> _initialState;
    private readonly Executor _executor;

    /// <summary>
    /// Initializes a new instance of the <see cref="PipelineActivityContext"/> class.
    /// </summary>
    /// <param name="initialState">The shared state passed from the orchestration.</param>
    /// <param name="executor">The executor running in this context.</param>
    public PipelineActivityContext(Dictionary<string, string>? initialState, Executor executor)
    {
        this._initialState = initialState ?? [];
        this._executor = executor;
    }

    /// <summary>
    /// Gets the events that were added during activity execution.
    /// </summary>
    public List<WorkflowEvent> Events { get; } = [];

    /// <summary>
    /// Gets the state updates made during activity execution.
    /// </summary>
    public Dictionary<string, string?> StateUpdates { get; } = [];

    /// <summary>
    /// Gets the scopes that were cleared during activity execution.
    /// </summary>
    public HashSet<string> ClearedScopes { get; } = [];

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
    {
        if (workflowEvent is not null)
        {
            this.Events.Add(workflowEvent);
        }

        return default;
    }

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
    {
        if (output is not null)
        {
            // Validate output type matches executor's declared output types (same as in-process execution)
            if (!CanOutput(this._executor.OutputTypes, output.GetType()))
            {
                throw new InvalidOperationException(
                    $"Cannot output object of type {output.GetType().Name}. " +
                    $"Expecting one of [{string.Join(", ", this._executor.OutputTypes)}].");
            }

            this.Events.Add(new DurableYieldedOutputEvent(this._executor.Id, output));
        }

        return default;
    }

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync()
    {
        this.Events.Add(new DurableHaltRequestedEvent(this._executor.Id));
        return default;
    }

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow state types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow state types.")]
    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string scopeKey = GetScopeKey(scopeName, key);
        string normalizedScope = scopeName ?? "__default__";

        // Check if scope was cleared
        if (this.ClearedScopes.Contains(normalizedScope))
        {
            // Only return from updates made after clear
            if (this.StateUpdates.TryGetValue(scopeKey, out string? updatedAfterClear) && updatedAfterClear is not null)
            {
                return ValueTask.FromResult(JsonSerializer.Deserialize<T>(updatedAfterClear));
            }

            return ValueTask.FromResult<T?>(default);
        }

        // Check local updates first (read-your-writes)
        if (this.StateUpdates.TryGetValue(scopeKey, out string? updated))
        {
            if (updated is null)
            {
                return ValueTask.FromResult<T?>(default);
            }

            return ValueTask.FromResult(JsonSerializer.Deserialize<T>(updated));
        }

        // Fall back to initial state passed from orchestration
        if (this._initialState.TryGetValue(scopeKey, out string? initial))
        {
            return ValueTask.FromResult(JsonSerializer.Deserialize<T>(initial));
        }

        return ValueTask.FromResult<T?>(default);
    }

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow state types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow state types.")]
    public async ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        T? value = await this.ReadStateAsync<T>(key, scopeName, cancellationToken).ConfigureAwait(false);

        if (value is not null)
        {
            return value;
        }

        // Initialize with factory value
        T initialValue = initialStateFactory();
        await this.QueueStateUpdateAsync(key, initialValue, scopeName, cancellationToken).ConfigureAwait(false);
        return initialValue;
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string scopePrefix = GetScopePrefix(scopeName);
        string normalizedScope = scopeName ?? "__default__";
        HashSet<string> keys = [];

        // If scope was cleared, only return keys from updates made after clear
        if (this.ClearedScopes.Contains(normalizedScope))
        {
            foreach (KeyValuePair<string, string?> update in this.StateUpdates)
            {
                if (update.Key.StartsWith(scopePrefix, StringComparison.Ordinal) && update.Value is not null)
                {
                    keys.Add(update.Key[scopePrefix.Length..]);
                }
            }

            return ValueTask.FromResult(keys);
        }

        // Start with keys from initial state
        foreach (string stateKey in this._initialState.Keys)
        {
            if (stateKey.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                keys.Add(stateKey[scopePrefix.Length..]);
            }
        }

        // Merge with updates
        foreach (KeyValuePair<string, string?> update in this.StateUpdates)
        {
            if (update.Key.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                string foundKey = update.Key[scopePrefix.Length..];
                if (update.Value is not null)
                {
                    keys.Add(foundKey);
                }
                else
                {
                    keys.Remove(foundKey);
                }
            }
        }

        return ValueTask.FromResult(keys);
    }

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow state types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow state types.")]
    public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string scopeKey = GetScopeKey(scopeName, key);
        this.StateUpdates[scopeKey] = value is null ? null : JsonSerializer.Serialize(value);
        return default;
    }

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        string normalizedScope = scopeName ?? "__default__";
        this.ClearedScopes.Add(normalizedScope);

        // Remove any pending updates in this scope
        string scopePrefix = GetScopePrefix(scopeName);
        List<string> keysToRemove = this.StateUpdates.Keys
            .Where(k => k.StartsWith(scopePrefix, StringComparison.Ordinal))
            .ToList();

        foreach (string key in keysToRemove)
        {
            this.StateUpdates.Remove(key);
        }

        return default;
    }

    /// <inheritdoc/>
    public IReadOnlyDictionary<string, string>? TraceContext => null;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => false;

    private static bool CanOutput(ISet<Type> outputTypes, Type messageType)
    {
        foreach (Type type in outputTypes)
        {
            if (type.IsAssignableFrom(messageType))
            {
                return true;
            }
        }

        return false;
    }

    private static string GetScopeKey(string? scopeName, string key)
        => $"{GetScopePrefix(scopeName)}{key}";

    private static string GetScopePrefix(string? scopeName)
        => scopeName is null ? "__default__:" : $"{scopeName}:";
}
