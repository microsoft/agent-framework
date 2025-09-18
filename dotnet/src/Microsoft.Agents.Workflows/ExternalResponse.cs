// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a request from an external input port.
/// </summary>
/// <param name="PortInfo">The port invoked.</param>
/// <param name="RequestId">The unique identifier of the corresponding request.</param>
/// <param name="Data">The data contained in the response.</param>
public record ExternalResponse(InputPortInfo PortInfo, string RequestId, PortableValue Data)
{
    /// <summary>
    /// Attempts to retrieve the underlying data as the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to which the data should be cast or converted.</typeparam>
    /// <returns>The data cast to the specified type, or null if the data cannot be cast to the specified type.</returns>
    public TValue? DataAs<TValue>() => this.Data.As<TValue>();

    /// <summary>
    /// Determines whether the underlying data is of the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to compare with the underlying data.</typeparam>
    /// <returns>true if the underlying data is of type TValue; otherwise, false.</returns>
    public bool DataIs<TValue>() => this.Data.Is<TValue>();

    /// <summary>
    /// Attempts to retrieve the underlying data as the specified type.
    /// </summary>
    /// <param name="targetType">The type to which the data should be cast or converted.</param>
    /// <returns>The data cast to the specified type, or null if the data cannot be cast to the specified type.</returns>
    public object? DataAs(Type targetType) => this.Data.AsType(targetType);
}
