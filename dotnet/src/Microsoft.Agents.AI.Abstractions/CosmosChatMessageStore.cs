// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a Cosmos DB implementation of the <see cref="ChatMessageStore"/> abstract class.
/// </summary>
public sealed class CosmosChatMessageStore : ChatMessageStore, IDisposable
{
    private readonly CosmosClient _cosmosClient;
    private readonly Container _container;
    private readonly string _conversationId;
    private readonly string _databaseId;
    private readonly string _containerId;
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

    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "JSON serialization is controlled")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "JSON serialization is controlled")]
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
    /// Gets or sets the Time-To-Live (TTL) in seconds for messages.
    /// Default is 86400 seconds (24 hours). Set to null to disable TTL.
    /// </summary>
    public int? MessageTtlSeconds { get; set; } = 86400;

    /// <summary>
    /// Gets the conversation ID associated with this message store.
    /// </summary>
    public string ConversationId => this._conversationId;

    /// <summary>
    /// Gets the database ID associated with this message store.
    /// </summary>
    public string DatabaseId => this._databaseId;

    /// <summary>
    /// Gets the container ID associated with this message store.
    /// </summary>
    public string ContainerId => this._containerId;

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
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Connection string cannot be null or whitespace.", nameof(connectionString));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Database ID cannot be null or whitespace.", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Container ID cannot be null or whitespace.", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(conversationId))
        {
            throw new ArgumentException("Conversation ID cannot be null or whitespace.", nameof(conversationId));
        }

        this._cosmosClient = new CosmosClient(connectionString);
        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = conversationId;
        this._databaseId = databaseId;
        this._containerId = containerId;
        this._ownsClient = true;

        // Initialize simple partitioning mode
        this._tenantId = null;
        this._userId = null;
        this._useHierarchicalPartitioning = false;
        this._partitionKey = new PartitionKey(conversationId);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using DefaultAzureCredential.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="useManagedIdentity">This parameter is used to distinguish this constructor from the connection string constructor. Always pass true.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, string databaseId, string containerId, bool useManagedIdentity)
        : this(accountEndpoint, databaseId, containerId, Guid.NewGuid().ToString("N"), useManagedIdentity)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using DefaultAzureCredential.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread.</param>
    /// <param name="useManagedIdentity">This parameter is used to distinguish this constructor from the connection string constructor. Always pass true.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, string databaseId, string containerId, string conversationId, bool useManagedIdentity)
    {
        if (string.IsNullOrWhiteSpace(accountEndpoint))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(accountEndpoint));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(conversationId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(conversationId));
        }

        if (!useManagedIdentity)
        {
            throw new ArgumentException("This constructor requires useManagedIdentity to be true. Use the connection string constructor for key-based authentication.", nameof(useManagedIdentity));
        }

        this._cosmosClient = new CosmosClient(accountEndpoint, new DefaultAzureCredential());
        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = conversationId;
        this._databaseId = databaseId;
        this._containerId = containerId;
        this._ownsClient = true;

        // Initialize simple partitioning mode
        this._tenantId = null;
        this._userId = null;
        this._useHierarchicalPartitioning = false;
        this._partitionKey = new PartitionKey(conversationId);
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
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._ownsClient = false;

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(conversationId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(conversationId));
        }

        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = conversationId;
        this._databaseId = databaseId;
        this._containerId = containerId;

        // Initialize simple partitioning mode
        this._tenantId = null;
        this._userId = null;
        this._useHierarchicalPartitioning = false;
        this._partitionKey = new PartitionKey(conversationId);
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
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Connection string cannot be null or whitespace.", nameof(connectionString));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Database ID cannot be null or whitespace.", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Container ID cannot be null or whitespace.", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(tenantId))
        {
            throw new ArgumentException("Tenant ID cannot be null or whitespace.", nameof(tenantId));
        }

        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new ArgumentException("User ID cannot be null or whitespace.", nameof(userId));
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            throw new ArgumentException("Session ID cannot be null or whitespace.", nameof(sessionId));
        }

        this._cosmosClient = new CosmosClient(connectionString);
        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = sessionId; // Use sessionId as conversationId for compatibility
        this._databaseId = databaseId;
        this._containerId = containerId;
        this._containerId = containerId;

        // Initialize hierarchical partitioning mode
        this._tenantId = tenantId;
        this._userId = userId;
        this._useHierarchicalPartitioning = true;
        // Use native hierarchical partition key with PartitionKeyBuilder
        this._partitionKey = new PartitionKeyBuilder()
            .Add(tenantId)
            .Add(userId)
            .Add(sessionId)
            .Build();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class using DefaultAzureCredential with hierarchical partition keys.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="tenantId">The tenant identifier for hierarchical partitioning.</param>
    /// <param name="userId">The user identifier for hierarchical partitioning.</param>
    /// <param name="sessionId">The session identifier for hierarchical partitioning.</param>
    /// <param name="useManagedIdentity">This parameter is used to distinguish this constructor from the connection string constructor. Always pass true.</param>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    public CosmosChatMessageStore(string accountEndpoint, string databaseId, string containerId, string tenantId, string userId, string sessionId, bool useManagedIdentity)
    {
        if (string.IsNullOrWhiteSpace(accountEndpoint))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(accountEndpoint));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(tenantId))
        {
            throw new ArgumentException("Tenant ID cannot be null or whitespace.", nameof(tenantId));
        }

        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new ArgumentException("User ID cannot be null or whitespace.", nameof(userId));
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            throw new ArgumentException("Session ID cannot be null or whitespace.", nameof(sessionId));
        }

        if (!useManagedIdentity)
        {
            throw new ArgumentException("This constructor requires useManagedIdentity to be true. Use the connection string constructor for key-based authentication.", nameof(useManagedIdentity));
        }

        this._cosmosClient = new CosmosClient(accountEndpoint, new DefaultAzureCredential());
        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = sessionId; // Use sessionId as conversationId for compatibility
        this._databaseId = databaseId;
        this._containerId = containerId;
        this._containerId = containerId;

        // Initialize hierarchical partitioning mode
        this._tenantId = tenantId;
        this._userId = userId;
        this._useHierarchicalPartitioning = true;
        // Use native hierarchical partition key with PartitionKeyBuilder
        this._partitionKey = new PartitionKeyBuilder()
            .Add(tenantId)
            .Add(userId)
            .Add(sessionId)
            .Build();
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
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._ownsClient = false;

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        if (string.IsNullOrWhiteSpace(tenantId))
        {
            throw new ArgumentException("Tenant ID cannot be null or whitespace.", nameof(tenantId));
        }

        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new ArgumentException("User ID cannot be null or whitespace.", nameof(userId));
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            throw new ArgumentException("Session ID cannot be null or whitespace.", nameof(sessionId));
        }

        this._container = this._cosmosClient.GetContainer(databaseId, containerId);
        this._conversationId = sessionId; // Use sessionId as conversationId for compatibility
        this._databaseId = databaseId;
        this._containerId = containerId;

        // Initialize hierarchical partitioning mode
        this._tenantId = tenantId;
        this._userId = userId;
        this._useHierarchicalPartitioning = true;
        // Use native hierarchical partition key with PartitionKeyBuilder
        this._partitionKey = new PartitionKeyBuilder()
            .Add(tenantId)
            .Add(userId)
            .Add(sessionId)
            .Build();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosChatMessageStore"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedStoreState">A <see cref="JsonElement"/> representing the serialized state of the message store.</param>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the serialized state cannot be deserialized.</exception>
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "StoreState type is controlled and used for serialization")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "StoreState type is controlled and used for serialization")]
    public CosmosChatMessageStore(JsonElement serializedStoreState, CosmosClient cosmosClient, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        this._cosmosClient = cosmosClient ?? throw new ArgumentNullException(nameof(cosmosClient));
        this._ownsClient = false;

        if (serializedStoreState.ValueKind is JsonValueKind.Object)
        {
            var state = JsonSerializer.Deserialize<StoreState>(serializedStoreState, jsonSerializerOptions);
            if (state?.ConversationIdentifier is { } conversationId && state.DatabaseIdentifier is { } databaseId && state.ContainerIdentifier is { } containerId)
            {
                this._conversationId = conversationId;
                this._databaseId = databaseId;
                this._containerId = containerId;
                this._container = this._cosmosClient.GetContainer(databaseId, containerId);

                // Initialize hierarchical partitioning if available in state
                this._tenantId = state.TenantId;
                this._userId = state.UserId;
                this._useHierarchicalPartitioning = state.UseHierarchicalPartitioning;

                if (this._useHierarchicalPartitioning && this._tenantId != null && this._userId != null)
                {
                    // Use native hierarchical partition key with PartitionKeyBuilder
                    this._partitionKey = new PartitionKeyBuilder()
                        .Add(this._tenantId)
                        .Add(this._userId)
                        .Add(conversationId)
                        .Build();
                }
                else
                {
                    this._partitionKey = new PartitionKey(conversationId);
                }

                return;
            }
        }

        throw new ArgumentException("Invalid serialized state", nameof(serializedStoreState));
    }

    /// <inheritdoc />
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "ChatMessage deserialization is controlled")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "ChatMessage deserialization is controlled")]
    public override async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(GetType().FullName);
        }
#pragma warning restore CA1513

        // Use type discriminator for efficient queries
        var query = new QueryDefinition("SELECT * FROM c WHERE c.conversationId = @conversationId AND c.Type = @type ORDER BY c.Timestamp ASC")
            .WithParameter("@conversationId", this._conversationId)
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
                if (!string.IsNullOrEmpty(document.Message))
                {
                    var message = JsonSerializer.Deserialize<ChatMessage>(document.Message, s_defaultJsonOptions);
                    if (message != null)
                    {
                        messages.Add(message);
                    }
                }
            }
        }

        return messages;
    }

    /// <inheritdoc />
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "ChatMessage serialization is controlled")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "ChatMessage serialization is controlled")]
    public override async Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        if (messages is null)
        {
            throw new ArgumentNullException(nameof(messages));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(GetType().FullName);
        }
#pragma warning restore CA1513

        var messageList = messages.ToList();
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
            await this.AddSingleMessageAsync(messageList[0], cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Adds multiple messages using transactional batch operations for atomicity.
    /// </summary>
    private async Task AddMessagesInBatchAsync(IList<ChatMessage> messages, CancellationToken cancellationToken)
    {
        var batch = this._container.CreateTransactionalBatch(this._partitionKey);
        var currentTimestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        foreach (var message in messages)
        {
            var document = this.CreateMessageDocument(message, currentTimestamp);
            batch.CreateItem(document);
        }

        try
        {
            var response = await batch.ExecuteAsync(cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException($"Batch operation failed with status: {response.StatusCode}");
            }
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.RequestEntityTooLarge)
        {
            // Fallback to individual operations if batch is too large
            foreach (var message in messages)
            {
                await this.AddSingleMessageAsync(message, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Adds a single message to the store.
    /// </summary>
    private async Task AddSingleMessageAsync(ChatMessage message, CancellationToken cancellationToken)
    {
        var document = this.CreateMessageDocument(message, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
        await this._container.CreateItemAsync(document, this._partitionKey, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates a message document with enhanced metadata.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "ChatMessage serialization is controlled")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "ChatMessage serialization is controlled")]
    private CosmosMessageDocument CreateMessageDocument(ChatMessage message, long timestamp)
    {
        return new CosmosMessageDocument
        {
            Id = Guid.NewGuid().ToString(),
            ConversationId = this._conversationId,
            Timestamp = timestamp,
            MessageId = message.MessageId ?? Guid.NewGuid().ToString(),
            Role = message.Role.Value ?? "unknown",
            Message = JsonSerializer.Serialize(message, s_defaultJsonOptions),
            Type = "ChatMessage", // Type discriminator
            Ttl = this.MessageTtlSeconds, // Configurable TTL
            // Include hierarchical metadata when using hierarchical partitioning
            TenantId = this._useHierarchicalPartitioning ? this._tenantId : null,
            UserId = this._useHierarchicalPartitioning ? this._userId : null,
            SessionId = this._useHierarchicalPartitioning ? this._conversationId : null
        };
    }

    /// <inheritdoc />
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "StoreState serialization is controlled")]
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling", Justification = "StoreState serialization is controlled")]
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(GetType().FullName);
        }
#pragma warning restore CA1513

        var state = new StoreState
        {
            ConversationIdentifier = this._conversationId,
            DatabaseIdentifier = this.DatabaseId,
            ContainerIdentifier = this.ContainerId,
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
            throw new ObjectDisposedException(GetType().FullName);
        }
#pragma warning restore CA1513

        // Efficient count query
        var query = new QueryDefinition("SELECT VALUE COUNT(1) FROM c WHERE c.conversationId = @conversationId AND c.Type = @type")
            .WithParameter("@conversationId", this._conversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<int>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = this._partitionKey
        });

        if (iterator.HasMoreResults)
        {
            var response = await iterator.ReadNextAsync(cancellationToken).ConfigureAwait(false);
            return response.FirstOrDefault();
        }

        return 0;
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
            throw new ObjectDisposedException(GetType().FullName);
        }
#pragma warning restore CA1513

        // Batch delete for efficiency
        var query = new QueryDefinition("SELECT VALUE c.id FROM c WHERE c.conversationId = @conversationId AND c.Type = @type")
            .WithParameter("@conversationId", this._conversationId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._container.GetItemQueryIterator<string>(query, requestOptions: new QueryRequestOptions
        {
            PartitionKey = new PartitionKey(this._conversationId),
            MaxItemCount = this.MaxItemCount
        });

        var deletedCount = 0;
        var partitionKey = new PartitionKey(this._conversationId);

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

    private sealed class StoreState
    {
        public string ConversationIdentifier { get; set; } = string.Empty;
        public string DatabaseIdentifier { get; set; } = string.Empty;
        public string ContainerIdentifier { get; set; } = string.Empty;
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

        [Newtonsoft.Json.JsonProperty(nameof(Timestamp))]
        public long Timestamp { get; set; }

        [Newtonsoft.Json.JsonProperty(nameof(MessageId))]
        public string MessageId { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty(nameof(Role))]
        public string Role { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty(nameof(Message))]
        public string Message { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty(nameof(Type))]
        public string Type { get; set; } = string.Empty;

        [Newtonsoft.Json.JsonProperty(nameof(Ttl))]
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