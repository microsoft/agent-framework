// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="InMemoryChatMessageStore"/> class.
/// </summary>
public class InMemoryChatMessageStoreTests
{
    [Fact]
    public async Task AddMessagesAsyncAddsMessagesAndReturnsNullThreadIdAsync()
    {
        var store = new InMemoryChatMessageStore();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        await store.AddMessagesAsync(messages, CancellationToken.None);

        Assert.Equal(2, store.Count);
        Assert.Equal("Hello", store[0].Text);
        Assert.Equal("Hi there!", store[1].Text);
    }

    [Fact]
    public async Task AddMessagesAsyncWithEmptyDoesNotFailAsync()
    {
        var store = new InMemoryChatMessageStore();

        await store.AddMessagesAsync([], CancellationToken.None);

        Assert.Empty(store);
    }

    [Fact]
    public async Task GetMessagesAsyncReturnsAllMessagesAsync()
    {
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "Test1"),
            new ChatMessage(ChatRole.Assistant, "Test2")
        };

        var result = (await store.GetMessagesAsync(CancellationToken.None)).ToList();

        Assert.Equal(2, result.Count);
        Assert.Contains(result, m => m.Text == "Test1");
        Assert.Contains(result, m => m.Text == "Test2");
    }

    [Fact]
    public async Task DeserializeWithEmptyElementAsync()
    {
        var newStore = new InMemoryChatMessageStore();

        var emptyObject = JsonSerializer.Deserialize<JsonElement>("{}");

        await newStore.DeserializeStateAsync(emptyObject);

        Assert.Empty(newStore);
    }

    [Fact]
    public async Task SerializeAndDeserializeRoundtripsAsync()
    {
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B")
        };

        var jsonElement = await store.SerializeStateAsync();
        var newStore = new InMemoryChatMessageStore();

        await newStore.DeserializeStateAsync(jsonElement);

        Assert.Equal(2, newStore.Count);
        Assert.Equal("A", newStore[0].Text);
        Assert.Equal("B", newStore[1].Text);
    }

    [Fact]
    public async Task AddMessagesAsyncWithEmptyMessagesDoesNotChangeStoreAsync()
    {
        var store = new InMemoryChatMessageStore();
        var messages = new List<ChatMessage>();

        await store.AddMessagesAsync(messages, CancellationToken.None);

        Assert.Empty(store);
    }
}
