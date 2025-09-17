// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Represents a fan-in <see cref="Edge"/> in the <see cref="Workflow"/>.
/// </summary>
public sealed class FanInEdgeInfo : EdgeInfo
{
    internal FanInEdgeInfo(FanInEdgeData data) : base(EdgeKind.FanIn, data.Connection)
    {
    }

    [JsonConstructor]
    internal FanInEdgeInfo(EdgeConnection connection) : base(EdgeKind.FanIn, connection)
    {
    }
}
