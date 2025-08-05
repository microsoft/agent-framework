// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.ObjectModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;

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

    /// <summary>
    /// LazyCosmosContainer constructor that initializes the container lazily.
    /// </summary>
    public LazyCosmosContainer(CosmosClient cosmosClient, string databaseName, string containerName)
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._databaseName = databaseName ?? throw new ArgumentNullException(nameof(databaseName));
        this._containerName = containerName ?? throw new ArgumentNullException(nameof(containerName));
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
}
