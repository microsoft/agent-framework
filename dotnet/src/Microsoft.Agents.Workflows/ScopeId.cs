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
public sealed class ScopeId(string executorId, string? scopeName = null)
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
    public override string ToString() => $"{this.ExecutorId}/{this.ScopeName ?? "default"}";

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        if (obj is ScopeId other)
        {
            if (other.ScopeName is null && this.ScopeName is null)
            {
                return this.ExecutorId == other.ExecutorId;
            }

            if (other.ScopeName is not null && this.ScopeName is not null)
            {
                return this.ScopeName == other.ScopeName;
            }

            // One has a scope name, the other does not.
        }

        return false;
    }

    /// <inheritdoc/>
    public static bool operator ==(ScopeId? left, ScopeId? right)
    {
        if (left is null && right is null)
        {
            return true;
        }

        if (right is null)
        {
            return false;
        }

        // The inversion here is necessary because the null analysis is incapable of proving to itself
        // that left cannot be null here: If it was, either right is null, and we returned true, or right
        // is not null, and we returned false.
        return right.Equals(left);
    }

    /// <inheritdoc/>
    public static bool operator !=(ScopeId? left, ScopeId? right) => !(left == right);

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
