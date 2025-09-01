// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
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
            if (updates[key].Count == 0)
            {
                continue;
            }

            if (updates[key].Count > 1)
            {
                throw new InvalidOperationException($"Expected exactly one update for key '{key}'.");
            }

            StateUpdate upadte = updates[key][0];
            if (upadte.IsDelete)
            {
                this._stateData.Remove(key);
            }
            else
            {
                this._stateData[key] = upadte.Value!;
            }
        }

        return default;
    }
}
