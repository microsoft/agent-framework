// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// In-memory implementation of conversation storage for testing and development.
/// This implementation is thread-safe but data is not persisted across application restarts.
/// </summary>
internal sealed class InMemoryConversationStorage : IConversationStorage, IDisposable
{
    private const int DefaultListItemLimit = 20;

    private readonly MemoryCache _cache;
    private readonly InMemoryStorageOptions _options;

    public InMemoryConversationStorage()
        : this(new InMemoryStorageOptions())
    {
    }

    public InMemoryConversationStorage(InMemoryStorageOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        this._options = options;
        this._cache = new MemoryCache(options.ToMemoryCacheOptions());
    }

    /// <inheritdoc />
    public Task<Conversation> CreateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        // Check if conversation already exists
        if (this._cache.TryGetValue(conversation.Id, out ConversationState? _))
        {
            throw new InvalidOperationException($"Conversation with ID '{conversation.Id}' already exists.");
        }

        var state = new ConversationState(conversation);
        var entryOptions = this._options.ToMemoryCacheEntryOptions();
        this._cache.Set(conversation.Id, state, entryOptions);
        return Task.FromResult(conversation);
    }

    /// <inheritdoc />
    public Task<Conversation?> GetConversationAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        if (this._cache.TryGetValue(conversationId, out ConversationState? state) && state is not null)
        {
            return Task.FromResult<Conversation?>(state.Conversation);
        }

        return Task.FromResult<Conversation?>(null);
    }

    /// <inheritdoc />
    public Task<Conversation?> UpdateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        if (this._cache.TryGetValue(conversation.Id, out ConversationState? state) && state is not null)
        {
            state.UpdateConversation(conversation);
            // Touch the cache entry to reset expiration
            var entryOptions = this._options.ToMemoryCacheEntryOptions();
            this._cache.Set(conversation.Id, state, entryOptions);
            return Task.FromResult<Conversation?>(conversation);
        }

        return Task.FromResult<Conversation?>(null);
    }

    /// <inheritdoc />
    public Task<bool> DeleteConversationAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        if (this._cache.TryGetValue<ConversationState>(conversationId, out _))
        {
            this._cache.Remove(conversationId);
            return Task.FromResult(true);
        }

        return Task.FromResult(false);
    }

    /// <inheritdoc />
    public Task AddItemsAsync(string conversationId, IEnumerable<ItemResource> items, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(conversationId, nameof(conversationId));
        ArgumentNullException.ThrowIfNull(items);

        if (!this._cache.TryGetValue(conversationId, out ConversationState? state) || state is null)
        {
            throw new InvalidOperationException($"Conversation '{conversationId}' not found.");
        }

        foreach (ItemResource item in items)
        {
            state.AddItem(item);
        }

        // Touch the cache entry to reset expiration
        var entryOptions = this._options.ToMemoryCacheEntryOptions();
        this._cache.Set(conversationId, state, entryOptions);
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<ItemResource?> GetItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
    {
        if (this._cache.TryGetValue(conversationId, out ConversationState? state) && state is not null)
        {
            return Task.FromResult(state.GetItem(itemId));
        }

        return Task.FromResult<ItemResource?>(null);
    }

    /// <inheritdoc/>
    public Task<ListResponse<ItemResource>> ListItemsAsync(
        string conversationId,
        int? limit = null,
        SortOrder? order = null,
        string? after = null,
        CancellationToken cancellationToken = default)
    {
        int effectiveLimit = Math.Clamp(limit ?? DefaultListItemLimit, 1, 100);
        SortOrder effectiveOrder = order ?? SortOrder.Descending;

        if (!this._cache.TryGetValue(conversationId, out ConversationState? state) || state is null)
        {
            throw new InvalidOperationException($"Conversation '{conversationId}' not found.");
        }

        var allItems = state.GetAllItems();

        // For descending order, reverse the list
        if (effectiveOrder == SortOrder.Descending)
        {
            allItems.Reverse();
        }

        var filtered = allItems.AsEnumerable();

        if (!string.IsNullOrEmpty(after))
        {
            var afterIndex = allItems.FindIndex(m => m.Id == after);
            if (afterIndex >= 0)
            {
                filtered = allItems.Skip(afterIndex + 1);
            }
        }

        List<ItemResource> result;
        bool hasMore;

        if (filtered.TryGetNonEnumeratedCount(out int count))
        {
            hasMore = count > effectiveLimit;
            result = filtered.Take(effectiveLimit).ToList();
        }
        else
        {
            result = filtered.Take(effectiveLimit + 1).ToList();
            hasMore = result.Count > effectiveLimit;
            if (hasMore)
            {
                result = result.Take(effectiveLimit).ToList();
            }
        }

        return Task.FromResult(new ListResponse<ItemResource>
        {
            Data = result,
            FirstId = result.FirstOrDefault()?.Id,
            LastId = result.LastOrDefault()?.Id,
            HasMore = hasMore
        });
    }

    /// <inheritdoc />
    public Task<bool> DeleteItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
    {
        if (this._cache.TryGetValue(conversationId, out ConversationState? state) && state is not null)
        {
            var removed = state.RemoveItem(itemId);
            if (removed)
            {
                // Touch the cache entry to reset expiration
                var entryOptions = this._options.ToMemoryCacheEntryOptions();
                this._cache.Set(conversationId, state, entryOptions);
            }

            return Task.FromResult(removed);
        }

        return Task.FromResult(false);
    }

    /// <summary>
    /// Encapsulates per-conversation state including items storage and synchronization.
    /// </summary>
    private sealed class ConversationState
    {
#if NET9_0_OR_GREATER
        private readonly OrderedDictionary<string, ItemResource> _items = [];
        private readonly object _lock = new();
        private Conversation _conversation;

        public ConversationState(Conversation conversation)
        {
            this._conversation = conversation;
        }

        public Conversation Conversation
        {
            get
            {
                lock (this._lock)
                {
                    return this._conversation;
                }
            }
        }

        public void UpdateConversation(Conversation conversation)
        {
            lock (this._lock)
            {
                this._conversation = conversation;
            }
        }

        public void AddItem(ItemResource item)
        {
            lock (this._lock)
            {
                if (!this._items.TryAdd(item.Id, item))
                {
                    throw new InvalidOperationException($"Item with ID '{item.Id}' already exists.");
                }
            }
        }

        public ItemResource? GetItem(string itemId)
        {
            lock (this._lock)
            {
                this._items.TryGetValue(itemId, out var item);
                return item;
            }
        }

        public List<ItemResource> GetAllItems()
        {
            lock (this._lock)
            {
                return this._items.Values.ToList();
            }
        }

        public bool RemoveItem(string itemId)
        {
            lock (this._lock)
            {
                return this._items.Remove(itemId);
            }
        }
#else
        private readonly List<ItemResource> _items = [];
        private readonly object _lock = new();
        private Conversation _conversation;

        public ConversationState(Conversation conversation)
        {
            this._conversation = conversation;
        }

        public Conversation Conversation
        {
            get
            {
                lock (this._lock)
                {
                    return this._conversation;
                }
            }
        }

        public void UpdateConversation(Conversation conversation)
        {
            lock (this._lock)
            {
                this._conversation = conversation;
            }
        }

        public void AddItem(ItemResource item)
        {
            lock (this._lock)
            {
                if (this._items.Exists(i => i.Id == item.Id))
                {
                    throw new InvalidOperationException($"Item with ID '{item.Id}' already exists.");
                }

                this._items.Add(item);
            }
        }

        public ItemResource? GetItem(string itemId)
        {
            lock (this._lock)
            {
                return this._items.Find(i => i.Id == itemId);
            }
        }

        public List<ItemResource> GetAllItems()
        {
            lock (this._lock)
            {
                return this._items.ToList();
            }
        }

        public bool RemoveItem(string itemId)
        {
            lock (this._lock)
            {
                return this._items.RemoveAll(i => i.Id == itemId) > 0;
            }
        }
#endif
    }

    public void Dispose()
    {
        this._cache.Dispose();
    }
}
