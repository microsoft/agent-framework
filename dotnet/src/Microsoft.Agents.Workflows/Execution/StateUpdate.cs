// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class StateUpdate
{
    public string Key { get; }
    public object? Value { get; }
    public bool IsDelete { get; }

    private StateUpdate(string key, object? value, bool isDelete = false)
    {
        this.Key = Throw.IfNullOrEmpty(key);
        this.Value = value;
        this.IsDelete = isDelete;
    }

    public static StateUpdate Update<T>(string key, T? value) => new(key, value, value is null);

    public static StateUpdate Delete(string key)
    {
        Throw.IfNullOrEmpty(key);
        return new StateUpdate(key, null, isDelete: true);
    }
}
