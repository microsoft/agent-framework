// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a request to an external input port.
/// </summary>
/// <param name="Port">The port to invoke.</param>
/// <param name="RequestId">A unique identifier for this request instance.</param>
/// <param name="Data">The data contained in the request.</param>
public record ExternalRequest(InputPort Port, string RequestId, object Data)
{
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

        return new ExternalRequest(port, requestId, data);
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
        if (!Throw.IfNull(this.Port).Response.IsAssignableFrom(Throw.IfNull(data).GetType()))
        {
            throw new InvalidOperationException(
                $"Message type {data.GetType().Name} is not assignable to the response type {this.Port.Response.Name} of input port {this.Port.Id}.");
        }

        return new ExternalResponse(this.Port, this.RequestId, data);
    }

    /// <summary>
    /// Creates a new <see cref="ExternalResponse"/> corresponding to the request, with the speicified data payload.
    /// </summary>
    /// <typeparam name="T">The type of the response data.</typeparam>
    /// <param name="data">The data contained in the response.</param>
    /// <returns>An <see cref="ExternalResponse"/> instance corresponding to this request with the specified data.</returns>
    public ExternalResponse CreateResponse<T>(T data) => this.CreateResponse((object)Throw.IfNull(data));
}
