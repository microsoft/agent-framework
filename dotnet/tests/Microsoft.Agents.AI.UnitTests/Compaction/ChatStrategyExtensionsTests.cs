// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ChatStrategyExtensions"/> class.
/// </summary>
public class ChatStrategyExtensionsTests
{
    [Fact]
    public void AsChatReducerNullStrategyThrows()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((CompactionStrategy)null!).AsChatReducer());
    }

    [Fact]
    public void AsChatReducerReturnsIChatReducer()
    {
        // Arrange
        ChatReducerCompactionStrategy strategy = new(new IdentityReducer(), CompactionTriggers.Always);

        // Act
        IChatReducer reducer = strategy.AsChatReducer();

        // Assert
        Assert.NotNull(reducer);
    }

    [Fact]
    public async Task ReduceAsyncReturnsAllMessagesWhenStrategyDoesNotCompactAsync()
    {
        // Arrange — trigger never fires, so no compaction occurs
        ChatReducerCompactionStrategy strategy = new(new IdentityReducer(), CompactionTriggers.Never);
        IChatReducer reducer = strategy.AsChatReducer();

        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi!"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await reducer.ReduceAsync(messages, CancellationToken.None);

        // Assert
        Assert.Equal(messages, result);
    }

    [Fact]
    public async Task ReduceAsyncCompactsMessagesWhenStrategyFiresAsync()
    {
        // Arrange — reducer keeps only the last message
        ChatReducerCompactionStrategy strategy = new(
            new TakeLastReducer(1),
            CompactionTriggers.Always);
        IChatReducer reducer = strategy.AsChatReducer();

        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.Assistant, "Response 1"),
            new(ChatRole.User, "Second"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await reducer.ReduceAsync(messages, CancellationToken.None);

        // Assert
        List<ChatMessage> resultList = [.. result];
        Assert.Single(resultList);
        Assert.Equal("Second", resultList[0].Text);
    }

    [Fact]
    public async Task ReduceAsyncPassesCancellationTokenToStrategyAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        CancellationToken capturedToken = default;

        CapturingReducer capturingReducer = new(token => capturedToken = token);
        ChatReducerCompactionStrategy strategy = new(capturingReducer, CompactionTriggers.Always);
        IChatReducer reducer = strategy.AsChatReducer();

        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.User, "World"),
        ];

        // Act
        await reducer.ReduceAsync(messages, cts.Token);

        // Assert
        Assert.Equal(cts.Token, capturedToken);
    }

    [Fact]
    public async Task ReduceAsyncEmptyMessagesReturnsEmptyAsync()
    {
        // Arrange
        ChatReducerCompactionStrategy strategy = new(new IdentityReducer(), CompactionTriggers.Always);
        IChatReducer reducer = strategy.AsChatReducer();

        // Act
        IEnumerable<ChatMessage> result = await reducer.ReduceAsync([], CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    /// <summary>
    /// An <see cref="IChatReducer"/> that returns messages unchanged.
    /// </summary>
    private sealed class IdentityReducer : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
            => Task.FromResult(messages);
    }

    /// <summary>
    /// An <see cref="IChatReducer"/> that keeps only the last <c>n</c> messages.
    /// </summary>
    private sealed class TakeLastReducer : IChatReducer
    {
        private readonly int _count;

        public TakeLastReducer(int count) => this._count = count;

        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
            => Task.FromResult(messages.Reverse().Take(this._count));
    }

    /// <summary>
    /// An <see cref="IChatReducer"/> that captures the <see cref="CancellationToken"/> passed to <see cref="ReduceAsync"/>.
    /// </summary>
    private sealed class CapturingReducer : IChatReducer
    {
        private readonly Action<CancellationToken> _capture;

        public CapturingReducer(Action<CancellationToken> capture) => this._capture = capture;

        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
        {
            this._capture(cancellationToken);
            IEnumerable<ChatMessage> reducedMessages = [messages.Reverse().First()];
            return Task.FromResult(reducedMessages);
        }
    }
}
