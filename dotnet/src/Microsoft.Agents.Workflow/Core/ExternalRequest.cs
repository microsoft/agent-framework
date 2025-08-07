// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
/// <param name="Port"></param>
/// <param name="RequestId"></param>
/// <param name="Data"></param>
public record ExternalRequest(InputPort Port, string RequestId, object Data)
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="port"></param>
    /// <param name="data"></param>
    /// <param name="requestId"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
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
    /// .
    /// </summary>
    /// <typeparam name="T"></typeparam>
    /// <param name="port"></param>
    /// <param name="data"></param>
    /// <param name="requestId"></param>
    /// <returns></returns>
    public static ExternalRequest Create<T>(InputPort port, T data, string? requestId = null) => Create(port, (object)Throw.IfNull(data), requestId);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="data"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
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
    /// .
    /// </summary>
    /// <typeparam name="T"></typeparam>
    /// <param name="data"></param>
    /// <returns></returns>
    public ExternalResponse CreateResponse<T>(T data) => this.CreateResponse((object)Throw.IfNull(data));
}
