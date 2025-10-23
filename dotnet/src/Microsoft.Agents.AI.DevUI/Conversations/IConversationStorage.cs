﻿// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Storage abstraction for conversations and messages.
/// This interface provides operations specifically designed for conversation management,
/// going beyond simple key-value storage to support conversation-specific queries and operations.
/// </summary>
internal interface IConversationStorage
{
    /// <summary>
    /// Creates a new conversation.
    /// </summary>
    /// <param name="conversation">The conversation to create.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The created conversation.</returns>
    Task<Conversation> CreateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a conversation by ID.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The conversation if found, null otherwise.</returns>
    Task<Conversation?> GetConversationAsync(string conversationId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Updates an existing conversation.
    /// </summary>
    /// <param name="conversation">The conversation with updated values.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The updated conversation if found, null otherwise.</returns>
    Task<Conversation?> UpdateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a conversation and all its messages.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if deleted, false if not found.</returns>
    Task<bool> DeleteConversationAsync(string conversationId, CancellationToken cancellationToken = default);

    // Item operations

    /// <summary>
    /// Adds an item to a conversation.
    /// </summary>
    /// <param name="item">The item to add.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The created item.</returns>
    Task<ConversationItem> AddItemAsync(ConversationItem item, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves an item by ID.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="itemId">The item ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The item if found, null otherwise.</returns>
    Task<ConversationItem?> GetItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Lists items in a conversation with pagination support.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="limit">Maximum number of items to return (default: 20, max: 100).</param>
    /// <param name="order">Sort order (default: Descending).</param>
    /// <param name="after">Cursor for pagination - return items after this ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A list response with items and pagination info.</returns>
    Task<ListResponse<ConversationItem>> ListItemsAsync(
        string conversationId,
        int limit = 20,
        SortOrder order = SortOrder.Descending,
        string? after = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a specific item from a conversation.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="itemId">The item ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if deleted, false if not found.</returns>
    Task<bool> DeleteItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default);
}
