// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// A delegating <see cref="IAgentConversationIndex"/> that scopes the index by the caller's isolation key,
/// so that listing conversations for an agent returns only the caller's own conversations.
/// </summary>
/// <remarks>
/// The agent identifier forms the index key and is therefore scoped; the conversation identifiers held in
/// the index remain bare, so they can be passed straight back into <see cref="IConversationStorage"/>.
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
        this._innerIndex = innerIndex ?? throw new ArgumentNullException(nameof(innerIndex));
        this._resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
    }

    /// <inheritdoc />
    public async Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        string scopedAgentId = await this._resolver.ScopeIdAsync(agentId, cancellationToken).ConfigureAwait(false);

        await this._innerIndex.AddConversationAsync(scopedAgentId, conversationId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
    {
        string scopedAgentId = await this._resolver.ScopeIdAsync(agentId, cancellationToken).ConfigureAwait(false);

        await this._innerIndex.RemoveConversationAsync(scopedAgentId, conversationId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<ListResponse<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
    {
        string scopedAgentId = await this._resolver.ScopeIdAsync(agentId, cancellationToken).ConfigureAwait(false);

        return await this._innerIndex.GetConversationIdsAsync(scopedAgentId, cancellationToken).ConfigureAwait(false);
    }
}
