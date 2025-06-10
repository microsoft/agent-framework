// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents;

/// <summary>
/// Chat client agent thread.
/// </summary>
public sealed class ChatClientAgentThread : AgentThread, IMessagesRetrievableThread
{
    private readonly List<ChatMessage> _chatMessages = [];

    /// <inheritdoc/>
#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously
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
        this._chatMessages.AddRange(newMessages);
        return Task.CompletedTask;
    }
}
