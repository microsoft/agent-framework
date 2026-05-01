// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

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
/// The handler applies the per-request <see cref="HttpRequestInfo.Timeout"/> using a linked <see cref="CancellationTokenSource"/>
/// so it does not mutate <see cref="HttpClient.Timeout"/> on shared instances.
/// </para>
/// </remarks>
public sealed class DefaultHttpRequestHandler : IHttpRequestHandler, IAsyncDisposable
{
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
        this._ownedHttpClient = new Lazy<HttpClient>(() => new HttpClient(), LazyThreadSafetyMode.ExecutionAndPublication);
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

        HttpClient? providedClient = null;
        if (this._httpClientProvider is not null)
        {
            providedClient = await this._httpClientProvider(request, cancellationToken).ConfigureAwait(false);
        }

        HttpClient client = providedClient ?? this._ownedHttpClient.Value;

        using HttpRequestMessage httpRequest = BuildHttpRequestMessage(request);

        using CancellationTokenSource? timeoutCts = request.Timeout is { } timeout && timeout > TimeSpan.Zero
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : null;

        timeoutCts?.CancelAfter(request.Timeout!.Value);

        CancellationToken effectiveToken = timeoutCts?.Token ?? cancellationToken;

        using HttpResponseMessage httpResponse = await client
            .SendAsync(httpRequest, HttpCompletionOption.ResponseContentRead, effectiveToken)
            .ConfigureAwait(false);

        string? body = httpResponse.Content is null
            ? null
#if NET
            : await httpResponse.Content.ReadAsStringAsync(effectiveToken).ConfigureAwait(false);
#else
            : await httpResponse.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif

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
