// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A base class for edge data, providing access to the <see cref="EdgeConnection"/> representation of the edge.
/// </summary>
public abstract class EdgeData
{
    /// <summary>
    /// Gets the connection representation of the edge.
    /// </summary>
    internal abstract EdgeConnection Connection { get; }

    internal EdgeData(EdgeId id, string? label = null)
    {
        this.Id = id;
        this.Label = label;
    }

    internal EdgeId Id { get; }

    /// <summary>
    /// An optional label for the edge, allowing for arbitrary metadata to be associated with it.
    /// </summary>
    public string? Label { get; }
}
