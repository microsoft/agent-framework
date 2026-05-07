// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ContextWindowCompactionStrategy"/> class.
/// </summary>
public class ContextWindowCompactionStrategyTests
{
    [Fact]
    public void Constructor_ValidParameters_SetsProperties()
    {
        // Arrange & Act
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 1_050_000,
            maxOutputTokens: 128_000);

        // Assert
        Assert.Equal(1_050_000, strategy.MaxContextWindowTokens);
        Assert.Equal(128_000, strategy.MaxOutputTokens);
        Assert.Equal(922_000, strategy.InputBudgetTokens);
        Assert.Equal(ContextWindowCompactionStrategy.DefaultToolEvictionThreshold, strategy.ToolEvictionThreshold);
        Assert.Equal(ContextWindowCompactionStrategy.DefaultTruncationThreshold, strategy.TruncationThreshold);
    }

    [Fact]
    public void Constructor_CustomThresholds_SetsProperties()
    {
        // Arrange & Act
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 1_000_000,
            maxOutputTokens: 100_000,
            toolEvictionThreshold: 0.3,
            truncationThreshold: 0.6);

        // Assert
        Assert.Equal(900_000, strategy.InputBudgetTokens);
        Assert.Equal(0.3, strategy.ToolEvictionThreshold);
        Assert.Equal(0.6, strategy.TruncationThreshold);
    }

    [Theory]
    [InlineData(0, 100)]        // maxContextWindowTokens <= 0
    [InlineData(-1, 100)]       // maxContextWindowTokens negative
    public void Constructor_InvalidContextWindow_Throws(int contextWindow, int maxOutput)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new ContextWindowCompactionStrategy(contextWindow, maxOutput));
    }

    [Theory]
    [InlineData(1000, -1)]       // maxOutputTokens negative
    [InlineData(1000, 1000)]     // maxOutputTokens == contextWindow
    [InlineData(1000, 1001)]     // maxOutputTokens > contextWindow
    public void Constructor_InvalidOutputTokens_Throws(int contextWindow, int maxOutput)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new ContextWindowCompactionStrategy(contextWindow, maxOutput));
    }

    [Theory]
    [InlineData(0.0)]   // Zero threshold
    [InlineData(-0.1)]  // Negative threshold
    [InlineData(1.1)]   // Over 1.0
    public void Constructor_InvalidToolEvictionThreshold_Throws(double threshold)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new ContextWindowCompactionStrategy(1000, 100, toolEvictionThreshold: threshold));
    }

    [Theory]
    [InlineData(0.0)]   // Zero threshold
    [InlineData(-0.1)]  // Negative threshold
    [InlineData(1.1)]   // Over 1.0
    public void Constructor_InvalidTruncationThreshold_Throws(double threshold)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new ContextWindowCompactionStrategy(1000, 100, truncationThreshold: threshold));
    }

    [Fact]
    public void Constructor_TruncationBelowToolEviction_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new ContextWindowCompactionStrategy(1000, 100, toolEvictionThreshold: 0.8, truncationThreshold: 0.5));
    }

    [Fact]
    public async Task CompactAsync_BelowToolEvictionThreshold_NoCompactionAsync()
    {
        // Arrange — input budget = 900 tokens, tool eviction at 450, truncation at 720
        // A few short messages should be well below any threshold.
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 1000,
            maxOutputTokens: 100);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi there!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(2, index.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsync_AboveTruncationThreshold_TruncatesOldestAsync()
    {
        // Arrange — use a budget of 5 tokens with truncation at 80% = 4 token threshold.
        // Even the shortest messages will exceed this, ensuring truncation fires.
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 10,
            maxOutputTokens: 5,
            toolEvictionThreshold: 0.5,
            truncationThreshold: 0.8);

        // Verify internal budget calculation
        Assert.Equal(5, strategy.InputBudgetTokens);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First user message"),
            new ChatMessage(ChatRole.Assistant, "First response"),
            new ChatMessage(ChatRole.User, "Second user message"),
            new ChatMessage(ChatRole.Assistant, "Second response"),
        ]);

        int groupsBefore = index.IncludedGroupCount;
        int tokensBefore = index.IncludedTokenCount;

        // Verify tokens actually exceed the truncation threshold (80% of 5 = 4)
        Assert.True(tokensBefore > 4, $"Expected tokens > 4 but got {tokensBefore}");
        Assert.True(groupsBefore > 1, $"Expected groups > 1 but got {groupsBefore}");

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — with tokens well above a 4-token threshold, truncation should fire
        Assert.True(result, $"Expected compaction to occur. Tokens before: {tokensBefore}, groups before: {groupsBefore}, NonSystemGroups: {index.IncludedNonSystemGroupCount}");
        Assert.True(index.IncludedGroupCount < groupsBefore);
    }

    [Fact]
    public async Task CompactAsync_ToolCallsAboveEvictionThreshold_CollapsesToolCallsAsync()
    {
        // Arrange — very small budget so tool eviction fires.
        // Input budget = 5, tool eviction at 50% = 2 token threshold.
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 10,
            maxOutputTokens: 5,
            toolEvictionThreshold: 0.5,
            truncationThreshold: 0.9);

        // Build messages with a tool call group: assistant with FunctionCallContent + tool result
        var assistantMessage = new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "get_data", arguments: new Dictionary<string, object?> { ["query"] = "test" })]);
        var toolResultMessage = new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call1", "Here is a long result with many words to ensure we exceed the token threshold")]);
        var userMessage = new ChatMessage(ChatRole.User, "What did you find?");
        var assistantResponse = new ChatMessage(ChatRole.Assistant, "Based on the results I found information.");

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            assistantMessage,
            toolResultMessage,
            userMessage,
            assistantResponse,
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — compaction should succeed for tool calls above the eviction threshold.
        // Do not assert on IncludedTokenCount because tool-result compaction preserves content
        // in summary form and tokenization can make the count stay the same or increase.
        Assert.True(result);
    }

    [Fact]
    public void Constructor_EqualThresholds_Succeeds()
    {
        // Arrange & Act — truncation == tool eviction should be valid
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 1000,
            maxOutputTokens: 100,
            toolEvictionThreshold: 0.7,
            truncationThreshold: 0.7);

        // Assert
        Assert.Equal(0.7, strategy.ToolEvictionThreshold);
        Assert.Equal(0.7, strategy.TruncationThreshold);
    }

    [Fact]
    public void Constructor_ZeroMaxOutputTokens_FullBudget()
    {
        // Arrange & Act
        var strategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: 1_000_000,
            maxOutputTokens: 0);

        // Assert — entire context window is the input budget
        Assert.Equal(1_000_000, strategy.InputBudgetTokens);
    }
}
