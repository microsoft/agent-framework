// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.ObjectModel;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

public class AIContextProviderTests
{
    [Fact]
    public async Task InvokedAsync_ReturnsCompletedTaskAsync()
    {
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>([]);
        var task = provider.InvokedAsync(new(messages));
        Assert.Equal(default, task);
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
        var actual = provider.DeserializeAsync(element);
        Assert.Equal(default, actual);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullMessages()
    {
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!));
    }

    private sealed class TestAIContextProvider : AIContextProvider
    {
        public override ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            return default;
        }

        public override async ValueTask<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return await base.SerializeAsync(jsonSerializerOptions, cancellationToken);
        }

        public override async ValueTask DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            await base.DeserializeAsync(serializedState, jsonSerializerOptions, cancellationToken);
        }
    }
}
