// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="CompactionStrategy"/> abstract base class.
/// </summary>
public class CompactionStrategyTests
{
    [Fact]
    public void ConstructorNullTriggerThrows()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new TestStrategy(null!));
    }

    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger never fires, but enough non-system groups to pass short-circuit
        TestStrategy strategy = new(_ => false);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(0, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncTriggerMetCallsApplyAsync()
    {
        // Arrange — trigger always fires, enough non-system groups
        TestStrategy strategy = new(_ => true, applyFunc: _ => true);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);
        Assert.Equal(1, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncReturnsFalseWhenApplyReturnsFalseAsync()
    {
        // Arrange — trigger fires but Apply does nothing
        TestStrategy strategy = new(_ => true, applyFunc: _ => false);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(1, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncSingleNonSystemGroupShortCircuitsAsync()
    {
        // Arrange — trigger would fire, but only 1 non-system group → short-circuit
        TestStrategy strategy = new(_ => true, applyFunc: _ => true);
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — short-circuited before trigger or Apply
        Assert.False(result);
        Assert.Equal(0, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncSingleNonSystemGroupWithSystemShortCircuitsAsync()
    {
        // Arrange — system group + 1 non-system group → still short-circuits
        TestStrategy strategy = new(_ => true, applyFunc: _ => true);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Hello"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — system groups don't count, still only 1 non-system group
        Assert.False(result);
        Assert.Equal(0, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncTwoNonSystemGroupsProceedsToTriggerAsync()
    {
        // Arrange — exactly 2 non-system groups: boundary passes, trigger fires
        TestStrategy strategy = new(_ => true, applyFunc: _ => true);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — not short-circuited, Apply was called
        Assert.True(result);
        Assert.Equal(1, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncDefaultTargetIsInverseOfTriggerAsync()
    {
        // Arrange — trigger fires when groups > 2
        // Default target should be: stop when groups <= 2 (i.e., !trigger)
        CompactionTrigger trigger = CompactionTriggers.GroupsExceed(2);
        TestStrategy strategy = new(trigger, applyFunc: index =>
        {
            // Exclude oldest non-system group one at a time
            foreach (CompactionMessageGroup group in index.Groups)
            {
                if (!group.IsExcluded && group.Kind != CompactionGroupKind.System)
                {
                    group.IsExcluded = true;
                    // Target (default = !trigger) returns true when groups <= 2
                    // So the strategy would check Target after this exclusion
                    break;
                }
            }

            return true;
        });

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — trigger fires (4 > 2), Apply is called
        Assert.True(result);
        Assert.Equal(1, strategy.ApplyCallCount);
    }

    [Fact]
    public async Task CompactAsyncCustomTargetIsPassedToStrategyAsync()
    {
        // Arrange — custom target that always signals stop
        bool targetCalled = false;
        bool CustomTarget(CompactionMessageIndex _)
        {
            targetCalled = true;
            return true;
        }

        TestStrategy strategy = new(_ => true, CustomTarget, _ =>
        {
            // Access the target from within the strategy
            return true;
        });

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — the custom target is accessible (verified by TestStrategy checking it)
        Assert.Equal(1, strategy.ApplyCallCount);
        // The target is accessible to derived classes via the protected property
        Assert.True(strategy.InvokeTarget(index));
        Assert.True(targetCalled);
    }

    /// <summary>
    /// A concrete test implementation of <see cref="CompactionStrategy"/> for testing the base class.
    /// </summary>
    private sealed class TestStrategy : CompactionStrategy
    {
        private readonly Func<CompactionMessageIndex, bool>? _applyFunc;

        public TestStrategy(
            CompactionTrigger trigger,
            CompactionTrigger? target = null,
            Func<CompactionMessageIndex, bool>? applyFunc = null)
            : base(trigger, target)
        {
            this._applyFunc = applyFunc;
        }

        public int ApplyCallCount { get; private set; }

        /// <summary>
        /// Exposes the protected Target property for test verification.
        /// </summary>
        public bool InvokeTarget(CompactionMessageIndex index) => this.Target(index);

        protected override ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
        {
            this.ApplyCallCount++;
            bool result = this._applyFunc?.Invoke(index) ?? false;
            return new(result);
        }
    }
}
