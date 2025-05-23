// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents;

/// <summary>
/// Represents a conversation thread based on an instance of <see cref="IList{ChatMessage}"/> that is managed inside this class.
/// </summary>
public sealed class ChatMessageAgentThread : AgentThread
{
    private readonly IList<ChatMessage> _chatMessages = new List<ChatMessage>();

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatMessageAgentThread"/> class.
    /// </summary>
    public ChatMessageAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatMessageAgentThread"/> class that resumes an existing thread.
    /// </summary>
    /// <param name="chatMessages">An existing chat history to base this thread on.</param>
    /// <param name="id">The id of the existing thread. If not provided, a new one will be generated.</param>
    public ChatMessageAgentThread(IList<ChatMessage> chatMessages, string? id = null)
    {
        Verify.NotNull(chatMessages);
        this._chatMessages = chatMessages;
        this.Id = id ?? Guid.NewGuid().ToString("N");
    }

    /// <summary>
    /// Gets the underlying <see cref="IEnumerable{ChatMessage}"/> object that stores the chat history for this thread.
    /// </summary>
    public IEnumerable<ChatMessage> ChatMessages => this._chatMessages;

    /// <summary>
    /// Creates the thread and returns the thread id.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the thread has been created.</returns>
    public new Task CreateAsync(CancellationToken cancellationToken = default)
    {
        return base.CreateAsync(cancellationToken);
    }

    /// <inheritdoc />
    protected override Task<string?> CreateInternalAsync(CancellationToken cancellationToken)
    {
        return Task.FromResult<string?>(Guid.NewGuid().ToString("N"));
    }

    /// <inheritdoc />
    protected override Task DeleteInternalAsync(CancellationToken cancellationToken)
    {
        this._chatMessages.Clear();
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    protected override Task OnNewMessageInternalAsync(ChatMessage newMessage, CancellationToken cancellationToken = default)
    {
        this._chatMessages.Add(newMessage);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Asynchronously retrieves all messages in the thread.
    /// </summary>
    /// <remarks>
    /// Messages will be returned in ascending chronological order.
    /// </remarks>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The messages in the thread.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    [Experimental("SKEXP0110")]
    public async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this.IsDeleted)
        {
            throw new InvalidOperationException("This thread has been deleted and cannot be used anymore.");
        }

        if (this.Id is null)
        {
            await this.CreateAsync(cancellationToken).ConfigureAwait(false);
        }

        foreach (var message in this._chatMessages)
        {
            yield return message;
        }
    }
}
