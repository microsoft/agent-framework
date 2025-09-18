// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Net;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

/// <summary>
/// A lazy wrapper around a Cosmos DB Container.
/// This avoids performing async I/O-bound operations (i.e. Cosmos DB setup) during
/// DI registration, deferring them until first access.
/// </summary>
internal sealed class LazyCosmosContainer : IAsyncDisposable
{
#if !NET
    [ThreadStatic]
    private static Random? t_random;
#endif

    private readonly CosmosClient? _cosmosClient;
    private readonly string? _databaseName;
    private readonly string? _containerName;

    private readonly CancellationTokenSource _cts = new();
    private Task<Container>? _initTask;

    // internal for testing
    internal static readonly string[] CosmosPartitionKeyPaths = ["/actorType", "/actorKey"];

    /// <summary>
    /// LazyCosmosContainer constructor that initializes the container lazily.
    /// </summary>
    public LazyCosmosContainer(CosmosClient cosmosClient, string databaseName, string containerName)
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._databaseName = databaseName ?? throw new ArgumentNullException(nameof(databaseName));
        this._containerName = containerName ?? throw new ArgumentNullException(nameof(containerName));
    }
    /// <summary>
    /// LazyCosmosContainer constructor that accepts an existing Container instance.
    /// </summary>
    public LazyCosmosContainer(Container container)
    {
        if (container is null)
        {
            throw new ArgumentNullException(nameof(container));
        }

        this._initTask = Task.FromResult(container);
    }

    /// <summary>
    /// Gets the Container, initializing it if necessary.
    /// </summary>
    public Task<Container> GetContainerAsync()
        => this._initTask ??= this.InitializeWithRetryAsync(this._cts.Token);

    private async Task<Container> InitializeWithRetryAsync(CancellationToken cancellationToken)
    {
        var baseDelay = TimeSpan.FromSeconds(1);
        var maxDelay = TimeSpan.FromSeconds(30);
        var previousDelay = baseDelay;

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                return await this.InitializeContainerAsync(cancellationToken).ConfigureAwait(false);
            }
            catch (CosmosException ex) when (IsTransient(ex))
            {
                // If server provided RetryAfter, respect it but add a small jitter so clients don't retry in perfect sync.
                if (ex.RetryAfter is not null && ex.RetryAfter > TimeSpan.Zero)
                {
                    var retry = ex.RetryAfter.Value;
                    var jitterMs = RandomNextDouble() * retry.TotalMilliseconds; // 0..retry
                    var delay = retry + TimeSpan.FromMilliseconds(jitterMs);
                    await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                    previousDelay = delay;
                    continue;
                }

                // sleep = min(maxDelay, random(baseDelay, previousDelay * 3))
                var minMs = baseDelay.TotalMilliseconds;
                var maxMs = Math.Min(maxDelay.TotalMilliseconds, Math.Max(minMs, previousDelay.TotalMilliseconds * 3));
                var sleepMs = (RandomNextDouble() * (maxMs - minMs)) + minMs;
                var jitterDelay = TimeSpan.FromMilliseconds(sleepMs);

                await Task.Delay(jitterDelay, cancellationToken).ConfigureAwait(false);
                previousDelay = jitterDelay;
            }
        }
    }

    private async Task<Container> InitializeContainerAsync(CancellationToken cancellationToken)
    {
        // Create database if it doesn't exist
        var database = await this._cosmosClient!.CreateDatabaseIfNotExistsAsync(this._databaseName!, cancellationToken: cancellationToken).ConfigureAwait(false);

        var containerProperties = new ContainerProperties(this._containerName!, CosmosPartitionKeyPaths)
        {
            Id = this._containerName!,
            IndexingPolicy = new IndexingPolicy
            {
                IndexingMode = IndexingMode.Consistent,
                Automatic = true
            },
            PartitionKeyPaths = CosmosPartitionKeyPaths
        };

        // Add composite index for efficient queries
        containerProperties.IndexingPolicy.CompositeIndexes.Add(
        [
            new() { Path = "/actorType", Order = CompositePathSortOrder.Ascending },
            new() { Path = "/actorKey", Order = CompositePathSortOrder.Ascending },
            new() { Path = "/key", Order = CompositePathSortOrder.Ascending }
        ]);

        var container = await database.Database.CreateContainerIfNotExistsAsync(containerProperties, cancellationToken: cancellationToken).ConfigureAwait(false);
        return container.Container;
    }

    private static bool IsTransient(Exception exception) => exception switch
    {
        CosmosException cosmosEx => cosmosEx.StatusCode switch
        {
#if NET9_0_OR_GREATER
            HttpStatusCode.TooManyRequests => true,     // 429 - Rate limited
#endif
            HttpStatusCode.InternalServerError => true, // 500 - Server error
            HttpStatusCode.BadGateway => true,          // 502 - Bad gateway
            HttpStatusCode.ServiceUnavailable => true,  // 503 - Service unavailable
            HttpStatusCode.GatewayTimeout => true,      // 504 - Gateway timeout
            HttpStatusCode.RequestTimeout => true,      // 408 - Request timeout
            _ => false
        },
        TaskCanceledException or OperationCanceledException or ArgumentException => false,
        _ => true // Retry other exceptions (network issues, etc.)
    };

    private static double RandomNextDouble() =>
#if NET
        Random.Shared.NextDouble();
#else
        (t_random ??= new()).NextDouble();
#endif

    public ValueTask DisposeAsync()
    {
        this._cts?.Cancel();
        this._cts?.Dispose();
        return default;
    }
}
