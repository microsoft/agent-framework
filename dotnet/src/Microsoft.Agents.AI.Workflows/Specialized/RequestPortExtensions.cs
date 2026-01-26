// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal static class RequestPortExtensions
{
    /// <summary>
    /// Attempts to process the incoming <see cref="ExternalResponse"/> as a response to a request sent
    /// through the specified <see cref="RequestPort"/>. If the response is to a different port, returns
    /// <see langword="false"/>. If the port matches, but the response data cannot be interpreted as the
    /// expected response type, throws an <see cref="InvalidOperationException"/>. Otherwise, returns
    /// <see langword="true"/>.
    /// </summary>
    /// <param name="port">The request port through which the original request was sent.</param>
    /// <param name="response">The candidate response to be processed</param>
    /// <returns><see langword="true"/> if the response is for the specified port and the data could be
    /// interpreted as the expected response type; otherwise, <see langword="false"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the response is for the specified port,
    /// but the data could not be interpreted as the expected response type.</exception>
    public static bool ShouldProcessResponse(this RequestPort port, ExternalResponse response)
    {
        Throw.IfNull(response);
        Throw.IfNull(response.Data);

        if (!port.IsResponsePort(response))
        {
            return false;
        }

        if (!response.Data.IsType(port.Response))
        {
            throw port.CreateExceptionForType(response);
        }

        return true;
    }

    internal static bool IsResponsePort(this RequestPort port, ExternalResponse response)
        => Throw.IfNull(response).PortInfo.PortId == port.Id;

    internal static InvalidOperationException CreateExceptionForType(this RequestPort port, ExternalResponse response)
        => new($"Message type {response.Data.TypeId} is not assignable to the response type {port.Response.Name}" +
               $" of input port {port.Id}.");
}
