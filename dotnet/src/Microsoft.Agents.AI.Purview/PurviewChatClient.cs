// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// A middleware chat client that connects to Microsoft Purview.
/// </summary>
internal class PurviewChatClient : IChatClient
{
    private readonly IChatClient _innerChatClient;
    private readonly PurviewWrapper _purviewWrapper;

    /// <summary>
    /// Initializes a new instance of the <see cref="PurviewChatClient"/> class.
    /// </summary>
    /// <param name="innerChatClient">The inner chat client to wrap.</param>
    /// <param name="purviewWrapper">The purview wrapper used to interact with the Purview service.</param>
    public PurviewChatClient(IChatClient innerChatClient, PurviewWrapper purviewWrapper)
    {
        this._innerChatClient = innerChatClient;
        this._purviewWrapper = purviewWrapper;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        this._purviewWrapper.Dispose();
        this._innerChatClient.Dispose();
    }

    /// <inheritdoc/>
    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this._purviewWrapper.ProcessChatContentAsync(messages, options, this._innerChatClient, cancellationToken);
    }

    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        return this._innerChatClient.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
                                                                                ChatOptions? options = null,
                                                                                [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Task<ChatResponse> responseTask = this._purviewWrapper.ProcessChatContentAsync(messages, options, this._innerChatClient, cancellationToken);

        foreach (var update in (await responseTask.ConfigureAwait(false)).ToChatResponseUpdates())
        {
            yield return update;
        }
    }
}
