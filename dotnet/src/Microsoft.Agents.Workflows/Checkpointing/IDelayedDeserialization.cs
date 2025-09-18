// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Implements an abstraction across serialization mechanisms to represent a lazily-deserialized value.
///
/// This can be used when the target-type information is not known at time of initial deserialization.
/// </summary>
internal interface IDelayedDeserialization
{
    /// <summary>
    /// Attempt to deserialize the value as the provided type.
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <returns></returns>
    TValue Deserialize<TValue>();

    /// <summary>
    /// Attempt to deserialize the value as the provided type.
    /// </summary>
    /// <param name="targetType"></param>
    /// <returns></returns>
    object? Deserialize(Type targetType);
}
