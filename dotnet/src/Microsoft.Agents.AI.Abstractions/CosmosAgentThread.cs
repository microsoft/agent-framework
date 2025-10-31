// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for agent threads that maintain conversation state in Azure Cosmos DB.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="CosmosAgentThread"/> is designed for scenarios where conversation state should be persisted
/// in Azure Cosmos DB for durability, scalability, and cross-session availability. This approach provides
/// reliable persistence while maintaining efficient access to conversation data.
/// </para>
/// <para>
/// Cosmos threads persist conversation data across application restarts and can be shared across
/// multiple application instances.
/// </para>
/// </remarks>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public abstract class CosmosAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosAgentThread"/> class.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread. If null, a new GUID will be generated.</param>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    /// <remarks>
    /// This constructor creates a new Cosmos DB message store with connection string authentication.
    /// </remarks>
    protected CosmosAgentThread(string connectionString, string databaseId, string containerId, string? conversationId = null)
    {
        this.MessageStore = new CosmosChatMessageStore(connectionString, databaseId, containerId, conversationId ?? Guid.NewGuid().ToString("N"));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosAgentThread"/> class using managed identity.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread. If null, a new GUID will be generated.</param>
    /// <param name="useManagedIdentity">Must be true to use this constructor. This parameter distinguishes this constructor from the connection string version.</param>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace, or when useManagedIdentity is false.</exception>
    /// <remarks>
    /// This constructor creates a new Cosmos DB message store with managed identity authentication.
    /// </remarks>
    protected CosmosAgentThread(string accountEndpoint, string databaseId, string containerId, string? conversationId, bool useManagedIdentity)
    {
        if (!useManagedIdentity)
        {
            throw new ArgumentException("This constructor requires useManagedIdentity to be true.", nameof(useManagedIdentity));
        }

        this.MessageStore = new CosmosChatMessageStore(accountEndpoint, databaseId, containerId, conversationId ?? Guid.NewGuid().ToString("N"), useManagedIdentity: true);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosAgentThread"/> class using an existing CosmosClient.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="conversationId">The unique identifier for this conversation thread. If null, a new GUID will be generated.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="cosmosClient"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    /// <remarks>
    /// This constructor allows reuse of an existing CosmosClient instance across multiple threads.
    /// </remarks>
    protected CosmosAgentThread(CosmosClient cosmosClient, string databaseId, string containerId, string? conversationId = null)
    {
        this.MessageStore = new CosmosChatMessageStore(cosmosClient, databaseId, containerId, conversationId ?? Guid.NewGuid().ToString("N"));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosAgentThread"/> class with a pre-configured message store.
    /// </summary>
    /// <param name="messageStore">
    /// A <see cref="CosmosChatMessageStore"/> instance to use for storing chat messages.
    /// If <see langword="null"/>, an exception will be thrown.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="messageStore"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor allows sharing of message stores between threads or providing pre-configured
    /// message stores with specific settings.
    /// </remarks>
    protected CosmosAgentThread(CosmosChatMessageStore messageStore)
    {
        this.MessageStore = messageStore ?? throw new ArgumentNullException(nameof(messageStore));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CosmosAgentThread"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="messageStoreFactory">
    /// Factory function to create the <see cref="CosmosChatMessageStore"/> from its serialized state.
    /// This is required because Cosmos DB connection information cannot be reconstructed from serialized state.
    /// </param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedThreadState"/> is not a JSON object.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="messageStoreFactory"/> is <see langword="null"/>.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedThreadState"/> is invalid or cannot be deserialized to the expected type.</exception>
    /// <remarks>
    /// This constructor enables restoration of Cosmos threads from previously saved state. Since Cosmos DB
    /// connection information cannot be serialized for security reasons, a factory function must be provided
    /// to reconstruct the message store with appropriate connection details.
    /// </remarks>
    protected CosmosAgentThread(
        JsonElement serializedThreadState,
        Func<JsonElement, JsonSerializerOptions?, CosmosChatMessageStore> messageStoreFactory,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
#if NET6_0_OR_GREATER
        ArgumentNullException.ThrowIfNull(messageStoreFactory);
#else
        if (messageStoreFactory is null)
        {
            throw new ArgumentNullException(nameof(messageStoreFactory));
        }
#endif

        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = serializedThreadState.Deserialize(
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(CosmosAgentThreadState))) as CosmosAgentThreadState;

        this.MessageStore = messageStoreFactory.Invoke(state?.StoreState ?? default, jsonSerializerOptions);
    }

    /// <summary>
    /// Gets the <see cref="CosmosChatMessageStore"/> used by this thread.
    /// </summary>
    public CosmosChatMessageStore MessageStore { get; }

    /// <summary>
    /// Gets the conversation ID for this thread from the underlying message store.
    /// </summary>
    public string ConversationId => this.MessageStore.ConversationId;

    /// <summary>
    /// Gets or sets the maximum number of messages to return in a single query batch.
    /// This is delegated to the underlying message store.
    /// </summary>
    public int MaxItemCount
    {
        get => this.MessageStore.MaxItemCount;
        set => this.MessageStore.MaxItemCount = value;
    }

    /// <summary>
    /// Gets or sets the Time-To-Live (TTL) in seconds for messages.
    /// This is delegated to the underlying message store.
    /// </summary>
    public int? MessageTtlSeconds
    {
        get => this.MessageStore.MessageTtlSeconds;
        set => this.MessageStore.MessageTtlSeconds = value;
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    /// <remarks>
    /// Note that connection strings and credentials are not included in the serialized state for security reasons.
    /// When deserializing, you will need to provide connection information through the messageStoreFactory parameter.
    /// </remarks>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var storeState = this.MessageStore.Serialize(jsonSerializerOptions);

        var state = new CosmosAgentThreadState
        {
            StoreState = storeState,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(CosmosAgentThreadState)));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey) ?? this.MessageStore?.GetService(serviceType, serviceKey);

    /// <inheritdoc />
    protected internal override Task MessagesReceivedAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
        => this.MessageStore.AddMessagesAsync(newMessages, cancellationToken);

    /// <summary>
    /// Gets the total number of messages in this conversation.
    /// This is a Cosmos-specific optimization that provides efficient message counting.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The total number of messages in the conversation.</returns>
    public async Task<int> GetMessageCountAsync(CancellationToken cancellationToken = default)
    {
        return await this.MessageStore.GetMessageCountAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Clears all messages in this conversation.
    /// This is a Cosmos-specific utility method for conversation cleanup.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of messages that were deleted.</returns>
    public async Task<int> ClearMessagesAsync(CancellationToken cancellationToken = default)
    {
        return await this.MessageStore.ClearMessagesAsync(cancellationToken).ConfigureAwait(false);
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay => $"ConversationId = {this.ConversationId}";

    internal sealed class CosmosAgentThreadState
    {
        public JsonElement? StoreState { get; set; }
    }
}