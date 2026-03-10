// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="SlidingWindowCompactionStrategy"/> class.
/// </summary>
public class SlidingWindowCompactionStrategyTests
{
    [Fact]
    public async Task CompactAsyncBelowMaxTurnsReturnsFalseAsync()
    {
        // Arrange — trigger requires > 3 turns, conversation has 2
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(3));
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
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncExceedsMaxTurnsExcludesOldestTurnsAsync()
    {
        // Arrange — trigger on > 2 turns, conversation has 3
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(2));
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
            new ChatMessage(ChatRole.Assistant, "A3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // Turn 1 (Q1 + A1) should be excluded
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        // Turn 2 and 3 should remain
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
        Assert.False(groups.Groups[4].IsExcluded);
        Assert.False(groups.Groups[5].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncPreservesSystemMessagesAsync()
    {
        // Arrange — trigger on > 1 turn
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(1));
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.False(groups.Groups[0].IsExcluded); // System preserved
        Assert.True(groups.Groups[1].IsExcluded);  // Turn 1 excluded
        Assert.True(groups.Groups[2].IsExcluded);  // Turn 1 response excluded
        Assert.False(groups.Groups[3].IsExcluded); // Turn 2 kept
    }

    [Fact]
    public async Task CompactAsyncPreservesToolCallGroupsInKeptTurnsAsync()
    {
        // Arrange — trigger on > 1 turn
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(1));
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "search")]),
            new ChatMessage(ChatRole.Tool, "Results"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // Turn 1 excluded
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        // Turn 2 kept (user + tool call group)
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger requires > 99 turns
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(99));

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncIncludedMessagesContainOnlyKeptTurnsAsync()
    {
        // Arrange — trigger on > 1 turn
        SlidingWindowCompactionStrategy strategy = new(CompactionTriggers.TurnsExceed(1));
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System"),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        await strategy.CompactAsync(groups);

        // Assert
        List<ChatMessage> included = [.. groups.GetIncludedMessages()];
        Assert.Equal(3, included.Count);
        Assert.Equal("System", included[0].Text);
        Assert.Equal("Q2", included[1].Text);
        Assert.Equal("A2", included[2].Text);
    }

    [Fact]
    public async Task CompactAsyncCustomTargetStopsExcludingEarlyAsync()
    {
        // Arrange — trigger on > 1 turn, custom target stops after removing 1 turn
        int removeCount = 0;
        bool TargetAfterOne(CompactionMessageIndex _) => ++removeCount >= 1;

        SlidingWindowCompactionStrategy strategy = new(
            CompactionTriggers.TurnsExceed(1),
            minimumPreservedTurns: 0,
            target: TargetAfterOne);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
            new ChatMessage(ChatRole.Assistant, "A3"),
            new ChatMessage(ChatRole.User, "Q4"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — only turn 1 excluded (target stopped after 1 removal)
        Assert.True(result);
        Assert.True(index.Groups[0].IsExcluded);   // Q1 (turn 1)
        Assert.True(index.Groups[1].IsExcluded);   // A1 (turn 1)
        Assert.False(index.Groups[2].IsExcluded);  // Q2 (turn 2) — kept
        Assert.False(index.Groups[3].IsExcluded);  // A2 (turn 2)
    }

    [Fact]
    public async Task CompactAsyncMinimumPreservedStopsCompactionAsync()
    {
        // Arrange — always trigger with never-satisfied target, but MinimumPreserved = 2 is hard floor
        SlidingWindowCompactionStrategy strategy = new(
            CompactionTriggers.TurnsExceed(1),
            minimumPreservedTurns: 2,
            target: _ => false);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
            new ChatMessage(ChatRole.Assistant, "A3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — target never says stop, but MinimumPreserved=2 protects the last 2 turns
        Assert.True(result);
        Assert.Equal(4, index.IncludedGroupCount);
        // Turn 1 excluded
        Assert.True(index.Groups[0].IsExcluded);   // Q1
        Assert.True(index.Groups[1].IsExcluded);   // A1
        // Last 2 turns must be preserved
        Assert.False(index.Groups[2].IsExcluded);  // Q2
        Assert.False(index.Groups[3].IsExcluded);  // A2
        Assert.False(index.Groups[4].IsExcluded);  // Q3
        Assert.False(index.Groups[5].IsExcluded);  // A3
    }

    [Fact]
    public async Task CompactAsyncSkipsExcludedAndSystemGroupsInEnumerationAsync()
    {
        // Arrange — includes system and pre-excluded groups that must be skipped
        SlidingWindowCompactionStrategy strategy = new(
            CompactionTriggers.TurnsExceed(1),
            minimumPreservedTurns: 0);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System prompt"),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);
        // Pre-exclude one group
        index.Groups[1].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — system preserved, pre-excluded skipped
        Assert.True(result);
        Assert.False(index.Groups[0].IsExcluded); // System preserved
    }

    [Fact]
    public async Task CompactAsyncPreservesTurnIndexZeroAsync()
    {
        // Arrange — assistant message before first user turn gets TurnIndex = 0
        SlidingWindowCompactionStrategy strategy = new(
            CompactionTriggers.TurnsExceed(1),
            minimumPreservedTurns: 0,
            target: _ => false);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.Assistant, "Welcome!"),  // TurnIndex = 0
            new ChatMessage(ChatRole.User, "Q1"),             // TurnIndex = 1
            new ChatMessage(ChatRole.Assistant, "A1"),        // TurnIndex = 1
            new ChatMessage(ChatRole.User, "Q2"),             // TurnIndex = 2
            new ChatMessage(ChatRole.Assistant, "A2"),        // TurnIndex = 2
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — TurnIndex = 0 is always preserved even with minimumPreservedTurns = 0
        Assert.True(result);
        Assert.False(index.Groups[0].IsExcluded);  // Welcome (TurnIndex 0) preserved
        Assert.True(index.Groups[1].IsExcluded);   // Q1 (TurnIndex 1) excluded
        Assert.True(index.Groups[2].IsExcluded);   // A1 (TurnIndex 1) excluded
        Assert.True(index.Groups[3].IsExcluded);   // Q2 (TurnIndex 2) excluded
        Assert.True(index.Groups[4].IsExcluded);   // A2 (TurnIndex 2) excluded
    }

    [Fact]
    public async Task CompactAsyncPreservesNullTurnIndexAsync()
    {
        // Arrange — system messages (TurnIndex = null) should never be removed
        SlidingWindowCompactionStrategy strategy = new(
            CompactionTriggers.TurnsExceed(0),
            minimumPreservedTurns: 0,
            target: _ => false);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — system message (TurnIndex null) always preserved
        Assert.True(result);
        Assert.False(index.Groups[0].IsExcluded);  // System (TurnIndex null) preserved
        Assert.True(index.Groups[1].IsExcluded);   // Q1 excluded
        Assert.True(index.Groups[2].IsExcluded);   // A1 excluded
    }
}
