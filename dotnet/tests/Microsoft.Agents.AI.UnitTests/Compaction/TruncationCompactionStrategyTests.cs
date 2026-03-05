// Copyright (c) Microsoft. All rights reserved.

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
    public async Task CompactAsync_BelowLimit_ReturnsFalseAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 5);
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
    public async Task CompactAsync_AtLimit_ReturnsFalseAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 2);
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

    [Fact]
    public async Task CompactAsync_ExceedsLimit_ExcludesOldestGroupsAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 2);
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response 1");
        ChatMessage msg3 = new(ChatRole.User, "Second");
        ChatMessage msg4 = new(ChatRole.Assistant, "Response 2");

        MessageIndex groups = MessageIndex.Create([msg1, msg2, msg3, msg4]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        Assert.Equal(2, groups.IncludedGroupCount);
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_PreservesSystemMessages_WhenEnabledAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 2, preserveSystemMessages: true);
        ChatMessage systemMsg = new(ChatRole.System, "You are helpful.");
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response 1");
        ChatMessage msg3 = new(ChatRole.User, "Second");

        MessageIndex groups = MessageIndex.Create([systemMsg, msg1, msg2, msg3]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // System message should be preserved
        Assert.False(groups.Groups[0].IsExcluded);
        Assert.Equal(MessageGroupKind.System, groups.Groups[0].Kind);
        // Oldest non-system groups should be excluded
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.True(groups.Groups[2].IsExcluded);
        // Most recent should remain
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_DoesNotPreserveSystemMessages_WhenDisabledAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 2, preserveSystemMessages: false);
        ChatMessage systemMsg = new(ChatRole.System, "You are helpful.");
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response");
        ChatMessage msg3 = new(ChatRole.User, "Second");

        MessageIndex groups = MessageIndex.Create([systemMsg, msg1, msg2, msg3]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
        // System message should be excluded (oldest)
        Assert.True(groups.Groups[0].IsExcluded);
        Assert.True(groups.Groups[1].IsExcluded);
        Assert.False(groups.Groups[2].IsExcluded);
        Assert.False(groups.Groups[3].IsExcluded);
    }

    [Fact]
    public async Task CompactAsync_PreservesToolCallGroupAtomicityAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(maxGroups: 1);

        ChatMessage assistantToolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
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
        TruncationCompactionStrategy strategy = new(maxGroups: 1);
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
        TruncationCompactionStrategy strategy = new(maxGroups: 1);
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
}
