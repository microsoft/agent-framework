// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a connection from a set of nodes to a single node. It will trigger either when all edges have data.
/// </summary>
/// <param name="sourceIds">An enumeration of ids of the source executor nodes.</param>
/// <param name="sinkId">The id of the target executor node.</param>
public sealed class FanInEdgeData(List<string> sourceIds, string sinkId) : EdgeData
{
    /// <summary>
    /// The ordered list of Ids of the source <see cref="Executor"/> nodes.
    /// </summary>
    public List<string> SourceIds => sourceIds;

    /// <summary>
    /// The Id of the destination <see cref="Executor"/> node.
    /// </summary>
    public string SinkId => sinkId;

    /// <inheritdoc />
    internal override EdgeConnection Connection { get; } = new(sourceIds, [sinkId]);
}
