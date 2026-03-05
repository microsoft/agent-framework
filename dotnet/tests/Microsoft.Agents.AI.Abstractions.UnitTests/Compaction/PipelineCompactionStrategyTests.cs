// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="PipelineCompactionStrategy"/> class.
/// </summary>
public class PipelineCompactionStrategyTests
{
    [Fact]
    public async Task CompactAsync_ExecutesAllStrategiesInOrder()
    {
        // Arrange
        List<string> executionOrder = [];
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback(() => executionOrder.Add("first"))
            .ReturnsAsync(false);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback(() => executionOrder.Add("second"))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object);
        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert
        Assert.Equal(["first", "second"], executionOrder);
    }

    [Fact]
    public async Task CompactAsync_ReturnsFalse_WhenNoStrategyCompacts()
    {
        // Arrange
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object);
        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsync_ReturnsTrue_WhenAnyStrategyCompacts()
    {
        // Arrange
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object);
        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public async Task CompactAsync_ContinuesAfterFirstCompaction_WhenEarlyStopDisabled()
    {
        // Arrange
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object);
        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert — both strategies were called
        strategy1.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        strategy2.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CompactAsync_StopsEarly_WhenTargetReached()
    {
        // Arrange — first strategy reduces to target
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                // Exclude the first group to bring count down
                groups.Groups[0].IsExcluded = true;
            })
            .ReturnsAsync(true);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object)
        {
            EarlyStop = true,
            TargetIncludedGroupCount = 2,
        };

        MessageGroups groups = MessageGroups.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert — strategy2 should not have been called
        Assert.True(result);
        strategy1.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        strategy2.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task CompactAsync_DoesNotStopEarly_WhenTargetNotReached()
    {
        // Arrange — first strategy does NOT bring count to target
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object)
        {
            EarlyStop = true,
            TargetIncludedGroupCount = 1,
        };

        MessageGroups groups = MessageGroups.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.User, "Second"),
            new ChatMessage(ChatRole.User, "Third"),
        ]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert — both strategies were called since target was never reached
        strategy1.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        strategy2.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CompactAsync_EarlyStopIgnored_WhenNoTargetSet()
    {
        // Arrange
        Mock<ICompactionStrategy> strategy1 = new();
        strategy1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        Mock<ICompactionStrategy> strategy2 = new();
        strategy2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        PipelineCompactionStrategy pipeline = new(strategy1.Object, strategy2.Object)
        {
            EarlyStop = true,
            // TargetIncludedGroupCount is null
        };

        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert — both strategies called because no target to check against
        strategy1.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        strategy2.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CompactAsync_ComposesStrategies_EndToEnd()
    {
        // Arrange — pipeline: first exclude oldest 2 non-system groups, then exclude 2 more
        Mock<ICompactionStrategy> phase1 = new();
        phase1.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                int excluded = 0;
                foreach (MessageGroup group in groups.Groups)
                {
                    if (!group.IsExcluded && group.Kind != MessageGroupKind.System && excluded < 2)
                    {
                        group.IsExcluded = true;
                        excluded++;
                    }
                }
            })
            .ReturnsAsync(true);

        Mock<ICompactionStrategy> phase2 = new();
        phase2.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                int excluded = 0;
                foreach (MessageGroup group in groups.Groups)
                {
                    if (!group.IsExcluded && group.Kind != MessageGroupKind.System && excluded < 2)
                    {
                        group.IsExcluded = true;
                        excluded++;
                    }
                }
            })
            .ReturnsAsync(true);

        PipelineCompactionStrategy pipeline = new(phase1.Object, phase2.Object);

        MessageGroups groups = MessageGroups.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert — system is preserved, phase1 excluded Q1+A1, phase2 excluded Q2+A2 → System + Q3
        Assert.True(result);
        Assert.Equal(2, groups.IncludedGroupCount);

        List<ChatMessage> included = [.. groups.GetIncludedMessages()];
        Assert.Equal(2, included.Count);
        Assert.Equal("You are helpful.", included[0].Text);
        Assert.Equal("Q3", included[1].Text);

        phase1.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        phase2.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CompactAsync_EmptyPipeline_ReturnsFalseAsync()
    {
        // Arrange
        PipelineCompactionStrategy pipeline = new(new List<ICompactionStrategy>());
        MessageGroups groups = MessageGroups.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }
}
