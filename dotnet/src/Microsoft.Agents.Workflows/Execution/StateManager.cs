// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal class StateManager
{
    private readonly Dictionary<ScopeId, StateScope> _scopes = new();
    private readonly Dictionary<UpdateKey, StateUpdate> _queuedUpdates = new();

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
                return new ValueTask<T?>((T?)default);
            }

            if (result.Value is T)
            {
                return new ValueTask<T?>((T?)result.Value);
            }

            throw new InvalidOperationException($"State for key '{key}' in scope '{scopeId}' is not of type '{typeof(T).Name}'.");
        }

        StateScope scope = this.GetOrCreateScope(scopeId);
        return scope.ReadStateAsync<T>(key);
    }

    public ValueTask WriteStateAsync<T>(string executorId, string? scopeName, string key, T? value)
        => this.WriteStateAsync<T>(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key, value);

    public ValueTask WriteStateAsync<T>(ScopeId scopeId, string key, T? value)
    {
        Throw.IfNullOrEmpty(key);

        UpdateKey stateKey = new(scopeId, key);
        StateUpdate update = value == null ? StateUpdate.Delete(key) : StateUpdate.Update(key, value);
        this._queuedUpdates[stateKey] = update;

        return default;
    }

    public async ValueTask PublishUpdatesAsync()
    {
        Dictionary<ScopeId, Dictionary<string, List<StateUpdate>>> updatesByScope = new();

        // Aggregate the updates for each scope
        foreach (UpdateKey key in this._queuedUpdates.Keys)
        {
            if (!updatesByScope.TryGetValue(key.ScopeId, out Dictionary<string, List<StateUpdate>>? scopeUpdates))
            {
                updatesByScope[key.ScopeId] = scopeUpdates = new();
            }

            if (!scopeUpdates.TryGetValue(key.Key, out List<StateUpdate>? stateUpdates))
            {
                scopeUpdates[key.Key] = stateUpdates = new();
            }

            stateUpdates.Add(this._queuedUpdates[key]);
        }

        foreach (ScopeId scope in updatesByScope.Keys)
        {
            StateScope stateScope = this.GetOrCreateScope(scope);
            await stateScope.WriteStateAsync(updatesByScope[scope]).ConfigureAwait(false);
        }
    }
}
