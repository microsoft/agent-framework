// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Specified the edge type.
/// </summary>
public enum EdgeKind
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
/// Represents a connection or relationship between nodes, characterized by its type and associated data.
/// </summary>
/// <remarks>
/// An <see cref="Edge"/> can be of type <see cref="EdgeKind.Direct"/>, <see cref="EdgeKind.FanOut"/>, or <see
/// cref="EdgeKind.FanIn"/>, as specified by the <see cref="Kind"/> property. The <see cref="Data"/> property holds
/// additional information relevant to the edge, and its concrete type depends on the value of <see
/// cref="Kind"/>, functioning as a tagged union.
/// </remarks>
public sealed class Edge
{
    /// <summary>
    /// Specifies the type of the edge, which determines how the edge is processed in the workflow.
    /// </summary>
    public EdgeKind Kind { get; init; }

    /// <summary>
    /// The <see cref="EdgeKind"/>-dependent edge data.
    /// </summary>
    /// <seealso cref="DirectEdgeData"/>
    /// <seealso cref="FanOutEdgeData"/>
    /// <seealso cref="FanInEdgeData"/>
    public EdgeData Data { get; init; }

    internal Edge(DirectEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.Kind = EdgeKind.Direct;
    }

    internal Edge(FanOutEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.Kind = EdgeKind.FanOut;
    }

    internal Edge(FanInEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.Kind = EdgeKind.FanIn;
    }

    internal DirectEdgeData? DirectEdgeData => this.Data as DirectEdgeData;
    internal FanOutEdgeData? FanOutEdgeData => this.Data as FanOutEdgeData;
    internal FanInEdgeData? FanInEdgeData => this.Data as FanInEdgeData;
}
