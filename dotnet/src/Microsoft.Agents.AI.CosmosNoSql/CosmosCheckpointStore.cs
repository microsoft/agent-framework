// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Azure.Cosmos;
using Microsoft.Shared.Diagnostics;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides a Cosmos DB implementation of the <see cref="JsonCheckpointStore"/> abstract class.
/// </summary>
/// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
[RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
public class CosmosCheckpointStore<T> : JsonCheckpointStore, IDisposable
{
    private readonly CosmosClient _cosmosClient;
    private readonly Container _container;
    private readonly bool _ownsClient;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosCheckpointStore{T}"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosCheckpointStore(string connectionString, string databaseId, string containerId)
    {
        var cosmosClientOptions = new CosmosClientOptions();

        this._cosmosClient = new CosmosClient(Throw.IfNullOrWhitespace(connectionString), cosmosClientOptions);
        this._container = this._cosmosClient.GetContainer(Throw.IfNullOrWhitespace(databaseId), Throw.IfNullOrWhitespace(containerId));
        this._ownsClient = true;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosCheckpointStore{T}"/> class using a TokenCredential for authentication.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosCheckpointStore(string accountEndpoint, TokenCredential tokenCredential, string databaseId, string containerId)
    {
        var cosmosClientOptions = new CosmosClientOptions
        {
            SerializerOptions = new CosmosSerializationOptions
            {
                PropertyNamingPolicy = CosmosPropertyNamingPolicy.CamelCase
            }
        };

        this._cosmosClient = new CosmosClient(Throw.IfNullOrWhitespace(accountEndpoint), Throw.IfNull(tokenCredential), cosmosClientOptions);
        this._container = this._cosmosClient.GetContainer(Throw.IfNullOrWhitespace(databaseId), Throw.IfNullOrWhitespace(containerId));
        this._ownsClient = true;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosCheckpointStore{T}"/> class using an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosCheckpointStore(CosmosClient cosmosClient, string databaseId, string containerId)
    {
        this._cosmosClient = Throw.IfNull(cosmosClient);

        this._container = this._cosmosClient.GetContainer(Throw.IfNullOrWhitespace(databaseId), Throw.IfNullOrWhitespace(containerId));
        this._ownsClient = false;
    }

    /// <summary>
    /// Gets the identifier of the Cosmos DB database.
    /// </summary>
    public string DatabaseId => this._container.Database.Id;

    /// <summary>
    /// Gets the identifier of the Cosmos DB container.
    /// </summary>
    public string ContainerId => this._container.Id;

    /// <inheritdoc />
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, JsonElement value, CheckpointInfo? parent = null)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var checkpointId = Guid.NewGuid().ToString("N");
        var checkpointInfo = new CheckpointInfo(runId, checkpointId);

        var document = new CosmosCheckpointDocument
        {
            Id = $"{runId}_{checkpointId}",
            RunId = runId,
            CheckpointId = checkpointId,
            Value = JToken.Parse(value.GetRawText()),
            ParentCheckpointId = parent?.CheckpointId,
            Timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
        };

        await this._container.CreateItemAsync(document, new PartitionKey(runId)).ConfigureAwait(false);
        return checkpointInfo;
    }

    /// <inheritdoc />
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string runId, CheckpointInfo key)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

        if (key is null)
        {
            throw new ArgumentNullException(nameof(key));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var id = $"{runId}_{key.CheckpointId}";

        try
        {
            var response = await this._container.ReadItemAsync<CosmosCheckpointDocument>(id, new PartitionKey(runId)).ConfigureAwait(false);
            using var document = JsonDocument.Parse(response.Resource.Value.ToString());
            return document.RootElement.Clone();
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            throw new InvalidOperationException($"Checkpoint with ID '{key.CheckpointId}' for run '{runId}' not found.");
        }
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        QueryDefinition query = withParent == null
            ? new QueryDefinition("SELECT c.runId, c.checkpointId FROM c WHERE c.runId = @runId ORDER BY c.timestamp ASC")
                .WithParameter("@runId", runId)
            : new QueryDefinition("SELECT c.runId, c.checkpointId FROM c WHERE c.runId = @runId AND c.parentCheckpointId = @parentCheckpointId ORDER BY c.timestamp ASC")
                .WithParameter("@runId", runId)
                .WithParameter("@parentCheckpointId", withParent.CheckpointId);

        var iterator = this._container.GetItemQueryIterator<CheckpointQueryResult>(query);
        var checkpoints = new List<CheckpointInfo>();

        while (iterator.HasMoreResults)
        {
            var response = await iterator.ReadNextAsync().ConfigureAwait(false);
            checkpoints.AddRange(response.Select(r => new CheckpointInfo(r.RunId, r.CheckpointId)));
        }

        return checkpoints;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Releases the unmanaged resources used by the <see cref="CosmosCheckpointStore{T}"/> and optionally releases the managed resources.
    /// </summary>
    /// <param name="disposing">true to release both managed and unmanaged resources; false to release only unmanaged resources.</param>
    protected virtual void Dispose(bool disposing)
    {
        if (!this._disposed)
        {
            if (disposing && this._ownsClient)
            {
                this._cosmosClient?.Dispose();
            }
            this._disposed = true;
        }
    }

    /// <summary>
    /// Represents a checkpoint document stored in Cosmos DB.
    /// </summary>
    internal sealed class CosmosCheckpointDocument
    {
        [JsonProperty("id")]
        public string Id { get; set; } = string.Empty;

        [JsonProperty("runId")]
        public string RunId { get; set; } = string.Empty;

        [JsonProperty("checkpointId")]
        public string CheckpointId { get; set; } = string.Empty;

        [JsonProperty("value")]
        public JToken Value { get; set; } = JValue.CreateNull();

        [JsonProperty("parentCheckpointId")]
        public string? ParentCheckpointId { get; set; }

        [JsonProperty("timestamp")]
        public long Timestamp { get; set; }
    }

    /// <summary>
    /// Represents the result of a checkpoint query.
    /// </summary>
    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by Cosmos DB query deserialization")]
    private sealed class CheckpointQueryResult
    {
        public string RunId { get; set; } = string.Empty;
        public string CheckpointId { get; set; } = string.Empty;
    }
}

/// <summary>
/// Provides a non-generic Cosmos DB implementation of the <see cref="JsonCheckpointStore"/> abstract class.
/// </summary>
[RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class CosmosCheckpointStore : CosmosCheckpointStore<JsonElement>
{
    /// <inheritdoc />
    public CosmosCheckpointStore(string connectionString, string databaseId, string containerId)
        : base(connectionString, databaseId, containerId)
    {
    }

    /// <inheritdoc />
    public CosmosCheckpointStore(string accountEndpoint, TokenCredential tokenCredential, string databaseId, string containerId)
        : base(accountEndpoint, tokenCredential, databaseId, containerId)
    {
    }

    /// <inheritdoc />
    public CosmosCheckpointStore(CosmosClient cosmosClient, string databaseId, string containerId)
        : base(cosmosClient, databaseId, containerId)
    {
    }
}
