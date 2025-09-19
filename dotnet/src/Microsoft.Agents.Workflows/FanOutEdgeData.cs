// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Execution;

using AssignerF = System.Func<object?, int, System.Collections.Generic.IEnumerable<int>>;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a connection from a single node to a set of nodes, optionally associated with a paritition selector
/// function which maps incoming messages to a subset of the target set.
/// </summary>
internal sealed class FanOutEdgeData : EdgeData
{
    internal FanOutEdgeData(string sourceId, List<string> sinkIds, EdgeId edgeId, AssignerF? assigner = null) : base(edgeId)
    {
        this.SourceId = sourceId;
        this.SinkIds = sinkIds;
        this.EdgeAssigner = assigner;
        this.Connection = new([sourceId], sinkIds);
    }

    /// <summary>
    /// The Id of the source <see cref="Executor"/> node.
    /// </summary>
    public string SourceId { get; }

    /// <summary>
    /// The ordered list of Ids of the destination <see cref="Executor"/> nodes.
    /// </summary>
    public List<string> SinkIds { get; }

    /// <summary>
    /// A function mapping an incoming message to a subset of the target executor nodes (or optionally all of them).
    /// If <see langword="null"/>, all destination nodes are selected.
    /// </summary>
    public AssignerF? EdgeAssigner { get; }

    /// <inheritdoc />
    internal override EdgeConnection Connection { get; }
}
