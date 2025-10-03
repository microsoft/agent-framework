// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a request from an external input port.
/// </summary>
/// <param name="PortInfo">The port invoked.</param>
/// <param name="RequestId">The unique identifier of the corresponding request.</param>
/// <param name="Data">The data contained in the response.</param>
public record ExternalResponse(RequestPortInfo PortInfo, string RequestId, PortableValue Data)
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
    /// Determines whether the underlying data can be retrieved as the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to which the underlying data is to be cast if available.</typeparam>
    /// <param name="value">When this method returns, contains the value of type <typeparamref name="TValue"/> if the data is
    /// available and compatible.</param>
    /// <returns>true if the data is present and can be cast to <typeparamref name="TValue"/>; otherwise, false.</returns>
    public bool DataIs<TValue>([NotNullWhen(true)] out TValue? value) => this.Data.Is(out value);

    /// <summary>
    /// Attempts to retrieve the underlying data as the specified type.
    /// </summary>
    /// <param name="targetType">The type to which the data should be cast or converted.</param>
    /// <returns>The data cast to the specified type, or null if the data cannot be cast to the specified type.</returns>
    public object? DataAs(Type targetType) => this.Data.AsType(targetType);
}
