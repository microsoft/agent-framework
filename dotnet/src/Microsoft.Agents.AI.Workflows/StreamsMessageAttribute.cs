// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// This attribute indicates that a message handler streams messages during its execution.
/// </summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
public sealed class StreamsMessageAttribute : Attribute
{
    /// <summary>
    /// The type of the message that the handler yields.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Indicates that the message handler yields streaming messages during the course of execution.
    /// </summary>
    public StreamsMessageAttribute(Type type)
    {
        // This attribute is used to mark executors that yield messages.
        this.Type = Throw.IfNull(type);
    }
}
