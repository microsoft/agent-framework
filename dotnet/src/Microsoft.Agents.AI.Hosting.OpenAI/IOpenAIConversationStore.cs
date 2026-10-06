// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Defines persistent storage for the OpenAI Conversations API used by hosted Responses endpoints and DevUI.
/// </summary>
/// <remarks>
/// Conversation and item payloads are opaque JSON documents owned by the hosting package. Store implementations
/// should persist them without modifying their contents and return independently owned <see cref="JsonElement"/>
/// values that remain valid after the operation completes. Conversation identifiers passed to this store may
/// already include a caller-isolation scope applied by the hosting layer.
/// </remarks>
public interface IOpenAIConversationStore
{
    /// <summary>Creates a conversation.</summary>
    ValueTask CreateConversationAsync(
        OpenAIConversationRecord conversation,
        CancellationToken cancellationToken = default);

    /// <summary>Gets a conversation by identifier, or <see langword="null"/> when it does not exist.</summary>
    ValueTask<OpenAIConversationRecord?> GetConversationAsync(
        string conversationId,
        CancellationToken cancellationToken = default);

    /// <summary>Updates an existing conversation.</summary>
    /// <returns><see langword="true"/> when the conversation existed and was updated.</returns>
    ValueTask<bool> UpdateConversationAsync(
        OpenAIConversationRecord conversation,
        CancellationToken cancellationToken = default);

    /// <summary>Deletes a conversation and its items.</summary>
    /// <returns><see langword="true"/> when the conversation existed and was deleted.</returns>
    ValueTask<bool> DeleteConversationAsync(
        string conversationId,
        CancellationToken cancellationToken = default);

    /// <summary>Adds items to a conversation atomically and in the supplied order.</summary>
    ValueTask AddItemsAsync(
        string conversationId,
        IReadOnlyList<OpenAIConversationItem> items,
        CancellationToken cancellationToken = default);

    /// <summary>Gets an item from a conversation, or <see langword="null"/> when it does not exist.</summary>
    ValueTask<OpenAIConversationItem?> GetItemAsync(
        string conversationId,
        string itemId,
        CancellationToken cancellationToken = default);

    /// <summary>Lists conversation items using cursor-based pagination.</summary>
    ValueTask<OpenAIConversationItemsPage> ListItemsAsync(
        string conversationId,
        int limit,
        OpenAIConversationItemOrder order,
        string? after,
        CancellationToken cancellationToken = default);

    /// <summary>Deletes an item from a conversation.</summary>
    /// <returns><see langword="true"/> when the item existed and was deleted.</returns>
    ValueTask<bool> DeleteItemAsync(
        string conversationId,
        string itemId,
        CancellationToken cancellationToken = default);

    /// <summary>Adds a conversation to the listing index for an agent.</summary>
    ValueTask AddConversationToAgentAsync(
        string agentId,
        string conversationId,
        CancellationToken cancellationToken = default);

    /// <summary>Removes a conversation from the listing index for an agent.</summary>
    ValueTask RemoveConversationFromAgentAsync(
        string agentId,
        string conversationId,
        CancellationToken cancellationToken = default);

    /// <summary>Lists the conversation identifiers indexed for an agent.</summary>
    ValueTask<IReadOnlyList<string>> ListConversationIdsAsync(
        string agentId,
        CancellationToken cancellationToken = default);
}

/// <summary>Represents an opaque serialized OpenAI conversation.</summary>
public sealed class OpenAIConversationRecord
{
    /// <summary>Gets the conversation identifier.</summary>
    public required string Id { get; init; }

    /// <summary>Gets the serialized conversation payload.</summary>
    public required JsonElement Data { get; init; }
}

/// <summary>Represents an opaque serialized item in an OpenAI conversation.</summary>
public sealed class OpenAIConversationItem
{
    /// <summary>Gets the item identifier.</summary>
    public required string Id { get; init; }

    /// <summary>Gets the serialized item payload.</summary>
    public required JsonElement Data { get; init; }
}

/// <summary>Represents one page of OpenAI conversation items.</summary>
public sealed class OpenAIConversationItemsPage
{
    /// <summary>Gets the items in the requested order.</summary>
    public required IReadOnlyList<OpenAIConversationItem> Items { get; init; }

    /// <summary>Gets a value indicating whether more items are available after this page.</summary>
    public bool HasMore { get; init; }
}

/// <summary>Specifies the order in which conversation items are returned.</summary>
public enum OpenAIConversationItemOrder
{
    /// <summary>Oldest items first.</summary>
    Ascending,

    /// <summary>Newest items first.</summary>
    Descending,
}
