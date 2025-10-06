// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A unique identifier of an <see cref="Edge"/> within a <see cref="Workflow"/>.
/// </summary>
public readonly struct EdgeId : IEquatable<EdgeId>
{
    [JsonConstructor]
    internal EdgeId(int edgeIndex)
    {
        this.EdgeIndex = edgeIndex;
    }

    internal int EdgeIndex { get; }

    /// <inheritdoc />
    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is EdgeId edgeId)
        {
            return this.EdgeIndex == edgeId.EdgeIndex;
        }

        if (obj is int edgeIndex)
        {
            return this.EdgeIndex == edgeIndex;
        }

        return false;
    }

    /// <inheritdoc />
    public bool Equals(EdgeId other)
    {
        return this.EdgeIndex == other.EdgeIndex;
    }

    /// <inheritdoc />
    public override int GetHashCode()
    {
        return this.EdgeIndex.GetHashCode();
    }

    /// <inheritdoc />
    public static bool operator ==(EdgeId left, EdgeId right) => left.Equals(right);

    /// <inheritdoc />
    public static bool operator !=(EdgeId left, EdgeId right) => !left.Equals(right);

    /// <inheritdoc />
    public override string ToString() => this.EdgeIndex.ToString();
}
