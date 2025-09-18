// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a unique key within a specific scope, combining a scope identifier and a key string.
/// </summary>
public sealed class ScopeKey
{
    /// <summary>
    /// The identifier for the scope associated with this key.
    /// </summary>
    public ScopeId ScopeId { get; }

    /// <summary>
    /// The unique key within the specified scope.
    /// </summary>
    public string Key { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="ScopeKey"/> class.
    /// </summary>
    /// <param name="executorId">The unique identifier for the executor.</param>
    /// <param name="scopeName">The name of the scope, if any.</param>
    /// <param name="key">The unique key within the specified scope.</param>
    public ScopeKey(string executorId, string? scopeName, string key)
        : this(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key)
    { }

    /// <summary>
    /// Iniitalizes a new instance of the <see cref="ScopeKey"/> class.
    /// </summary>
    /// <param name="scopeId">The <see cref="ScopeId"/> associated with this key.</param>
    /// <param name="key">The unique key within the specified scope.</param>
    [JsonConstructor]
    public ScopeKey(ScopeId scopeId, string key)
    {
        this.ScopeId = Throw.IfNull(scopeId);
        this.Key = Throw.IfNullOrEmpty(key);
    }

    /// <inheritdoc/>
    public override string ToString()
    {
        return $"{this.ScopeId}/{this.Key}";
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        if (obj is ScopeKey other)
        {
            // Unlike ScopeId, ScopeKey is equal only if both the Executor and ScopeName are the same
            return this.ScopeId.Equals(other.ScopeId) && this.Key == other.Key;
        }
        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        return HashCode.Combine(this.ScopeId, this.Key);
    }
}
