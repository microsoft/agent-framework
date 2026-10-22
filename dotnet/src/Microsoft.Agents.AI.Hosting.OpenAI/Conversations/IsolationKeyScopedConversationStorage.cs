// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// A delegating <see cref="IConversationStorage"/> that scopes conversation keys by the caller's isolation
/// key, so that a conversation can only be resolved by the caller that created it.
/// </summary>
/// <remarks>
/// Only the storage key is scoped. The <see cref="Conversation.Id"/> observed by callers is always the bare
/// identifier, so the wire format of the OpenAI Conversations API is unchanged.
/// </remarks>
internal sealed class IsolationKeyScopedConversationStorage : IConversationStorage
{
    private readonly IConversationStorage _innerStorage;
    private readonly IsolationKeyResolver _resolver;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedConversationStorage"/> class.
    /// </summary>
    /// <param name="innerStorage">The underlying storage to delegate to.</param>
    /// <param name="resolver">The resolver used to scope conversation identifiers.</param>
    public IsolationKeyScopedConversationStorage(IConversationStorage innerStorage, IsolationKeyResolver resolver)
    {
        this._innerStorage = Throw.IfNull(innerStorage);
        this._resolver = Throw.IfNull(resolver);
    }

    /// <inheritdoc />
    public async Task<Conversation> CreateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(conversation);

        var key = await this._resolver.GetKeyAsync(cancellationToken).ConfigureAwait(false);

        var created = await this._innerStorage.CreateConversationAsync(ScopeConversation(conversation, key), cancellationToken).ConfigureAwait(false);

        return UnscopeConversation(created, key);
    }

    /// <inheritdoc />
    public async Task<Conversation?> GetConversationAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        var key = await this._resolver.GetKeyAsync(cancellationToken).ConfigureAwait(false);

        var conversation = await this._innerStorage.GetConversationAsync(IsolationKeyResolver.ScopeId(conversationId, key), cancellationToken).ConfigureAwait(false);

        return conversation is null ? null : UnscopeConversation(conversation, key);
    }

    /// <inheritdoc />
    public async Task<Conversation?> UpdateConversationAsync(Conversation conversation, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(conversation);

        var key = await this._resolver.GetKeyAsync(cancellationToken).ConfigureAwait(false);

        var updated = await this._innerStorage.UpdateConversationAsync(ScopeConversation(conversation, key), cancellationToken).ConfigureAwait(false);

        return updated is null ? null : UnscopeConversation(updated, key);
    }

    /// <inheritdoc />
    public async Task<bool> DeleteConversationAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        var scopedId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return await this._innerStorage.DeleteConversationAsync(scopedId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task AddItemsAsync(string conversationId, IEnumerable<ItemResource> items, CancellationToken cancellationToken = default)
    {
        var scopedId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        await this._innerStorage.AddItemsAsync(scopedId, items, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<ItemResource?> GetItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
    {
        var scopedId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return await this._innerStorage.GetItemAsync(scopedId, itemId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<ListResponse<ItemResource>> ListItemsAsync(string conversationId, int? limit = null, SortOrder? order = null, string? after = null, CancellationToken cancellationToken = default)
    {
        var scopedId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return await this._innerStorage.ListItemsAsync(scopedId, limit, order, after, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<bool> DeleteItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
    {
        var scopedId = await this._resolver.ScopeIdAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return await this._innerStorage.DeleteItemAsync(scopedId, itemId, cancellationToken).ConfigureAwait(false);
    }

    private static Conversation ScopeConversation(Conversation conversation, string? key)
        => key is null ? conversation : conversation with { Id = IsolationKeyResolver.ScopeId(conversation.Id, key) };

    private static Conversation UnscopeConversation(Conversation conversation, string? key)
        => key is null ? conversation : conversation with { Id = IsolationKeyResolver.UnscopeId(conversation.Id, key) };
}
