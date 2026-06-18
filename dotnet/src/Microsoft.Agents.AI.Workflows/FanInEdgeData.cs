// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a connection from a set of nodes to a single node. It will trigger either when all edges have data.
/// </summary>
internal sealed class FanInEdgeData : EdgeData
{
    internal FanInEdgeData(List<string> sourceIds, string sinkId, EdgeId id, string? label) : base(id, label)
    {
        this.SourceIds = sourceIds;
        this.SinkId = sinkId;
        this.Connection = new(sourceIds, [sinkId]);
    }

    /// <summary>
    /// The ordered list of Ids of the source <see cref="Executor"/> nodes.
    /// </summary>
    public List<string> SourceIds { get; }

    /// <summary>
    /// The Id of the destination <see cref="Executor"/> node.
    /// </summary>
    public string SinkId { get; }

    /// <inheritdoc />
    internal override EdgeConnection Connection { get; }
}
