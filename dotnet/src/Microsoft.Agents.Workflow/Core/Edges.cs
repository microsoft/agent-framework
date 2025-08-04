// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

using PredicateT = System.Func<object?, bool>;
using PartitionerT = System.Func<object?, int, System.Collections.Generic.IEnumerable<int>>;
using System;

namespace Microsoft.Agents.Workflows.Core;

internal record DirectEdgeData(
    string SourceId,
    string SinkId,
    PredicateT? Condition = null)
{
    public static implicit operator FlowEdge(DirectEdgeData data)
    {
        return new FlowEdge(data);
    }
}

internal record FanOutEdgeData(
    string SourceId,
    List<string> SinkIds,
    PartitionerT? Partitioner = null)
{
    public static implicit operator FlowEdge(FanOutEdgeData data)
    {
        return new FlowEdge(data);
    }
}

internal enum FanInTrigger
{
    WhenAll,
    WhenAny
}

internal record FanInEdgeData(
    IEnumerable<string> SourceIds,
    string SinkId,
    FanInTrigger Trigger = FanInTrigger.WhenAll)
{
    internal Guid UniqueKey { get; } = Guid.NewGuid();

    public static implicit operator FlowEdge(FanInEdgeData data)
    {
        return new FlowEdge(data);
    }
}

internal class FlowEdge
{
    public enum Type
    {
        Direct,
        FanOut,
        FanIn
    }

    public Type EdgeType { get; init; }
    public object Data { get; init; }

    public FlowEdge(DirectEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.Direct;
    }

    public FlowEdge(FanOutEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanOut;
    }

    public FlowEdge(FanInEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanIn;
    }

    public DirectEdgeData? DirectEdgeData => this.Data as DirectEdgeData;
    public FanOutEdgeData? FanOutEdgeData => this.Data as FanOutEdgeData;
    public FanInEdgeData? FanInEdgeData => this.Data as FanInEdgeData;
}
