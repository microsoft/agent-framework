// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A unique identifier for a scope within an executor. If a scope name is not provided, it references the
/// default scope private to the executor. Otherwise, regardless of the executorId, it references a shared
/// scope with the specified name.
/// </summary>
/// <param name="executorId">The unique identifier for the executor associated with this ScopeId.</param>
/// <param name="scopeName">The name of the scope, if any. If <see langword="null"/>, this ScopeId
/// corresponds to the Executor's private scope.</param>
public class ScopeId(string executorId, string? scopeName = null)
{
    /// <summary>
    /// Gets the unique identifier of the executor.
    /// </summary>
    public string ExecutorId { get; } = Throw.IfNullOrEmpty(executorId);

    /// <summary>
    /// Gets the name of the current scope, if any.
    /// </summary>
    public string? ScopeName { get; } = scopeName;

    /// <inheritdoc/>
    public override string ToString()
    {
        return $"{this.ExecutorId}/{this.ScopeName ?? "default"}";
    }

    /// <inheritdoc/>
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

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.ScopeName is null)
        {
            return this.ExecutorId.GetHashCode();
        }

        return this.ScopeName.GetHashCode();
    }
}
