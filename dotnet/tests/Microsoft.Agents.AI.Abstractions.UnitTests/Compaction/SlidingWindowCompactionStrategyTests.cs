// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class SlidingWindowCompactionStrategyTests
{
    [Fact]
    public void ShouldCompact_UnderLimit_ReturnsFalse()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 10);
        CompactionMetric metrics = new() { UserTurnCount = 3 };

        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ShouldCompact_OverLimit_ReturnsTrue()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 2);
        CompactionMetric metrics = new() { UserTurnCount = 5 };

        Assert.True(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 10);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Equal(2, messages.Count);
    }

    [Fact]
    public async Task KeepsLastNTurnsAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 2);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
            new(ChatRole.User, "Turn 3"),
            new(ChatRole.Assistant, "Reply 3"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Equal(4, messages.Count);
        Assert.Equal("Turn 2", messages[0].Text);
        Assert.Equal("Reply 2", messages[1].Text);
        Assert.Equal("Turn 3", messages[2].Text);
        Assert.Equal("Reply 3", messages[3].Text);
    }

    [Fact]
    public async Task PreservesSystemMessagesAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Equal(3, messages.Count);
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
        Assert.Equal("Turn 2", messages[1].Text);
        Assert.Equal("Reply 2", messages[2].Text);
    }

    [Fact]
    public async Task PreservesToolGroupsWithinKeptTurnsAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Get weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.Assistant, "It's sunny!"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        // Turn 1 dropped, Turn 2 kept (user + assistant-tool-group + plain assistant)
        Assert.Equal(4, messages.Count);
        Assert.Equal("Get weather", messages[0].Text);
    }

    [Fact]
    public async Task SingleTurn_AtLimit_NoChangeAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Equal(2, messages.Count);
    }

    [Fact]
    public async Task DropsResponseGroupsFromOldTurnsAsync()
    {
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "search")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "result")]),
            new(ChatRole.Assistant, "Here's what I found"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Equal(2, messages.Count);
        Assert.Equal("Turn 2", messages[0].Text);
        Assert.Equal("Reply 2", messages[1].Text);
    }
}
