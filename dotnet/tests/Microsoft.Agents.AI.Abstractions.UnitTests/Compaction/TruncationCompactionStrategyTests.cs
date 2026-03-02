// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class TruncationCompactionStrategyTests
{
    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        TruncationCompactionStrategy strategy = new(maxTokens: 100000);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Single(messages);
    }

    [Fact]
    public async Task OverLimit_RemovesOldestGroupsAsync()
    {
        // Use a very low max to trigger compaction
        TruncationCompactionStrategy strategy = new(maxTokens: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First message"),
            new(ChatRole.Assistant, "First reply"),
            new(ChatRole.User, "Second message"),
            new(ChatRole.Assistant, "Second reply"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        // Should have removed old groups, keeping at least the last one
        Assert.True(messages.Count < 4);
        Assert.True(messages.Count > 0);
    }

    [Fact]
    public void ShouldCompact_ReturnsFalseWhenUnderLimit()
    {
        TruncationCompactionStrategy strategy = new(maxTokens: 10000);
        CompactionMetric metrics = new() { TokenCount = 500 };

        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ShouldCompact_ReturnsTrueWhenOverLimit()
    {
        TruncationCompactionStrategy strategy = new(maxTokens: 100);
        CompactionMetric metrics = new() { TokenCount = 500 };

        Assert.True(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public async Task SystemOnlyMessages_NoChangeAsync()
    {
        // Only system messages → removableGroups.Count == 0 → no change
        TruncationCompactionStrategy strategy = new(maxTokens: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        // ShouldCompact triggers but reducer finds nothing removable
        Assert.Single(messages);
        Assert.Equal(result.After.MessageCount, result.Before.MessageCount);
        Assert.Equal(result.After.TokenCount, result.Before.TokenCount);
    }

    [Fact]
    public async Task SingleNonSystemGroup_NoChangeAsync()
    {
        // Only one non-system group → maxRemovable <= 0 → no change
        TruncationCompactionStrategy strategy = new(maxTokens: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "System prompt"),
            new(ChatRole.User, "Only user message"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.Equal(2, messages.Count);
        Assert.Equal(result.After.MessageCount, result.Before.MessageCount);
        Assert.Equal(result.After.TokenCount, result.Before.TokenCount);
    }

    [Fact]
    public async Task PreserveRecentGroups_KeepsMultipleGroupsAsync()
    {
        // preserveRecentGroups=2 means keep at least the last 2 non-system groups
        TruncationCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 2);
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
        // 6 groups (3 user + 3 assistant), protect last 2 → 4 removable
        // Should keep at least: Turn 3 user + Reply 3 assistant (last 2 groups)
        Assert.True(messages.Count >= 2);
        Assert.Equal("Reply 3", messages[^1].Text);
    }
}
