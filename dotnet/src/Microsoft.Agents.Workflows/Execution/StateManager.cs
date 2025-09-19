// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class StateManager
{
    private readonly Dictionary<ScopeId, StateScope> _scopes = [];
    private readonly Dictionary<UpdateKey, StateUpdate> _queuedUpdates = [];

    private StateScope GetOrCreateScope(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        if (!this._scopes.TryGetValue(scopeId, out StateScope? scope))
        {
            scope = new StateScope(scopeId);
            this._scopes[scopeId] = scope;
        }

        return scope;
    }

    private IEnumerable<UpdateKey> GetUpdatesForScopeStrict(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        return this._queuedUpdates.Keys.Where(key => key.IsMatchingScope(scopeId, strict: true));
    }

    public ValueTask ClearStateAsync(string executorId, string? scopeName)
        => this.ClearStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName));

    public async ValueTask ClearStateAsync(ScopeId scopeId)
    {
        Throw.IfNull(scopeId);

        if (this._scopes.TryGetValue(scopeId, out StateScope? scope))
        {
            HashSet<string> keysToDelete = await scope.ReadKeysAsync().ConfigureAwait(false);

            foreach (UpdateKey updateKey in this.GetUpdatesForScopeStrict(scopeId))
            {
                StateUpdate update = this._queuedUpdates[updateKey];
                if (!update.IsDelete)
                {
                    this._queuedUpdates[updateKey] = StateUpdate.Delete(update.Key);
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

    private HashSet<string> ApplyUnpublishedUpdates(ScopeId scopeId, HashSet<string> keys)
    {
        // Apply any queued updates for this scope
        foreach (UpdateKey key in this.GetUpdatesForScopeStrict(scopeId))
        {
            StateUpdate update = this._queuedUpdates[key];
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

    public ValueTask<T?> ReadStateAsync<T>(ScopeId scopeId, string key)
    {
        Throw.IfNullOrEmpty(key);

        UpdateKey stateKey = new(scopeId, key);

        // If there is executor-local state (from a queued update), read it first
        if (this._queuedUpdates.TryGetValue(stateKey, out StateUpdate? result))
        {
            // What's the right thing to do when we have a state object, but it is the wrong type?
            if (result.IsDelete)
            {
                return new((T?)default);
            }

            if (result.Value is T)
            {
                return new((T?)result.Value);
            }

            throw new InvalidOperationException($"State for key '{key}' in scope '{scopeId}' is not of type '{typeof(T).Name}'.");
        }

        StateScope scope = this.GetOrCreateScope(scopeId);
        return scope.ReadStateAsync<T>(key);
    }

    public ValueTask WriteStateAsync<T>(string executorId, string? scopeName, string key, T value)
        => this.WriteStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key, value);

    public ValueTask WriteStateAsync<T>(ScopeId scopeId, string key, T value)
    {
        Throw.IfNullOrEmpty(key);

        UpdateKey stateKey = new(scopeId, key);
        this._queuedUpdates[stateKey] = StateUpdate.Update(key, value);

        return default;
    }

    public ValueTask ClearStateAsync(string executorId, string? scopeName, string key)
        => this.ClearStateAsync(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key);

    public ValueTask ClearStateAsync(ScopeId scopeId, string key)
    {
        Throw.IfNullOrEmpty(key);
        UpdateKey stateKey = new(scopeId, key);
        this._queuedUpdates[stateKey] = StateUpdate.Delete(key);
        return default;
    }

    public async ValueTask PublishUpdatesAsync(IStepTracer? tracer)
    {
        Dictionary<ScopeId, Dictionary<string, List<StateUpdate>>> updatesByScope = [];

        // Aggregate the updates for each scope
        foreach (UpdateKey key in this._queuedUpdates.Keys)
        {
            if (!updatesByScope.TryGetValue(key.ScopeId, out Dictionary<string, List<StateUpdate>>? scopeUpdates))
            {
                updatesByScope[key.ScopeId] = scopeUpdates = [];
            }

            if (!scopeUpdates.TryGetValue(key.Key, out List<StateUpdate>? stateUpdates))
            {
                scopeUpdates[key.Key] = stateUpdates = [];
            }

            stateUpdates.Add(this._queuedUpdates[key]);
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

        this._queuedUpdates.Clear();
    }

    private static IEnumerable<KeyValuePair<ScopeKey, PortableValue>> ExportScope(StateScope scope)
    {
        foreach (KeyValuePair<string, PortableValue> state in scope.ExportStates())
        {
            yield return new(new ScopeKey(scope.ScopeId, state.Key), state.Value);
        }
    }

    internal async ValueTask<Dictionary<ScopeKey, PortableValue>> ExportStateAsync()
    {
        if (this._queuedUpdates.Count != 0)
        {
            throw new InvalidOperationException("Cannot export state while there are queued updates. Call PublishUpdatesAsync() first.");
        }

        return this._scopes.Values.SelectMany(ExportScope).ToDictionary(kvp => kvp.Key, kvp => kvp.Value);
    }

    internal ValueTask ImportStateAsync(Checkpoint checkpoint)
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
            StateScope scope = this.GetOrCreateScope(scopeKey.ScopeId);
            scope.ImportState(scopeKey.Key, importedState[scopeKey]);
        }

        return default;
    }
}
