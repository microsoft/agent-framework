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
    private static readonly CompactionTrigger s_alwaysTrigger = _ => true;

    [Fact]
    public async Task CompactAsync_AlwaysTrigger_CompactsToPreserveRecentAsync()
    {
        // Arrange — always-trigger means always compact
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 1);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_TriggerNotMet_ReturnsFalseAsync()
    {
        // Arrange — trigger requires > 1000 tokens, conversation is tiny
        TruncationCompactionStrategy strategy = new(
            preserveRecentGroups: 1,
            trigger: CompactionTriggers.TokensExceed(1000));

        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_TriggerMet_ExcludesOldestGroupsAsync()
    {
        // Arrange — trigger on groups > 2
        TruncationCompactionStrategy strategy = new(
            preserveRecentGroups: 1,
            trigger: CompactionTriggers.GroupsExceed(2));

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
            new ChatMessage(ChatRole.Assistant, "Response 2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.Equal(1, groups.IncludedGroupCount);
        // Oldest 3 excluded, newest 1 kept
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.True(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_PreservesSystemMessagesAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 1);
        MessageIndex groups = MessageIndex.Create(
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
        Assert.Equal(MessageGroupKind.System, groups.Groups[0].Kind);
        // Oldest non-system groups excluded
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.True(groups.Groups[2].IsExcluded);
        // Most recent kept
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_PreservesToolCallGroupAtomicityAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 1);

        ChatMessage assistantToolCall= new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");
        ChatMessage finalResponse = new(ChatRole.User, "Thanks!");

        MessageIndex groups = MessageIndex.Create([assistantToolCall, toolResult, finalResponse]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // Tool call group should be excluded as one atomic unit
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.Equal(MessageGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(2, groups.Groups[0].Messages.Count);
        Assert.False(groups.Groups[1].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_SetsExcludeReasonAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 1);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_SkipsAlreadyExcludedGroupsAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 1);
        MessageIndex groups = MessageIndex.Create(
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
    public async Task CompactAsync_PreserveRecentGroups_KeepsMultipleAsync()
    {
        // Arrange — keep 2 most recent
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 2);
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
        Assert.True(result);
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_NothingToRemove_ReturnsFalseAsync()
    {
        // Arrange — preserve 5 but only 2 groups
        TruncationCompactionStrategy strategy = new(s_alwaysTrigger, preserveRecentGroups: 5);
        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }
}
