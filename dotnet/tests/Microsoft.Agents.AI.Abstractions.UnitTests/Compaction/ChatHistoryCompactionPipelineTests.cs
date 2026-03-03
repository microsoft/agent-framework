// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class ChatHistoryCompactionPipelineTests
{
    [Fact]
    public async Task EmptyStrategies_ReturnsUnmodifiedAsync()
    {
        // Arrange
        ChatHistoryCompactionPipeline pipeline = new([]);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        CompactionPipelineResult result = await pipeline.CompactAsync(messages);

        // Assert
        Assert.False(result.AnyApplied);
        Assert.Equal(1, result.Before.MessageCount);
        Assert.Equal(1, result.After.MessageCount);
        Assert.Empty(result.StrategyResults);
    }

    [Fact]
    public async Task ChainsStrategies_InOrderAsync()
    {
        // Arrange
        ChatHistoryCompactionStrategy[] strategies =
        [
            new NeverCompactStrategy(),
            new RemoveFirstMessageStrategy(),
        ];
        ChatHistoryCompactionPipeline pipeline = new(strategies);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
        ];

        // Act
        CompactionPipelineResult result = await pipeline.CompactAsync(messages);

        // Assert
        Assert.True(result.AnyApplied);
        Assert.Equal(2, result.StrategyResults.Count);
        Assert.False(result.StrategyResults[0].Applied);
        Assert.True(result.StrategyResults[1].Applied);
        Assert.Single(messages);
    }

    [Fact]
    public async Task ReportsOverallMetricsAsync()
    {
        // Arrange
        ChatHistoryCompactionPipeline pipeline = new([new RemoveFirstMessageStrategy()]);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
            new(ChatRole.User, "Third"),
        ];

        // Act
        CompactionPipelineResult result = await pipeline.CompactAsync(messages);

        // Assert
        Assert.Equal(3, result.Before.MessageCount);
        Assert.Equal(2, result.After.MessageCount);
    }

    [Fact]
    public async Task CustomMetricsCalculator_IsUsedAsync()
    {
        // Arrange
        Moq.Mock<IChatHistoryMetricsCalculator> calcMock = new();
        calcMock
            .Setup(c => c.Calculate(Moq.It.IsAny<IReadOnlyList<ChatMessage>>()))
            .Returns(new ChatHistoryMetric { MessageCount = 42 });
        ChatHistoryCompactionPipeline pipeline = new(calcMock.Object, []);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        CompactionPipelineResult result = await pipeline.CompactAsync(messages);

        // Assert
        Assert.Equal(42, result.Before.MessageCount);
        calcMock.Verify(c => c.Calculate(Moq.It.IsAny<IReadOnlyList<ChatMessage>>()), Moq.Times.Once);
    }

    [Fact]
    public async Task ReduceAsync_DelegatesCompactionAsync()
    {
        // Arrange
        ChatHistoryCompactionPipeline pipeline = new([new RemoveFirstMessageStrategy()]);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
            new(ChatRole.User, "Third"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await pipeline.ReduceAsync(messages, default);
        List<ChatMessage> resultList = result.ToList();

        // Assert
        Assert.Equal(2, resultList.Count);
        Assert.Equal("Second", resultList[0].Text);
        Assert.Equal("Third", resultList[1].Text);
    }

    [Fact]
    public async Task ReduceAsync_EmptyStrategies_ReturnsAllMessagesAsync()
    {
        // Arrange
        ChatHistoryCompactionPipeline pipeline = new([]);
        ChatMessage[] messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.User, "World"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await pipeline.ReduceAsync(messages, default);

        // Assert
        Assert.Equal(2, result.Count());
    }
}
