// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Inert <see cref="IChatClient"/> that satisfies the <see cref="ChatClientAgent"/> dependency of agents built by
/// <c>AddAIAgent(name, instructions)</c>. The request-issuing members throw and <see cref="GetService"/> returns
/// <see langword="null"/>, because no test drives inference through it.
/// </summary>
internal sealed class MockChatClient : IChatClient
{
    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotImplementedException();

    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotImplementedException();

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
        // Nothing to dispose: this fake holds no resources.
    }
}
