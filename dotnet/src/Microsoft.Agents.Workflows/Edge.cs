// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a connection or relationship between nodes, characterized by its type and associated data.
/// </summary>
/// <remarks>
/// An <see cref="Edge"/> can be of type <see cref="Type.Direct"/>, <see cref="Type.FanOut"/>, or <see
/// cref="Type.FanIn"/>, as specified by the <see cref="EdgeType"/> property. The <see cref="Data"/> property holds
/// additional information relevant to the edge, and its concrete type depends on the value of <see
/// cref="EdgeType"/>, functioning as a tagged union.
/// </remarks>
public sealed class Edge
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
    public EdgeData Data { get; init; }

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
