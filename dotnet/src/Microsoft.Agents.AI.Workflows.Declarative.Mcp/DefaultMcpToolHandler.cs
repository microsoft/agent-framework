// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.ExceptionServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Default implementation of <see cref="IMcpToolHandler"/> using the MCP C# SDK.
/// </summary>
/// <remarks>
/// This provider supports per-server authentication via the <c>httpClientProvider</c> callback.
/// The callback allows different MCP servers to use different authentication configurations by returning
/// a pre-configured <see cref="HttpClient"/> for each server.
/// Provider-backed invocations create and dispose a separate MCP session for every call, including
/// <c>tools/list</c>, because provider authentication is not represented in the session cache key.
/// Without a provider, workflow invocations are cached by workflow session, server URL, label,
/// connection name, and explicit headers in a bounded least-recently-used cache. Evicted sessions
/// are disposed after their active invocations finish.
/// Non-cancellation cleanup failures are reported through <see cref="Trace"/> warnings without replacing
/// the invocation result or error.
/// </remarks>
public sealed class DefaultMcpToolHandler : IWorkflowScopedMcpToolHandler, IAsyncDisposable
{
    private const int DefaultClientCacheMaxSize = 32;
    private const string FilenameAdditionalPropertyName = "filename";

    /// <summary>
    /// Reserved <c>toolName</c> value that maps an <see cref="IMcpToolHandler.InvokeToolAsync"/> request
    /// to the MCP protocol <c>tools/list</c> discovery operation.
    /// </summary>
    public const string ListToolsToolName = "tools/list";

    private static readonly JsonWriterOptions s_toolListJsonWriterOptions = new() { Indented = true };
    private static readonly OperationCanceledException s_clientCreationCancelledException =
        new("The MCP client creator was cancelled.");

    private readonly Func<string, CancellationToken, Task<HttpClient?>>? _httpClientProvider;
    private readonly Func<HttpMessageHandler> _httpMessageHandlerFactory;
    private readonly Func<ClientConnection, ValueTask> _clientConnectionDisposer;
    private readonly Dictionary<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash), CachedClient> _clients = [];
    private readonly Dictionary<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash), TaskCompletionSource<CachedClient>> _clientCreations = [];
    private readonly HashSet<TaskCompletionSource<bool>> _clientCreationLifetimes = [];
    private readonly LinkedList<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> _clientLru = [];
    private readonly HashSet<CachedClient> _retiredClients = [];
    private readonly Dictionary<string, OwnedHttpClient> _ownedHttpClients = [];
    private readonly SemaphoreSlim _clientLock = new(1, 1);
    private readonly SemaphoreSlim _clientCreationSemaphore;
    private readonly int _clientCacheMaxSize;
    private readonly AsyncLocal<ProviderInvocationContext?> _providerInvocationContext = new();
    private TaskCompletionSource<bool>? _providerInvocationsDrained;
    private int _activeProviderInvocations;
    private bool _disposing;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback that provides an <see cref="HttpClient"/> for each MCP server.
    /// The callback receives (serverUrl, cancellationToken) and should return an HttpClient
    /// configured with any required authentication. Return <see langword="null"/> to use a default HttpClient with no auth.
    /// <para>
    /// The callback is invoked for each tool invocation. MCP sessions are not cached when a callback is
    /// configured, even if it returns the same client or <see langword="null"/>. This adds session setup
    /// per call and does not preserve server-side session state between calls. Supplied HTTP clients
    /// remain caller-owned. Applications requiring session continuity should provide an
    /// <see cref="IMcpToolHandler"/> with an explicitly scoped authentication and session lifetime.
    /// </para>
    /// <para>
    /// Security: HttpClients created by this handler pin credential headers to the configured server
    /// origin and disable auto-redirect. When you supply your own <see cref="HttpClient"/>, you are
    /// responsible for equivalent protection — attach credentials only for the configured server origin
    /// (for example via a <see cref="DelegatingHandler"/>) so a server-advertised endpoint or redirect on
    /// a different origin cannot capture the Authorization token.
    /// </para>
    /// </param>
    public DefaultMcpToolHandler(Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider = null)
        : this(httpClientProvider, CreateHttpMessageHandler)
    {
    }

    internal DefaultMcpToolHandler(
        Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider,
        Func<HttpMessageHandler> httpMessageHandlerFactory,
        int clientCacheMaxSize = DefaultClientCacheMaxSize,
        Func<ClientConnection, ValueTask>? clientConnectionDisposer = null)
    {
        if (clientCacheMaxSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(clientCacheMaxSize), "The MCP client cache size must be positive.");
        }

        this._httpClientProvider = httpClientProvider;
        this._httpMessageHandlerFactory = Throw.IfNull(httpMessageHandlerFactory);
        this._clientConnectionDisposer = clientConnectionDisposer ?? (connection => connection.DisposeAsync());
        this._clientCacheMaxSize = clientCacheMaxSize;
        this._clientCreationSemaphore = new(clientCacheMaxSize, clientCacheMaxSize);
    }

    /// <inheritdoc/>
    public async Task<McpServerToolResultContent> InvokeToolAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, object?>? arguments,
        IDictionary<string, string>? headers,
        string? connectionName,
        CancellationToken cancellationToken = default)
        => await this.InvokeToolInWorkflowSessionAsync(
            serverUrl,
            serverLabel,
            toolName,
            arguments,
            headers,
            connectionName,
            workflowSessionId: string.Empty,
            cancellationToken).ConfigureAwait(false);

    /// <inheritdoc/>
    public async Task<McpServerToolResultContent> InvokeToolInWorkflowSessionAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, object?>? arguments,
        IDictionary<string, string>? headers,
        string? connectionName,
        string workflowSessionId,
        CancellationToken cancellationToken = default)
    {
        if (IsListToolsToolName(toolName))
        {
            ThrowIfListToolsArgumentsSpecified(arguments);
        }

        if (this._httpClientProvider is not null)
        {
            TaskCompletionSource<bool> invocationCompleted = new(TaskCreationOptions.RunContinuationsAsynchronously);
            await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
            try
            {
                this.ThrowIfDisposing();
                if (this._activeProviderInvocations++ == 0)
                {
                    this._providerInvocationsDrained = new(TaskCreationOptions.RunContinuationsAsynchronously);
                }
            }
            finally
            {
                this._clientLock.Release();
            }

            ProviderInvocationContext? previousInvocation = this._providerInvocationContext.Value;
            this._providerInvocationContext.Value = new(invocationCompleted.Task, previousInvocation);
            try
            {
                ClientConnection invocationClient = await this.CreateClientAsync(
                    serverUrl.Trim(), serverLabel, headers, cancellationToken).ConfigureAwait(false);
                await using (invocationClient.ConfigureAwait(false))
                {
                    return await InvokeClientAsync(invocationClient.Client, toolName, arguments, cancellationToken).ConfigureAwait(false);
                }
            }
            finally
            {
                await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
                try
                {
                    if (--this._activeProviderInvocations == 0)
                    {
                        this._providerInvocationsDrained!.SetResult(true);
                    }
                }
                finally
                {
                    invocationCompleted.SetResult(true);
                    this._providerInvocationContext.Value = previousInvocation;
                    this._clientLock.Release();
                }
            }
        }

        CachedClient cachedClient = await this.AcquireClientAsync(
            serverUrl, serverLabel, headers, connectionName, workflowSessionId, cancellationToken).ConfigureAwait(false);
        try
        {
            return await InvokeClientAsync(cachedClient.Connection.Client, toolName, arguments, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            await this.ReleaseClientAsync(cachedClient).ConfigureAwait(false);
        }
    }

    private static async Task<McpServerToolResultContent> InvokeClientAsync(
        McpClient client,
        string toolName,
        IDictionary<string, object?>? arguments,
        CancellationToken cancellationToken)
    {
        if (IsListToolsToolName(toolName))
        {
            IList<McpClientTool> tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
            return CreateListToolsResultContent(tools.Select(tool => tool.ProtocolTool));
        }

        McpServerToolResultContent resultContent = new(Guid.NewGuid().ToString());

        // Convert IDictionary to IReadOnlyDictionary for CallToolAsync
        IReadOnlyDictionary<string, object?>? readOnlyArguments = arguments is null
            ? null
            : arguments as IReadOnlyDictionary<string, object?> ?? new Dictionary<string, object?>(arguments);

        CallToolResult result = await client.CallToolAsync(
            toolName,
            readOnlyArguments,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        // Map MCP content blocks to MEAI AIContent types
        PopulateResultContent(resultContent, result);

        return resultContent;
    }

    internal static bool IsListToolsToolName(string toolName) =>
        string.Equals(toolName, ListToolsToolName, StringComparison.Ordinal);

    internal static McpServerToolResultContent CreateListToolsResultContent(IEnumerable<Tool> tools)
    {
        Throw.IfNull(tools);

        McpServerToolResultContent resultContent = new(Guid.NewGuid().ToString())
        {
            Outputs = []
        };

        resultContent.Outputs.Add(new TextContent(SerializeToolsList(tools)));

        return resultContent;
    }

    /// <inheritdoc/>
    /// <exception cref="InvalidOperationException">
    /// Disposal is requested from an active provider-backed invocation, including a child execution context.
    /// Dispose the handler from its owning scope instead.
    /// </exception>
    public async ValueTask DisposeAsync()
    {
        for (ProviderInvocationContext? context = this._providerInvocationContext.Value; context is not null; context = context.Parent)
        {
            if (!context.Completion.IsCompleted)
            {
                throw new InvalidOperationException("Cannot dispose the MCP handler from an active provider-backed invocation.");
            }
        }

        Task? providerInvocations;
        List<Task<bool>> clientCreationLifetimes;
        await this._clientLock.WaitAsync().ConfigureAwait(false);
        try
        {
            this.ThrowIfDisposing();
            this._disposing = true;
            providerInvocations = this._providerInvocationsDrained?.Task;
            clientCreationLifetimes = this._clientCreationLifetimes.Select(source => source.Task).ToList();
        }
        finally
        {
            this._clientLock.Release();
        }

        if (providerInvocations is not null)
        {
            await providerInvocations.ConfigureAwait(false);
        }

        Exception? clientCreationException = null;
        try
        {
            await Task.WhenAll(clientCreationLifetimes).ConfigureAwait(false);
        }
        catch (Exception exception) when (!IsFatalException(exception))
        {
            clientCreationException = exception;
        }

        List<CachedClient> cachedClients;
        List<CachedClient> clientsToDispose = [];
        await this._clientLock.WaitAsync().ConfigureAwait(false);
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
            this._clientLock.Release();
        }

        Exception? clientCleanupException = null;
        try
        {
            await DrainCleanupAsync(
                clientsToDispose.Select(client => this.DisposeCachedClientAsync(client)),
                cachedClients.Select(client => client.Disposed.Task)).ConfigureAwait(false);
        }
        catch (Exception exception) when (!IsFatalException(exception))
        {
            clientCleanupException = exception;
        }
        finally
        {
            this._clientLock.Dispose();
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

    internal static async Task DrainCleanupAsync(IEnumerable<Task> cleanupTasks, IEnumerable<Task> completionTasks)
    {
        Exception? cleanupException = null;
        try
        {
            await Task.WhenAll(cleanupTasks).ConfigureAwait(false);
        }
        catch (Exception exception) when (!IsFatalException(exception))
        {
            cleanupException = exception;
        }

        await Task.WhenAll(completionTasks).ConfigureAwait(false);

        if (cleanupException is not null)
        {
            ExceptionDispatchInfo.Capture(cleanupException).Throw();
        }
    }

    private static bool IsFatalException(Exception exception) =>
        exception is OutOfMemoryException and not InsufficientMemoryException
        or StackOverflowException
        or AccessViolationException
        or AppDomainUnloadedException
        or BadImageFormatException
        or CannotUnloadAppDomainException
        or InvalidProgramException
        or ThreadAbortException;

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
        Justification = "The helper is not available on .NET Framework or .NET Standard 2.0.")]
    private void ThrowIfDisposing()
    {
        if (this._disposing)
        {
            throw new ObjectDisposedException(nameof(DefaultMcpToolHandler));
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

        await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            this.ThrowIfDisposing();
            if (this._clients.TryGetValue(clientCacheKey, out CachedClient? existingClient))
            {
                existingClient.ActiveInvocations++;
                this._clientLru.Remove(existingClient.LruNode);
                this._clientLru.AddLast(existingClient.LruNode);
                return existingClient;
            }

            if (!this._clientCreations.TryGetValue(clientCacheKey, out clientCreation))
            {
                clientCreation = new(TaskCreationOptions.RunContinuationsAsynchronously);
                this._clientCreations[clientCacheKey] = clientCreation;
                clientCreationLifetime = new(TaskCreationOptions.RunContinuationsAsynchronously);
                this._clientCreationLifetimes.Add(clientCreationLifetime);
                ownsClientCreation = true;
            }
        }
        finally
        {
            this._clientLock.Release();
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
        ClientConnection? connection = null;
        bool creationSemaphoreEntered = false;
        Exception? clientCreationCleanupException = null;
        try
        {
            await this._clientCreationSemaphore.WaitAsync(cancellationToken).ConfigureAwait(false);
            creationSemaphoreEntered = true;
            await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
            try
            {
                this.ThrowIfDisposing();
            }
            finally
            {
                this._clientLock.Release();
            }

            connection = await this.CreateClientAsync(
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
        await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            this._clientCreations.Remove(clientCacheKey);
            if (this._disposing)
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

                if (this._clients.Count > this._clientCacheMaxSize)
                {
                    LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> evictedNode =
                        this._clientLru.First!;
                    this._clientLru.RemoveFirst();
                    CachedClient evictedClient = this._clients[evictedNode.Value];
                    this._clients.Remove(evictedNode.Value);
                    evictedClient.Evicted = true;
                    this._retiredClients.Add(evictedClient);
                    if (evictedClient.ActiveInvocations == 0)
                    {
                        evictedClient.DisposalClaimed = true;
                        clientToDispose = evictedClient;
                    }
                }

                result = newClient;
                clientCreation.TrySetResult(newClient);
            }
        }
        finally
        {
            this._clientLock.Release();
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

            if (clientToDispose is not null)
            {
                await this.DisposeCachedClientAsync(clientToDispose).ConfigureAwait(false);
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
        await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
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
            this._clientLock.Release();
        }
    }

    private async Task CompleteClientCreationLifetimeAsync(
        TaskCompletionSource<bool> clientCreationLifetime,
        Exception? cleanupException = null)
    {
        await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            this._clientCreationLifetimes.Remove(clientCreationLifetime);
        }
        finally
        {
            this._clientLock.Release();
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
        await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
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
            this._clientLock.Release();
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
            await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
            try
            {
                this._retiredClients.Remove(client);
            }
            finally
            {
                this._clientLock.Release();
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

    private async Task<ClientConnection> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        CancellationToken cancellationToken,
        Action<Exception>? reportCleanupFailure = null)
    {
        HttpClient? httpClient = null;
        bool ownsHttpClient = false;
        OwnedHttpClientLease? ownedHttpClientLease = null;

        if (this._httpClientProvider is not null)
        {
            httpClient = await this._httpClientProvider(serverUrl, cancellationToken).ConfigureAwait(false);
        }

        if (httpClient is null && this._httpClientProvider is not null)
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
            ClientConnection connection = new(client, transport, ownedHttpClientLease);
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
                        await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
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
        await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
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
            this._clientLock.Release();
        }
    }

    private async ValueTask ReleaseOwnedHttpClientAsync(string serverUrl)
    {
        HttpClient? clientToDispose = null;
        await this._clientLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
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
            this._clientLock.Release();
        }

        clientToDispose?.Dispose();
    }

    private HttpClient CreatePinnedHttpClient(string serverUrl)
    {
        // Pin credential headers to the configured server origin as defense-in-depth. Forcing
        // StreamableHttp (below) already removes the primary vector (a server-advertised cross-origin
        // SSE message endpoint), and AllowAutoRedirect=false blocks auto-redirects. This handler is the
        // backstop: it guarantees the Authorization token and other credentials never leave the pinned
        // origin even if a future change re-enables AutoDetect or redirects, or the SDK constructs a
        // request to a new URI (AdditionalHeaders are re-stamped by the transport, so HttpClient's own
        // redirect header-stripping does not cover them).
        OriginPinningHandler pinningHandler = new(new Uri(serverUrl)) { InnerHandler = this._httpMessageHandlerFactory() };
        return new HttpClient(pinningHandler);
    }

    private static HttpMessageHandler CreateHttpMessageHandler() =>
        new HttpClientHandler
        {
            // Keep cookies out of pooled transport state and prevent credential-bearing redirects.
            UseCookies = false,
            AllowAutoRedirect = false,
            CheckCertificateRevocationList = true
        };

    private sealed class ProviderInvocationContext(Task completion, ProviderInvocationContext? parent)
    {
        public Task Completion { get; } = completion;
        public ProviderInvocationContext? Parent { get; } = parent;
    }

    private sealed class CachedClient(
        ClientConnection connection,
        LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> lruNode)
    {
        public ClientConnection Connection { get; } = connection;

        public LinkedListNode<(string WorkflowSession, string Url, string Label, string Connection, string HeadersHash)> LruNode { get; } = lruNode;

        public TaskCompletionSource<bool> Disposed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int ActiveInvocations { get; set; }

        public bool Evicted { get; set; }

        public bool DisposalClaimed { get; set; }
    }

    private sealed class OwnedHttpClient(HttpClient client)
    {
        public HttpClient Client { get; } = client;

        public int ReferenceCount { get; set; }
    }

    private sealed class OwnedHttpClientLease(
        DefaultMcpToolHandler owner,
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

    internal sealed class ClientConnection(
        McpClient client,
        IAsyncDisposable transport,
        IAsyncDisposable? ownedHttpClientLease = null) : IAsyncDisposable
    {
        public McpClient Client { get; } = client;

        public async ValueTask DisposeAsync()
        {
            try
            {
                await DisposeResourceAsync(this.Client, "session").ConfigureAwait(false);
            }
            finally
            {
                try
                {
                    // McpClient owns the connected session, not the reusable transport factory.
                    await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
                }
                finally
                {
                    if (ownedHttpClientLease is not null)
                    {
                        await ownedHttpClientLease.DisposeAsync().ConfigureAwait(false);
                    }
                }
            }
        }
    }

    private static async ValueTask DisposeResourceAsync<T>(T resource, string resourceName)
        where T : IAsyncDisposable
    {
        try
        {
            await resource.DisposeAsync().ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            Trace.TraceWarning("Failed to dispose MCP {0}: {1}", resourceName, exception);
        }
    }

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

    private static void ThrowIfListToolsArgumentsSpecified(IDictionary<string, object?>? arguments)
    {
        if (arguments is { Count: > 0 })
        {
            throw new ArgumentException(
                $"The reserved MCP '{ListToolsToolName}' operation does not accept tool arguments.",
                nameof(arguments));
        }
    }

    private static void PopulateResultContent(McpServerToolResultContent resultContent, CallToolResult result)
    {
        // Ensure Outputs list is initialized
        resultContent.Outputs ??= [];

        if (result.IsError == true)
        {
            // Collect error text from content blocks
            string? errorText = null;
            if (result.Content is not null)
            {
                foreach (ContentBlock block in result.Content)
                {
                    if (block is TextContentBlock textBlock)
                    {
                        errorText = errorText is null ? textBlock.Text : $"{errorText}\n{textBlock.Text}";
                    }
                }
            }

            resultContent.Outputs.Add(new TextContent($"Error: {errorText ?? "Unknown error from MCP Server call"}"));
            return;
        }

        if (result.Content is null || result.Content.Count == 0)
        {
            return;
        }

        // Map each MCP content block to an MEAI AIContent type
        foreach (ContentBlock block in result.Content)
        {
            AIContent content = ConvertContentBlock(block);
            if (content is not null)
            {
                resultContent.Outputs.Add(content);
            }
        }
    }

    internal static AIContent ConvertContentBlock(ContentBlock block)
    {
        // Delegate to the MCP SDK's canonical converter. It maps every known
        // ContentBlock subtype (Text/Image/Audio/EmbeddedResource/ToolUse/ToolResult)
        // and sets RawRepresentation + AdditionalProperties from block.Meta.
        // It intentionally returns null for ResourceLinkBlock — map that to
        // UriContent here so callers always receive a usable AIContent.
        return block.ToAIContent() ?? block switch
        {
            ResourceLinkBlock link => new UriContent(link.Uri, link.MimeType ?? "application/octet-stream")
            {
                RawRepresentation = link,
                AdditionalProperties = CreateAdditionalProperties(link),
            },
            _ => new TextContent(block.ToString() ?? string.Empty)
            {
                RawRepresentation = block,
                AdditionalProperties = CreateAdditionalProperties(block),
            },
        };
    }

    private static AdditionalPropertiesDictionary? CreateAdditionalProperties(ContentBlock block)
    {
        AdditionalPropertiesDictionary? properties = null;

        if (block.Meta is not null)
        {
            foreach (var property in block.Meta)
            {
                properties ??= new AdditionalPropertiesDictionary();
                properties.Add(property.Key, property.Value);
            }
        }

        if (block is ResourceLinkBlock { Name: { Length: > 0 } name })
        {
            properties ??= new AdditionalPropertiesDictionary();
            properties.TryAdd(FilenameAdditionalPropertyName, name);
        }

        return properties;
    }

    private static string SerializeToolsList(IEnumerable<Tool> tools)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream, s_toolListJsonWriterOptions))
        {
            writer.WriteStartObject();
            writer.WriteStartArray("tools");

            foreach (Tool tool in tools)
            {
                writer.WriteStartObject();
                writer.WriteString("name", tool.Name);
                writer.WriteString("description", tool.Description);
                writer.WritePropertyName("inputSchema");
                tool.InputSchema.WriteTo(writer);
                writer.WritePropertyName("outputSchema");
                if (tool.OutputSchema is JsonElement outputSchema)
                {
                    outputSchema.WriteTo(writer);
                }
                else
                {
                    writer.WriteNullValue();
                }

                writer.WriteEndObject();
            }

            writer.WriteEndArray();
            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(stream.GetBuffer(), 0, (int)stream.Length);
    }
}
