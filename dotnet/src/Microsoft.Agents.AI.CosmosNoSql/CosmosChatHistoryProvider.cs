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
/// Provides a Cosmos DB implementation of the <see cref="ChatHistoryProvider"/> abstract class.
/// </summary>
[RequiresUnreferencedCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class CosmosChatHistoryProvider : ChatHistoryProvider, IDisposable
{
    private readonly ProviderSessionState<State> _sessionState;
    private readonly CosmosClient _cosmosClient;
    private readonly Container _container;
    private readonly bool _ownsClient;
    private bool _disposed;

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
    /// Gets or sets the maximum number of messages to retrieve from the provider.
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
    /// Gets the database ID associated with this provider.
    /// </summary>
    public string DatabaseId { get; init; }

    /// <summary>
    /// Gets the container ID associated with this provider.
    /// </summary>
    public string ContainerId { get; init; }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation, providing the conversation routing info (conversationId, tenantId, userId).</param>
    /// <param name="ownsClient">Whether this instance owns the CosmosClient and should dispose it.</param>
    /// <param name="stateKey">An optional key to use for storing the state in the <see cref="AgentSession.StateBag"/>.</param>
    /// <param name="provideOutputMessageFilter">An optional filter function to apply to messages when retrieving them from the chat history.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to messages before storing them in the chat history. If not set, defaults to excluding messages with source type <see cref="AgentRequestMessageSourceType.ChatHistory"/>.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> or <paramref name="stateInitializer"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatHistoryProvider(
        CosmosClient cosmosClient,
        string databaseId,
        string containerId,
        Func<AgentSession?, State> stateInitializer,
        bool ownsClient = false,
        string? stateKey = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
        : base(provideOutputMessageFilter, storeInputMessageFilter)
    {
        this._sessionState = new ProviderSessionState<State>(
            Throw.IfNull(stateInitializer),
            stateKey ?? this.GetType().Name);
        this._cosmosClient = Throw.IfNull(cosmosClient);
        this.DatabaseId = Throw.IfNullOrWhitespace(databaseId);
        this.ContainerId = Throw.IfNullOrWhitespace(containerId);
        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._ownsClient = ownsClient;
    }

    /// <inheritdoc />
    public override string StateKey => this._sessionState.StateKey;

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatHistoryProvider"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="stateKey">An optional key to use for storing the state in the <see cref="AgentSession.StateBag"/>.</param>
    /// <param name="provideOutputMessageFilter">An optional filter function to apply to messages when retrieving them from the chat history.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to messages before storing them in the chat history. If not set, defaults to excluding messages with source type <see cref="AgentRequestMessageSourceType.ChatHistory"/>.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatHistoryProvider(
        string connectionString,
        string databaseId,
        string containerId,
        Func<AgentSession?, State> stateInitializer,
        string? stateKey = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(connectionString)), databaseId, containerId, stateInitializer, ownsClient: true, stateKey, provideOutputMessageFilter, storeInputMessageFilter)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatHistoryProvider"/> class using TokenCredential for authentication.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="stateKey">An optional key to use for storing the state in the <see cref="AgentSession.StateBag"/>.</param>
    /// <param name="provideOutputMessageFilter">An optional filter function to apply to messages when retrieving them from the chat history.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to messages before storing them in the chat history. If not set, defaults to excluding messages with source type <see cref="AgentRequestMessageSourceType.ChatHistory"/>.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatHistoryProvider(
        string accountEndpoint,
        TokenCredential tokenCredential,
        string databaseId,
        string containerId,
        Func<AgentSession?, State> stateInitializer,
        string? stateKey = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
        : this(new CosmosClient(Throw.IfNullOrWhitespace(accountEndpoint), Throw.IfNull(tokenCredential)), databaseId, containerId, stateInitializer, ownsClient: true, stateKey, provideOutputMessageFilter, storeInputMessageFilter)
    {
    }

    /// <summary>
    /// Determines whether hierarchical partitioning should be used based on the state.
    /// </summary>
    private static bool UseHierarchicalPartitioning(State state) =>
        state.TenantId is not null && state.UserId is not null;

    /// <summary>
    /// Builds the partition key from the state.
    /// </summary>
    private static PartitionKey BuildPartitionKey(State state)
    {
        if (UseHierarchicalPartitioning(state))
        {
            return new PartitionKeyBuilder()
                .Add(state.TenantId)
                .Add(state.UserId)
                .Add(state.ConversationId)
                .Build();
        }

        return new PartitionKey(state.ConversationId);
    }

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var partitionKey = BuildPartitionKey(state);

        // Fetch most recent messages in descending order when limit is set, then reverse to ascending
        var orderDirection = this.MaxMessagesToRetrieve.HasValue ? "DESC" : "ASC";
        var query = new QueryDefinition($"SELECT * FROM c WHERE c.conversationId = @conversationId AND c.type = @type ORDER BY c.timestamp {orderDirection}")
            .WithParameter("@conversationId", state.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<CosmosMessageDocument>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = partitionKey,
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
    protected override async ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var messageList = context.RequestMessages.Concat(context.ResponseMessages ?? []).ToList();
        if (messageList.Count == 0)
        {
            return;
        }

        var partitionKey = BuildPartitionKey(state);

        // Use transactional batch for atomic operations
        if (messageList.Count > 1)
        {
            await this.AddMessagesInBatchAsync(partitionKey, state, messageList, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await this.AddSingleMessageAsync(partitionKey, state, messageList.First(), cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Adds multiple messages using transactional batch operations for atomicity.
    /// </summary>
    private async Task AddMessagesInBatchAsync(PartitionKey partitionKey, State state, List<ChatMessage> messages, CancellationToken cancellationToken)
    {
        var currentTimestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        // Process messages in optimal batch sizes
        for (int i = 0; i < messages.Count; i += this.MaxBatchSize)
        {
            var batchMessages = messages.Skip(i).Take(this.MaxBatchSize).ToList();
            await this.ExecuteBatchOperationAsync(partitionKey, state, batchMessages, currentTimestamp, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Executes a single batch operation with enhanced error handling.
    /// Cosmos SDK handles throttling (429) retries automatically.
    /// </summary>
    private async Task ExecuteBatchOperationAsync(PartitionKey partitionKey, State state, List<ChatMessage> messages, long timestamp, CancellationToken cancellationToken)
    {
        // Create all documents upfront for validation and batch operation
        var documents = new List<CosmosMessageDocument>(messages.Count);
        foreach (var message in messages)
        {
            documents.Add(this.CreateMessageDocument(state, message, timestamp));
        }

        // Defensive check: Verify all messages share the same partition key values
        // In hierarchical partitioning, this means same tenantId, userId, and sessionId
        // In simple partitioning, this means same conversationId
        if (documents.Count > 0)
        {
            if (UseHierarchicalPartitioning(state))
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
        var batch = this._container.CreateTransactionalBatch(partitionKey);

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
                await this.AddSingleMessageAsync(partitionKey, state, messages[0], cancellationToken).ConfigureAwait(false);
                return;
            }

            // Split the batch in half and retry
            var midpoint = messages.Count / 2;
            var firstHalf = messages.Take(midpoint).ToList();
            var secondHalf = messages.Skip(midpoint).ToList();

            await this.ExecuteBatchOperationAsync(partitionKey, state, firstHalf, timestamp, cancellationToken).ConfigureAwait(false);
            await this.ExecuteBatchOperationAsync(partitionKey, state, secondHalf, timestamp, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Adds a single message to the store.
    /// </summary>
    private async Task AddSingleMessageAsync(PartitionKey partitionKey, State state, ChatMessage message, CancellationToken cancellationToken)
    {
        var document = this.CreateMessageDocument(state, message, DateTimeOffset.UtcNow.ToUnixTimeSeconds());

        try
        {
            await this._container.CreateItemAsync(document, partitionKey, cancellationToken: cancellationToken).ConfigureAwait(false);
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
    private CosmosMessageDocument CreateMessageDocument(State state, ChatMessage message, long timestamp)
    {
        var useHierarchical = UseHierarchicalPartitioning(state);

        return new CosmosMessageDocument
        {
            Id = Guid.NewGuid().ToString(),
            ConversationId = state.ConversationId,
            Timestamp = timestamp,
            MessageId = message.MessageId,
            Role = message.Role.Value,
            Message = JsonSerializer.Serialize(message, s_defaultJsonOptions),
            Type = "ChatMessage", // Type discriminator
            Ttl = this.MessageTtlSeconds, // Configurable TTL
            // Include hierarchical metadata when using hierarchical partitioning
            TenantId = useHierarchical ? state.TenantId : null,
            UserId = useHierarchical ? state.UserId : null,
            SessionId = useHierarchical ? state.ConversationId : null
        };
    }

    /// <summary>
    /// Gets the count of messages in this conversation.
    /// This is an additional utility method beyond the base contract.
    /// </summary>
    /// <param name="session">The agent session to get state from.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of messages in the conversation.</returns>
    public async Task<int> GetMessageCountAsync(AgentSession? session, CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var state = this._sessionState.GetOrInitializeState(session);
        var partitionKey = BuildPartitionKey(state);

        // Efficient count query
        var query = new QueryDefinition("SELECT VALUE COUNT(1) FROM c WHERE c.conversationId = @conversationId AND c.type = @type")
            .WithParameter("@conversationId", state.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<int>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = partitionKey
        });

        // COUNT queries always return a result
        var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
        return response.FirstOrDefault();
    }

    /// <summary>
    /// Deletes all messages in this conversation.
    /// This is an additional utility method beyond the base contract.
    /// </summary>
    /// <param name="session">The agent session to get state from.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of messages deleted.</returns>
    public async Task<int> ClearMessagesAsync(AgentSession? session, CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var state = this._sessionState.GetOrInitializeState(session);
        var partitionKey = BuildPartitionKey(state);

        // Batch delete for efficiency
        var query = new QueryDefinition("SELECT VALUE c.id FROM c WHERE c.conversationId = @conversationId AND c.type = @type")
            .WithParameter("@conversationId", state.ConversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<string>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = partitionKey,
            MaxItemCount = this.MaxItemCount
        });

        var deletedCount = 0;

        while (iterator.HasMoreResults)
        {
            var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
            var batch = this._container.CreateTransactionalBatch(partitionKey);
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

    /// <summary>
    /// Represents the per-session state of a <see cref="CosmosChatHistoryProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class.
        /// </summary>
        /// <param name="conversationId">The unique identifier for this conversation thread.</param>
        /// <param name="tenantId">Optional tenant identifier for hierarchical partitioning.</param>
        /// <param name="userId">Optional user identifier for hierarchical partitioning.</param>
        public State(string conversationId, string? tenantId = null, string? userId = null)
        {
            this.ConversationId = Throw.IfNullOrWhitespace(conversationId);
            this.TenantId = tenantId;
            this.UserId = userId;
        }

        /// <summary>
        /// Gets the conversation ID associated with this state.
        /// </summary>
        public string ConversationId { get; }

        /// <summary>
        /// Gets the tenant identifier for hierarchical partitioning, if any.
        /// </summary>
        public string? TenantId { get; }

        /// <summary>
        /// Gets the user identifier for hierarchical partitioning, if any.
        /// </summary>
        public string? UserId { get; }
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
