// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a Cosmos DB implementation of the <see cref="ChatMessageStore"/> abstract class.
/// </summary>
[RequiresUnreferencedCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class CosmosChatMessageStore : ChatMessageStore, IDisposable
{
    private readonly CosmosClient _cosmosClient;
    private readonly Container _container;
    private readonly bool _ownsClient;
    private bool _disposed;

    // Hierarchical partition key support
    private readonly string? _tenantId;
    private readonly string? _userId;
    private readonly PartitionKey _partitionKey;
    private readonly bool _useHierarchicalPartitioning;

    /// <summary>
    /// Cached JSON serializer options for .NET 9.0 compatibility.
    /// </summary>
    private static readonly JsonSerializerOptions s_defaultJsonOptions = CreateDefaultJsonOptions();

    private static JsonSerializerOptions CreateDefaultJsonOptions()
    {
        var options = new JsonSerializerOptions();
#if NET9_0_OR_GREATER
        // Configure TypeInfoResolver for .NET 9.0 to enable JSON serialization
        options.TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver();
#endif
        return options;
    }

    /// <summary>
    /// Gets or sets the maximum number of messages to return in a single query batch.
    /// Default is 100 for optimal performance.
    /// </summary>
    public int MaxItemCount { get; set; } = 100;

    /// <summary>
    /// Gets or sets the maximum number of items per transactional batch operation.
    /// Default is 100, maximum allowed by Cosmos DB is 100.
    /// </summary>
    public int MaxBatchSize { get; set; } = 100;

    /// <summary>
    /// Gets or sets the maximum number of messages to retrieve from the store.
    /// This helps prevent exceeding LLM context windows in long conversations.
    /// Default is null (no limit). When set, only the most recent messages are returned.
    /// </summary>
    public int? MaxMessagesToRetrieve { get; set; }

    /// <summary>
    /// Gets or sets the Time-To-Live (TTL) in seconds for messages.
    /// Default is 86400 seconds (24 hours). Set to null to disable TTL.
    /// </summary>
    public int? MessageTtlSeconds { get; set; } = 86400;

    /// <summary>
    /// Gets the conversation ID associated with this message store.
    /// </summary>
    public string ConversationId { get; init; }

    /// <summary>
    /// Gets the database ID associated with this message store.
    /// </summary>
    public string DatabaseId { get; init; }

    /// <summary>
    /// Gets the container ID associated with this message store.
    /// </summary>
    public string ContainerId { get; init; }

    /// <summary>
    /// Internal primary constructor used by all public constructors.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread.</param>
    /// <param name="ownsClient">Whether this instance owns the CosmosClient and should dispose it.</param>
    /// <param name="tenantId">Optional tenant identifier for hierarchical partitioning.</param>
    /// <param name="userId">Optional user identifier for hierarchical partitioning.</param>
    internal CosmosChatMessageStore(CosmosClient cosmosClient, string databaseId, string containerId, string conversationId, bool ownsClient, string? tenantId = null, string? userId = null)
    {
        this._cosmosClient = Throw.IfNull(cosmosClient);
        this._container = this._cosmosClient.GetContainer(Throw.IfNullOrWhitespace(databaseId), Throw.IfNullOrWhitespace(containerId));
        this.ConversationId = Throw.IfNullOrWhitespace(conversationId);
        this.DatabaseId = databaseId;
        this.ContainerId = containerId;
        this._ownsClient = ownsClient;

        // Initialize partitioning mode
        this._tenantId = tenantId;
        this._userId = userId;
        this._useHierarchicalPartitioning = tenantId != null && userId != null;

        this._partitionKey = this._useHierarchicalPartitioning
            ? new PartitionKeyBuilder()
                .Add(tenantId!)
                .Add(userId!)
                .Add(conversationId)
                .Build()
            : new PartitionKey(conversationId);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string connectionString, string databaseId, string containerId)
        : this(connectionString, databaseId, containerId, Guid.NewGuid().ToString("N"))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string connectionString, string databaseId, string containerId, string conversationId)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(connectionString)), databaseId, containerId, conversationId, ownsClient: true)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using TokenCredential for authentication.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, TokenCredential tokenCredential, string databaseId, string containerId)
        : this(accountEndpoint, tokenCredential, databaseId, containerId, Guid.NewGuid().ToString("N"))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using a TokenCredential for authentication.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, TokenCredential tokenCredential, string databaseId, string containerId, string conversationId)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(accountEndpoint), Throw.IfNull(tokenCredential)), databaseId, containerId, conversationId, ownsClient: true)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(CosmosClient cosmosClient, string databaseId, string containerId)
        : this(cosmosClient, databaseId, containerId, Guid.NewGuid().ToString("N"))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(CosmosClient cosmosClient, string databaseId, string containerId, string conversationId)
        : this(cosmosClient, databaseId, containerId, conversationId, ownsClient: false)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using a connection string with hierarchical partition keys.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="tenantId">The tenant identifier for hierarchical partitioning.</param>
    /// <param name="userId">The user identifier for hierarchical partitioning.</param>
    /// <param name="sessionId">The session identifier for hierarchical partitioning.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string connectionString, string databaseId, string containerId, string tenantId, string userId, string sessionId)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(connectionString)), databaseId, containerId, Throw.IfNullOrWhitespace(sessionId), ownsClient: true, Throw.IfNullOrWhitespace(tenantId), Throw.IfNullOrWhitespace(userId))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using a TokenCredential for authentication with hierarchical partition keys.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="tenantId">The tenant identifier for hierarchical partitioning.</param>
    /// <param name="userId">The user identifier for hierarchical partitioning.</param>
    /// <param name="sessionId">The session identifier for hierarchical partitioning.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, TokenCredential tokenCredential, string databaseId, string containerId, string tenantId, string userId, string sessionId)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(accountEndpoint), Throw.IfNull(tokenCredential)), databaseId, containerId, Throw.IfNullOrWhitespace(sessionId), ownsClient: true, Throw.IfNullOrWhitespace(tenantId), Throw.IfNullOrWhitespace(userId))
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using an existing <see cref="CosmosClient"/> with hierarchical partition keys.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="tenantId">The tenant identifier for hierarchical partitioning.</param>
    /// <param name="userId">The user identifier for hierarchical partitioning.</param>
    /// <param name="sessionId">The session identifier for hierarchical partitioning.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(CosmosClient cosmosClient, string databaseId, string containerId, string tenantId, string userId, string sessionId)
        : this(cosmosClient, databaseId, containerId, Throw.IfNullOrWhitespace(sessionId), ownsClient: false, Throw.IfNullOrWhitespace(tenantId), Throw.IfNullOrWhitespace(userId))
    {
    }

    /// <summary>
    /// Creates a new instance of the <see cref="CosmosChatMessageStore"/> class from previously serialized state.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="serializedStoreState">A <see cref="JsonElement"/> representing the serialized state of the message store.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <returns>A new instance of <see cref="CosmosChatMessageStore"/> initialized from the serialized state.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the serialized state cannot be deserialized.</exception>
    public static CosmosChatMessageStore CreateFromSerializedState(CosmosClient cosmosClient, JsonElement serializedStoreState, string databaseId, string containerId, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        Throw.IfNull(cosmosClient);
        Throw.IfNullOrWhitespace(databaseId);
        Throw.IfNullOrWhitespace(containerId);

        if (serializedStoreState.ValueKind is not JsonValueKind.Object)
        {
            throw new ArgumentException("Invalid serialized state", nameof(serializedStoreState));
        }

        var state = JsonSerializer.Deserialize<StoreState>(serializedStoreState, jsonSerializerOptions);
        if (state?.ConversationIdentifier is not { } conversationId)
        {
            throw new ArgumentException("Invalid serialized state", nameof(serializedStoreState));
        }

        // Use the internal constructor with all parameters to ensure partition key logic is centralized
        return state.UseHierarchicalPartitioning && state.TenantId != null && state.UserId != null
            ? new CosmosChatMessageStore(cosmosClient, databaseId, containerId, conversationId, ownsClient: false, state.TenantId, state.UserId)
            : new CosmosChatMessageStore(cosmosClient, databaseId, containerId, conversationId, ownsClient: false);
    }

    /// <inheritdoc />
    public override async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        // Fetch most recent messages in descending order when limit is set, then reverse to ascending
        var orderDirection = this.MaxMessagesToRetrieve.HasValue ? "DESC" : "ASC";
        var query = new QueryDefinition($"SELECT * FROM c WHERE c.conversationId = @conversationId AND c.type = @type ORDER BY c.timestamp {orderDirection}")
            .WithParameter("@conversationId", this.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<CosmosMessageDocument>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = this._partitionKey,
            MaxItemCount = this.MaxItemCount // Configurable query performance
        });

        var messages = new List<ChatMessage>();

        while (iterator.HasMoreResults)
        {
            var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);

            foreach (var document in response)
            {
                if (this.MaxMessagesToRetrieve.HasValue && messages.Count >= this.MaxMessagesToRetrieve.Value)
                {
                    break;
                }

                if (!string.IsNullOrEmpty(document.Message))
                {
                    var message = JsonSerializer.Deserialize<ChatMessage>(document.Message, s_defaultJsonOptions);
                    if (message != null)
                    {
                        messages.Add(message);
                    }
                }
            }

            if (this.MaxMessagesToRetrieve.HasValue && messages.Count >= this.MaxMessagesToRetrieve.Value)
            {
                break;
            }
        }

        // If we fetched in descending order (most recent first), reverse to ascending order
        if (this.MaxMessagesToRetrieve.HasValue)
        {
            messages.Reverse();
        }

        return messages;
    }

    /// <inheritdoc />
    public override async Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        if (messages is null)
        {
            throw new ArgumentNullException(nameof(messages));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var messageList = messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList();
        if (messageList.Count == 0)
        {
            return;
        }

        // Use transactional batch for atomic operations
        if (messageList.Count > 1)
        {
            await this.AddMessagesInBatchAsync(messageList, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await this.AddSingleMessageAsync(messageList.First(), cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Adds multiple messages using transactional batch operations for atomicity.
    /// </summary>
    private async Task AddMessagesInBatchAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        var currentTimestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        // Process messages in optimal batch sizes
        for (int i = 0; i < messages.Count; i += this.MaxBatchSize)
        {
            var batchMessages = messages.Skip(i).Take(this.MaxBatchSize).ToList();
            await this.ExecuteBatchOperationAsync(batchMessages, currentTimestamp, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Executes a single batch operation with enhanced error handling.
    /// Cosmos SDK handles throttling (429) retries automatically.
    /// </summary>
    private async Task ExecuteBatchOperationAsync(List<ChatMessage> messages, long timestamp, CancellationToken cancellationToken)
    {
        // Create all documents upfront for validation and batch operation
        var documents = new List<CosmosMessageDocument>(messages.Count);
        foreach (var message in messages)
        {
            documents.Add(this.CreateMessageDocument(message, timestamp));
        }

        // Defensive check: Verify all messages share the same partition key values
        // In hierarchical partitioning, this means same tenantId, userId, and sessionId
        // In simple partitioning, this means same conversationId
        if (documents.Count > 0)
        {
            if (this._useHierarchicalPartitioning)
            {
                // Verify all documents have matching hierarchical partition key components
                var firstDoc = documents[0];
                if (!documents.All(d => d.TenantId == firstDoc.TenantId && d.UserId == firstDoc.UserId && d.SessionId == firstDoc.SessionId))
                {
                    throw new InvalidOperationException("All messages in a batch must share the same partition key values (tenantId, userId, sessionId).");
                }
            }
            else
            {
                // Verify all documents have matching conversationId
                var firstConversationId = documents[0].ConversationId;
                if (!documents.All(d => d.ConversationId == firstConversationId))
                {
                    throw new InvalidOperationException("All messages in a batch must share the same partition key value (conversationId).");
                }
            }
        }

        // All messages in this store share the same partition key by design
        // Transactional batches require all items to share the same partition key
        var batch = this._container.CreateTransactionalBatch(this._partitionKey);

        foreach (var document in documents)
        {
            batch.CreateItem(document);
        }

        try
        {
            var response = await batch.ExecuteAsync(cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException($"Batch operation failed with status: {response.StatusCode}. Details: {response.ErrorMessage}");
            }
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.RequestEntityTooLarge)
        {
            // If batch is too large, split into smaller batches
            if (messages.Count == 1)
            {
                // Can't split further, use single operation
                await this.AddSingleMessageAsync(messages[0], cancellationToken).ConfigureAwait(false);
                return;
            }

            // Split the batch in half and retry
            var midpoint = messages.Count / 2;
            var firstHalf = messages.Take(midpoint).ToList();
            var secondHalf = messages.Skip(midpoint).ToList();

            await this.ExecuteBatchOperationAsync(firstHalf, timestamp, cancellationToken).ConfigureAwait(false);
            await this.ExecuteBatchOperationAsync(secondHalf, timestamp, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Adds a single message to the store.
    /// </summary>
    private async Task AddSingleMessageAsync(ChatMessage message, CancellationToken cancellationToken)
    {
        var document = this.CreateMessageDocument(message, DateTimeOffset.UtcNow.ToUnixTimeSeconds());

        try
        {
            await this._container.CreateItemAsync(document, this._partitionKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.RequestEntityTooLarge)
        {
            throw new InvalidOperationException(
                "Message exceeds Cosmos DB's maximum item size limit of 2MB. " +
                "Message ID: " + message.MessageId + ", Serialized size is too large. " +
                "Consider reducing message content or splitting into smaller messages.",
                ex);
        }
    }

    /// <summary>
    /// Creates a message document with enhanced metadata.
    /// </summary>
    private CosmosMessageDocument CreateMessageDocument(ChatMessage message, long timestamp)
    {
        return new CosmosMessageDocument
        {
            Id = Guid.NewGuid().ToString(),
            ConversationId = this.ConversationId,
            Timestamp = timestamp,
            MessageId = message.MessageId,
            Role = message.Role.Value,
            Message = JsonSerializer.Serialize(message, s_defaultJsonOptions),
            Type = "ChatMessage", // Type discriminator
            Ttl = this.MessageTtlSeconds, // Configurable TTL
            // Include hierarchical metadata when using hierarchical partitioning
            TenantId = this._useHierarchicalPartitioning ? this._tenantId : null,
            UserId = this._useHierarchicalPartitioning ? this._userId : null,
            SessionId = this._useHierarchicalPartitioning ? this.ConversationId : null
        };
    }

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var state = new StoreState
        {
            ConversationIdentifier = this.ConversationId,
            TenantId = this._tenantId,
            UserId = this._userId,
            UseHierarchicalPartitioning = this._useHierarchicalPartitioning
        };

        var options = jsonSerializerOptions ?? s_defaultJsonOptions;
        return JsonSerializer.SerializeToElement(state, options);
    }

    /// <summary>
    /// Gets the count of messages in this conversation.
    /// This is an additional utility method beyond the base contract.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of messages in the conversation.</returns>
    public async Task<int> GetMessageCountAsync(CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        // Efficient count query
        var query = new QueryDefinition("SELECT VALUE COUNT(1) FROM c WHERE c.conversationId = @conversationId AND c.Type = @type")
            .WithParameter("@conversationId", this.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<int>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = this._partitionKey
        });

        // COUNT queries always return a result
        var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
        return response.FirstOrDefault();
    }

    /// <summary>
    /// Deletes all messages in this conversation.
    /// This is an additional utility method beyond the base contract.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of messages deleted.</returns>
    public async Task<int> ClearMessagesAsync(CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        // Batch delete for efficiency
        var query = new QueryDefinition("SELECT VALUE c.id FROM c WHERE c.conversationId = @conversationId AND c.Type = @type")
            .WithParameter("@conversationId", this.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<string>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = this._partitionKey,
            MaxItemCount = this.MaxItemCount
        });

        var deletedCount = 0;

        while (iterator.HasMoreResults)
        {
            var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
            var batch = this._container.CreateTransactionalBatch(this._partitionKey);
            var batchItemCount = 0;

            foreach (var itemId in response)
            {
                if (!string.IsNullOrEmpty(itemId))
                {
                    batch.DeleteItem(itemId);
                    batchItemCount++;
                    deletedCount++;
                }
            }

            if (batchItemCount > 0)
            {
                await batch.ExecuteAsync(cancellationToken).ConfigureAwait(false);
            }
        }

        return deletedCount;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (!this._disposed)
        {
            if (this._ownsClient)
            {
                this._cosmosClient?.Dispose();
            }
            this._disposed = true;
        }
    }

    private sealed class StoreState
    {
        public string ConversationIdentifier { get; set; } = string.Empty;
        public string? TenantId { get; set; }
        public string? UserId { get; set; }
        public bool UseHierarchicalPartitioning { get; set; }
    }

    /// <summary>
    /// Represents a document stored in Cosmos DB for chat messages.
    /// </summary>
    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by Cosmos DB operations")]
    private sealed class CosmosMessageDocument
    {
        [Newtonsoft.Json.JsonProperty("id")]
        public string Id { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty("conversationId")]
        public string ConversationId { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty("timestamp")]
        public long Timestamp { get; set; }

        [Newtonsoft.Json.JsonProperty("messageId")]
        public string? MessageId { get; set; }

        [Newtonsoft.Json.JsonProperty("role")]
        public string? Role { get; set; }

        [Newtonsoft.Json.JsonProperty("message")]
        public string Message { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty("type")]
        public string Type { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty("ttl")]
        public int? Ttl { get; set; }

        /// <summary>
        /// Tenant ID for hierarchical partitioning scenarios (optional).
        /// </summary>
        [Newtonsoft.Json.JsonProperty("tenantId")]
        public string? TenantId { get; set; }

        /// <summary>
        /// User ID for hierarchical partitioning scenarios (optional).
        /// </summary>
        [Newtonsoft.Json.JsonProperty("userId")]
        public string? UserId { get; set; }

        /// <summary>
        /// Session ID for hierarchical partitioning scenarios (same as ConversationId for compatibility).
        /// </summary>
        [Newtonsoft.Json.JsonProperty("sessionId")]
        public string? SessionId { get; set; }
    }
}
