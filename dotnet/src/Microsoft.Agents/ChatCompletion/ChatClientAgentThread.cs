// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Chat client agent thread.
/// </summary>
public sealed class ChatClientAgentThread : AgentThread, IMessagesRetrievableThread
{
    private readonly ChatClientAgentThreadStorageLocation _storageLocation;
    private readonly List<ChatMessage> _chatMessages = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="storageLocation">The storage location for the thread messages. Defaults to <see cref="ChatClientAgentThreadStorageLocation.LocalInMemory"/> if not specified.</param>
    public ChatClientAgentThread(ChatClientAgentThreadStorageLocation storageLocation = ChatClientAgentThreadStorageLocation.LocalInMemory)
    {
        this._storageLocation = storageLocation;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="id">The id of an existing server side thread to continue.</param>
    /// <remarks>
    /// Ths constructor creates a <see cref="ChatClientAgentThread"/> that supports in-service message storage.
    /// </remarks>
    public ChatClientAgentThread(string id)
    {
        Throw.IfNullOrWhitespace(id);

        this.Id = id;
        this._storageLocation = ChatClientAgentThreadStorageLocation.InService;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="messages">A set of initial messages to seed the thread with.</param>
    /// <remarks>
    /// Ths constructor creates a <see cref="ChatClientAgentThread"/> that supports local in-memory message storage.
    /// </remarks>
    public ChatClientAgentThread(IEnumerable<ChatMessage> messages)
    {
        Throw.IfNull(messages);

        this._chatMessages.AddRange(messages);
        this._storageLocation = ChatClientAgentThreadStorageLocation.LocalInMemory;
    }

    /// <summary>
    /// Gets the location of the thread contents.
    /// </summary>
    public ChatClientAgentThreadStorageLocation StorageLocation => this._storageLocation;

#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously
    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var message in this._chatMessages)
        {
            yield return message;
        }
    }

#pragma warning restore CS1998 // Async method lacks 'await' operators and will run synchronously

    /// <inheritdoc/>
    protected override Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        switch (this.StorageLocation)
        {
            case ChatClientAgentThreadStorageLocation.LocalInMemory:
                this._chatMessages.AddRange(newMessages);
                break;
            case ChatClientAgentThreadStorageLocation.InService:
                // If the thread messages are stored in the service
                // there is nothing to do here, since invoking the
                // service should already update the thread.
                break;
            default:
                throw new UnreachableException();
        }

        return Task.CompletedTask;
    }
}
