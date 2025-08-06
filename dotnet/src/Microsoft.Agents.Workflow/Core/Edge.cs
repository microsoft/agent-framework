// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

using PredicateT = System.Func<object?, bool>;
using PartitionerT = System.Func<object?, int, System.Collections.Generic.IEnumerable<int>>;
using System;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
/// <param name="SourceId"></param>
/// <param name="SinkId"></param>
/// <param name="Condition"></param>
public record DirectEdgeData(
    string SourceId,
    string SinkId,
    PredicateT? Condition = null)
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="data"></param>
    public static implicit operator Edge(DirectEdgeData data)
    {
        return new Edge(data);
    }
}

/// <summary>
/// .
/// </summary>
/// <param name="SourceId"></param>
/// <param name="SinkIds"></param>
/// <param name="Partitioner"></param>
public record FanOutEdgeData(
    string SourceId,
    List<string> SinkIds,
    PartitionerT? Partitioner = null)
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="data"></param>
    public static implicit operator Edge(FanOutEdgeData data)
    {
        return new Edge(data);
    }
}

/// <summary>
/// .
/// </summary>
public enum FanInTrigger
{
    /// <summary>
    /// .
    /// </summary>
    WhenAll,
    /// <summary>
    /// .
    /// </summary>
    WhenAny
}

/// <summary>
/// .
/// </summary>
/// <param name="SourceIds"></param>
/// <param name="SinkId"></param>
/// <param name="Trigger"></param>
public record FanInEdgeData(
    IEnumerable<string> SourceIds,
    string SinkId,
    FanInTrigger Trigger = FanInTrigger.WhenAll)
{
    internal Guid UniqueKey { get; } = Guid.NewGuid();

    /// <summary>
    /// .
    /// </summary>
    /// <param name="data"></param>
    public static implicit operator Edge(FanInEdgeData data)
    {
        return new Edge(data);
    }
}

/// <summary>
/// .
/// </summary>
public class Edge
{
    /// <summary>
    /// .
    /// </summary>
    public enum Type
    {
        /// <summary>
        /// .
        /// </summary>
        Direct,
        /// <summary>
        /// .
        /// </summary>
        FanOut,
        /// <summary>
        /// .
        /// </summary>
        FanIn
    }

    /// <summary>
    /// .
    /// </summary>
    public Type EdgeType { get; init; }

    /// <summary>
    /// .
    /// </summary>
    public object Data { get; init; }

    internal Edge(DirectEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.Direct;
    }

    internal Edge(FanOutEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanOut;
    }

    internal Edge(FanInEdgeData data)
    {
        this.Data = Throw.IfNull(data);

        this.EdgeType = Type.FanIn;
    }

    internal DirectEdgeData? DirectEdgeData => this.Data as DirectEdgeData;
    internal FanOutEdgeData? FanOutEdgeData => this.Data as FanOutEdgeData;
    internal FanInEdgeData? FanInEdgeData => this.Data as FanInEdgeData;
}
