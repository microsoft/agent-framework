// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

using PartitionerT = System.Func<object?, int, System.Collections.Generic.IEnumerable<int>>;
using PredicateT = System.Func<object?, bool>;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Represents a directed edge between two nodes, optionally associated with a condition that determines whether the
/// edge is active.
/// </summary>
/// <param name="SourceId">The id of the source executor node.</param>
/// <param name="SinkId">The id of the target executor node.</param>
/// <param name="Condition">A predicate determining whether the edge is active for a given message.</param>
public record DirectEdgeData(
    string SourceId,
    string SinkId,
    PredicateT? Condition = null)
{
    /// <summary>
    /// Converts a <see cref="DirectEdgeData"/> instance to an <see cref="Edge"/>.
    /// </summary>
    /// <param name="data">The <see cref="DirectEdgeData"/> to convert t.</param>
    public static implicit operator Edge(DirectEdgeData data)
    {
        return new Edge(Throw.IfNull(data));
    }
}

/// <summary>
/// Represents a connection from a single node to a set of nodes, optionally associated with a paritition selector
/// function which maps incoming messages to a subset of the target set.
/// </summary>
/// <param name="SourceId">The id of the source executor node.</param>
/// <param name="SinkIds">A list of ids of the target executor nodes.</param>
/// <param name="Partitioner">A function that maps an incoming message to a subset of the target executor nodes.</param>
public record FanOutEdgeData(
    string SourceId,
    List<string> SinkIds,
    PartitionerT? Partitioner = null)
{
    /// <summary>
    /// Converts a <see cref="FanOutEdgeData"/> instance to an <see cref="Edge"/>.
    /// </summary>
    /// <param name="data">The <see cref="FanOutEdgeData"/> to convert.</param>
    public static implicit operator Edge(FanOutEdgeData data)
    {
        return new Edge(data);
    }
}

/// <summary>
/// Specifies the condition under which a fan-in operation is triggered in a workflow.
/// Use <see cref="FanInTrigger.WhenAll"/> to trigger the operation when all incoming edges have data, or
/// <see cref="FanInTrigger.WhenAny"/> to trigger when any incoming edge has data.
/// </summary>
public enum FanInTrigger
{
    /// <summary>
    /// Trigger when all incoming edges have data.
    /// </summary>
    WhenAll,
    /// <summary>
    /// Trigger when any incoming edge has data.
    /// </summary>
    WhenAny
}

/// <summary>
/// Represents a connection from a set of nodes to a single node. It can trigger either when all edges have data
/// or when any of them have data.
/// </summary>
/// <param name="SourceIds">An enumeration of ids of the source executor nodes.</param>
/// <param name="SinkId">The id of the target executor node.</param>
/// <param name="Trigger">The <see cref="FanInTrigger"/> that determines when the fan-in edge is activated.</param>
public record FanInEdgeData(
    IEnumerable<string> SourceIds,
    string SinkId,
    FanInTrigger Trigger = FanInTrigger.WhenAll)
{
    internal Guid UniqueKey { get; } = Guid.NewGuid();

    /// <summary>
    /// Converts a <see cref="FanInEdgeData"/> instance to an <see cref="Edge"/>.
    /// </summary>
    /// <param name="data">The <see cref="FanInEdgeData"/> to convert.</param>
    public static implicit operator Edge(FanInEdgeData data)
    {
        return new Edge(data);
    }
}

/// <summary>
/// Represents a connection or relationship between nodes, characterized by its type and associated data.
/// </summary>
/// <remarks>
/// An <see cref="Edge"/> can be of type <see cref="Type.Direct"/>, <see cref="Type.FanOut"/>, or <see
/// cref="Type.FanIn"/>, as specified by the <see cref="EdgeType"/> property. The <see cref="Data"/> property holds
/// additional information relevant to the edge, and its concrete type depends on the value of <see
/// cref="EdgeType"/>, functioning as a tagged union.
/// </remarks>
public class Edge
{
    /// <summary>
    /// Specified the edge type.
    /// </summary>
    public enum Type
    {
        /// <summary>
        /// A direct connection from one node to another.
        /// </summary>
        Direct,
        /// <summary>
        /// A connection from one node to a set of nodes.
        /// </summary>
        FanOut,
        /// <summary>
        /// A connection from a set of nodes to a single node.
        /// </summary>
        FanIn
    }

    /// <summary>
    /// Specifies the type of the edge, which determines how the edge is processed in the workflow.
    /// </summary>
    public Type EdgeType { get; init; }

    /// <summary>
    /// The <see cref="Type"/>-dependent edge data.
    /// </summary>
    /// <seealso cref="DirectEdgeData"/>
    /// <seealso cref="FanOutEdgeData"/>
    /// <seealso cref="FanInEdgeData"/>
    public object Data { get; init; }

    internal Edge(DirectEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.Direct;
    }

    internal Edge(FanOutEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanOut;
    }

    internal Edge(FanInEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanIn;
    }

    internal DirectEdgeData? DirectEdgeData => this.Data as DirectEdgeData;
    internal FanOutEdgeData? FanOutEdgeData => this.Data as FanOutEdgeData;
    internal FanInEdgeData? FanInEdgeData => this.Data as FanInEdgeData;
}
