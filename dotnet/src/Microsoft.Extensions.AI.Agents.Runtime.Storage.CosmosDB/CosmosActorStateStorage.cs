// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

/// <summary>
/// Cosmos DB implementation of actor state storage.
/// </summary>
public class CosmosActorStateStorage : IActorStateStorage
{
    private readonly LazyCosmosContainer _lazyContainer;
    private const string InitialEtag = "0"; // Initial ETag value when no state exists

    /// <summary>
    /// Constructs a new instance of <see cref="CosmosActorStateStorage"/> with the specified Cosmos DB container.
    /// </summary>
    /// <param name="container">The Cosmos DB container to use for storage.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="container"/> is null.</exception>
    public CosmosActorStateStorage(Container container) => this._lazyContainer = new LazyCosmosContainer(container);

    /// <summary>
    /// This constructor is used by dependency injection to create an instance of <see cref="CosmosActorStateStorage"/>
    /// with a lazy-loaded Cosmos container whose initialization is deferred until first access.
    /// </summary>
    /// <param name="lazyContainer">The lazy-loaded Cosmos container.</param>
    /// <throws cref="ArgumentNullException">Thrown when <paramref name="lazyContainer"/> is null.</throws>
    internal CosmosActorStateStorage(LazyCosmosContainer lazyContainer) =>
        this._lazyContainer = lazyContainer ?? throw new ArgumentNullException(nameof(lazyContainer));

    /// <summary>
    /// Writes state changes to the actor's persistent storage.
    /// </summary>
    public async ValueTask<WriteResponse> WriteStateAsync(
        ActorId actorId,
        IReadOnlyCollection<ActorStateWriteOperation> operations,
        string etag,
        CancellationToken cancellationToken = default)
    {
        if (operations.Count == 0)
        {
            throw new InvalidOperationException("No operations provided for write. At least one operation is required.");
        }

        var container = await this._lazyContainer.GetContainerAsync().ConfigureAwait(false);
        var batch = container.CreateTransactionalBatch(GetPartitionKey(actorId));
        var actorIdStr = actorId.ToString();

        // Add data operations to batch
        foreach (var op in operations)
        {
            switch (op)
            {
                case SetValueOperation set:
                    var docId = GetDocumentId(set.Key);

                    var item = new ActorStateDocument
                    {
                        Id = docId,
                        ActorId = actorIdStr,
                        Key = set.Key,
                        Value = set.Value
                    };

                    batch.UpsertItem(item);
                    break;

                case RemoveKeyOperation remove:
                    var docToRemove = GetDocumentId(remove.Key);
                    batch.DeleteItem(docToRemove);
                    break;

                default:
                    throw new ArgumentException($"Unsupported write operation: {op.GetType().Name}");
            }
        }

        // Add root document update to batch
        var newRoot = new ActorRootDocument
        {
            Id = RootDocumentId,
            ActorId = actorId.ToString(),
            LastModified = DateTimeOffset.UtcNow,
        };

        if (string.IsNullOrEmpty(etag) || etag == InitialEtag)
        {
            // No eTag provided or initial eTag - create new root document (will fail if it already exists)
            batch.CreateItem(newRoot);
        }
        else
        {
            // eTag provided - replace existing root document with eTag check
            batch.ReplaceItem(RootDocumentId, newRoot, new TransactionalBatchItemRequestOptions { IfMatchEtag = etag });
        }

        try
        {
            var result = await batch.ExecuteAsync(cancellationToken).ConfigureAwait(false);
            if (!result.IsSuccessStatusCode)
            {
                return new WriteResponse(eTag: string.Empty, success: false);
            }

            // Get the ETag from the root document operation (last operation in batch)
            var rootResult = result[result.Count - 1];
            return new WriteResponse(eTag: rootResult.ETag, success: true);
        }
        catch (CosmosException)
        {
            // If any operation in the batch fails, we return failure
            return new WriteResponse(eTag: string.Empty, success: false);
        }
    }

    /// <summary>
    /// Reads state data from the actor's persistent storage.
    /// </summary>
    public async ValueTask<ReadResponse> ReadStateAsync(
        ActorId actorId,
        IReadOnlyCollection<ActorStateReadOperation> operations,
        CancellationToken cancellationToken = default)
    {
        if (operations.Count == 0)
        {
            throw new InvalidOperationException("No operations provided for read. At least one operation is required.");
        }

        var container = await this._lazyContainer.GetContainerAsync().ConfigureAwait(false);
        var results = new List<ActorReadResult>();

        // Read root document first to get actor-level ETag
        string actorETag = await this.GetActorETagAsync(container, actorId, cancellationToken).ConfigureAwait(false);

        foreach (var op in operations)
        {
            switch (op)
            {
                case GetValueOperation get:
                    var id = GetDocumentId(get.Key);
                    try
                    {
                        var response = await container.ReadItemAsync<ActorStateDocument>(
                            id,
                            GetPartitionKey(actorId),
                            cancellationToken: cancellationToken)
                            .ConfigureAwait(false);

                        results.Add(new GetValueResult(response.Resource.Value));
                    }
                    catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
                    {
                        results.Add(new GetValueResult(null));
                    }
                    break;

                case ListKeysOperation list:
                    QueryDefinition query;
                    if (!string.IsNullOrEmpty(list.KeyPrefix))
                    {
                        query = new QueryDefinition("SELECT c.key FROM c WHERE c.actorId = @actorId AND c.key != null AND STARTSWITH(c.key, @keyPrefix)")
                            .WithParameter("@actorId", actorId.ToString())
                            .WithParameter("@keyPrefix", list.KeyPrefix);
                    }
                    else
                    {
                        query = new QueryDefinition("SELECT c.key FROM c WHERE c.actorId = @actorId AND c.key != null")
                            .WithParameter("@actorId", actorId.ToString());
                    }

                    var requestOptions = new QueryRequestOptions
                    {
                        PartitionKey = GetPartitionKey(actorId),
                        MaxItemCount = -1 // Use dynamic page size
                    };

                    var iterator = container.GetItemQueryIterator<KeyProjection>(
                        query,
                        list.ContinuationToken,
                        requestOptions);

                    var keys = new List<string>();
                    string? continuationToken = null;

                    while (iterator.HasMoreResults)
                    {
                        var page = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
                        foreach (var projection in page)
                        {
                            keys.Add(projection.Key);
                        }

                        continuationToken = page.ContinuationToken;
                    }

                    results.Add(new ListKeysResult(keys, continuationToken));
                    break;

                default:
                    throw new NotSupportedException($"Unsupported read operation: {op.GetType().Name}");
            }
        }

        return new ReadResponse(actorETag, results);
    }

    private static string GetDocumentId(string key) => $"state_{CosmosIdSanitizer.Sanitize(key)}";
    private const string RootDocumentId = "rootdoc";

    private static PartitionKey GetPartitionKey(ActorId actorId)
        => new(actorId.ToString());

    /// <summary>
    /// Gets the current ETag for the actor's root document.
    /// Returns a generated ETag if no root document exists.
    /// </summary>
    private async ValueTask<string> GetActorETagAsync(Container container, ActorId actorId, CancellationToken cancellationToken)
    {
        try
        {
            var rootResponse = await container.ReadItemAsync<ActorRootDocument>(
                RootDocumentId,
                GetPartitionKey(actorId),
                cancellationToken: cancellationToken).ConfigureAwait(false);
            return rootResponse.ETag;
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            // No root document means no actor state exists
            return Guid.NewGuid().ToString("N");
        }
    }
}
