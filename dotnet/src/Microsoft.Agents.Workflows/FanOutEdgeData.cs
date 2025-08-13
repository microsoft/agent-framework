// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using PartitionerT = System.Func<object?, int, System.Collections.Generic.IEnumerable<int>>;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a connection from a single node to a set of nodes, optionally associated with a paritition selector
/// function which maps incoming messages to a subset of the target set.
/// </summary>
/// <param name="sourceId">The id of the source executor node.</param>
/// <param name="sinkIds">A list of ids of the target executor nodes.</param>
/// <param name="partitioner">A function that maps an incoming message to a subset of the target executor nodes.</param>
public sealed class FanOutEdgeData(
    string sourceId,
    List<string> sinkIds,
    PartitionerT? partitioner = null)
{
    /// <summary>
    /// The Id of the source <see cref="Executor"/> node.
    /// </summary>
    public string SourceId => sourceId;

    /// <summary>
    /// The ordered list of Ids of the destination <see cref="Executor"/> nodes.
    /// </summary>
    public List<string> SinkIds => sinkIds;

    /// <summary>
    /// A function mapping an incoming message to a subset of the target executor nodes (or optionally all of them).
    /// If <see langword="null"/>, all destination nodes are selected.
    /// </summary>
    public PartitionerT? PartitionAssigner => partitioner;
}
