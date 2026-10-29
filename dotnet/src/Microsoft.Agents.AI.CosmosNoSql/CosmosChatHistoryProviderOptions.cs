// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="CosmosChatHistoryProvider"/>.
/// </summary>
public sealed class CosmosChatHistoryProviderOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether the provider disposes a caller-supplied <see cref="CosmosClient"/>.
    /// </summary>
    /// <value>Defaults to <see langword="false"/>. Clients created by the provider are always disposed by it.</value>
    public bool OwnsClient { get; set; }

    /// <summary>
    /// Gets or sets the key used to store provider state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <value>Defaults to the provider's type name.</value>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets a delegate that builds the partition key for all storage, retrieval, count, and delete operations.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider uses a hierarchical key of tenant ID, user ID, and conversation ID
    /// if both tenant ID and user ID are set; otherwise, it uses the conversation ID.
    /// </value>
    /// <remarks>
    /// The key must match the container's partition key definition and the values persisted on the document.
    /// Tenant and user IDs are persisted whenever set, and the session ID is always the conversation ID,
    /// regardless of this strategy. To use flat <c>/conversationId</c> partitioning while retaining tenant and user
    /// metadata, set this to <c>state => new PartitionKey(state.ConversationId)</c>.
    /// Partition keys and metadata do not replace application-level authorization.
    /// </remarks>
    public Func<CosmosChatHistoryProvider.State, PartitionKey>? PartitionKeyFactory { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to messages retrieved from chat history.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? ProvideOutputMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to request messages before storing them in chat history.
    /// </summary>
    /// <value>When <see langword="null"/>, messages with source type <see cref="AgentRequestMessageSourceType.ChatHistory"/> are excluded.</value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StoreInputRequestMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to response messages before storing them in chat history.
    /// </summary>
    /// <value>When <see langword="null"/>, all response messages are stored.</value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StoreInputResponseMessageFilter { get; set; }
}
