// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A base class for edge data, providing access to the <see cref="EdgeConnection"/> representation of the edge.
/// </summary>
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
