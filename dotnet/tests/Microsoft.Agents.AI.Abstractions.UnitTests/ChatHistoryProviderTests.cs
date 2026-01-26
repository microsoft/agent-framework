// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProvider"/> class.
/// </summary>
public class ChatHistoryProviderTests
{
    #region GetService Method Tests

    [Fact]
    public void GetService_RequestingExactProviderType_ReturnsProvider()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(TestChatHistoryProvider));
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_RequestingBaseProviderType_ReturnsProvider()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(ChatHistoryProvider));
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(string));
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(TestChatHistoryProvider), "some-key");
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        var provider = new TestChatHistoryProvider();
        Assert.Throws<ArgumentNullException>(() => provider.GetService(null!));
    }

    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService<TestChatHistoryProvider>();
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService<string>();
        Assert.Null(result);
    }

    #endregion

    private sealed class TestChatHistoryProvider : ChatHistoryProvider
    {
        public override ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(Array.Empty<ChatMessage>());

        public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }
}
