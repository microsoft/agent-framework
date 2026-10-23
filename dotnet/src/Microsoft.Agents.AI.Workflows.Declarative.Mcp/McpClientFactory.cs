// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Creates MCP connections and manages ownership of their HTTP clients.
/// </summary>
internal sealed class McpClientFactory(
    Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider,
    Func<HttpMessageHandler> httpMessageHandlerFactory,
    McpClientLifetime lifetime)
{
    private readonly Func<HttpMessageHandler> _httpMessageHandlerFactory = Throw.IfNull(httpMessageHandlerFactory);
    private readonly Dictionary<string, OwnedHttpClient> _ownedHttpClients = [];

    public bool HasHttpClientProvider => httpClientProvider is not null;

    public Task<T> InvokeProviderAsync<T>(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        Func<McpClient, Task<T>> invocation,
        CancellationToken cancellationToken)
        => lifetime.InvokeProviderAsync(async () =>
        {
            McpClientConnection connection = await this.CreateClientAsync(
                serverUrl.Trim(), serverLabel, headers, cancellationToken).ConfigureAwait(false);
            await using (connection.ConfigureAwait(false))
            {
                return await invocation(connection.Client).ConfigureAwait(false);
            }
        }, cancellationToken);

    public async Task<McpClientConnection> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        CancellationToken cancellationToken,
        Action<Exception>? reportCleanupFailure = null)
    {
        HttpClient? httpClient = null;
        bool ownsHttpClient = false;
        OwnedHttpClientLease? ownedHttpClientLease = null;

        if (httpClientProvider is not null)
        {
            httpClient = await httpClientProvider(serverUrl, cancellationToken).ConfigureAwait(false);
        }

        if (httpClient is null && httpClientProvider is not null)
        {
            httpClient = this.CreatePinnedHttpClient(serverUrl);
            ownsHttpClient = true;
        }
        else if (httpClient is null)
        {
            ownedHttpClientLease = await this.AcquireOwnedHttpClientAsync(serverUrl, cancellationToken).ConfigureAwait(false);
            httpClient = ownedHttpClientLease.Client;
        }

        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = new Uri(serverUrl),
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = headers,
            // Use Streamable HTTP rather than AutoDetect so the client does not negotiate down to the
            // legacy HTTP+SSE transport, which trusts a server-advertised message endpoint. That
            // server-controlled endpoint is the primary vector for redirecting the Authorization token
            // to a different origin; Streamable HTTP keeps every request on the configured origin.
            TransportMode = HttpTransportMode.StreamableHttp
        };

        HttpClientTransport? transport = null;
        try
        {
            HttpClient resolvedHttpClient = httpClient ?? throw new InvalidOperationException("Failed to resolve MCP HTTP client.");
            transport = new(transportOptions, resolvedHttpClient, ownsHttpClient: ownsHttpClient);
            McpClient client = await McpClient.CreateAsync(transport, cancellationToken: cancellationToken).ConfigureAwait(false);
            McpClientConnection connection = new(client, transport, ownedHttpClientLease);
            ownedHttpClientLease = null;
            return connection;
        }
        catch
        {
            try
            {
                try
                {
                    if (transport is not null)
                    {
                        await McpClientConnection.DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
                    }
                }
                finally
                {
                    if (ownedHttpClientLease is not null)
                    {
                        await ownedHttpClientLease.DisposeAsync().ConfigureAwait(false);
                    }
                }
            }
            catch (Exception cleanupException)
            {
                reportCleanupFailure?.Invoke(cleanupException);
                throw;
            }

            throw;
        }
    }

    private async Task<OwnedHttpClientLease> AcquireOwnedHttpClientAsync(
        string serverUrl,
        CancellationToken cancellationToken)
    {
        await lifetime.SyncLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!this._ownedHttpClients.TryGetValue(serverUrl, out OwnedHttpClient? entry))
            {
                entry = new(this.CreatePinnedHttpClient(serverUrl));
                this._ownedHttpClients[serverUrl] = entry;
            }

            entry.ReferenceCount++;
            return new(this, serverUrl, entry.Client);
        }
        finally
        {
            lifetime.SyncLock.Release();
        }
    }

    private async ValueTask ReleaseOwnedHttpClientAsync(string serverUrl)
    {
        HttpClient? clientToDispose = null;
        await lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            OwnedHttpClient entry = this._ownedHttpClients[serverUrl];
            if (--entry.ReferenceCount == 0)
            {
                this._ownedHttpClients.Remove(serverUrl);
                clientToDispose = entry.Client;
            }
        }
        finally
        {
            lifetime.SyncLock.Release();
        }

        try
        {
            clientToDispose?.Dispose();
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            Trace.TraceWarning("Failed to dispose MCP HTTP client: {0}", exception);
        }
    }

    private HttpClient CreatePinnedHttpClient(string serverUrl)
    {
        // Pin credential headers to the configured server origin as defense-in-depth. Forcing
        // StreamableHttp already removes the primary vector (a server-advertised cross-origin
        // SSE message endpoint), and AllowAutoRedirect=false blocks auto-redirects. This handler is the
        // backstop: it guarantees the Authorization token and other credentials never leave the pinned
        // origin even if a future change re-enables AutoDetect or redirects, or the SDK constructs a
        // request to a new URI (AdditionalHeaders are re-stamped by the transport, so HttpClient's own
        // redirect header-stripping does not cover them).
        OriginPinningHandler pinningHandler = new(new Uri(serverUrl)) { InnerHandler = this._httpMessageHandlerFactory() };
        return new HttpClient(pinningHandler);
    }

    internal static HttpMessageHandler CreateHttpMessageHandler() =>
        new HttpClientHandler
        {
            // Keep cookies out of pooled transport state and prevent credential-bearing redirects.
            UseCookies = false,
            AllowAutoRedirect = false,
            CheckCertificateRevocationList = true
        };

    private sealed class OwnedHttpClient(HttpClient client)
    {
        public HttpClient Client { get; } = client;

        public int ReferenceCount { get; set; }
    }

    private sealed class OwnedHttpClientLease(
        McpClientFactory owner,
        string serverUrl,
        HttpClient client) : IAsyncDisposable
    {
        private bool _disposed;

        public HttpClient Client { get; } = client;

        public async ValueTask DisposeAsync()
        {
            if (!this._disposed)
            {
                this._disposed = true;
                await owner.ReleaseOwnedHttpClientAsync(serverUrl).ConfigureAwait(false);
            }
        }
    }
}
