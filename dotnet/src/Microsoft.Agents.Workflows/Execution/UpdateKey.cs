// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal class UpdateKey(ScopeId scopeId, string key)
{
    public ScopeId ScopeId { get; } = Throw.IfNull(scopeId);
    public string Key { get; } = Throw.IfNullOrEmpty(key);

    public UpdateKey(string executorId, string? scopeName, string key)
        : this(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key)
    { }

    public override string ToString()
    {
        return $"{this.ScopeId}/{this.Key}";
    }

    public override bool Equals(object? obj)
    {
        if (obj is UpdateKey other)
        {
            // Unlike ScopeId, UpdateKey is equal only if both the Executor and ScopeName are the same
            return this.ScopeId.ExecutorId == other.ScopeId.ExecutorId &&
                   this.ScopeId.ScopeName == other.ScopeId.ScopeName &&
                   this.Key == other.Key;
        }

        return false;
    }

    public override int GetHashCode()
    {
        return HashCode.Combine(this.ScopeId.ExecutorId, this.ScopeId.ScopeName, this.Key);
    }
}
