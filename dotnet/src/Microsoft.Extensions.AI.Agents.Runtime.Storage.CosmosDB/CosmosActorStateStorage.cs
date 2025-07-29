// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

#pragma warning disable IL3050, IL2026

/// <summary>
///
/// TODO: partitionkey can be heirarchical - actortype + actorkey
///
/// Cosmos DB implementation of actor state storage.
///
/// Document Structure (one per actor key):
/// {
///   "id": "actor-123__foo",            // Composite ID: actorId__key (__ separator for safety)
///   "actorId": "actor-123",             // Partition key
///   "key": "foo",                       // Logical key
///   "value": { "bar": 42, "baz": "hello" }  // Arbitrary JsonElement payload
/// }
///
/// Root document (one per actor for ETag tracking):
/// {
///   "id": "actor-123",                  // Root document ID: actorId
///   "actorId": "actor-123",             // Partition key (same as ID)
///   "lastModified": "2024-...",          // Timestamp
///   "version": 123                       // Incrementing version number
/// }
/// </summary>
public class CosmosActorStateStorage : IActorStateStorage
{
    private readonly Container _container;
    private const string InitialEtag = "0"; // Initial ETag value when no state exists

    /// <summary>
    /// Constructs a new instance of <see cref="CosmosActorStateStorage"/> with the specified Cosmos DB container.
    /// </summary>
    /// <param name="container">The Cosmos DB container to use for storage.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="container"/> is null.</exception>
    public CosmosActorStateStorage(Container container) => this._container = container ?? throw new ArgumentNullException(nameof(container));

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
            // No operations to perform - return success with current ETag or generate new one
            string resultEtag = !string.IsNullOrEmpty(etag) ? etag : Guid.NewGuid().ToString("N");
            return new WriteResponse(eTag: resultEtag, success: true);
        }

        var partitionKey = new PartitionKey(actorId.ToString());
        var batch = this._container.CreateTransactionalBatch(partitionKey);

        // First, try to read existing root document to get current version
        var rootDocId = GetRootDocumentId(actorId);
        ActorRootDocument? existingRoot = null;
        try
        {
            var rootResponse = await this._container.ReadItemAsync<ActorRootDocument>(
                rootDocId,
                partitionKey,
                cancellationToken: cancellationToken).ConfigureAwait(false);
            existingRoot = rootResponse.Resource;

            // Validate ETag if provided
            if (!string.IsNullOrEmpty(etag) && rootResponse.ETag != etag)
            {
                return new WriteResponse(eTag: string.Empty, success: false);
            }
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            // Root document doesn't exist - will be created
            if (!string.IsNullOrEmpty(etag) && etag != InitialEtag)
            {
                // ETag provided but no document exists (and it's not the initial "0" ETag)
                return new WriteResponse(eTag: InitialEtag, success: false);
            }
        }

        // Add data operations to batch
        foreach (var op in operations)
        {
            switch (op)
            {
                case SetValueOperation set:
                    var docId = GetDocumentId(actorId, set.Key);

                    var item = new ActorStateDocument
                    {
                        Id = docId,
                        ActorId = actorId.ToString(),
                        Key = set.Key,
                        Value = set.Value
                    };

                    batch.UpsertItem(item);
                    break;

                case RemoveKeyOperation remove:
                    var docToRemove = GetDocumentId(actorId, remove.Key);
                    batch.DeleteItem(docToRemove);
                    break;

                default:
                    throw new ArgumentException($"Unsupported write operation: {op.GetType().Name}");
            }
        }

        // Add root document update to batch
        var newRoot = new ActorRootDocument
        {
            Id = rootDocId,
            ActorId = actorId.ToString(),
            LastModified = DateTimeOffset.UtcNow,
            Version = (existingRoot?.Version ?? 0) + 1
        };

        if (existingRoot != null && !string.IsNullOrEmpty(etag))
        {
            batch.ReplaceItem(rootDocId, newRoot, new TransactionalBatchItemRequestOptions { IfMatchEtag = etag });
        }
        else
        {
            batch.UpsertItem(newRoot);
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
        var results = new List<ActorReadResult>();

        // Read root document first to get actor-level ETag
        string actorETag = await this.GetActorETagAsync(actorId, cancellationToken).ConfigureAwait(false);

        foreach (var op in operations)
        {
            switch (op)
            {
                case GetValueOperation get:
                    var id = GetDocumentId(actorId, get.Key);
                    try
                    {
                        var response = await this._container.ReadItemAsync<ActorStateDocument>(
                            id,
                            new PartitionKey(actorId.ToString()),
                            cancellationToken: cancellationToken)
                            .ConfigureAwait(false);

                        var jsonElement = JsonSerializer.SerializeToElement(response.Resource.Value);

                        results.Add(new GetValueResult(jsonElement));
                    }
                    catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
                    {
                        results.Add(new GetValueResult(null));
                    }
                    break;

                case ListKeysOperation list:
                    var keys = new List<string>();
                    string? continuationToken = null;

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
                        PartitionKey = new PartitionKey(actorId.ToString()),
                        MaxItemCount = 100 // TODO Fix 
                    };

                    var iterator = this._container.GetItemQueryIterator<KeyProjection>(
                        query,
                        list.ContinuationToken,
                        requestOptions);

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

    [SuppressMessage("Performance", "CA1812", Justification = "This is a projection class for Cosmos DB queries.")]
    private sealed class KeyProjection
    {
        [JsonPropertyName("key")]
        public string Key { get; set; } = default!;
    }

    /// <summary>
    /// Root document for each actor that provides actor-level ETag semantics.
    /// Every write operation updates this document to ensure a single ETag represents
    /// the entire actor's state for optimistic concurrency control.
    /// This document contains no actor state data. It only serves to track version and
    /// provide ETag for the entire actor's state.
    /// </summary>
    private sealed class ActorRootDocument
    {
        [JsonPropertyName("id")]
        public string Id { get; set; } = default!;

        [JsonPropertyName("actorId")]
        public string ActorId { get; set; } = default!;

        [JsonPropertyName("lastModified")]
        public DateTimeOffset LastModified { get; set; }

        [JsonPropertyName("version")]
        public long Version { get; set; }
    }

    private sealed class ActorStateDocument
    {
        [JsonPropertyName("id")]
        public string Id { get; set; } = default!;

        [JsonPropertyName("actorId")]
        public string ActorId { get; set; } = default!;

        [JsonPropertyName("key")]
        public string Key { get; set; } = default!;

        [JsonPropertyName("value")]
        public object Value { get; set; } = default!;
    }

    private static string Sanitize(string input)
    => Uri.EscapeDataString(input).Replace("%2F", "__");

    private static string GetDocumentId(ActorId actorId, string key)
        => $"{Sanitize(actorId.ToString())}__{Sanitize(key)}";

    private static string GetRootDocumentId(ActorId actorId)
        => Sanitize(actorId.ToString());

    /// <summary>
    /// Gets the current ETag for the actor's root document.
    /// Returns a generated ETag if no root document exists.
    /// </summary>
    private async ValueTask<string> GetActorETagAsync(ActorId actorId, CancellationToken cancellationToken)
    {
        var rootDocId = GetRootDocumentId(actorId);
        try
        {
            var rootResponse = await this._container.ReadItemAsync<ActorRootDocument>(
                rootDocId,
                new PartitionKey(actorId.ToString()),
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
