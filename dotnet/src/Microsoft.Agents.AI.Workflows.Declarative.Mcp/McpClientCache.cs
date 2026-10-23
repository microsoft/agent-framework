// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.ExceptionServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Manages bounded workflow-scoped MCP sessions, concurrent creation, and active client leases.
/// </summary>
internal sealed class McpClientCache : IAsyncDisposable
{
    private static readonly OperationCanceledException s_clientCreationCancelledException =
        new("The MCP client creator was cancelled.");

    private readonly McpClientFactory _clientFactory;
    private readonly McpClientLifetime _lifetime;
    private readonly Func<McpClientConnection, ValueTask> _clientConnectionDisposer;
    private readonly Dictionary<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash), CachedClient> _clients = [];
    private readonly Dictionary<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash), TaskCompletionSource<CachedClient>> _clientCreations = [];
    private readonly HashSet<TaskCompletionSource<bool>> _clientCreationLifetimes = [];
    private readonly LinkedList<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> _clientLru = [];
    private readonly HashSet<CachedClient> _retiredClients = [];
    private readonly SemaphoreSlim _clientCreationSemaphore;
    private readonly int _clientCacheMaxSize;

    public McpClientCache(
        McpClientFactory clientFactory,
        McpClientLifetime lifetime,
        int clientCacheMaxSize,
        Func<McpClientConnection, ValueTask>? clientConnectionDisposer)
    {
        if (clientCacheMaxSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(clientCacheMaxSize), "The MCP client cache size must be positive.");
        }

        this._clientFactory = clientFactory;
        this._lifetime = lifetime;
        this._clientConnectionDisposer = clientConnectionDisposer ?? (connection => connection.DisposeAsync());
        this._clientCacheMaxSize = clientCacheMaxSize;
        this._clientCreationSemaphore = new(clientCacheMaxSize, clientCacheMaxSize);
    }

    public async Task<T> InvokeAsync<T>(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        string? connectionName,
        string workflowSessionId,
        Func<McpClient, Task<T>> invocation,
        CancellationToken cancellationToken)
    {
        CachedClient cachedClient = await this.AcquireClientAsync(
            serverUrl, serverLabel, headers, connectionName, workflowSessionId, cancellationToken).ConfigureAwait(false);
        try
        {
            return await invocation(cachedClient.Connection.Client).ConfigureAwait(false);
        }
        finally
        {
            await this.ReleaseClientAsync(cachedClient).ConfigureAwait(false);
        }
    }

    public async ValueTask DisposeAsync()
    {
        this._lifetime.ThrowIfProviderInvocationActive();

        Task providerInvocations;
        List<Task<bool>> clientCreationLifetimes;
        await this._lifetime.SyncLock.WaitAsync().ConfigureAwait(false);
        try
        {
            providerInvocations = this._lifetime.BeginDisposalAsync();
            clientCreationLifetimes = this._clientCreationLifetimes.Select(source => source.Task).ToList();
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        await providerInvocations.ConfigureAwait(false);

        Exception? clientCreationException = null;
        try
        {
            await Task.WhenAll(clientCreationLifetimes).ConfigureAwait(false);
        }
        catch (Exception exception) when (!McpClientLifetime.IsFatalException(exception))
        {
            clientCreationException = exception;
        }

        List<CachedClient> cachedClients;
        List<CachedClient> clientsToDispose = [];
        await this._lifetime.SyncLock.WaitAsync().ConfigureAwait(false);
        try
        {
            cachedClients = [.. this._clients.Values, .. this._retiredClients];
            foreach (CachedClient client in cachedClients)
            {
                client.Evicted = true;
                this._retiredClients.Add(client);
                if (client.ActiveInvocations == 0 && !client.DisposalClaimed)
                {
                    client.DisposalClaimed = true;
                    clientsToDispose.Add(client);
                }
            }

            this._clients.Clear();
            this._clientLru.Clear();
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        Exception? clientCleanupException = null;
        try
        {
            await McpClientLifetime.DrainCleanupAsync(
                clientsToDispose.Select(client => this.DisposeCachedClientAsync(client)),
                cachedClients.Select(client => client.Disposed.Task)).ConfigureAwait(false);
        }
        catch (Exception exception) when (!McpClientLifetime.IsFatalException(exception))
        {
            clientCleanupException = exception;
        }
        finally
        {
            this._lifetime.Dispose();
            this._clientCreationSemaphore.Dispose();
        }

        if (clientCreationException is not null)
        {
            ExceptionDispatchInfo.Capture(clientCreationException).Throw();
        }

        if (clientCleanupException is not null)
        {
            ExceptionDispatchInfo.Capture(clientCleanupException).Throw();
        }
    }

    private async Task<CachedClient> AcquireClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        string? connectionName,
        string workflowSessionId,
        CancellationToken cancellationToken)
    {
        string trimmedUrl = serverUrl.Trim();
        var clientCacheKey = BuildCacheKey(workflowSessionId, trimmedUrl, serverLabel, connectionName, headers);
        CachedClient? clientToDispose = null;
        TaskCompletionSource<CachedClient>? clientCreation;
        TaskCompletionSource<bool>? clientCreationLifetime = null;
        bool ownsClientCreation = false;

        await this._lifetime.SyncLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            this._lifetime.ThrowIfDisposing();
            if (this._clients.TryGetValue(clientCacheKey, out CachedClient? existingClient))
            {
                existingClient.ActiveInvocations++;
                this._clientLru.Remove(existingClient.LruNode);
                this._clientLru.AddLast(existingClient.LruNode);
                return existingClient;
            }

            if (!this._clientCreations.TryGetValue(clientCacheKey, out clientCreation))
            {
                if (this._clients.Count + this._retiredClients.Count + this._clientCreations.Count >= this._clientCacheMaxSize)
                {
                    LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)>? idleNode =
                        this._clientLru.First;
                    while (idleNode is not null && this._clients[idleNode.Value].ActiveInvocations != 0)
                    {
                        idleNode = idleNode.Next;
                    }

                    if (idleNode is null)
                    {
                        throw new InvalidOperationException("MCP client capacity is exhausted; retry when an active invocation completes.");
                    }

                    clientToDispose = this._clients[idleNode.Value];
                    this._clients.Remove(idleNode.Value);
                    this._clientLru.Remove(idleNode);
                    clientToDispose.Evicted = true;
                    clientToDispose.DisposalClaimed = true;
                    this._retiredClients.Add(clientToDispose);
                }

                clientCreation = new(TaskCreationOptions.RunContinuationsAsynchronously);
                this._clientCreations[clientCacheKey] = clientCreation;
                clientCreationLifetime = new(TaskCreationOptions.RunContinuationsAsynchronously);
                this._clientCreationLifetimes.Add(clientCreationLifetime);
                ownsClientCreation = true;
            }
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        if (!ownsClientCreation)
        {
            try
            {
                await WaitForClientCreationAsync(clientCreation.Task, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException exception)
                when (ReferenceEquals(exception, s_clientCreationCancelledException))
            {
                return await this.AcquireClientAsync(
                    serverUrl, serverLabel, headers, connectionName, workflowSessionId, cancellationToken).ConfigureAwait(false);
            }

            return await this.AcquireClientAsync(
                serverUrl, serverLabel, headers, connectionName, workflowSessionId, cancellationToken).ConfigureAwait(false);
        }

        TaskCompletionSource<bool> ownedClientCreationLifetime = clientCreationLifetime ??
            throw new InvalidOperationException("Missing MCP client creation lifetime.");
        McpClientConnection? connection = null;
        bool creationSemaphoreEntered = false;
        Exception? clientCreationCleanupException = null;
        try
        {
            if (clientToDispose is not null)
            {
                try
                {
                    await this.DisposeCachedClientAsync(clientToDispose).ConfigureAwait(false);
                }
                catch (Exception cleanupException)
                {
                    clientCreationCleanupException = cleanupException;
                    throw;
                }
            }

            await this._clientCreationSemaphore.WaitAsync(cancellationToken).ConfigureAwait(false);
            creationSemaphoreEntered = true;
            await this._lifetime.SyncLock.WaitAsync(cancellationToken).ConfigureAwait(false);
            try
            {
                this._lifetime.ThrowIfDisposing();
            }
            finally
            {
                this._lifetime.SyncLock.Release();
            }

            connection = await this._clientFactory.CreateClientAsync(
                trimmedUrl, serverLabel, headers, cancellationToken,
                cleanupException => clientCreationCleanupException = cleanupException).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            Exception sharedCreationException =
                exception is OperationCanceledException && cancellationToken.IsCancellationRequested
                    ? s_clientCreationCancelledException
                    : exception;
            try
            {
                await this.CompleteClientCreationFailureAsync(
                    clientCacheKey, clientCreation, sharedCreationException).ConfigureAwait(false);
            }
            finally
            {
                if (creationSemaphoreEntered)
                {
                    this._clientCreationSemaphore.Release();
                    creationSemaphoreEntered = false;
                }

                await this.CompleteClientCreationLifetimeAsync(
                    ownedClientCreationLifetime, clientCreationCleanupException).ConfigureAwait(false);
            }

            throw;
        }

        ObjectDisposedException? disposedException = null;
        CachedClient? result = null;
        await this._lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            this._clientCreations.Remove(clientCacheKey);
            if (this._lifetime.IsDisposing)
            {
                disposedException = new ObjectDisposedException(nameof(DefaultMcpToolHandler));
            }
            else
            {
                LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> node =
                    this._clientLru.AddLast(clientCacheKey);
                CachedClient newClient = new(connection, node) { ActiveInvocations = 1 };
                connection = null;
                this._clients[clientCacheKey] = newClient;

                result = newClient;
                clientCreation.TrySetResult(newClient);
            }
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        try
        {
            if (connection is not null)
            {
                await this._clientConnectionDisposer(connection).ConfigureAwait(false);
            }

            if (disposedException is not null)
            {
                clientCreation.TrySetException(disposedException);
                throw disposedException;
            }
        }
        catch (Exception exception)
        {
            if (disposedException is not null && !ReferenceEquals(exception, disposedException))
            {
                clientCreation.TrySetException(exception);
                clientCreationCleanupException = exception;
            }

            if (result is not null)
            {
                await this.ReleaseClientAsync(result).ConfigureAwait(false);
            }

            throw;
        }
        finally
        {
            if (creationSemaphoreEntered)
            {
                this._clientCreationSemaphore.Release();
            }

            await this.CompleteClientCreationLifetimeAsync(
                ownedClientCreationLifetime, clientCreationCleanupException).ConfigureAwait(false);
        }

        return result ?? throw new InvalidOperationException("Failed to acquire MCP client.");
    }

    private static async Task WaitForClientCreationAsync(Task<CachedClient> clientCreation, CancellationToken cancellationToken)
    {
        if (!cancellationToken.CanBeCanceled || clientCreation.IsCompleted)
        {
            await clientCreation.ConfigureAwait(false);
            return;
        }

        TaskCompletionSource<bool> cancellation = new(TaskCreationOptions.RunContinuationsAsynchronously);
        using CancellationTokenRegistration registration = cancellationToken.Register(
            static state => ((TaskCompletionSource<bool>)state!).TrySetResult(true),
            cancellation);

        if (await Task.WhenAny(clientCreation, cancellation.Task).ConfigureAwait(false) == cancellation.Task)
        {
            cancellationToken.ThrowIfCancellationRequested();
        }

        await clientCreation.ConfigureAwait(false);
    }

    private async Task CompleteClientCreationFailureAsync(
        (string WorkflowSession, string Url, string Label, string Connection, string HeadersHash) clientCacheKey,
        TaskCompletionSource<CachedClient> clientCreation,
        Exception exception)
    {
        await this._lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            if (this._clientCreations.TryGetValue(clientCacheKey, out TaskCompletionSource<CachedClient>? existingCreation) &&
                ReferenceEquals(existingCreation, clientCreation))
            {
                this._clientCreations.Remove(clientCacheKey);
            }

            clientCreation.TrySetException(exception);
            _ = clientCreation.Task.Exception;
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }
    }

    private async Task CompleteClientCreationLifetimeAsync(
        TaskCompletionSource<bool> clientCreationLifetime,
        Exception? cleanupException = null)
    {
        await this._lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            this._clientCreationLifetimes.Remove(clientCreationLifetime);
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        if (cleanupException is not null)
        {
            clientCreationLifetime.TrySetException(cleanupException);
        }
        else
        {
            clientCreationLifetime.TrySetResult(true);
        }
    }

    private async ValueTask ReleaseClientAsync(CachedClient client)
    {
        bool dispose = false;
        await this._lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            client.ActiveInvocations--;
            if (client.ActiveInvocations == 0 && client.Evicted && !client.DisposalClaimed)
            {
                client.DisposalClaimed = true;
                dispose = true;
            }
        }
        finally
        {
            this._lifetime.SyncLock.Release();
        }

        if (dispose)
        {
            await this.DisposeCachedClientAsync(client).ConfigureAwait(false);
        }
    }

    private async Task DisposeCachedClientAsync(CachedClient client)
    {
        Exception? cleanupException = null;
        try
        {
            await this._clientConnectionDisposer(client.Connection).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            cleanupException = exception;
            throw;
        }
        finally
        {
            await this._lifetime.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
            try
            {
                this._retiredClients.Remove(client);
            }
            finally
            {
                this._lifetime.SyncLock.Release();
            }

            if (cleanupException is not null)
            {
                client.Disposed.TrySetException(cleanupException);
            }
            else
            {
                client.Disposed.TrySetResult(true);
            }
        }
    }

    /// <summary>
    /// Builds the per-client cache key as a 5-tuple of
    /// (workflowSessionId, trimmed serverUrl, serverLabel, connectionName, headers hash).
    /// All five components participate so that separate workflow sessions and callers using
    /// different labels/connections/headers receive distinct <see cref="McpClient"/> instances
    /// even when targeting the same URL.
    /// </summary>
    internal static (string WorkflowSession, string Url, string Label, string Connection, string HeadersHash) BuildCacheKey(
        string workflowSessionId,
        string trimmedUrl,
        string? serverLabel,
        string? connectionName,
        IDictionary<string, string>? headers) =>
        (workflowSessionId, trimmedUrl, serverLabel ?? string.Empty, connectionName ?? string.Empty, ComputeHeadersHash(headers));

    /// <summary>
    /// Computes a deterministic, order-independent hash of the header set.
    /// Header names are lower-cased for case-insensitive matching (RFC 7230 §3.2).
    /// Header values remain case-sensitive (RFC 7235 — credentials are case-sensitive).
    /// </summary>
#pragma warning disable CA1308 // RFC 7230 §3.2 requires lower-cased header names for case-insensitive comparison; CA1308's uppercase preference does not apply here
    internal static string ComputeHeadersHash(IDictionary<string, string>? headers)
    {
        if (headers is null || headers.Count == 0)
        {
            return string.Empty;
        }

        // Sort by lower-cased key for deterministic ordering, preserving value case.
        SortedDictionary<string, string> sorted = new(StringComparer.Ordinal);
        foreach (KeyValuePair<string, string> header in headers)
        {
            sorted[header.Key.ToLowerInvariant()] = header.Value;
        }

        StringBuilder payload = new();
        foreach (KeyValuePair<string, string> kvp in sorted)
        {
            payload.Append(kvp.Key).Append(':').Append(kvp.Value).Append('\n');
        }

        byte[] inputBytes = Encoding.UTF8.GetBytes(payload.ToString());
#if NET5_0_OR_GREATER
        byte[] hashBytes = SHA256.HashData(inputBytes);
#else
        using SHA256 sha256 = SHA256.Create();
        byte[] hashBytes = sha256.ComputeHash(inputBytes);
#endif

        // Convert to hex string (compatible with net472/netstandard2.0)
        StringBuilder hex = new(hashBytes.Length * 2);
        foreach (byte b in hashBytes)
        {
            hex.Append(b.ToString("X2", System.Globalization.CultureInfo.InvariantCulture));
        }

        return hex.ToString();
    }
#pragma warning restore CA1308

    private sealed class CachedClient(
        McpClientConnection connection,
        LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> lruNode)
    {
        public McpClientConnection Connection { get; } = connection;

        public LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> LruNode { get; } = lruNode;

        public TaskCompletionSource<bool> Disposed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int ActiveInvocations { get; set; }

        public bool Evicted { get; set; }

        public bool DisposalClaimed { get; set; }
    }
}
