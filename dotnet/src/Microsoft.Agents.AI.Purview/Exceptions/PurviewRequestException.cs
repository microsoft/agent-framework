// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Exception for general http request errors from Purview.
/// </summary>
public class PurviewRequestException : PurviewException
{
    /// <summary>
    /// HTTP status code returned by the Purview service.
    /// </summary>
    public HttpStatusCode StatusCode { get; }

    /// <inheritdoc />
    public PurviewRequestException(HttpStatusCode statusCode, string endpointName)
        : base($"Failed to call {endpointName}. Status code: {statusCode}")
    {
        this.StatusCode = statusCode;
    }

    /// <inheritdoc />
    public PurviewRequestException(string message)
        : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewRequestException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewRequestException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
