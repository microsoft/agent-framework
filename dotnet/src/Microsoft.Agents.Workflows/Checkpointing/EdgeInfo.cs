// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal abstract class EdgeInfo(Edge.Type edgeType, EdgeConnection connection)
{
    public Edge.Type EdgeType => edgeType;
    public EdgeConnection Connection { get; } = Throw.IfNull(connection);

    public bool IsMatch(Edge edge)
    {
        return this.EdgeType == edge.EdgeType
            && this.Connection.Equals(edge.Data.Connection)
            && this.IsMatchInternal(edge.Data);
    }

    protected virtual bool IsMatchInternal(EdgeData edgeData) => true;
}
