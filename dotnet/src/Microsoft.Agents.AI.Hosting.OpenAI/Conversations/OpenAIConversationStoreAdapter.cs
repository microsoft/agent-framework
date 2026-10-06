// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

internal sealed class OpenAIConversationStoreAdapter(IOpenAIConversationStore store) : IConversationStorage, IAgentConversationIndex
{
    private const int DefaultListItemLimit = 20;

    private readonly IOpenAIConversationStore _store = store ?? throw new ArgumentNullException(nameof(store));

    public async Task<Conversation> CreateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        await this._store.CreateConversationAsync(ToRecord(conversation), cancellationToken).ConfigureAwait(false);
        return conversation;
    }

    public async Task<Conversation?> GetConversationAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        OpenAIConversationRecord? record = await this._store.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        return record is null ? null : FromRecord(record);
    }

    public async Task<Conversation?> UpdateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        return await this._store.UpdateConversationAsync(ToRecord(conversation), cancellationToken).ConfigureAwait(false)
            ? conversation
            : null;
    }

    public Task<bool> DeleteConversationAsync(string conversationId, CancellationToken cancellationToken = default)
        => this._store.DeleteConversationAsync(conversationId, cancellationToken).AsTask();

    public async Task AddItemsAsync(string conversationId, IEnumerable<ItemResource> items, CancellationToken cancellationToken = default)
    {
        OpenAIConversationItem[] records = [.. items.Select(ToRecord)];
        await this._store.AddItemsAsync(conversationId, records, cancellationToken).ConfigureAwait(false);
    }

    public async Task<ItemResource?> GetItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
    {
        OpenAIConversationItem? record = await this._store.GetItemAsync(conversationId, itemId, cancellationToken).ConfigureAwait(false);
        return record is null ? null : FromRecord(record);
    }

    public async Task<ListResponse<ItemResource>> ListItemsAsync(
        string conversationId,
        int? limit = null,
        SortOrder? order = null,
        string? after = null,
        CancellationToken cancellationToken = default)
    {
        int effectiveLimit = Math.Clamp(limit ?? DefaultListItemLimit, 1, 100);
        OpenAIConversationItemOrder effectiveOrder = order is SortOrder.Ascending
            ? OpenAIConversationItemOrder.Ascending
            : OpenAIConversationItemOrder.Descending;
        OpenAIConversationItemsPage page = await this._store.ListItemsAsync(
            conversationId,
            effectiveLimit,
            effectiveOrder,
            after,
            cancellationToken).ConfigureAwait(false);
        List<ItemResource> items = [.. page.Items.Select(FromRecord)];

        return new ListResponse<ItemResource>
        {
            Data = items,
            FirstId = items.FirstOrDefault()?.Id,
            LastId = items.LastOrDefault()?.Id,
            HasMore = page.HasMore,
        };
    }

    public Task<bool> DeleteItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
        => this._store.DeleteItemAsync(conversationId, itemId, cancellationToken).AsTask();

    public Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
        => this._store.AddConversationToAgentAsync(agentId, conversationId, cancellationToken).AsTask();

    public Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
        => this._store.RemoveConversationFromAgentAsync(agentId, conversationId, cancellationToken).AsTask();

    public async Task<ListResponse<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
    {
        IReadOnlyList<string> conversationIds = await this._store.ListConversationIdsAsync(agentId, cancellationToken).ConfigureAwait(false);
        return new ListResponse<string>
        {
            Data = [.. conversationIds],
            HasMore = false,
        };
    }

    private static OpenAIConversationRecord ToRecord(Conversation conversation) => new()
    {
        Id = conversation.Id,
        Data = JsonSerializer.SerializeToElement(conversation, OpenAIHostingJsonContext.Default.Conversation),
    };

    private static Conversation FromRecord(OpenAIConversationRecord record)
    {
        Conversation conversation = record.Data.Deserialize(OpenAIHostingJsonContext.Default.Conversation)
            ?? throw new InvalidOperationException($"Stored conversation '{record.Id}' could not be deserialized.");
        if (!string.Equals(record.Id, conversation.Id, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Stored conversation key '{record.Id}' does not match payload id '{conversation.Id}'.");
        }

        return conversation;
    }

    private static OpenAIConversationItem ToRecord(ItemResource item) => new()
    {
        Id = item.Id,
        Data = JsonSerializer.SerializeToElement(item, OpenAIHostingJsonContext.Default.ItemResource),
    };

    private static ItemResource FromRecord(OpenAIConversationItem record)
    {
        ItemResource item = record.Data.Deserialize(OpenAIHostingJsonContext.Default.ItemResource)
            ?? throw new InvalidOperationException($"Stored conversation item '{record.Id}' could not be deserialized.");
        if (!string.Equals(record.Id, item.Id, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Stored item key '{record.Id}' does not match payload id '{item.Id}'.");
        }

        return item;
    }
}
