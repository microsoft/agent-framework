// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Defines the contract for executing HTTP requests emitted by <c>HttpRequestAction</c> within declarative workflows.
/// </summary>
/// <remarks>
/// This interface allows the HTTP request dispatch to be abstracted, enabling different implementations
/// for local development, hosted workflows, authenticated scenarios, and testing.
/// </remarks>
public interface IHttpRequestHandler
{
    /// <summary>
    /// Sends an HTTP request and returns the response.
    /// </summary>
    /// <param name="request">The HTTP request to send.</param>
    /// <param name="cancellationToken">A token to observe cancellation.</param>
    /// <returns>The <see cref="HttpRequestResult"/> describing the HTTP response.</returns>
    Task<HttpRequestResult> SendAsync(
        HttpRequestInfo request,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Describes an HTTP request to be sent by an <see cref="IHttpRequestHandler"/>.
/// </summary>
[SuppressMessage("Design", "CA1056:URI-like properties should not be strings", Justification = "URL is carried as a string to preserve the declarative expression result and to avoid forcing handler implementations to construct a Uri eagerly.")]
public sealed class HttpRequestInfo
{
    /// <summary>
    /// Gets the HTTP method to use (GET, POST, PUT, PATCH, DELETE).
    /// </summary>
    public string Method { get; init; } = "GET";

    /// <summary>
    /// Gets the absolute URL to send the request to.
    /// </summary>
    public string Url { get; init; } = string.Empty;

    /// <summary>
    /// Gets the headers to include on the request, excluding the <c>Content-Type</c> header (which is supplied via <see cref="BodyContentType"/>).
    /// </summary>
    public IReadOnlyDictionary<string, string>? Headers { get; init; }

    /// <summary>
    /// Gets the <c>Content-Type</c> of the request body, or <see langword="null"/> if no body is sent.
    /// </summary>
    public string? BodyContentType { get; init; }

    /// <summary>
    /// Gets the serialized request body, or <see langword="null"/> if no body is sent.
    /// </summary>
    public string? Body { get; init; }

    /// <summary>
    /// Gets the maximum amount of time to wait for the request to complete, or <see langword="null"/> to use the handler default.
    /// </summary>
    public TimeSpan? Timeout { get; init; }

    /// <summary>
    /// Gets the query parameters to append to the request URL, with values already formatted as strings.
    /// </summary>
    public IReadOnlyDictionary<string, string>? QueryParameters { get; init; }

    /// <summary>
    /// Gets the name of the declared remote connection, or <see langword="null"/> if no connection is declared.
    /// This maps to the Foundry project connection Id and is only used when running in foundry service.
    /// </summary>
    public string? ConnectionName { get; init; }
}

/// <summary>
/// Represents the result of an HTTP request executed by an <see cref="IHttpRequestHandler"/>.
/// </summary>
public sealed class HttpRequestResult
{
    /// <summary>
    /// Gets the HTTP status code returned by the server.
    /// </summary>
    public int StatusCode { get; init; }

    /// <summary>
    /// Gets a value indicating whether the status code is in the range 200-299.
    /// </summary>
    public bool IsSuccessStatusCode { get; init; }

    /// <summary>
    /// Gets the response body, or <see langword="null"/> if no body was returned.
    /// </summary>
    public string? Body { get; init; }

    /// <summary>
    /// Gets the response headers keyed by header name. Each header may have multiple values.
    /// </summary>
    public IReadOnlyDictionary<string, IReadOnlyList<string>>? Headers { get; init; }
}
