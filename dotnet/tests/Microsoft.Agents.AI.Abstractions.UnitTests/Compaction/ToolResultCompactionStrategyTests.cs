// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class ToolResultCompactionStrategyTests
{
    [Fact]
    public void ShouldCompact_UnderLimit_ReturnsFalse()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 100000);
        CompactionMetric metrics = new() { TokenCount = 500, ToolCallCount = 3 };

        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ShouldCompact_OverLimitNoToolCalls_ReturnsFalse()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 100);
        CompactionMetric metrics = new() { TokenCount = 500, ToolCallCount = 0 };

        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ShouldCompact_OverLimitWithToolCalls_ReturnsTrue()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 100);
        CompactionMetric metrics = new() { TokenCount = 500, ToolCallCount = 2 };

        Assert.True(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 100000);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Equal(3, messages.Count);
    }

    [Fact]
    public async Task CollapsesOldToolGroupAsync()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny, 72°F")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        // The old tool group (assistant+tool = 2 messages) should be collapsed to 1
        Assert.Equal(4, messages.Count); // user + [collapsed] + user + assistant
        Assert.Contains("[Tool calls: get_weather]", messages[1].Text);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
    }

    [Fact]
    public async Task ProtectsRecentGroupsAsync()
    {
        // With preserveRecentGroups=4, all groups are protected (5 groups, protect 4 non-system)
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 10);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        // All groups protected, so no collapse
        Assert.False(result.Applied);
        Assert.Equal(5, messages.Count);
    }

    [Fact]
    public async Task PreservesSystemMessagesAsync()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
    }

    [Fact]
    public async Task MultipleToolCalls_ListedInSummaryAsync()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Do research"),
            new ChatMessage(ChatRole.Assistant, [
                new FunctionCallContent("c1", "search"),
                new FunctionCallContent("c2", "fetch_page"),
            ]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "results...")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c2", "page content...")]),
            new(ChatRole.User, "Summarize"),
            new(ChatRole.Assistant, "Here's the summary."),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        // Old tool group (1 assistant + 2 tools = 3 messages) collapsed to 1
        Assert.Equal(4, messages.Count);
        Assert.Contains("search", messages[1].Text);
        Assert.Contains("fetch_page", messages[1].Text);
    }

    [Fact]
    public async Task NoToolGroups_NoChangeAsync()
    {
        ToolResultCompactionStrategy strategy = new(maxTokens: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        // ToolCallCount is 0, so ShouldCompact returns false
        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Equal(2, messages.Count);
    }
}
