// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

/// <summary>
/// A unique identifier for a scope within an executor. If a scope name is not provided, it references the
/// default scope private to the executor. Otherwise, regardless of the executorId, it references a shared
/// scope with the specified name.
/// </summary>
/// <param name="executorId"></param>
/// <param name="scopeName"></param>
internal class ScopeId(string executorId, string? scopeName = null)
{
    public string ExecutorId { get; } = Throw.IfNullOrEmpty(executorId);
    public string? ScopeName { get; } = scopeName;

    public override string ToString()
    {
        return $"{this.ExecutorId}/{this.ScopeName ?? "default"}";
    }

    public override bool Equals(object? obj)
    {
        if (obj is ScopeId other)
        {
            if (other.ScopeName is null && this.ScopeName is null)
            {
                return this.ExecutorId == other.ExecutorId;
            }
            else if (other.ScopeName is not null && this.ScopeName is not null)
            {
                return this.ScopeName == other.ScopeName;
            }
            else
            {
                return false; // One has a scope name, the other does not.
            }
        }

        return false;
    }

    public override int GetHashCode()
    {
        if (this.ScopeName is null)
        {
            return this.ExecutorId.GetHashCode();
        }

        return this.ScopeName.GetHashCode();
    }
}
