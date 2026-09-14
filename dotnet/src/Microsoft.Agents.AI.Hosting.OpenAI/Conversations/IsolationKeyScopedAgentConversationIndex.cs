// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// A delegating <see cref="IAgentConversationIndex"/> that scopes indexed conversation identifiers by the caller's isolation key,
/// so that listing conversations for an agent returns only the caller's own conversations.
/// </summary>
/// <remarks>
/// The index is keyed by the bare agent identifier, so the underlying cache holds one entry per agent
/// rather than one per caller-agent pair. Conversation identifiers held in that entry are scoped,
/// filtered for the current caller, and returned bare.
/// </remarks>
internal sealed class IsolationKeyScopedAgentConversationIndex : IAgentConversationIndex
{
    private readonly IAgentConversationIndex _innerIndex;
    private readonly IsolationKeyResolver _resolver;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedAgentConversationIndex"/> class.
    /// </summary>
    /// <param name="innerIndex">The underlying index to delegate to.</param>
    /// <param name="resolver">The resolver used to scope agent identifiers.</param>
    public IsolationKeyScopedAgentConversationIndex(IAgentConversationIndex innerIndex, IsolationKeyResolver resolver)
    {
        this._innerIndex = Throw.IfNull(innerIndex);
        this._resolver = Throw.IfNull(resolver);
    }

    /// <inheritdoc />
    public async Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        string scopedConversationId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        await this._innerIndex.AddConversationAsync(agentId, scopedConversationId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        string scopedConversationId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        await this._innerIndex.RemoveConversationAsync(agentId, scopedConversationId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<ListResponse<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
    {
        string? key = await this._resolver.GetKeyAsync(cancellationToken).ConfigureAwait(false);
        ListResponse<string> response = await this._innerIndex.GetConversationIdsAsync(agentId, cancellationToken).ConfigureAwait(false);

        if (key is null)
        {
            return response;
        }

        var conversationIds = new List<string>(response.Data.Count);
        foreach (string scopedConversationId in response.Data)
        {
            if (IsolationKeyResolver.IsInScope(scopedConversationId, key))
            {
                conversationIds.Add(IsolationKeyResolver.UnscopeId(scopedConversationId, key));
            }
        }

        return new ListResponse<string>
        {
            Data = conversationIds,
            FirstId = conversationIds.Count > 0 ? conversationIds[0] : null,
            LastId = conversationIds.Count > 0 ? conversationIds[^1] : null,
            HasMore = response.HasMore,
        };
    }
}
