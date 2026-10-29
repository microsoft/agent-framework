// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net;
using System.Net.Http;
#if NET
using System.IO;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Cryptography.X509Certificates;
#endif
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
/// This handler supports per-request authentication via an optional <c>httpClientProvider</c> callback that
/// returns a pre-configured <see cref="HttpClient"/> for a given request (e.g. authenticated, custom handler).
/// When the provider returns <see langword="null"/>, or no provider is supplied, a shared internal <see cref="HttpClient"/>
/// is used.
/// </para>
/// <para>
/// Requests must use HTTP or HTTPS. The internally owned client connects directly to public addresses only,
/// including after redirects, and does not use system proxies. To access other destinations or use a proxy,
/// supply a client with an explicit destination policy. Caller-supplied clients are responsible for validating
/// their destinations, resolved addresses, and redirects.
/// The internally owned client requires .NET 8 or later; other target frameworks require a supplied client.
/// </para>
/// <para>
/// The handler applies the per-request <see cref="HttpRequestInfo.Timeout"/> using a linked <see cref="CancellationTokenSource"/>
/// so it does not mutate <see cref="HttpClient.Timeout"/> on shared instances.
/// </para>
/// <para>
/// Redirects are handled by this handler only when using its internally owned client, which disables automatic
/// redirects so per-request headers are not forwarded to redirect destinations. If a supplied client returns a
/// redirect response, this handler does not follow it because the client's redirect behavior is opaque. Supplied
/// clients should disable automatic redirects and handle redirect responses before returning them to this handler.
/// The provider is invoked for redirect destinations, but redirects that would switch from the internally owned
/// client to a provider-supplied client are rejected before sending the redirected request.
/// </para>
/// </remarks>
public sealed class DefaultHttpRequestHandler : IHttpRequestHandler, IAsyncDisposable
{
    private const int MaxAutomaticRedirections = 50;

    private readonly Func<HttpRequestInfo, CancellationToken, Task<HttpClient?>>? _httpClientProvider;
    private readonly Lazy<HttpClient> _ownedHttpClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultHttpRequestHandler"/> class that uses an
    /// internally owned <see cref="HttpClient"/> for all requests. The internal client is disposed
    /// when <see cref="DisposeAsync"/> is called.
    /// </summary>
    public DefaultHttpRequestHandler()
        : this(httpClientProvider: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultHttpRequestHandler"/> class that uses the
    /// supplied <see cref="HttpClient"/> for all requests.
    /// </summary>
    /// <param name="httpClient">
    /// The <see cref="HttpClient"/> to use for all requests. The caller retains ownership of this
    /// instance; it is not disposed by <see cref="DisposeAsync"/>.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="httpClient"/> is <see langword="null"/>.</exception>
    public DefaultHttpRequestHandler(HttpClient httpClient)
        : this(CreateSingleClientProvider(httpClient))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultHttpRequestHandler"/> class that selects
    /// an <see cref="HttpClient"/> per request via a caller-supplied callback — for example, to route
    /// different URLs through differently authenticated clients.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback invoked for each request. The callback receives the <see cref="HttpRequestInfo"/>
    /// and should return a pre-configured <see cref="HttpClient"/> (e.g. with authentication or a custom
    /// transport). Return <see langword="null"/> to fall back to the handler's shared internal
    /// <see cref="HttpClient"/>.
    /// </param>
    /// <remarks>
    /// <para>
    /// <b>Redirects</b>: the callback is also invoked for redirect destinations when the internally owned client
    /// follows a redirect. It may reject a destination by throwing, or return <see langword="null"/> to continue
    /// using the internally owned client. Returning a client for a redirect destination causes an
    /// <see cref="HttpRequestException"/>; redirects cannot change the selected client.
    /// </para>
    /// <para>
    /// <b>Ownership</b>: the caller is solely responsible for the lifetime of clients returned by this
    /// callback. <see cref="DefaultHttpRequestHandler"/> will <b>not</b> dispose provider-returned
    /// clients; only the handler's internally owned fallback client is disposed by <see cref="DisposeAsync"/>.
    /// </para>
    /// <para>
    /// <b>Reuse</b>: callers are expected to cache and reuse clients (for example, keyed by base URL or
    /// auth scope) across requests. Returning a newly allocated <see cref="HttpClient"/> on every
    /// invocation will leak sockets and handler resources.
    /// </para>
    /// </remarks>
    public DefaultHttpRequestHandler(Func<HttpRequestInfo, CancellationToken, Task<HttpClient?>>? httpClientProvider)
    {
        this._httpClientProvider = httpClientProvider;
        this._ownedHttpClient = new Lazy<HttpClient>(CreateOwnedHttpClient, LazyThreadSafetyMode.ExecutionAndPublication);
    }

    private static Func<HttpRequestInfo, CancellationToken, Task<HttpClient?>> CreateSingleClientProvider(HttpClient httpClient)
    {
        if (httpClient is null)
        {
            throw new ArgumentNullException(nameof(httpClient));
        }

        return (_, _) => Task.FromResult<HttpClient?>(httpClient);
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

        using CancellationTokenSource? timeoutCts = request.Timeout is { } timeout && timeout > TimeSpan.Zero
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : null;

        timeoutCts?.CancelAfter(request.Timeout!.Value);

        CancellationToken effectiveToken = timeoutCts?.Token ?? cancellationToken;

        for (int redirectCount = 0; redirectCount <= MaxAutomaticRedirections; redirectCount++)
        {
            HttpClient? providedClient = null;
            if (this._httpClientProvider is not null)
            {
                providedClient = await this._httpClientProvider(currentRequest, effectiveToken).ConfigureAwait(false);
                if (redirectCount > 0 && providedClient is not null)
                {
                    throw new HttpRequestException("Redirects that change the HTTP client are not allowed.");
                }
            }

            if (providedClient is null)
            {
                ValidateDefaultDestination(currentUri);
            }

            HttpClient client = providedClient ?? this._ownedHttpClient.Value;

            using HttpRequestMessage httpRequest = BuildHttpRequestMessage(currentRequest);

            using HttpResponseMessage httpResponse = await client
                .SendAsync(httpRequest, HttpCompletionOption.ResponseHeadersRead, effectiveToken)
                .ConfigureAwait(false);

            if (providedClient is null &&
                TryCreateRedirectRequest(httpResponse, currentRequest, currentUri, out HttpRequestInfo? redirectRequest, out Uri? redirectUri))
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

    /// <inheritdoc/>
    public ValueTask DisposeAsync()
    {
        if (this._ownedHttpClient.IsValueCreated)
        {
            this._ownedHttpClient.Value.Dispose();
        }

        return default;
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

    private static HttpClient CreateOwnedHttpClient()
    {
#if NET
        return new HttpClient(CreateOwnedHttpMessageHandler());
#else
        throw new PlatformNotSupportedException(
            "The internally owned HTTP client requires .NET 8 or later. Supply an HttpClient with an explicit destination policy on this target framework.");
#endif
    }

#if NET
    internal static SocketsHttpHandler CreateOwnedHttpMessageHandler() =>
        new()
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            UseProxy = false,
            SslOptions = new SslClientAuthenticationOptions
            {
                CertificateRevocationCheckMode = X509RevocationMode.Online,
            },
            ConnectCallback = ConnectToPublicAddressAsync,
        };

    private static async ValueTask<Stream> ConnectToPublicAddressAsync(
        SocketsHttpConnectionContext context, CancellationToken cancellationToken)
    {
        IPAddress[] addresses = await Dns.GetHostAddressesAsync(context.DnsEndPoint.Host, cancellationToken).ConfigureAwait(false);
        if (addresses.Length == 0)
        {
            throw new HttpRequestException("The destination did not resolve to a public address.");
        }

        foreach (IPAddress address in addresses)
        {
            ValidatePublicAddress(address);
        }

        Socket socket = new(SocketType.Stream, ProtocolType.Tcp) { NoDelay = true };
        try
        {
            // Connect to the validated addresses without resolving the hostname again.
            await socket.ConnectAsync(addresses, context.DnsEndPoint.Port, cancellationToken).ConfigureAwait(false);
            return new NetworkStream(socket, ownsSocket: true);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }
#endif

    private static void ValidateDefaultDestination(Uri uri)
    {
        if (uri.IsLoopback)
        {
            throw new HttpRequestException("The internally owned HTTP client only allows public destinations.");
        }

        if (IPAddress.TryParse(uri.IdnHost.Trim('[', ']'), out IPAddress? address))
        {
            ValidatePublicAddress(address);
        }
    }

    private static void ValidatePublicAddress(IPAddress address)
    {
        if (address.IsIPv4MappedToIPv6)
        {
            address = address.MapToIPv4();
        }

        byte[] bytes = address.GetAddressBytes();
        bool isPublic;
        if (bytes.Length == 4)
        {
            // Exclude private and special-use ranges, including the host platform's service address.
            isPublic = bytes[0] is not (0 or 10 or 127) &&
                bytes[0] < 224 &&
                !(bytes[0] == 100 && bytes[1] is >= 64 and <= 127) &&
                !(bytes[0] == 169 && bytes[1] == 254) &&
                !(bytes[0] == 172 && bytes[1] is >= 16 and <= 31) &&
                !(bytes[0] == 192 && bytes[1] == 0 && bytes[2] is 0 or 2) &&
                !(bytes[0] == 192 && bytes[1] == 88 && bytes[2] == 99) &&
                !(bytes[0] == 192 && bytes[1] == 168) &&
                !(bytes[0] == 198 && bytes[1] is 18 or 19) &&
                !(bytes[0] == 198 && bytes[1] == 51 && bytes[2] == 100) &&
                !(bytes[0] == 203 && bytes[1] == 0 && bytes[2] == 113) &&
                !(bytes[0] == 168 && bytes[1] == 63 && bytes[2] == 129 && bytes[3] == 16);
        }
        else
        {
            // Allow global unicast except protocol assignments, documentation, and transition ranges.
            isPublic = address.ScopeId == 0 &&
                (bytes[0] & 0xE0) == 0x20 &&
                !(bytes[0] == 0x20 && bytes[1] == 0x01 && bytes[2] <= 0x01) &&
                !(bytes[0] == 0x20 && bytes[1] == 0x01 && bytes[2] == 0x0D && bytes[3] == 0xB8) &&
                !(bytes[0] == 0x20 && bytes[1] == 0x02) &&
                !(bytes[0] == 0x3F && bytes[1] == 0xFF && (bytes[2] & 0xF0) == 0);
        }

        if (!isPublic)
        {
            throw new HttpRequestException("The internally owned HTTP client only allows public destinations.");
        }
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
