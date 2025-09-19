// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

/// <summary>
/// Represents a unique key used to identify an update within a specific scope.
/// </summary>
/// <remarks>An <see cref="UpdateKey"/> is composed of a <see cref="ScopeId"/> and a key, similar
/// to <see cref="ScopeKey"/>. The difference is in how equality is determined: Unlike ScopeKey,
/// two UpdateKeys that differ only by their ScopeId's ExecutorId are considered different, because
/// updates coming from different executors need to be tracked separately, until they are marged (if
/// appropriate) and published during a step transition.</remarks>
/// <param name="scopeId"></param>
/// <param name="key"></param>
internal sealed class UpdateKey(ScopeId scopeId, string key)
{
    public ScopeId ScopeId { get; } = Throw.IfNull(scopeId);
    public string Key { get; } = Throw.IfNullOrEmpty(key);

    public UpdateKey(string executorId, string? scopeName, string key)
        : this(new ScopeId(Throw.IfNullOrEmpty(executorId), scopeName), key)
    { }

    public override string ToString() => $"{this.ScopeId}/{this.Key}";

    public bool IsMatchingScope(ScopeId scopeId, bool strict = false) => this.ScopeId == scopeId && (!strict || this.ScopeId.ExecutorId == scopeId.ExecutorId);

    public override bool Equals(object? obj)
    {
        if (obj is UpdateKey other)
        {
            // Unlike ScopeId, UpdateKey is equal only if both the Executor and ScopeName are the same
            return this.IsMatchingScope(other.ScopeId, strict: true) &&
                   this.Key == other.Key;
        }

        return false;
    }

    public override int GetHashCode() => HashCode.Combine(this.ScopeId.ExecutorId, this.ScopeId.ScopeName, this.Key);
}
