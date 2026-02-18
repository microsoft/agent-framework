// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// A workflow context for durable activity execution.
/// </summary>
/// <remarks>
/// State is passed in from the orchestration and updates are collected for return.
/// Events emitted during execution are collected and returned to the orchestration
/// as part of the activity output for streaming to callers.
/// </remarks>
[DebuggerDisplay("Executor = {_executor.Id}, StateEntries = {_initialState.Count}")]
internal sealed class DurableActivityContext : IWorkflowContext
{
    /// <summary>
    /// The default scope name used when no explicit scope is specified.
    /// Scopes partition shared state into logical namespaces so that different
    /// parts of a workflow can manage their state keys independently.
    /// </summary>
    private const string DefaultScopeName = "__default__";

    private readonly Dictionary<string, string> _initialState;
    private readonly Executor _executor;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableActivityContext"/> class.
    /// </summary>
    /// <param name="initialState">The shared state passed from the orchestration.</param>
    /// <param name="executor">The executor running in this context.</param>
    internal DurableActivityContext(Dictionary<string, string>? initialState, Executor executor)
    {
        this._executor = executor;
        this._initialState = initialState ?? [];
    }

    /// <summary>
    /// Gets the messages sent during activity execution via <see cref="SendMessageAsync"/>.
    /// </summary>
    internal List<TypedPayload> SentMessages { get; } = [];

    /// <summary>
    /// Gets the events that were added during activity execution.
    /// </summary>
    internal List<WorkflowEvent> Events { get; } = [];

    /// <summary>
    /// Gets the state updates made during activity execution.
    /// </summary>
    internal Dictionary<string, string?> StateUpdates { get; } = [];

    /// <summary>
    /// Gets the scopes that were cleared during activity execution.
    /// </summary>
    internal HashSet<string> ClearedScopes { get; } = [];

    /// <summary>
    /// Gets a value indicating whether the executor requested a workflow halt.
    /// </summary>
    internal bool HaltRequested { get; private set; }

    /// <inheritdoc/>
    public ValueTask AddEventAsync(
        WorkflowEvent workflowEvent,
        CancellationToken cancellationToken = default)
    {
        if (workflowEvent is not null)
        {
            this.Events.Add(workflowEvent);
        }

        return default;
    }

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow message types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow message types registered at startup.")]
    public ValueTask SendMessageAsync(
        object message,
        string? targetId = null,
        CancellationToken cancellationToken = default)
    {
        if (message is not null)
        {
            Type messageType = message.GetType();
            this.SentMessages.Add(new TypedPayload
            {
                Data = JsonSerializer.Serialize(message, messageType, DurableSerialization.Options),
                TypeName = messageType.AssemblyQualifiedName
            });
        }

        return default;
    }

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(
        object output,
        CancellationToken cancellationToken = default)
    {
        if (output is not null)
        {
            Type outputType = output.GetType();
            if (!this._executor.CanOutput(outputType))
            {
                throw new InvalidOperationException(
                    $"Cannot output object of type {outputType.Name}. " +
                    $"Expecting one of [{string.Join(", ", this._executor.OutputTypes)}].");
            }

            this.Events.Add(new WorkflowOutputEvent(output, this._executor.Id));
        }

        return default;
    }

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync()
    {
        this.HaltRequested = true;
        this.Events.Add(new DurableHaltRequestedEvent(this._executor.Id));
        return default;
    }

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(
        string key,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(key);

        string scopeKey = GetScopeKey(scopeName, key);
        string normalizedScope = scopeName ?? DefaultScopeName;
        bool scopeCleared = this.ClearedScopes.Contains(normalizedScope);

        // Local updates take priority over initial state.
        if (this.StateUpdates.TryGetValue(scopeKey, out string? updated))
        {
            return DeserializeStateAsync<T>(updated);
        }

        // If scope was cleared, ignore initial state
        if (scopeCleared)
        {
            return ValueTask.FromResult<T?>(default);
        }

        // Fall back to initial state passed from orchestration
        if (this._initialState.TryGetValue(scopeKey, out string? initial))
        {
            return DeserializeStateAsync<T>(initial);
        }

        return ValueTask.FromResult<T?>(default);
    }

    /// <inheritdoc/>
    public async ValueTask<T> ReadOrInitStateAsync<T>(
        string key,
        Func<T> initialStateFactory,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(key);
        ArgumentNullException.ThrowIfNull(initialStateFactory);

        // Cannot rely on `value is not null` because T? on an unconstrained generic
        // parameter does not become Nullable<T> for value types — the null check is
        // always true for types like int. Instead, check key existence directly.
        if (this.HasStateKey(key, scopeName))
        {
            T? value = await this.ReadStateAsync<T>(key, scopeName, cancellationToken).ConfigureAwait(false);
            if (value is not null)
            {
                return value;
            }
        }

        T initialValue = initialStateFactory();
        await this.QueueStateUpdateAsync(key, initialValue, scopeName, cancellationToken).ConfigureAwait(false);
        return initialValue;
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        string scopePrefix = GetScopePrefix(scopeName);
        int scopePrefixLength = scopePrefix.Length;
        HashSet<string> keys = new(StringComparer.Ordinal);

        bool scopeCleared = scopeName is null
            ? this.ClearedScopes.Contains(DefaultScopeName)
            : this.ClearedScopes.Contains(scopeName);

        // Start with keys from initial state (skip if scope was cleared)
        if (!scopeCleared)
        {
            foreach (string stateKey in this._initialState.Keys)
            {
                if (stateKey.StartsWith(scopePrefix, StringComparison.Ordinal))
                {
                    keys.Add(stateKey[scopePrefixLength..]);
                }
            }
        }

        // Merge local updates: add if non-null, remove if null (deleted)
        foreach (KeyValuePair<string, string?> update in this.StateUpdates)
        {
            if (!update.Key.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                continue;
            }

            string key = update.Key[scopePrefixLength..];
            if (update.Value is not null)
            {
                keys.Add(key);
            }
            else
            {
                keys.Remove(key);
            }
        }

        return ValueTask.FromResult(keys);
    }

    /// <inheritdoc/>
    public ValueTask QueueStateUpdateAsync<T>(
        string key,
        T? value,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(key);

        string scopeKey = GetScopeKey(scopeName, key);
        this.StateUpdates[scopeKey] = value is null ? null : SerializeState(value);
        return default;
    }

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        this.ClearedScopes.Add(scopeName ?? DefaultScopeName);

        // Remove any pending updates in this scope (snapshot keys to allow removal during iteration)
        string scopePrefix = GetScopePrefix(scopeName);
        foreach (string key in this.StateUpdates.Keys.ToArray())
        {
            if (key.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                this.StateUpdates.Remove(key);
            }
        }

        return default;
    }

    /// <inheritdoc/>
    public IReadOnlyDictionary<string, string>? TraceContext => null;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => false;

    private static string GetScopeKey(string? scopeName, string key)
        => $"{GetScopePrefix(scopeName)}{key}";

    /// <summary>
    /// Checks whether the given key exists in local updates or initial state,
    /// respecting cleared scopes.
    /// </summary>
    private bool HasStateKey(string key, string? scopeName)
    {
        string scopeKey = GetScopeKey(scopeName, key);

        if (this.StateUpdates.TryGetValue(scopeKey, out string? updated))
        {
            return updated is not null;
        }

        string normalizedScope = scopeName ?? DefaultScopeName;
        if (this.ClearedScopes.Contains(normalizedScope))
        {
            return false;
        }

        return this._initialState.ContainsKey(scopeKey);
    }

    /// <summary>
    /// Returns the key prefix for the given scope. Scopes partition shared state
    /// into logical namespaces, allowing different workflow executors to manage
    /// their state keys independently. When no scope is specified, the
    /// <see cref="DefaultScopeName"/> is used.
    /// </summary>
    private static string GetScopePrefix(string? scopeName)
        => scopeName is null ? $"{DefaultScopeName}:" : $"{scopeName}:";

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow state types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow state types.")]
    private static string SerializeState<T>(T value)
        => JsonSerializer.Serialize(value, DurableSerialization.Options);

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow state types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow state types.")]
    private static ValueTask<T?> DeserializeStateAsync<T>(string? json)
    {
        if (json is null)
        {
            return ValueTask.FromResult<T?>(default);
        }

        return ValueTask.FromResult(JsonSerializer.Deserialize<T>(json, DurableSerialization.Options));
    }
}
