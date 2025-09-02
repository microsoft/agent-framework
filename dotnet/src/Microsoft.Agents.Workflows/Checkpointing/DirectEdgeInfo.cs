// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class DirectEdgeInfo(DirectEdgeData data) : EdgeInfo(Edge.Type.Direct, data.Connection)
{
    public bool HasCondition => data.Condition != null;

    protected override bool IsMatchInternal(EdgeData edgeData)
    {
        return edgeData is DirectEdgeData directEdge
            && this.HasCondition == (directEdge.Condition != null);
    }
}
