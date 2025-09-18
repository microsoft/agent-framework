// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Represents a fan-out <see cref="Edge"/> in the <see cref="Workflow"/>.
/// </summary>
public sealed class FanOutEdgeInfo : EdgeInfo
{
    internal FanOutEdgeInfo(FanOutEdgeData data) : this(data.EdgeAssigner is not null, data.Connection) { }

    [JsonConstructor]
    internal FanOutEdgeInfo(bool hasAssigner, EdgeConnection connection) : base(EdgeKind.FanOut, connection)
    {
        this.HasAssigner = hasAssigner;
    }

    /// <summary>
    /// Gets a value indicating whether this fan-out edge has an edge-assigner associated with it.
    /// </summary>
    public bool HasAssigner { get; }

    internal override bool IsMatchInternal(EdgeData edgeData)
    {
        return edgeData is FanOutEdgeData fanOutEdge
            && this.HasAssigner == (fanOutEdge.EdgeAssigner is not null);
    }
}
