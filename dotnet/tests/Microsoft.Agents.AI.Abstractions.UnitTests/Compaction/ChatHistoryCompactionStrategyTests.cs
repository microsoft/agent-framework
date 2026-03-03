// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class ChatHistoryCompactionStrategyTests
{
    [Fact]
    public async Task ShouldCompactReturnsFalse_SkipsAsync()
    {
        // Arrange
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];
        NeverCompactStrategy strategy = new();

        // Act
        CompactionResult result = await RunCompactionStrategyAsync(strategy, messages);

        // Assert
        Assert.False(result.Applied);
    }

    [Fact]
    public async Task ShouldCompactReturnsTrue_RunsCompactionAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ];
        RemoveFirstMessageStrategy strategy = new();

        // Act
        CompactionResult result = await RunCompactionStrategyAsync(strategy, messages);

        // Assert
        Assert.True(result.Applied);
        Assert.Single(messages);
        Assert.Equal("Second", messages[0].Text);
        Assert.Equal(2, result.Before.MessageCount);
        Assert.Equal(1, result.After.MessageCount);
    }

    [Fact]
    public async Task DelegatesToReducerAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ];
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> messages, CancellationToken _) => messages.Skip(1));
        TestCompactionStrategy strategy = new(reducerMock.Object);

        // Act
        CompactionResult result = await RunCompactionStrategyAsync(strategy, messages);

        // Assert
        Assert.True(result.Applied);
        Assert.Single(messages);
        Assert.Equal("Second", messages[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ReducerNoChange_ReturnsFalseAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
        ];
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs);
        TestCompactionStrategy strategy = new(reducerMock.Object, shouldCompact: false);

        // Act
        CompactionResult result = await RunCompactionStrategyAsync(strategy, messages);

        // Assert
        Assert.False(result.Applied);
        Assert.Single(messages);
    }

    [Fact]
    public void ReducerLifecycle()
    {
        // Arrange
        Mock<IChatReducer> reducerMock = new();

        // Act
        TestCompactionStrategy strategy = new(reducerMock.Object);

        // Assert
        Assert.Same(reducerMock.Object, strategy.Reducer);
        Assert.NotNull(strategy.Name);
        Assert.NotEmpty(strategy.Name);
        Assert.Equal(reducerMock.Object.GetType().Name, strategy.Name);
    }

    [Fact]
    public void CurrentMetrics_OutsideStrategy_Throws()
    {
        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => TestCompactionStrategy.GetCurrentMetrics());
    }

    public static async ValueTask<CompactionResult> RunCompactionStrategyAsync(ChatHistoryCompactionStrategy strategy, List<ChatMessage> messages)
    {
        // Act
        ChatHistoryCompactionStrategy.s_currentMetrics.Value = DefaultChatHistoryMetricsCalculator.Instance.Calculate(messages);
        return await strategy.CompactAsync(messages, DefaultChatHistoryMetricsCalculator.Instance);
    }

    private sealed class TestCompactionStrategy : ChatHistoryCompactionStrategy
    {
        private readonly bool _shouldCompact;

        public TestCompactionStrategy(IChatReducer reducer, bool shouldCompact = true)
            : base(reducer)
        {
            this._shouldCompact = shouldCompact;
        }

        protected override bool ShouldCompact(ChatHistoryMetric metrics) => this._shouldCompact;

        public static ChatHistoryMetric GetCurrentMetrics() => CurrentMetrics;
    }
}
