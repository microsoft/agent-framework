// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.UnitTests.Mock;

internal sealed class MockChatClient : IChatClient
{
    private int _responsesCounter = 1;

    public ChatClientMetadata? Metadata { get; }

    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        await Task.Yield();

        ChatMessage responseMessage = new(ChatRole.Assistant, $"Response #{this._responsesCounter++}");
        return new ChatResponse([responseMessage]);
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();

        var responseText = $"Response #{this._responsesCounter++}";

        yield return new ChatResponseUpdate(ChatRole.Assistant, responseText);
    }

    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        return null;
    }

    public TService? GetService<TService>(object? serviceKey = null)
    {
        return default;
    }

    public void Dispose()
    {
    }
}
