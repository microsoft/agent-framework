// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// A chat client agent thread that supports storing messages in a store.
/// </summary>
public sealed class PersistedChatClientAgentThread : ChatClientAgentThread
{
    private readonly ConversationStore _conversationStore;
    private readonly int _maxMessageCount;

    /// <summary>
    /// Initializes a new instance of the <see cref="PersistedChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="conversationStore">The store to save the conversation to.</param>
    /// <param name="threadId">The id to store messages under in the vector store.</param>
    /// <param name="options">Options for configuring the thread.</param>
    /// <remarks>
    /// This constructor creates a <see cref="ChatClientAgentThread"/> that supports local in-memory message storage.
    /// </remarks>
    public PersistedChatClientAgentThread(ConversationStore conversationStore, string threadId, PersistedChatClientAgentThreadOptions? options = null)
    {
        this._conversationStore = Throw.IfNull(conversationStore);
        this.Id = Throw.IfNullOrWhitespace(threadId);
        this.StorageLocation = ChatClientAgentThreadType.AgentThreadManaged;
        this._maxMessageCount = options?.MaxMessageCount ?? 20;
    }

    /// <summary>
    /// Gets the location of the thread contents.
    /// </summary>
    internal override ChatClientAgentThreadType? StorageLocation
    {
        get => base.StorageLocation;
        set
        {
            if (value != ChatClientAgentThreadType.AgentThreadManaged)
            {
                throw new NotSupportedException($"{nameof(PersistedChatClientAgentThread)} only supports a ${nameof(this.StorageLocation)} of ${nameof(ChatClientAgentThreadType.AgentThreadManaged)}.");
            }

            base.StorageLocation = value;
        }
    }

    /// <inheritdoc/>
    internal override async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Debug.Assert(this.Id is not null, "Thread ID must be set before retrieving messages.");

        foreach (var message in await this._conversationStore.GetRecentMessages(
            this.Id,
            this._maxMessageCount,
            cancellationToken).ConfigureAwait(false))
        {
            yield return message;
        }
    }

    /// <inheritdoc/>
    internal override Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        Debug.Assert(this.Id is not null, "Thread ID must be set before storing messages.");

        return this._conversationStore.AddMessages(
            this.Id,
            newMessages,
            cancellationToken);
    }
}
