// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a request to an external input port.
/// </summary>
/// <param name="PortInfo">The port to invoke.</param>
/// <param name="RequestId">A unique identifier for this request instance.</param>
/// <param name="Data">The data contained in the request.</param>
public record ExternalRequest(InputPortInfo PortInfo, string RequestId, PortableValue Data)
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
    /// Creates a new <see cref="ExternalRequest"/> for the specified input port and data payload.
    /// </summary>
    /// <param name="port">The port to invoke.</param>
    /// <param name="data">The data contained in the request.</param>
    /// <param name="requestId">An optional unique identifier for this request instance. If <c>null</c>, a UUID will be generated.</param>
    /// <returns>An <see cref="ExternalRequest"/> instance containing the specified port, data, and request identifier.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the input data object does not match the expected request type.</exception>
    public static ExternalRequest Create(InputPort port, [NotNull] object data, string? requestId = null)
    {
        if (!port.Request.IsAssignableFrom(Throw.IfNull(data).GetType()))
        {
            throw new InvalidOperationException(
                $"Message type {data.GetType().Name} is not assignable to the request type {port.Request.Name} of input port {port.Id}.");
        }

        requestId ??= Guid.NewGuid().ToString("N");

        return new ExternalRequest(port.ToPortInfo(), requestId, new PortableValue(data));
    }

    /// <summary>
    /// Creates a new <see cref="ExternalRequest"/> for the specified input port and data payload.
    /// </summary>
    /// <typeparam name="T">The type of request data.</typeparam>
    /// <param name="port">The input port that identifies the target endpoint for the request. Must not be <c>null</c>.</param>
    /// <param name="data">The data payload to include in the request. Must not be <c>null</c>.</param>
    /// <param name="requestId">An optional identifier for the request. If <c>null</c>, a default identifier may be assigned.</param>
    /// <returns>An <see cref="ExternalRequest"/> instance containing the specified port, data, and request identifier.</returns>
    public static ExternalRequest Create<T>(InputPort port, T data, string? requestId = null) => Create(port, (object)Throw.IfNull(data), requestId);

    /// <summary>
    /// Creates a new <see cref="ExternalResponse"/> corresponding to the request, with the speicified data payload.
    /// </summary>
    /// <param name="data">The data contained in the response.</param>
    /// <returns>An <see cref="ExternalResponse"/> instance corresponding to this request with the specified data.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the input data object does not match the expected response type.</exception>
    public ExternalResponse CreateResponse(object data)
    {
        if (!Throw.IfNull(this.PortInfo).ResponseType.IsMatchPolymorphic(Throw.IfNull(data).GetType()))
        {
            throw new InvalidOperationException(
                $"Message type {data.GetType().Name} does not match expected response type {this.PortInfo.ResponseType.TypeName} of input port {this.PortInfo.PortId}.");
        }

        return new ExternalResponse(this.PortInfo, this.RequestId, new PortableValue(data));
    }

    /// <summary>
    /// Creates a new <see cref="ExternalResponse"/> corresponding to the request, with the speicified data payload.
    /// </summary>
    /// <typeparam name="T">The type of the response data.</typeparam>
    /// <param name="data">The data contained in the response.</param>
    /// <returns>An <see cref="ExternalResponse"/> instance corresponding to this request with the specified data.</returns>
    public ExternalResponse CreateResponse<T>(T data) => this.CreateResponse((object)Throw.IfNull(data));
}
