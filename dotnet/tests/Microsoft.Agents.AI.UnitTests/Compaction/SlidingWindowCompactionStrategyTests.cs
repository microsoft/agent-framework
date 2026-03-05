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
    public async Task CompactAsync_BelowMaxTurns_ReturnsFalseAsync()
    {
        // Arrange
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 3);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_ExceedsMaxTurns_ExcludesOldestTurnsAsync()
    {
        // Arrange — keep 2 turns, conversation has 3
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 2);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_PreservesSystemMessagesAsync()
    {
        // Arrange
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 1);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_PreservesToolCallGroupsInKeptTurnsAsync()
    {
        // Arrange
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 1);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_CustomTrigger_OverridesDefaultAsync()
    {
        // Arrange — custom trigger: only compact when tokens exceed threshold
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 99);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act — tokens are tiny, trigger not met
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsync_IncludedMessages_ContainOnlyKeptTurnsAsync()
    {
        // Arrange
        SlidingWindowCompactionStrategy strategy = new(maximumTurns: 1);
        MessageIndex groups = MessageIndex.Create(
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
}
