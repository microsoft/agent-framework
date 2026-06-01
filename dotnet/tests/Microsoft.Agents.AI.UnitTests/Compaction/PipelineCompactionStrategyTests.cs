// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="PipelineCompactionStrategy"/> class.
/// </summary>
public class PipelineCompactionStrategyTests
{
    [Fact]
    public async Task CompactAsyncExecutesAllStrategiesInOrderAsync()
    {
        // Arrange
        List<string> executionOrder = [];
        TestCompactionStrategy strategy1 = new(
            _ =>
            {
                executionOrder.Add("first");
                return false;
            });

        TestCompactionStrategy strategy2 = new(
            _ =>
            {
                executionOrder.Add("second");
                return false;
            });

        PipelineCompactionStrategy pipeline = new(strategy1, strategy2);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert
        Assert.Equal(["first", "second"], executionOrder);
    }

    [Fact]
    public async Task CompactAsyncReturnsFalseWhenNoStrategyCompactsAsync()
    {
        // Arrange
        TestCompactionStrategy strategy1 = new(_ => false);

        PipelineCompactionStrategy pipeline = new(strategy1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncReturnsTrueWhenAnyStrategyCompactsAsync()
    {
        // Arrange
        TestCompactionStrategy strategy1 = new(_ => false);
        TestCompactionStrategy strategy2 = new(_ => true);

        PipelineCompactionStrategy pipeline = new(strategy1, strategy2);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public async Task CompactAsyncContinuesAfterFirstCompactionAsync()
    {
        // Arrange
        TestCompactionStrategy strategy1 = new(_ => true);
        TestCompactionStrategy strategy2 = new(_ => false);

        PipelineCompactionStrategy pipeline = new(strategy1, strategy2);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        await pipeline.CompactAsync(groups);

        // Assert — both strategies were called
        Assert.Equal(1, strategy1.ApplyCallCount);
        Assert.Equal(1, strategy2.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncComposesStrategiesEndToEndAsync()
    {
        // Arrange — pipeline: first exclude oldest 2 non-system groups, then exclude 2 more
        static void ExcludeOldest2(CompactionMessageIndex index)
        {
            int excluded = 0;
            foreach (CompactionMessageGroup group in index.Groups)
            {
                if (!group.IsExcluded && group.Kind != CompactionGroupKind.System && excluded < 2)
                {
                    group.IsExcluded = true;
                    excluded++;
                }
            }
        }

        TestCompactionStrategy phase1 = new(
            index =>
            {
                ExcludeOldest2(index);
                return true;
            });

        TestCompactionStrategy phase2 = new(
            index =>
            {
                ExcludeOldest2(index);
                return true;
            });

        PipelineCompactionStrategy pipeline = new(phase1, phase2);

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
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

        Assert.Equal(1, phase1.ApplyCallCount);
        Assert.Equal(1, phase2.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncEmptyPipelineReturnsFalseAsync()
    {
        // Arrange
        PipelineCompactionStrategy pipeline = new(new List<CompactionStrategy>());
        CompactionMessageIndex groups = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        bool result = await pipeline.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    /// <summary>
    /// A simple test implementation of <see cref="CompactionStrategy"/> that delegates to a synchronous callback.
    /// </summary>
    private sealed class TestCompactionStrategy : CompactionStrategy
    {
        private readonly Func<CompactionMessageIndex, bool> _applyFunc;

        public TestCompactionStrategy(Func<CompactionMessageIndex, bool> applyFunc)
            : base(CompactionTriggers.Always)
        {
            this._applyFunc = applyFunc;
        }

        public int ApplyCallCount { get; private set; }

        protected override ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
        {
            this.ApplyCallCount++;
            return new(this._applyFunc(index));
        }
    }
}
