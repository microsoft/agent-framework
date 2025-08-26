// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class FanOutEdgeInfo(FanOutEdgeData data) : EdgeInfo(Edge.Type.FanOut, data.Connection)
{
    public bool HasAssigner => data.EdgeAssigner != null;

    protected override bool IsMatchInternal(EdgeData edgeData)
    {
        return edgeData is FanOutEdgeData fanOutEdge
            && this.HasAssigner == (fanOutEdge.EdgeAssigner != null);
    }
}
