﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal class StateScope
{
    private readonly Dictionary<string, object> _stateData = new();
    public ScopeId ScopeId { get; }

    public StateScope(ScopeId scopeId)
    {
        this.ScopeId = Throw.IfNull(scopeId);
    }

    public StateScope(string executor, string? scopeName = null) : this(new ScopeId(Throw.IfNullOrEmpty(executor), scopeName))
    {
    }

    public ValueTask<HashSet<string>> ReadKeysAsync()
    {
        HashSet<string> keys = new(this._stateData.Keys, this._stateData.Comparer);

        return new(keys);
    }

    public ValueTask<T?> ReadStateAsync<T>(string key)
    {
        Throw.IfNullOrEmpty(key);
        if (this._stateData.TryGetValue(key, out object? value) && value is T typedValue)
        {
            return new ValueTask<T?>(typedValue);
        }

        return new ValueTask<T?>((T?)default);
    }

    public ValueTask WriteStateAsync(Dictionary<string, List<StateUpdate>> updates)
    {
        Throw.IfNull(updates);

        foreach (string key in updates.Keys)
        {
            if (updates == null || updates[key].Count == 0)
            {
                continue;
            }

            if (updates[key].Count > 1)
            {
                throw new InvalidOperationException($"Expected exactly one update for key '{key}'.");
            }

            StateUpdate update = updates[key][0];
            if (update.IsDelete)
            {
                this._stateData.Remove(key);
            }
            else
            {
                this._stateData[key] = update.Value!;
            }
        }

        return default;
    }

    public IEnumerable<KeyValuePair<string, ExportedState>> ExportStates()
    {
        return this._stateData.Keys.Select(WrapStates);

        KeyValuePair<string, ExportedState> WrapStates(string key)
        {
            return new(key, new(this._stateData[key]));
        }
    }

    public void ImportState(string key, ExportedState state)
    {
        Throw.IfNullOrEmpty(key);
        Throw.IfNull(state);

        this._stateData[key] = state.Value;
    }
}
