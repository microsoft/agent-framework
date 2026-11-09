// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Default implementation of <see cref="IHttpRequestHandler"/> built on <see cref="HttpClient"/>.
/// </summary>
/// <remarks>
/// <para>
/// This handler obtains a handler pipeline from the application-owned <see cref="IHttpMessageHandlerFactory"/>
/// and creates and disposes an HTTP client for each request, including redirects, without disposing the pipeline.
/// The factory manages the lifetime of the underlying HTTP handlers.
/// Configure the named pipeline with automatic redirects and cookies disabled. Authentication handlers must
/// bind credentials to the intended origin on each request, including redirects; do not put credentials in
/// headers when multiple origins are allowed. Client configuration registered through
/// <see cref="IHttpClientFactory"/> does not apply; configure headers and authentication in delegating handlers.
/// </para>
/// <para>
/// Requests must use HTTP or HTTPS and target a host explicitly allowed by the application, including after
/// redirects. Every constructor requires an explicit allowlist; an empty list rejects all requests.
/// Host matching is exact and case-insensitive, with internationalized names and trailing DNS dots normalized;
/// wildcards and implicit subdomains are not supported. Entries may include a port; omitted ports default to 443.
/// Authorization matches the host and port, independently of whether HTTP or HTTPS is used.
/// The allowlist is copied at construction and applies before creating a client.
/// Workflow-supplied Host headers are rejected; the transport derives the authority from the request URL.
/// DNS resolution and network routing are delegated to the HTTP transport, not classified by this handler.
/// </para>
/// <para>
/// The handler applies the per-request <see cref="HttpRequestInfo.Timeout"/> using a linked <see cref="CancellationTokenSource"/>
/// for the entire operation, including redirects and response body reads. A positive per-request timeout
/// disables the client's independent timeout so longer workflow deadlines are honored.
/// </para>
/// <para>
/// Redirects are handled explicitly so each destination is checked against the allowlist and workflow-supplied
/// headers are not forwarded. Before sending, the pipeline must terminate in a supported HTTP transport with
/// automatic redirects and cookies disabled. Unsupported transports are rejected. Application-owned delegating
/// handlers must preserve the validated destination and must not follow redirects themselves.
/// </para>
/// </remarks>
public sealed class DefaultHttpRequestHandler : IHttpRequestHandler
{
    private const int MaxAutomaticRedirections = 50;

    private readonly AllowedHttpHosts _allowedHosts;
    private readonly IHttpMessageHandlerFactory _httpMessageHandlerFactory;
    private readonly string _httpClientName;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultHttpRequestHandler"/> class with allowed hosts
    /// and an application-owned HTTP message handler factory.
    /// </summary>
    /// <param name="allowedHosts">
    /// The exact DNS names or IP literals, optionally including a port, the application permits.
    /// Omitted ports default to 443. Use brackets around IPv6 literals when specifying a port.
    /// Schemes, paths, and wildcards are not supported. An empty collection rejects all requests.
    /// The collection is copied.
    /// </param>
    /// <param name="httpMessageHandlerFactory">
    /// The factory supplying pooled handler pipelines. The primary handler must be a
    /// <see cref="HttpClientHandler"/> or, on .NET, a <c>SocketsHttpHandler</c>,
    /// with automatic redirects and cookies disabled. Bind authentication to the intended origin in a
    /// delegating handler. The application owns the factory and its handlers.
    /// </param>
    /// <param name="httpClientName">The configured client name, or <see langword="null"/> for the default client.</param>
    /// <exception cref="ArgumentNullException">An argument other than <paramref name="httpClientName"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">An allowed host is invalid.</exception>
    public DefaultHttpRequestHandler(
        IEnumerable<string> allowedHosts,
        IHttpMessageHandlerFactory httpMessageHandlerFactory,
        string? httpClientName = null)
    {
        Throw.IfNull(allowedHosts);
        Throw.IfNull(httpMessageHandlerFactory);
        this._allowedHosts = new(allowedHosts);

        this._httpMessageHandlerFactory = httpMessageHandlerFactory;
        this._httpClientName = httpClientName ?? string.Empty;
    }

    /// <inheritdoc/>
    public async Task<HttpRequestResult> SendAsync(HttpRequestInfo request, CancellationToken cancellationToken = default)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Url))
        {
            throw new ArgumentException("Request URL must be provided.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Method))
        {
            throw new ArgumentException("Request method must be provided.", nameof(request));
        }

        HttpRequestInfo currentRequest = CreateCanonicalRequestInfo(request, out Uri currentUri);

        if (request.Headers is not null)
        {
            foreach (KeyValuePair<string, string> header in request.Headers)
            {
                if (string.Equals(header.Key, "Host", StringComparison.OrdinalIgnoreCase))
                {
                    throw new HttpRequestException("Request headers must not override the Host header.");
                }
            }
        }

        using CancellationTokenSource? timeoutCts = request.Timeout is { } timeout && timeout > TimeSpan.Zero
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : null;

        timeoutCts?.CancelAfter(request.Timeout!.Value);

        CancellationToken effectiveToken = timeoutCts?.Token ?? cancellationToken;

        for (int redirectCount = 0; redirectCount <= MaxAutomaticRedirections; redirectCount++)
        {
            if (!this._allowedHosts.Contains(currentUri))
            {
                throw new HttpRequestException("The request host and port are not in the allowed hosts list.");
            }

            HttpMessageHandler messageHandler = this._httpMessageHandlerFactory.CreateHandler(this._httpClientName);
            ValidateTransport(messageHandler);
            using HttpClient client = new(messageHandler, disposeHandler: false);
            if (timeoutCts is not null)
            {
                client.Timeout = Timeout.InfiniteTimeSpan;
            }

            using HttpRequestMessage httpRequest = BuildHttpRequestMessage(currentRequest);

            using HttpResponseMessage httpResponse = await client
                .SendAsync(httpRequest, HttpCompletionOption.ResponseHeadersRead, effectiveToken)
                .ConfigureAwait(false);

            if (TryCreateRedirectRequest(httpResponse, currentRequest, currentUri, out HttpRequestInfo? redirectRequest, out Uri? redirectUri))
            {
                currentRequest = redirectRequest;
                currentUri = redirectUri;
                continue;
            }

            string? body = httpResponse.Content is null
                ? null
                : await ReadResponseBodyAsStringAsync(httpResponse.Content, effectiveToken).ConfigureAwait(false);

            Dictionary<string, IReadOnlyList<string>> headers = new(StringComparer.OrdinalIgnoreCase);
            AppendHeaders(headers, httpResponse.Headers);
            if (httpResponse.Content is not null)
            {
                AppendHeaders(headers, httpResponse.Content.Headers);
            }

            return new HttpRequestResult
            {
                StatusCode = (int)httpResponse.StatusCode,
                IsSuccessStatusCode = httpResponse.IsSuccessStatusCode,
                Body = body,
                Headers = headers,
            };
        }

        throw new HttpRequestException($"The maximum number of HTTP redirects ({MaxAutomaticRedirections}) was exceeded.");
    }

    private static void ValidateTransport(HttpMessageHandler handler)
    {
        while (handler is DelegatingHandler delegatingHandler)
        {
            handler = delegatingHandler.InnerHandler
                ?? throw new InvalidOperationException("The HTTP handler pipeline must have a primary handler.");
        }

        bool allowAutoRedirect;
        bool useCookies;
        if (handler is HttpClientHandler httpClientHandler)
        {
            allowAutoRedirect = httpClientHandler.AllowAutoRedirect;
            useCookies = httpClientHandler.UseCookies;
        }
#if NET
        else if (handler is SocketsHttpHandler socketsHttpHandler)
        {
            allowAutoRedirect = socketsHttpHandler.AllowAutoRedirect;
            useCookies = socketsHttpHandler.UseCookies;
        }
#endif
        else
        {
            throw new InvalidOperationException("The HTTP handler pipeline must use a supported primary HTTP handler.");
        }

        if (allowAutoRedirect || useCookies)
        {
            throw new InvalidOperationException("The primary HTTP handler must disable automatic redirects and cookies.");
        }
    }

    private static async Task<string> ReadResponseBodyAsStringAsync(HttpContent content, CancellationToken cancellationToken)
    {
#if NET
        return await content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
        Task<string> readTask = content.ReadAsStringAsync();
        Task cancellationTask = Task.Delay(Timeout.Infinite, cancellationToken);
        Task completedTask = await Task.WhenAny(readTask, cancellationTask).ConfigureAwait(false);
        if (completedTask == readTask)
        {
            return await readTask.ConfigureAwait(false);
        }

        content.Dispose();
        _ = readTask.ContinueWith(
            static task => _ = task.Exception,
            CancellationToken.None,
            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
            TaskScheduler.Default);

        cancellationToken.ThrowIfCancellationRequested();
        throw new OperationCanceledException(cancellationToken);
#endif
    }

    private static HttpRequestMessage BuildHttpRequestMessage(HttpRequestInfo request)
    {
        HttpMethod method = ResolveMethod(request.Method);
        string requestUri = ResolveRequestUri(request);
        HttpRequestMessage httpRequest = new(method, requestUri);

        if (request.Body is not null)
        {
            string contentType = string.IsNullOrWhiteSpace(request.BodyContentType)
                ? "text/plain"
                : request.BodyContentType!;

            httpRequest.Content = new StringContent(request.Body, Encoding.UTF8);
            // Replace the default content-type header (including charset) with the declared type.
            httpRequest.Content.Headers.Remove("Content-Type");
            ValidateHeaderValue("Content-Type", contentType);
            httpRequest.Content.Headers.TryAddWithoutValidation("Content-Type", contentType);
        }

        if (request.Headers is not null)
        {
            foreach (KeyValuePair<string, string> header in request.Headers)
            {
                if (string.IsNullOrEmpty(header.Key))
                {
                    continue;
                }

                ValidateHeader(header.Key, header.Value);

                // Content-* headers belong on HttpContent; all others belong on the request.
                if (header.Key.StartsWith("Content-", StringComparison.OrdinalIgnoreCase) && httpRequest.Content is not null)
                {
                    httpRequest.Content.Headers.Remove(header.Key);
                    httpRequest.Content.Headers.TryAddWithoutValidation(header.Key, header.Value);
                    continue;
                }

                if (!httpRequest.Headers.TryAddWithoutValidation(header.Key, header.Value))
                {
                    httpRequest.Content?.Headers.TryAddWithoutValidation(header.Key, header.Value);
                }
            }
        }

        return httpRequest;
    }

    private static void ValidateHeader(string name, string value)
    {
        HttpHeaderValidation.ValidateNoProhibitedCharacters(
            name,
            nameof(name),
            "HTTP header name contains invalid characters.");

        ValidateHeaderValue(name, value);
    }

    private static void ValidateHeaderValue(string name, string value)
    {
        HttpHeaderValidation.ValidateNoProhibitedCharacters(
            value,
            nameof(value),
            $"HTTP header '{name}' contains invalid characters.");
    }

    private static Uri CreateAbsoluteUri(string requestUri)
    {
        if (!Uri.TryCreate(requestUri, UriKind.Absolute, out Uri? uri))
        {
            throw new ArgumentException("Request URL must be an absolute URL.", nameof(requestUri));
        }

        if (!string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            throw new HttpRequestException("Request URLs must use HTTP or HTTPS.");
        }

        return uri;
    }

    private static HttpRequestInfo CreateCanonicalRequestInfo(HttpRequestInfo request, out Uri uri)
    {
        uri = CreateAbsoluteUri(ResolveRequestUri(request));
        return new HttpRequestInfo
        {
            Method = request.Method,
            Url = uri.ToString(),
            Headers = request.Headers,
            BodyContentType = request.BodyContentType,
            Body = request.Body,
            Timeout = request.Timeout,
            ConnectionName = request.ConnectionName,
        };
    }

    private static bool TryCreateRedirectRequest(
        HttpResponseMessage response,
        HttpRequestInfo currentRequest,
        Uri currentUri,
        [NotNullWhen(true)] out HttpRequestInfo? redirectRequest,
        [NotNullWhen(true)] out Uri? redirectUri)
    {
        redirectRequest = null;
        redirectUri = null;

        if (!IsRedirectStatusCode(response.StatusCode) || response.Headers.Location is null)
        {
            return false;
        }

        redirectUri = response.Headers.Location.IsAbsoluteUri
            ? response.Headers.Location
            : new Uri(currentUri, response.Headers.Location);
        redirectUri = CreateAbsoluteUri(redirectUri.ToString());

        if (IsHttpsToHttpRedirect(currentUri, redirectUri))
        {
            throw new HttpRequestException("Redirects from HTTPS to HTTP are not allowed.");
        }

        bool rewriteToGet = ShouldRewriteRedirectMethodToGet(response.StatusCode, currentRequest.Method);
        if (!rewriteToGet && currentRequest.Body is not null && !HaveSameOrigin(currentUri, redirectUri))
        {
            throw new HttpRequestException("Redirects that preserve the request body to a different origin are not allowed.");
        }

        redirectRequest = new HttpRequestInfo
        {
            Method = rewriteToGet ? "GET" : currentRequest.Method,
            Url = redirectUri.ToString(),
            Body = rewriteToGet ? null : currentRequest.Body,
            BodyContentType = rewriteToGet ? null : currentRequest.BodyContentType,
            Timeout = currentRequest.Timeout,
            ConnectionName = currentRequest.ConnectionName,
        };

        return true;
    }

    private static bool IsRedirectStatusCode(HttpStatusCode statusCode)
    {
        int code = (int)statusCode;
        return code is 301 or 302 or 303 or 307 or 308;
    }

    private static bool ShouldRewriteRedirectMethodToGet(HttpStatusCode statusCode, string method)
    {
        string normalized = method.Trim().ToUpperInvariant();
        int code = (int)statusCode;
        return code == 303 || ((code == 301 || code == 302) && string.Equals(normalized, "POST", StringComparison.Ordinal));
    }

    private static bool IsHttpsToHttpRedirect(Uri currentUri, Uri redirectUri) =>
        string.Equals(currentUri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) &&
        string.Equals(redirectUri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase);

    private static bool HaveSameOrigin(Uri currentUri, Uri redirectUri) =>
        Uri.Compare(
            currentUri,
            redirectUri,
            UriComponents.SchemeAndServer,
            UriFormat.Unescaped,
            StringComparison.OrdinalIgnoreCase) == 0;

    private static HttpMethod ResolveMethod(string method)
    {
        string normalized = method.Trim().ToUpperInvariant();
        return normalized switch
        {
            "GET" => HttpMethod.Get,
            "POST" => HttpMethod.Post,
            "PUT" => HttpMethod.Put,
            "DELETE" => HttpMethod.Delete,
#if NET
            "PATCH" => HttpMethod.Patch,
#else
            "PATCH" => new HttpMethod("PATCH"),
#endif
            _ => new HttpMethod(normalized),
        };
    }

    private static string ResolveRequestUri(HttpRequestInfo request)
    {
        string baseUrl = request.Url;
        if (request.QueryParameters is null || request.QueryParameters.Count == 0)
        {
            return baseUrl;
        }

        StringBuilder queryBuilder = new();
        foreach (KeyValuePair<string, string> parameter in request.QueryParameters)
        {
            if (string.IsNullOrEmpty(parameter.Key))
            {
                continue;
            }

            if (queryBuilder.Length > 0)
            {
                queryBuilder.Append('&');
            }

            queryBuilder.Append(Uri.EscapeDataString(parameter.Key))
                .Append('=')
                .Append(Uri.EscapeDataString(parameter.Value ?? string.Empty));
        }

        if (queryBuilder.Length == 0)
        {
            return baseUrl;
        }

        char separator = baseUrl.Contains('?') ? '&' : '?';
        return string.Concat(baseUrl, separator.ToString(), queryBuilder.ToString());
    }

    private static void AppendHeaders(
        Dictionary<string, IReadOnlyList<string>> target,
        System.Net.Http.Headers.HttpHeaders source)
    {
        foreach (KeyValuePair<string, IEnumerable<string>> header in source)
        {
            string[] values = header.Value.ToArray();

            if (target.TryGetValue(header.Key, out IReadOnlyList<string>? existing))
            {
                List<string> combined = new(existing);
                combined.AddRange(values);
                target[header.Key] = combined;
            }
            else
            {
                target[header.Key] = values;
            }
        }
    }
}
