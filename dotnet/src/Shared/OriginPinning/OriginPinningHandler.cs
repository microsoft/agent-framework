// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="DelegatingHandler"/> that removes configured headers from any outbound request whose
/// origin differs from the origin of a pinned endpoint.
/// </summary>
/// <remarks>
/// <para>
/// Use this handler to keep credentials on the endpoint an <see cref="HttpClient"/> was configured for.
/// A remote endpoint can make a client build a request for a different URI, for example by advertising
/// another endpoint or issuing a redirect. Headers that the transport re-adds to that new request are not
/// covered by <see cref="HttpClient"/>'s own redirect header removal. This handler removes the configured
/// headers from any request to another origin before it reaches the inner handler. Requests to the pinned
/// origin are left untouched.
/// </para>
/// <para>
/// Place this handler inside every handler that adds credentials, so the headers those outer handlers add
/// are also removed. Headers added by a handler inside this one are not covered.
/// </para>
/// <para>
/// The configured headers are removed from <em>every</em> request to another origin. A client that must
/// legitimately send credentials to a second origin, such as an OAuth authorization server, needs a
/// separate client or an allow list for that origin.
/// </para>
/// </remarks>
internal sealed class OriginPinningHandler : DelegatingHandler
{
    private readonly Uri _pinnedEndpoint;
    private readonly string[] _headerNames;

    /// <summary>
    /// Initializes a new instance of the <see cref="OriginPinningHandler"/> class.
    /// </summary>
    /// <param name="pinnedEndpoint">The endpoint whose origin keeps the configured headers. Must be an absolute URI.</param>
    /// <param name="headerNames">
    /// The names of the headers to remove from requests to any other origin. When <see langword="null"/>,
    /// <see cref="DefaultHeaderNames"/> is used.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="pinnedEndpoint"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">
    /// <paramref name="pinnedEndpoint"/> is not an absolute URI, or <paramref name="headerNames"/> is empty or
    /// contains a <see langword="null"/>, empty, or whitespace name.
    /// </exception>
    public OriginPinningHandler(Uri pinnedEndpoint, IEnumerable<string>? headerNames = null)
    {
        _ = Throw.IfNull(pinnedEndpoint);
        if (!pinnedEndpoint.IsAbsoluteUri)
        {
            throw new ArgumentException("The pinned endpoint must be an absolute URI.", nameof(pinnedEndpoint));
        }

        string[] names = headerNames is null ? [.. DefaultHeaderNames] : [.. headerNames];
        if (names.Length == 0)
        {
            throw new ArgumentException("At least one header name must be specified.", nameof(headerNames));
        }

        foreach (string name in names)
        {
            _ = Throw.IfNullOrWhitespace(name, nameof(headerNames));
        }

        this._pinnedEndpoint = pinnedEndpoint;
        this._headerNames = names;
    }

    /// <summary>
    /// Gets the credential-bearing headers removed when no header names are specified.
    /// </summary>
    internal static IReadOnlyList<string> DefaultHeaderNames { get; } =
    [
        "Authorization",
        "Proxy-Authorization",
        "Cookie",
    ];

    /// <summary>
    /// Determines whether <paramref name="requestUri"/> targets the origin of <paramref name="pinnedEndpoint"/>.
    /// </summary>
    /// <param name="requestUri">The request URI to check.</param>
    /// <param name="pinnedEndpoint">The endpoint that defines the trusted origin.</param>
    /// <returns><see langword="true"/> when the request stays on the pinned origin; otherwise, <see langword="false"/>.</returns>
    /// <remarks>
    /// The comparison covers scheme, host, and port and ignores case. <see cref="Uri.Compare"/> normalizes
    /// default ports, so an explicit default port such as <c>:443</c> for https matches an omitted one. A
    /// missing or relative request URI counts as the same origin because <see cref="HttpClient"/> resolves it
    /// against its base address before sending, so it cannot select another origin by itself.
    /// </remarks>
    internal static bool IsSameOrigin(Uri? requestUri, Uri pinnedEndpoint)
    {
        _ = Throw.IfNull(pinnedEndpoint);

        return requestUri is not { IsAbsoluteUri: true }
            || Uri.Compare(
                requestUri,
                pinnedEndpoint,
                UriComponents.SchemeAndServer,
                UriFormat.Unescaped,
                StringComparison.OrdinalIgnoreCase) == 0;
    }

    /// <inheritdoc/>
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(request);

        if (!IsSameOrigin(request.RequestUri, this._pinnedEndpoint))
        {
            foreach (string headerName in this._headerNames)
            {
                request.Headers.Remove(headerName);
            }
        }

        return base.SendAsync(request, cancellationToken);
    }
}
