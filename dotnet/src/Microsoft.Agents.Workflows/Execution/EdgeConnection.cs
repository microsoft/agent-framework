// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

/// <summary>
/// A representation for the connection structure of an edge of any multiplicity, defined by an ordered list
/// of sources and sinks connected by this edge. Can also function as a unique identifier for the edge.
/// </summary>
/// <remarks>
/// Ordering is relevant because in at least one case, the order of sinks is significant for the execution of
/// the edge: <see cref="FanOutEdgeData"/>.
/// </remarks>
public sealed class EdgeConnection : IEquatable<EdgeConnection>
{
    /// <summary>
    /// Create an <see cref="EdgeConnection"/> instance with the specified source and sink IDs.
    /// </summary>
    /// <param name="sourceIds">An ordered list of unique identifiers of the sources connected by this edge.</param>
    /// <param name="sinkIds">An ordered list of unique identifiers of the sinks connected by this edge.</param>
    public EdgeConnection(List<string> sourceIds, List<string> sinkIds)
    {
        this.SourceIds = Throw.IfNull(sourceIds);
        this.SinkIds = Throw.IfNull(sinkIds);
    }

    /// <summary>
    /// Creates a new <see cref="EdgeConnection"/> instance with the specified source and sink IDs, ensuring that all
    /// IDs are unique.
    /// </summary>
    /// <param name="sourceIds">A list of source IDs. Each ID must be unique within the list.</param>
    /// <param name="sinkIds">A list of sink IDs. Each ID must be unique within the list.</param>
    /// <returns>An <see cref="EdgeConnection"/> instance containing the specified source and sink IDs.</returns>
    /// <exception cref="ArgumentNullException">Throw if <paramref name="sourceIds"/> or <paramref name="sinkIds"/>
    /// is <see langword="null"/></exception>
    /// <exception cref="ArgumentException">Thrown if <paramref name="sourceIds"/> or <paramref name="sinkIds"/>
    /// contains duplicate values.</exception>
    public static EdgeConnection CreateChecked(List<string> sourceIds, List<string> sinkIds)
    {
        HashSet<string> sourceSet = new(Throw.IfNull(sourceIds));
        HashSet<string> sinkSet = new(Throw.IfNull(sinkIds));

        if (sourceSet.Count != sourceIds.Count)
        {
            throw new ArgumentException("Source IDs must be unique.", nameof(sourceIds));
        }

        if (sinkSet.Count != sinkIds.Count)
        {
            throw new ArgumentException("Sink IDs must be unique.", nameof(sinkIds));
        }

        return new EdgeConnection(sourceIds, sinkIds);
    }

    /// <inheritdoc />
    public bool Equals(EdgeConnection? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        return this.SourceIds.SequenceEqual(other.SourceIds) &&
               this.SinkIds.SequenceEqual(other.SinkIds);
    }

    /// <inheritdoc />
    public override bool Equals(object? obj)
    {
        return this.Equals(obj as EdgeConnection);
    }

    /// <inheritdoc />
    public override int GetHashCode()
    {
        return HashCode.Combine(
            this.SourceIds.Count,
            this.SinkIds.Count,
            this.SourceIds.Aggregate(0, (hash, id) => HashCode.Combine(hash, id.GetHashCode())),
            this.SinkIds.Aggregate(0, (hash, id) => HashCode.Combine(hash, id.GetHashCode()))
        );
    }

    /// <inheritdoc />
    public static bool operator ==(EdgeConnection? left, EdgeConnection? right)
    {
        if (left is null)
        {
            return right is null;
        }

        return left.Equals(right);
    }

    /// <inheritdoc />
    public static bool operator !=(EdgeConnection? left, EdgeConnection? right) => !(left == right);

    /// <summary>
    /// The unique identifiers of the sources connected by this edge.
    /// </summary>
    public List<string> SourceIds { get; }

    /// <summary>
    /// The unique identifiers of the sinks connected by this edge.
    /// </summary>
    public List<string> SinkIds { get; }
}
