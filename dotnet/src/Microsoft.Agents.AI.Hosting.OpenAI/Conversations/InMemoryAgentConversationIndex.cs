// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// In-memory implementation of IAgentConversationIndex for development and testing.
/// This is a non-standard extension to the OpenAI Conversations API.
/// </summary>
internal sealed class InMemoryAgentConversationIndex : IAgentConversationIndex, IDisposable
{
    private readonly MemoryCache _cache;
    private readonly InMemoryStorageOptions _options;

    private sealed class ConversationSet
    {
        private readonly HashSet<string> _conversations = [];
        private readonly object _lock = new();

        public void Add(string conversationId)
        {
            lock (this._lock)
            {
                this._conversations.Add(conversationId);
            }
        }

        public bool Remove(string conversationId)
        {
            lock (this._lock)
            {
                return this._conversations.Remove(conversationId);
            }
        }

        public string[] GetAll()
        {
            lock (this._lock)
            {
                return [.. this._conversations];
            }
        }
    }

    public InMemoryAgentConversationIndex()
        : this(new InMemoryStorageOptions())
    {
    }

    public InMemoryAgentConversationIndex(InMemoryStorageOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        this._options = options;
        this._cache = new MemoryCache(options.ToMemoryCacheOptions());
    }

    private async Task<ConversationSet> GetOrCreateConversationSetAsync(string agentId, CancellationToken cancellationToken)
    {
        var conversationSet = await this._cache.GetOrCreateAtomicAsync(
            agentId,
            entry =>
            {
                entry.SetOptions(this._options.ToMemoryCacheEntryOptions());
                return new ConversationSet();
            },
            cancellationToken).ConfigureAwait(false);

        return conversationSet!;
    }

    /// <inheritdoc />
    public async Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);
        ArgumentException.ThrowIfNullOrEmpty(conversationId);

        ConversationSet conversationSet = await this.GetOrCreateConversationSetAsync(agentId, cancellationToken).ConfigureAwait(false);
        conversationSet.Add(conversationId);
    }

    /// <inheritdoc />
    public async Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);
        ArgumentException.ThrowIfNullOrEmpty(conversationId);

        if (this._cache.TryGetValue(agentId, out ConversationSet? conversationSet) && conversationSet is not null)
        {
            conversationSet.Remove(conversationId);
        }
    }

    /// <inheritdoc/>
    public async Task<ListResponse<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);

        string[] conversations = (this._cache.TryGetValue(agentId, out ConversationSet? conversationSet) && conversationSet is not null)
            ? conversationSet.GetAll()
            : [];

        return new ListResponse<string>
        {
            Data = [.. conversations],
            HasMore = false
        };
    }

    public void Dispose()
    {
        // The MemoryCache will call the post-eviction callbacks when disposed,
        // which will dispose all ConversationSet instances
        this._cache.Dispose();
    }
}
