// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatMessageStore"/> class.
/// </summary>
public class ChatMessageStoreTests
{
    #region GetService Method Tests

    [Fact]
    public void GetService_RequestingExactStoreType_ReturnsStore()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(TestChatMessageStore));
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_RequestingBaseStoreType_ReturnsStore()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(ChatMessageStore));
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(string));
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(TestChatMessageStore), "some-key");
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        var store = new TestChatMessageStore();
        Assert.Throws<ArgumentNullException>(() => store.GetService(null!));
    }

    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService<TestChatMessageStore>();
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService<string>();
        Assert.Null(result);
    }

    #endregion

    private sealed class TestChatMessageStore : ChatMessageStore
    {
        public override ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(Array.Empty<ChatMessage>());

        public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }
}
