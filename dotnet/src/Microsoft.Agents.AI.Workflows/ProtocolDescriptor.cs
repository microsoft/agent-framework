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
    /// Gets a value indicating whether the <see cref="Workflow"/> or <see cref="Executor"/> has a "catch-all" handler.
    /// </summary>
    public bool AcceptsAll { get; set; }

    internal ProtocolDescriptor(IEnumerable<Type> acceptedTypes, bool acceptsAll)
    {
        this.Accepts = acceptedTypes.ToArray();
        this.AcceptsAll = acceptsAll;
    }
}
