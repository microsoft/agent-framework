// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;
internal class PurviewChatClient : IChatClient
{
    private readonly IChatClient _innerChatClient;
    private readonly PurviewWrapper _purviewWrapper;

    public PurviewChatClient(IChatClient innerChatClient, PurviewWrapper purviewWrapper)
    {
        this._innerChatClient = innerChatClient;
        this._purviewWrapper = purviewWrapper;
    }

    public void Dispose()
    {
        this._purviewWrapper.Dispose();
        this._innerChatClient.Dispose();
    }

    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this._purviewWrapper.ProcessChatContentAsync(messages, options, this._innerChatClient, cancellationToken);
    }

    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        return this._innerChatClient.GetService(serviceType, serviceKey);
    }

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
