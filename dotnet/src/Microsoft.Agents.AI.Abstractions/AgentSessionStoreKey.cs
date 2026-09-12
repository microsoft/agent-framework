// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Identifies an agent session in persistent storage.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="SessionId"/> identifies the session while <see cref="Partitions"/> contains additional
/// named dimensions that isolate sessions sharing that identifier. Every partition is part of the
/// identity and must be honored by <see cref="AgentSessionStore"/> implementations.
/// </para>
/// <para>
/// Partition names are compared using ordinal, case-sensitive comparison. Partition ordering does not
/// affect identity. Names and values cannot be empty or whitespace.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSessionStoreKey : IEquatable<AgentSessionStoreKey>
{
    private readonly int _hashCode;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSessionStoreKey"/> class.
    /// </summary>
    /// <param name="sessionId">The logical session identifier.</param>
    /// <param name="partitions">
    /// Optional named partition values. Every partition contributes to identity. The collection is copied.
    /// </param>
    public AgentSessionStoreKey(
        string sessionId,
        IReadOnlyDictionary<string, string>? partitions = null)
    {
        this.SessionId = Throw.IfNullOrWhitespace(sessionId);

        var partitionCopy = new SortedDictionary<string, string>(StringComparer.Ordinal);
        if (partitions is not null)
        {
            foreach (KeyValuePair<string, string> partition in partitions)
            {
                partitionCopy.Add(
                    Throw.IfNullOrWhitespace(partition.Key, nameof(partitions)),
                    Throw.IfNullOrWhitespace(partition.Value, nameof(partitions)));
            }
        }

        this.Partitions = new ReadOnlyDictionary<string, string>(partitionCopy);

        this._hashCode = this.ComputeHashCode();
    }

    /// <summary>
    /// Gets the logical session identifier.
    /// </summary>
    public string SessionId { get; }

    /// <summary>
    /// Gets the named partition values that form part of the session identity.
    /// </summary>
    public IReadOnlyDictionary<string, string> Partitions { get; }

    /// <summary>
    /// Returns a new key containing the specified partition.
    /// </summary>
    /// <param name="name">The partition name.</param>
    /// <param name="value">The partition value.</param>
    /// <returns>
    /// A new key with the partition added or replaced, or this instance when the partition already has
    /// the specified value.
    /// </returns>
    public AgentSessionStoreKey WithPartition(string name, string value)
    {
        name = Throw.IfNullOrWhitespace(name);
        value = Throw.IfNullOrWhitespace(value);

        if (this.Partitions.TryGetValue(name, out string? existingValue)
            && string.Equals(existingValue, value, StringComparison.Ordinal))
        {
            return this;
        }

        var partitions = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (KeyValuePair<string, string> partition in this.Partitions)
        {
            partitions.Add(partition.Key, partition.Value);
        }
        partitions[name] = value;

        return new AgentSessionStoreKey(this.SessionId, partitions);
    }

    /// <inheritdoc/>
    public bool Equals(AgentSessionStoreKey? other)
    {
        if (ReferenceEquals(this, other))
        {
            return true;
        }

        if (other is null
            || !string.Equals(this.SessionId, other.SessionId, StringComparison.Ordinal)
            || this.Partitions.Count != other.Partitions.Count)
        {
            return false;
        }

        foreach (KeyValuePair<string, string> partition in this.Partitions)
        {
            if (!other.Partitions.TryGetValue(partition.Key, out string? value)
                || !string.Equals(partition.Value, value, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as AgentSessionStoreKey);

    /// <inheritdoc/>
    public override int GetHashCode() => this._hashCode;

    private int ComputeHashCode()
    {
        unchecked
        {
            int hashCode = StringComparer.Ordinal.GetHashCode(this.SessionId);
            foreach (KeyValuePair<string, string> partition in this.Partitions)
            {
                hashCode = (hashCode * 31) + StringComparer.Ordinal.GetHashCode(partition.Key);
                hashCode = (hashCode * 31) + StringComparer.Ordinal.GetHashCode(partition.Value);
            }

            return hashCode;
        }
    }
}
