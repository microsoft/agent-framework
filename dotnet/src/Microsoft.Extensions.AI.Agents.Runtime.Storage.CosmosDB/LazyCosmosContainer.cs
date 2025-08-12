// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.ObjectModel;
using System.Threading;
using System.Threading.Tasks;
using System.Net;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Options;
using Microsoft.Extensions.Options;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

#pragma warning disable VSTHRD011 // Use AsyncLazy<T>

/// <summary>
/// A lazy wrapper around a Cosmos DB Container.
/// This avoids performing async I/O-bound operations (i.e. Cosmos DB setup) during
/// DI registration, deferring them until first access.
/// </summary>
internal sealed class LazyCosmosContainer
{
    private readonly CosmosClient? _cosmosClient;
    private readonly string? _databaseName;
    private readonly string? _containerName;
    private readonly Lazy<Task<Container>> _lazyContainer;

    private readonly CosmosActorStateStorageOptions _options = new();
    private CosmosActorStateStorageOptions.RetryOptions RetryOptions => this._options.Retry;

    /// <summary>
    /// LazyCosmosContainer constructor that initializes the container lazily.
    /// </summary>
    public LazyCosmosContainer(
        CosmosClient cosmosClient,
        string databaseName,
        string containerName,
        IOptions<CosmosActorStateStorageOptions>? options = null)
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._databaseName = databaseName ?? throw new ArgumentNullException(nameof(databaseName));
        this._containerName = containerName ?? throw new ArgumentNullException(nameof(containerName));
        this._options = options?.Value ?? new();

        this._lazyContainer = new Lazy<Task<Container>>(this.InitializeContainerAsync, LazyThreadSafetyMode.ExecutionAndPublication);
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

        this._lazyContainer = new Lazy<Task<Container>>(() => Task.FromResult(container), LazyThreadSafetyMode.ExecutionAndPublication);
    }

    /// <summary>
    /// Gets the Container, initializing it if necessary.
    /// </summary>
    public Task<Container> GetContainerAsync() => this._lazyContainer.Value;

    private async Task<Container> InitializeContainerAsync()
    {
        var attempt = 0;
        Exception? lastException = null;

        while (attempt <= this.RetryOptions.MaxRetryAttempts)
        {
            try
            {
                // Create database if it doesn't exist
                var database = await this._cosmosClient!.CreateDatabaseIfNotExistsAsync(this._databaseName!).ConfigureAwait(false);

                var containerProperties = new ContainerProperties(this._containerName!, "/actorId")
                {
                    Id = this._containerName!,
                    IndexingPolicy = new IndexingPolicy
                    {
                        IndexingMode = IndexingMode.Consistent,
                        Automatic = true
                    },
                    PartitionKeyPaths = ["/actorId"]
                };

                // Add composite index for efficient queries
                containerProperties.IndexingPolicy.CompositeIndexes.Add(new Collection<CompositePath>
                {
                    new() { Path = "/actorId", Order = CompositePathSortOrder.Ascending },
                    new() { Path = "/key", Order = CompositePathSortOrder.Ascending }
                });

                var container = await database.Database.CreateContainerIfNotExistsAsync(containerProperties).ConfigureAwait(false);
                return container.Container;
            }
            catch (Exception ex) when (IsRetriableException(ex) && attempt < this.RetryOptions.MaxRetryAttempts)
            {
                lastException = ex;
                attempt++;

                if (attempt <= this.RetryOptions.MaxRetryAttempts)
                {
                    var delay = this.CalculateDelay(attempt);
                    await Task.Delay(delay).ConfigureAwait(false);
                }
            }
        }

        // Exhausted all retries
        throw lastException ?? new InvalidOperationException("Container initialization failed after all retry attempts.");
    }

    /// <summary>
    /// Determines if an exception is retriable.
    /// </summary>
    private static bool IsRetriableException(Exception exception)
    {
        return exception switch
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
    }

    /// <summary>
    /// Calculates the delay for the given attempt using exponential backoff.
    /// </summary>
    private TimeSpan CalculateDelay(int attempt)
    {
        var delay = TimeSpan.FromTicks((long)(this.RetryOptions.BaseDelay.Ticks * Math.Pow(this.RetryOptions.BackoffMultiplier, attempt - 1)));
        if (delay > this.RetryOptions.MaxDelay)
        {
            delay = this.RetryOptions.MaxDelay;
        }

        return delay;
    }
}
