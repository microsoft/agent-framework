// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// In-memory implementation of IAgentConversationIndex for development and testing.
/// This is a non-standard extension to the OpenAI Conversations API.
/// </summary>
internal sealed class InMemoryAgentConversationIndex : IAgentConversationIndex
{
    private readonly ConcurrentDictionary<string, ConcurrentBag<string>> _agentConversations = new();

    /// <inheritdoc />
    public Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);
        ArgumentException.ThrowIfNullOrEmpty(conversationId);

        this._agentConversations.AddOrUpdate(
            agentId,
            _ => [conversationId],
            (_, existing) =>
            {
                existing.Add(conversationId);
                return existing;
            });

        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);
        ArgumentException.ThrowIfNullOrEmpty(conversationId);

        if (this._agentConversations.TryGetValue(agentId, out var conversations))
        {
            // Note: ConcurrentBag doesn't support removal, so we'll recreate the bag without the target item
            var updatedConversations = new ConcurrentBag<string>();
            foreach (var id in conversations)
            {
                if (id != conversationId)
                {
                    updatedConversations.Add(id);
                }
            }
            this._agentConversations.TryUpdate(agentId, updatedConversations, conversations);
        }

        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<IReadOnlyList<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentId);

        var conversations = this._agentConversations.TryGetValue(agentId, out var bag)
            ? bag.ToArray()
            : Array.Empty<string>();

        return Task.FromResult<IReadOnlyList<string>>(conversations);
    }
}
