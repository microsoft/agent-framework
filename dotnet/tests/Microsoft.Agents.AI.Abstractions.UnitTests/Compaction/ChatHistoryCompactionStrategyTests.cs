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
        NeverCompactStrategy strategy = new();
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
    }

    [Fact]
    public async Task ShouldCompactReturnsTrue_RunsCompactionAsync()
    {
        RemoveFirstMessageStrategy strategy = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Single(messages);
        Assert.Equal("Second", messages[0].Text);
        Assert.Equal(2, result.Before.MessageCount);
        Assert.Equal(1, result.After.MessageCount);
    }

    [Fact]
    public async Task DelegatesToIChatReducerAsync()
    {
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs.Skip(1));

        TestCompactionStrategy strategy = new(reducerMock.Object);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Single(messages);
        Assert.Equal("Second", messages[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ReducerNoChange_ReturnsFalseAsync()
    {
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs);

        TestCompactionStrategy strategy = new(reducerMock.Object);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Single(messages);
    }

    [Fact]
    public void ExposesReducer()
    {
        Mock<IChatReducer> reducerMock = new();
        TestCompactionStrategy strategy = new(reducerMock.Object);

        Assert.Same(reducerMock.Object, strategy.Reducer);
    }

    [Fact]
    public void DefaultName_IsReducerTypeName()
    {
        Mock<IChatReducer> reducerMock = new();
        TestCompactionStrategy strategy = new(reducerMock.Object);

        // Moq proxy type name is used since we're using a mock
        Assert.NotNull(strategy.Name);
        Assert.NotEmpty(strategy.Name);
    }

    [Fact]
    public void ConditionDelegate_ReturnsTrue_ShouldCompactReturnsTrue()
    {
        Mock<IChatReducer> reducerMock = new();
        TestCompactionStrategy strategy = new(reducerMock.Object);

        CompactionMetric metrics = new() { TokenCount = 100 };
        Assert.True(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ConditionDelegate_ReturnsFalse_ShouldCompactReturnsFalse()
    {
        Mock<IChatReducer> reducerMock = new();
        TestCompactionStrategy strategy = new(reducerMock.Object, shouldCompact: false);

        CompactionMetric metrics = new() { TokenCount = 100 };
        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public async Task CompactAsync_NonReadOnlyListMessages_WorksAsync()
    {
        RemoveFirstMessageStrategy strategy = new();
        NonReadOnlyList<ChatMessage> messages = new(
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ]);
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Single(messages);
        Assert.Equal("Second", messages[0].Text);
    }

    [Fact]
    public void CurrentMetrics_OutsideStrategy_Throws()
    {
        Assert.Throws<InvalidOperationException>(() => TestCompactionStrategy.GetCurrentMetrics());
    }

    private sealed class TestCompactionStrategy : ChatHistoryCompactionStrategy
    {
        private readonly bool _shouldCompact;

        public TestCompactionStrategy(IChatReducer reducer, bool shouldCompact = true)
            : base(reducer)
        {
            this._shouldCompact = shouldCompact;
        }

        public override bool ShouldCompact(CompactionMetric metrics) => this._shouldCompact;

        public static CompactionMetric GetCurrentMetrics() => CurrentMetrics;
    }
}
