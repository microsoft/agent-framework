// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Base class representing information about an edge in a workflow.
/// </summary>
[JsonPolymorphic(UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(DirectEdgeInfo), (int)EdgeKind.Direct)]
[JsonDerivedType(typeof(FanOutEdgeInfo), (int)EdgeKind.FanOut)]
[JsonDerivedType(typeof(FanInEdgeInfo), (int)EdgeKind.FanIn)]
public class EdgeInfo
{
    /// <summary>
    /// The kind of edge.
    /// </summary>
    public EdgeKind Kind { get; }

    /// <summary>
    /// Gets the connection information associated with the edge.
    /// </summary>
    public EdgeConnection Connection { get; }

    [JsonConstructor]
    internal EdgeInfo(EdgeKind kind, EdgeConnection connection)
    {
        this.Kind = kind;
        this.Connection = Throw.IfNull(connection);
    }

    internal bool IsMatch(Edge edge)
    {
        return this.Kind == edge.Kind
            && this.Connection.Equals(edge.Data.Connection)
            && this.IsMatchInternal(edge.Data);
    }

    internal virtual bool IsMatchInternal(EdgeData edgeData) => true;
}
