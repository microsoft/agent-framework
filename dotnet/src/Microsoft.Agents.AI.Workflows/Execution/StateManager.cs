// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class StateManager
{
    private readonly Dictionary<ScopeId, StateScope> _scopes = [];
    private readonly Dictionary<UpdateKey, StateUpdate> _queuedUpdates = [];

    // InProcessRunner.RunSuperstepAsync delivers a superstep's messages to every receiving executor
    // concurrently (one DeliverMessagesAsync task per receiver, awaited with Task.WhenAll), and each
    // of those executors reaches this instance through its bound IWorkflowContext. Two executors
    // queueing a state update in the same superstep therefore write _queuedUpdates from two threads,
    // and Dictionary<,> is not safe for that: it throws
    // "Operations that change non-concurrent collections must have exclusive access" or, worse,
    // silently corrupts. Every access to the two dictionaries takes this lock; the scope contents
    // themselves are only written by PublishUpdatesAsync and ImportStateAsync, which run between
    // supersteps, so the await-ing reads of a StateScope stay outside the lock.
    private readonly object _syncRoot = new();

    private StateScope GetOrCreateScope(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        lock (this._syncRoot)
        {
            if (!this._scopes.TryGetValue(scopeId, out StateScope? scope))
            {
                scope = new StateScope(scopeId);
                this._scopes[scopeId] = scope;
            }

            return scope;
        }
    }

    private bool TryGetScope(ScopeId scopeId, out StateScope? scope)
    {
        lock (this._syncRoot)
        {
            return this._scopes.TryGetValue(scopeId, out scope);
        }
    }

    /// <summary>
    /// Snapshot of the queued updates for a scope. Materialized under the lock so the caller can
    /// enumerate it while other executors keep queueing.
    /// </summary>
    private List<KeyValuePair<UpdateKey, StateUpdate>> GetUpdatesForScopeStrict(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        lock (this._syncRoot)
        {
            return this._queuedUpdates.Where(kvp => kvp.Key.IsMatchingScope(scopeId, strict: true)).ToList();
        }
    }

    public ValueTask ClearStateAsync(string executorId, string? scopeName)
        => this.ClearStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName));

    public async ValueTask ClearStateAsync(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        if (this.TryGetScope(scopeId, out StateScope? scope))
        {
            HashSet<string> keysToDelete = await scope!.ReadKeysAsync().ConfigureAwait(false);

            lock (this._syncRoot)
            {
                foreach (KeyValuePair<UpdateKey, StateUpdate> queued in this._queuedUpdates.Where(kvp => kvp.Key.IsMatchingScope(scopeId, strict: true)).ToList())
                {
                    StateUpdate update = queued.Value;
                    if (!update.IsDelete)
                    {
                        this._queuedUpdates[queued.Key] = StateUpdate.Delete(update.Key);
                    }

                    keysToDelete.Remove(update.Key);
                }

                foreach (string key in keysToDelete)
                {
                    UpdateKey updateKey = new(scopeId, key);
                    this._queuedUpdates[updateKey] = StateUpdate.Delete(key);
                }
            }
        }
    }

    private HashSet<string> ApplyUnpublishedUpdates(ScopeId scopeId, HashSet<string> keys)
    {
        // Apply any queued updates for this scope
        foreach (KeyValuePair<UpdateKey, StateUpdate> queued in this.GetUpdatesForScopeStrict(scopeId))
        {
            StateUpdate update = queued.Value;
            if (update.IsDelete)
            {
                keys.Remove(update.Key);
            }
            else
            {
                // Add is idempotent on Sets
                keys.Add(update.Key);
            }
        }

        return keys;
    }

    public ValueTask<HashSet<string>> ReadKeysAsync(string executorId, string? scopeName = null)
        => this.ReadKeysAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName));

    public async ValueTask<HashSet<string>> ReadKeysAsync(ScopeId scopeId)
    {
        StateScope scope = this.GetOrCreateScope(scopeId);
        HashSet<string> keys = await scope.ReadKeysAsync().ConfigureAwait(false);
        return this.ApplyUnpublishedUpdates(scopeId, keys);
    }

    public ValueTask<T?> ReadStateAsync<T>(string executorId, string? scopeName, string key)
        => this.ReadStateAsync<T>(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key);

    public ValueTask<T> ReadOrInitStateAsync<T>(string executorId, string? scopeName, string key, Func<T> initialStateFactory)
        => this.ReadOrInitStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key, initialStateFactory);

    private async ValueTask<T?> ReadValueOrDefaultAsync<T>(ScopeId scopeId, string key, Func<T>? defaultValueFactory = default, bool initOnDefault = false)
    {
        if (typeof(T) == typeof(object))
        {
            // Reading as object will break across serialize/deserialize boundaries, e.g. checkpointing, distributed runtime, etc.
            throw new NotSupportedException("Reading state as 'object' is not supported. Use 'PortableValue' instead for variants.");
        }

        Throw.IfNullOrEmpty(key);

        UpdateKey stateKey = new(scopeId, key);

        T? result = defaultValueFactory != null ? defaultValueFactory() : default;
        bool needsInit = false;

        // If there is executor-local state (from a queued update), read it first
        StateUpdate? update;
        lock (this._syncRoot)
        {
            this._queuedUpdates.TryGetValue(stateKey, out update);
        }

        if (update is not null)
        {
            // What's the right thing to do when we have a state object, but it is the wrong type?
            if (update.IsDelete || update.Value is null)
            {
                needsInit = initOnDefault;
            }
            else if (update.Value is T typed)
            {
                result = typed;
            }
            else if (typeof(T) == typeof(PortableValue) && update.Value != null)
            {
                result = (T)(object)new PortableValue(update.Value);
            }
            else
            {
                throw new InvalidOperationException($"State for key '{key}' in scope '{scopeId}' is not of type '{typeof(T).Name}'.");
            }
        }
        else
        {
            StateScope scope = this.GetOrCreateScope(scopeId);
            if (scope.ContainsKey(key))
            {
                result = await scope.ReadStateAsync<T>(key).ConfigureAwait(false);
            }
            else if (initOnDefault)
            {
                needsInit = true;
            }
        }

        if (needsInit)
        {
            if (defaultValueFactory is null)
            {
                throw new ArgumentNullException(nameof(defaultValueFactory), "Default value must be provided when initializing state.");
            }

            Debug.Assert(initOnDefault);

            await this.WriteStateAsync(scopeId, key, defaultValueFactory()).ConfigureAwait(false);
        }

        return result;
    }

    public ValueTask<T?> ReadStateAsync<T>(ScopeId scopeId, string key)
        => this.ReadValueOrDefaultAsync<T>(scopeId, key);

    public async ValueTask<T> ReadOrInitStateAsync<T>(ScopeId scopeId, string key, Func<T> initialStateFactory)
    {
        return (await this.ReadValueOrDefaultAsync(scopeId, key, initialStateFactory, initOnDefault: true)
                          .ConfigureAwait(false))!;
    }

    public ValueTask WriteStateAsync<T>(string executorId, string? scopeName, string key, T value)
        => this.WriteStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key, value);

    public ValueTask WriteStateAsync<T>(ScopeId scopeId, string key, T value)
    {
        Throw.IfNullOrEmpty(key);

        UpdateKey stateKey = new(scopeId, key);
        lock (this._syncRoot)
        {
            this._queuedUpdates[stateKey] = StateUpdate.Update(key, value);
        }

        return default;
    }

    public ValueTask ClearStateAsync(string executorId, string? scopeName, string key)
        => this.ClearStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key);

    public ValueTask ClearStateAsync(ScopeId scopeId, string key)
    {
        Throw.IfNullOrEmpty(key);
        UpdateKey stateKey = new(scopeId, key);
        lock (this._syncRoot)
        {
            this._queuedUpdates[stateKey] = StateUpdate.Delete(key);
        }

        return default;
    }

    public async ValueTask PublishUpdatesAsync(IStepTracer? tracer)
    {
        // Take the queued updates out under the lock, then publish the snapshot without holding it:
        // StateScope.WriteStateAsync awaits, and a lock cannot span an await.
        List<KeyValuePair<UpdateKey, StateUpdate>> queued;
        lock (this._syncRoot)
        {
            queued = this._queuedUpdates.ToList();
            this._queuedUpdates.Clear();
        }

        Dictionary<ScopeId, Dictionary<string, List<StateUpdate>>> updatesByScope = [];

        // Aggregate the updates for each scope
        foreach (KeyValuePair<UpdateKey, StateUpdate> entry in queued)
        {
            UpdateKey key = entry.Key;
            if (!updatesByScope.TryGetValue(key.ScopeId, out Dictionary<string, List<StateUpdate>>? scopeUpdates))
            {
                updatesByScope[key.ScopeId] = scopeUpdates = [];
            }

            if (!scopeUpdates.TryGetValue(key.Key, out List<StateUpdate>? stateUpdates))
            {
                scopeUpdates[key.Key] = stateUpdates = [];
            }

            stateUpdates.Add(entry.Value);
        }

        if (tracer is not null && (updatesByScope.Count > 0))
        {
            tracer.TraceStatePublished();
        }

        foreach (ScopeId scope in updatesByScope.Keys)
        {
            StateScope stateScope = this.GetOrCreateScope(scope);
            await stateScope.WriteStateAsync(updatesByScope[scope]).ConfigureAwait(false);
        }
    }

    private static IEnumerable<KeyValuePair<ScopeKey, PortableValue>> ExportScope(StateScope scope)
    {
        foreach (KeyValuePair<string, PortableValue> state in scope.ExportStates())
        {
            yield return new(new ScopeKey(scope.ScopeId, state.Key), state.Value);
        }
    }

    internal ValueTask<Dictionary<ScopeKey, PortableValue>> ExportStateAsync()
    {
        lock (this._syncRoot)
        {
            if (this._queuedUpdates.Count != 0)
            {
                throw new InvalidOperationException("Cannot export state while there are queued updates. Call PublishUpdatesAsync() first.");
            }

            return new(this._scopes.Values.SelectMany(ExportScope).ToDictionary(kvp => kvp.Key, kvp => kvp.Value));
        }
    }

    internal ValueTask ImportStateAsync(Checkpoint checkpoint)
    {
        lock (this._syncRoot)
        {
            // TODO: Should this be a warning instead?
            if (this._queuedUpdates.Count != 0)
            {
                throw new InvalidOperationException("Cannot import state while there are queued updates. Call PublishUpdatesAsync() first.");
            }

            this._queuedUpdates.Clear();
            this._scopes.Clear();

            Dictionary<ScopeKey, PortableValue> importedState = checkpoint.StateData;

            foreach (ScopeKey scopeKey in importedState.Keys)
            {
                if (!this._scopes.TryGetValue(scopeKey.ScopeId, out StateScope? scope))
                {
                    scope = new StateScope(scopeKey.ScopeId);
                    this._scopes[scopeKey.ScopeId] = scope;
                }

                scope.ImportState(scopeKey.Key, importedState[scopeKey]);
            }
        }

        return default;
    }
}
