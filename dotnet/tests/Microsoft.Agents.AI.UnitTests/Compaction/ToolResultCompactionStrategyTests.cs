// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
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
    public async Task CompactAsyncCollapsesOldToolGroupsAsync()
    {
        // Arrange — always trigger
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 1);

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
    public async Task CompactAsyncPreservesRecentToolGroupsAsync()
    {
        // Arrange — protect 2 recent non-system groups (the tool group + Q2)
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 3);

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
    public async Task CompactAsyncPreservesSystemMessagesAsync()
    {
        // Arrange
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 1);

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
    public async Task CompactAsyncExtractsMultipleToolNamesAsync()
    {
        // Arrange — assistant calls two tools
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 1);

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
    public async Task CompactAsyncNoToolGroupsReturnsFalseAsync()
    {
        // Arrange — trigger fires but no tool groups to collapse
        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 0);

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
    public async Task CompactAsyncCompoundTriggerRequiresTokensAndToolCallsAsync()
    {
        // Arrange — compound: tokens > 0 AND has tool calls
        ToolResultCompactionStrategy strategy = new(
            CompactionTriggers.All(
                CompactionTriggers.TokensExceed(0),
                CompactionTriggers.HasToolCalls()),
            minimumPreserved: 1);

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

    [Fact]
    public async Task CompactAsyncTargetStopsCollapsingEarlyAsync()
    {
        // Arrange — 2 tool groups, target met after first collapse
        int collapseCount = 0;
        bool TargetAfterOne(MessageIndex _) => ++collapseCount >= 1;

        ToolResultCompactionStrategy strategy = new(
            trigger: _ => true,
            minimumPreserved: 1,
            target: TargetAfterOne);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn1")]),
            new ChatMessage(ChatRole.Tool, "result1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c2", "fn2")]),
            new ChatMessage(ChatRole.Tool, "result2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — only first tool group collapsed, second left intact
        Assert.True(result);

        // Count collapsed tool groups (excluded with ToolCall kind)
        int collapsedToolGroups = 0;
        foreach (MessageGroup group in index.Groups)
        {
            if (group.IsExcluded && group.Kind == MessageGroupKind.ToolCall)
            {
                collapsedToolGroups++;
            }
        }

        Assert.Equal(1, collapsedToolGroups);
    }

    [Fact]
    public async Task CompactAsyncSkipsPreExcludedAndSystemGroupsAsync()
    {
        // Arrange — pre-excluded and system groups in the enumeration
        ToolResultCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreserved: 0);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.System, "System prompt"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, "Result 1"),
            new ChatMessage(ChatRole.User, "Q1"),
        ];

        MessageIndex index = MessageIndex.Create(messages);
        // Pre-exclude the user group
        index.Groups[index.Groups.Count - 1].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — system never excluded, pre-excluded skipped
        Assert.True(result);
        Assert.False(index.Groups[0].IsExcluded); // System stays
    }
}
