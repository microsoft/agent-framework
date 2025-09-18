// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Represents a direct <see cref="Edge"/> in the <see cref="Workflow"/>.
/// </summary>
public sealed class DirectEdgeInfo : EdgeInfo
{
    internal DirectEdgeInfo(DirectEdgeData data) : this(data.Condition is not null, data.Connection) { }

    [JsonConstructor]
    internal DirectEdgeInfo(bool hasCondition, EdgeConnection connection) : base(EdgeKind.Direct, connection)
    {
        this.HasCondition = hasCondition;
    }

    /// <summary>
    /// Gets a value indicating whether this direct edge has a condition associated with it.
    /// </summary>
    public bool HasCondition { get; }

    internal override bool IsMatchInternal(EdgeData edgeData)
    {
        return edgeData is DirectEdgeData directEdge
            && this.HasCondition == (directEdge.Condition is not null);
    }
}
