// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;

namespace Microsoft.Agents.AI.Agentforce;

/// <summary>
/// Represents an error returned by the Salesforce Agentforce API.
/// </summary>
public sealed class AgentforceApiException : Exception
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceApiException"/> class.
    /// </summary>
    public AgentforceApiException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceApiException"/> class.
    /// </summary>
    /// <param name="message">The error message.</param>
    public AgentforceApiException(string message)
        : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceApiException"/> class.
    /// </summary>
    /// <param name="message">The error message.</param>
    /// <param name="statusCode">The HTTP status code from the API response.</param>
    /// <param name="errorCode">The error code from the API response.</param>
    public AgentforceApiException(string message, HttpStatusCode statusCode, string? errorCode = null)
        : base(message)
    {
        this.StatusCode = statusCode;
        this.ErrorCode = errorCode;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceApiException"/> class.
    /// </summary>
    /// <param name="message">The error message.</param>
    /// <param name="innerException">The inner exception.</param>
    public AgentforceApiException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    /// <summary>
    /// Gets the HTTP status code from the API response, if available.
    /// </summary>
    public HttpStatusCode? StatusCode { get; }

    /// <summary>
    /// Gets the error code from the API response, if available.
    /// </summary>
    public string? ErrorCode { get; }
}
