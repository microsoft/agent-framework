// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Describes the protocol for communication with a <see cref="Workflow"/> or <see cref="Executor"/>.
/// </summary>
public class ProtocolDescriptor
{
    /// <summary>
    /// Get the collection of types explicitly accepted by the <see cref="Workflow"/> or <see cref="Executor"/>.
    /// </summary>
    public IEnumerable<Type> Accepts { get; }

    /// <summary>
    /// Gets the collection of types that could be yielded as output by the <see cref="Workflow"/> or <see cref="Executor"/>.
    /// </summary>
    public IEnumerable<Type> Yields { get; }

    /// <summary>
    /// Gets the collection of types that could be sent from the <see cref="Executor"/>. This is always empty for a <see cref="Workflow"/>.
    /// </summary>
    public IEnumerable<Type> Sends { get; }

    /// <summary>
    /// Gets a value indicating whether the <see cref="Workflow"/> or <see cref="Executor"/> has a "catch-all" handler.
    /// </summary>
    public bool AcceptsAll { get; set; }

    internal ProtocolDescriptor(IEnumerable<Type> acceptedTypes, IEnumerable<Type> yieldedTypes, IEnumerable<Type> sentTypes, bool acceptsAll)
    {
        this.Accepts = acceptedTypes.ToArray();
        this.Yields = yieldedTypes.ToArray();
        this.Sends = sentTypes.ToArray();

        this.AcceptsAll = acceptsAll;
    }
}
