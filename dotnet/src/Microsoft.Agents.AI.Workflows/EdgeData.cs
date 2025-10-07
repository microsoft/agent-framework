// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A base class for edge data, providing access to the <see cref="EdgeConnection"/> representation of the edge.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(FanInEdgeData), typeDiscriminator: "fanIn")]
[JsonDerivedType(typeof(FanOutEdgeData), typeDiscriminator: "fanOut")]
[JsonDerivedType(typeof(DirectEdgeData), typeDiscriminator: "direct")]
public abstract class EdgeData
{
    /// <summary>
    /// Gets the connection representation of the edge.
    /// </summary>
    internal abstract EdgeConnection Connection { get; }

    internal EdgeData(EdgeId id)
    {
        this.Id = id;
    }

    internal EdgeId Id { get; }
}
