// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class ChatReducerCompactionStrategyTests : CompactionStrategyTestBase
{
    [Fact]
    public async Task ConditionFalse_SkipsAsync()
    {
        // Arrange
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];
        Mock<IChatReducer> reducerMock = new();
        ChatReducerCompactionStrategy strategy = new(reducerMock.Object, _ => false);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);

        // Assert
        reducerMock.Verify(
            r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task ConditionTrue_RunsReducerAsync()
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
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs.Skip(1));
        ChatReducerCompactionStrategy strategy = new(reducerMock.Object, _ => true);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 1);

        // Assert
        Assert.Equal("Second", messages[0].Text);
        reducerMock.Verify(
            r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task ConditionReceivesMetricsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        ChatHistoryMetric? capturedMetrics = null;
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs);
        ChatReducerCompactionStrategy strategy = new(
            reducerMock.Object,
            metrics =>
            {
                capturedMetrics = metrics;
                return false;
            });

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);

        // Assert
        Assert.NotNull(capturedMetrics);
        Assert.Equal(2, capturedMetrics!.MessageCount);
    }

    [Fact]
    public async Task ReducerNoChange_AppliedFalseAsync()
    {
        // Arrange
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];
        Mock<IChatReducer> reducerMock = new();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> msgs, CancellationToken _) => msgs);
        ChatReducerCompactionStrategy strategy = new(reducerMock.Object, _ => true);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public void Name_ReturnsReducerTypeName()
    {
        // Arrange
        Mock<IChatReducer> reducerMock = new();

        // Act
        ChatReducerCompactionStrategy strategy = new(reducerMock.Object, _ => true);

        // Assert
        Assert.Equal(reducerMock.Object.GetType().Name, strategy.Name);
    }
}
