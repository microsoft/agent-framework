// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Tests.Mock;

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

        List<ChatMessage> messageList = messages.ToList();
        ChatMessage lastUserMessage = messageList.LastOrDefault(m => m.Role == ChatRole.User)
            ?? new ChatMessage(ChatRole.User, "No user message");

        ChatMessage responseMessage = new(ChatRole.Assistant, $"Response #{this._responsesCounter++}");

        return new ChatResponse([responseMessage]);
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();

        List<ChatMessage> messageList = messages.ToList();
        ChatMessage lastUserMessage = messageList.LastOrDefault(m => m.Role == ChatRole.User)
            ?? new ChatMessage(ChatRole.User, "No user message");

        string responseText = $"Mock response to: {lastUserMessage.Text}";

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
