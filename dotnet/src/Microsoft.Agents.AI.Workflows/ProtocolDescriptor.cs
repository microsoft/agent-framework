// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Describes the protocol for communication with a <see cref="Workflow"/> or <see cref="Executor"/>.
/// </summary>
public class ProtocolDescriptor
{
    /// <summary>
    /// Get the collection of types accepted by the <see cref="Workflow"/> or <see cref="Executor"/>.
    /// </summary>
    public IEnumerable<Type> Accepts { get; }

    internal ProtocolDescriptor(IEnumerable<Type> acceptedTypes)
    {
        this.Accepts = acceptedTypes;
    }
}
