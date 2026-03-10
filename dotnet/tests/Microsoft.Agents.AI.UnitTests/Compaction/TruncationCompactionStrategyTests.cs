// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="TruncationCompactionStrategy"/> class.
/// </summary>
public class TruncationCompactionStrategyTests
{
    [Fact]
    public async Task CompactAsyncAlwaysTriggerCompactsToPreserveRecentAsync()
    {
        // Arrange — always-trigger means always compact
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.Equal(1, groups.Groups.Count(g => !g.IsExcluded));
    }

    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger requires > 1000 tokens, conversation is tiny
        TruncationCompactionStrategy strategy = new(
            minimumPreservedGroups: 1,
            trigger: CompactionTriggers.TokensExceed(1000));

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
        Assert.Equal(2, groups.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncTriggerMetExcludesOldestGroupsAsync()
    {
        // Arrange — trigger on groups > 2
        TruncationCompactionStrategy strategy = new(
            minimumPreservedGroups: 1,
            trigger: CompactionTriggers.GroupsExceed(2));

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
            new ChatMessage(ChatRole.Assistant, "Response 2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert — incremental: excludes until GroupsExceed(2) is no longer met → 2 groups remain
        Assert.True(result);
        Assert.Equal(2, groups.IncludedGroupCount);
        // Oldest 2 excluded, newest 2 kept
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncPreservesSystemMessagesAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // System message should be preserved
        Assert.False(groups.Groups[0].IsExcluded);
        Assert.Equal(CompactionGroupKind.System, groups.Groups[0].Kind);
        // Oldest non-system groups excluded
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.True(groups.Groups[2].IsExcluded);
        // Most recent kept
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncPreservesToolCallGroupAtomicityAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);

        ChatMessage assistantToolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");
        ChatMessage finalResponse = new(ChatRole.User, "Thanks!");

        CompactionMessageIndex groups = CompactionMessageIndex.Create([assistantToolCall, toolResult, finalResponse]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // Tool call group should be excluded as one atomic unit
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.Equal(CompactionGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(2, groups.Groups[0].Messages.Count);
        Assert.False(groups.Groups[1].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncSetsExcludeReasonAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Old"),
            new ChatMessage(ChatRole.User, "New"),
        ]);

        // Act
        await strategy.CompactAsync(groups);

        // Assert
        Assert.NotNull(groups.Groups[0].ExcludeReason);
        Assert.Contains("TruncationCompactionStrategy", groups.Groups[0].ExcludeReason);
    }

    [Fact]
    public async Task CompactAsyncSkipsAlreadyExcludedGroupsAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Already excluded"),
            new ChatMessage(ChatRole.User, "Included 1"),
            new ChatMessage(ChatRole.User, "Included 2"),
        ]);
        groups.Groups[0].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.True(groups.Groups[0].IsExcluded); // was already excluded
        Assert.True(groups.Groups[1].IsExcluded); // newly excluded
        Assert.False(groups.Groups[2].IsExcluded); // kept
    }

    [Fact]
    public async Task CompactAsyncMinimumPreservedKeepsMultipleAsync()
    {
        // Arrange — keep 2 most recent
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 2);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncNothingToRemoveReturnsFalseAsync()
    {
        // Arrange — preserve 5 but only 2 groups
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 5);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncCustomTargetStopsEarlyAsync()
    {
        // Arrange — always trigger, custom target stops after 1 exclusion
        int targetChecks = 0;
        bool TargetAfterOne(CompactionMessageIndex _) => ++targetChecks >= 1;

        TruncationCompactionStrategy strategy = new(
            CompactionTriggers.Always,
            minimumPreservedGroups: 1,
            target: TargetAfterOne);

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert — only 1 group excluded (target met after first)
        Assert.True(result);
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.False(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncIncrementalStopsAtTargetAsync()
    {
        // Arrange — trigger on groups > 2, target is default (inverse of trigger: groups <= 2)
        TruncationCompactionStrategy strategy = new(
            CompactionTriggers.GroupsExceed(2),
            minimumPreservedGroups: 1);

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act — 5 groups, trigger fires (5 > 2), compacts until groups <= 2
        bool result = await strategy.CompactAsync(groups);

        // Assert — should stop at 2 included groups (not go all the way to 1)
        Assert.True(result);
        Assert.Equal(2, groups.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncLoopExitsWhenMaxRemovableReachedAsync()
    {
        // Arrange — target never stops (always false), so the loop must exit via removed >= maxRemovable
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 2, target: CompactionTriggers.Never);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert — only 2 removed (maxRemovable = 4 - 2 = 2), 2 preserved
        Assert.True(result);
        Assert.Equal(2, groups.IncludedGroupCount);
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncSkipsPreExcludedAndSystemGroupsAsync()
    {
        // Arrange — has excluded + system groups that the loop must skip
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System"),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);
        // Pre-exclude one group
        groups.Groups[1].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert — system preserved, pre-excluded skipped, A1 removed, Q2 preserved
        Assert.True(result);
        Assert.False(groups.Groups[0].IsExcluded); // System
        Assert.True(groups.Groups[1].IsExcluded);  // Pre-excluded Q1
        Assert.True(groups.Groups[2].IsExcluded);  // Newly excluded A1
        Assert.False(groups.Groups[3].IsExcluded); // Preserved Q2
    }
}
