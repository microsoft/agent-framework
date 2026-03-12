// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for <see cref="CompactionStrategy.Create"/>.
/// </summary>
public class CompactionStrategyCreateTests
{
    private static IChatClient CreateMockChatClient()
    {
        Mock<IChatClient> mock = new();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "summary")]));
        return mock.Object;
    }

    // ── Gentle ────────────────────────────────────────────────────────────────

    [Fact]
    public void CreateGentleCompactReturnsTwoStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Compact));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleModerateReturnsTwoStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleGenerousReturnsTwoStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Generous));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleDoesNotRequireChatClient()
    {
        // No chatClient supplied — should succeed without throwing.
        CompactionStrategy strategy = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate);
        Assert.NotNull(strategy);
    }

    // ── Balanced ──────────────────────────────────────────────────────────────

    [Fact]
    public void CreateBalancedCompactReturnsThreeStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Balanced, CompactionSize.Compact, CreateMockChatClient()));

        Assert.Equal(3, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[2]);
    }

    [Fact]
    public void CreateBalancedModerateReturnsThreeStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Balanced, CompactionSize.Moderate, CreateMockChatClient()));

        Assert.Equal(3, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[2]);
    }

    [Fact]
    public void CreateBalancedGenerousReturnsThreeStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Balanced, CompactionSize.Generous, CreateMockChatClient()));

        Assert.Equal(3, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[2]);
    }

    [Fact]
    public void CreateBalancedNullChatClientThrows()
    {
        Assert.Throws<ArgumentNullException>(
            () => CompactionStrategy.Create(CompactionApproach.Balanced, CompactionSize.Moderate, null));
    }

    // ── Aggressive ────────────────────────────────────────────────────────────

    [Fact]
    public void CreateAggressiveCompactReturnsFourStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Aggressive, CompactionSize.Compact, CreateMockChatClient()));

        Assert.Equal(4, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<SlidingWindowCompactionStrategy>(pipeline.Strategies[2]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[3]);
    }

    [Fact]
    public void CreateAggressiveModerateReturnsFourStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Aggressive, CompactionSize.Moderate, CreateMockChatClient()));

        Assert.Equal(4, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<SlidingWindowCompactionStrategy>(pipeline.Strategies[2]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[3]);
    }

    [Fact]
    public void CreateAggressiveGenerousReturnsFourStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Aggressive, CompactionSize.Generous, CreateMockChatClient()));

        Assert.Equal(4, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
        Assert.IsType<SlidingWindowCompactionStrategy>(pipeline.Strategies[2]);
        Assert.IsType<TruncationCompactionStrategy>(pipeline.Strategies[3]);
    }

    [Fact]
    public void CreateAggressiveNullChatClientThrows()
    {
        Assert.Throws<ArgumentNullException>(
            () => CompactionStrategy.Create(CompactionApproach.Aggressive, CompactionSize.Moderate, null));
    }

    // ── Invalid enum values ───────────────────────────────────────────────────

    [Fact]
    public void CreateInvalidApproachThrows()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => CompactionStrategy.Create((CompactionApproach)99, CompactionSize.Moderate));
    }

    [Fact]
    public void CreateInvalidSizeThrows()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => CompactionStrategy.Create(CompactionApproach.Gentle, (CompactionSize)99));
    }

    // ── Size-threshold behavioral verification ────────────────────────────────

    /// <summary>
    /// Verifies that <see cref="CompactionSize.Compact"/> and <see cref="CompactionSize.Moderate"/>
    /// configure different message thresholds: 18 messages (17 groups) should trigger the Compact
    /// ToolResultCompaction stage (threshold 10) but NOT the Moderate one (threshold 20).
    /// </summary>
    [Fact]
    public async Task CreateGentleSizeDifferentiatesMessageThresholdsAsync()
    {
        // Arrange: 17 groups = 1 ToolCall + 8 User + 8 AssistantText = 18 messages.
        //   Compact ToolResult triggers at MessagesExceed(10) → 18 > 10 → fires.
        //   Moderate ToolResult triggers at MessagesExceed(20) → 18 < 20 → does not fire.
        //
        //   With minimumPreservedGroups=16 and 17 total groups the oldest 1 group (the tool-call
        //   group) is eligible for collapsing, making the behavioral difference observable.
        CompactionStrategy compactPipeline = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Compact);
        CompactionStrategy moderatePipeline = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate);

        List<ChatMessage> messages =
        [
            // 1 tool-call group (assistant FunctionCall + tool result = 2 messages, 1 group)
            new(ChatRole.Assistant, [new FunctionCallContent("c1", "fetch")]),
            new(ChatRole.Tool, "data"),
            // 8 user/assistant pairs = 16 messages, 16 groups
            new(ChatRole.User, "Q1"), new(ChatRole.Assistant, "A1"),
            new(ChatRole.User, "Q2"), new(ChatRole.Assistant, "A2"),
            new(ChatRole.User, "Q3"), new(ChatRole.Assistant, "A3"),
            new(ChatRole.User, "Q4"), new(ChatRole.Assistant, "A4"),
            new(ChatRole.User, "Q5"), new(ChatRole.Assistant, "A5"),
            new(ChatRole.User, "Q6"), new(ChatRole.Assistant, "A6"),
            new(ChatRole.User, "Q7"), new(ChatRole.Assistant, "A7"),
            new(ChatRole.User, "Q8"), new(ChatRole.Assistant, "A8"),
        ];

        // Two separate indexes so strategies run independently.
        CompactionMessageIndex compactIndex = CompactionMessageIndex.Create(messages);
        CompactionMessageIndex moderateIndex = CompactionMessageIndex.Create(messages);

        // Act
        bool compactCompacted = await compactPipeline.CompactAsync(compactIndex);
        bool moderateCompacted = await moderatePipeline.CompactAsync(moderateIndex);

        // Assert
        Assert.True(compactCompacted, "Compact size should trigger ToolResult compaction at 18 messages (> threshold of 10).");
        Assert.False(moderateCompacted, "Moderate size should NOT trigger ToolResult compaction at 18 messages (< threshold of 20).");
    }
}
