// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ToolResultCompactionStrategy"/> class.
/// </summary>
public class ToolResultCompactionStrategyTests
{
    [Fact]
    public async Task CompactAsync_TriggerNotMet_ReturnsFalseAsync()
    {
        // Arrange — trigger requires > 1000 tokens
        ToolResultCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(1000));

        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "What's the weather?"),
            toolCall,
            toolResult,
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsync_CollapsesOldToolGroupsAsync()
    {
        // Arrange — always trigger
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            preserveRecentGroups: 1);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, "Sunny and 72°F"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);

        List<ChatMessage> included = [.. groups.GetIncludedMessages()];
        // Q1 + collapsed tool summary + Q2
        Assert.Equal(3, included.Count);
        Assert.Equal("Q1", included[0].Text);
        Assert.Contains("[Tool calls: get_weather]", included[1].Text);
        Assert.Equal("Q2", included[2].Text);
    }

    [Fact]
    public async Task CompactAsync_PreservesRecentToolGroupsAsync()
    {
        // Arrange — protect 2 recent non-system groups (the tool group + Q2)
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            preserveRecentGroups: 3);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "search")]),
            new ChatMessage(ChatRole.Tool, "Results"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert — all groups are in the protected window, nothing to collapse
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsync_PreservesSystemMessagesAsync()
    {
        // Arrange
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            preserveRecentGroups: 1);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "fn")]),
            new ChatMessage(ChatRole.Tool, "result"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(groups);

        // Assert
        List<ChatMessage> included = [.. groups.GetIncludedMessages()];
        Assert.Equal("You are helpful.", included[0].Text);
    }

    [Fact]
    public async Task CompactAsync_ExtractsMultipleToolNamesAsync()
    {
        // Arrange — assistant calls two tools
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            preserveRecentGroups: 1);

        ChatMessage multiToolCall = new(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "get_weather"),
            new FunctionCallContent("c2", "search_docs"),
        ]);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            multiToolCall,
            new ChatMessage(ChatRole.Tool, "Sunny"),
            new ChatMessage(ChatRole.Tool, "Found 3 docs"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(groups);

        // Assert
        List<ChatMessage> included = [.. groups.GetIncludedMessages()];
        string collapsed = included[1].Text!;
        Assert.Contains("get_weather", collapsed);
        Assert.Contains("search_docs", collapsed);
    }

    [Fact]
    public async Task CompactAsync_NoToolGroups_ReturnsFalseAsync()
    {
        // Arrange — trigger fires but no tool groups to collapse
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            preserveRecentGroups: 0);

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
    public async Task CompactAsync_CompoundTrigger_RequiresTokensAndToolCallsAsync()
    {
        // Arrange — compound: tokens > 0 AND has tool calls
        ToolResultCompactionStrategy strategy = new(
            CompactionTriggers.All(
                CompactionTriggers.TokensExceed(0),
                CompactionTriggers.HasToolCalls()),
            preserveRecentGroups: 1);

        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, "result"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(groups);

        // Assert
        Assert.True(result);
    }
}
