// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

public class AIContextProviderTests
{
    [Fact]
    public async Task MessagesAddingAsync_ReturnsCompletedTaskAsync()
    {
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>(new List<ChatMessage>());
        var task = provider.MessagesAddingAsync(messages, "thread1");
        Assert.True(task.IsCompleted);
    }

    [Fact]
    public async Task SerializeAsync_ReturnsEmptyElementAsync()
    {
        var provider = new TestAIContextProvider();
        var actual = await provider.SerializeAsync();
        Assert.Equal(default, actual);
    }

    [Fact]
    public async Task DeserializeAsync_ReturnsCompletedTaskAsync()
    {
        var provider = new TestAIContextProvider();
        var element = default(JsonElement);
        var task = provider.DeserializeAsync(element);
        Assert.True(task.IsCompleted);
    }

    private sealed class TestAIContextProvider : AIContextProvider
    {
        public override Task<AIContext> ModelInvokingAsync(IEnumerable<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(new AIContext());
        }

        public override async Task MessagesAddingAsync(IReadOnlyCollection<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default)
        {
            await base.MessagesAddingAsync(newMessages, agentThreadId, cancellationToken);
        }

        protected internal override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return await base.SerializeAsync(jsonSerializerOptions, cancellationToken);
        }

        protected internal override async Task DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            await base.DeserializeAsync(serializedState, jsonSerializerOptions, cancellationToken);
        }
    }
}
