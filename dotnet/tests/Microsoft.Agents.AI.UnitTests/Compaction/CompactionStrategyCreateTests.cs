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
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Compact, CreateMockChatClient()));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleModerateReturnsTwoStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate, CreateMockChatClient()));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleGenerousReturnsTwoStrategyPipeline()
    {
        PipelineCompactionStrategy pipeline =
            Assert.IsType<PipelineCompactionStrategy>(
                CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Generous, CreateMockChatClient()));

        Assert.Equal(2, pipeline.Strategies.Count);
        Assert.IsType<ToolResultCompactionStrategy>(pipeline.Strategies[0]);
        Assert.IsType<SummarizationCompactionStrategy>(pipeline.Strategies[1]);
    }

    [Fact]
    public void CreateGentleDoesNotRequireChatClient()
    {
        // No chatClient supplied — should succeed without throwing.
        CompactionStrategy strategy = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate, CreateMockChatClient());
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
            () => CompactionStrategy.Create(CompactionApproach.Balanced, CompactionSize.Moderate, null!));
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

    // ── Invalid enum values ───────────────────────────────────────────────────

    [Fact]
    public void CreateInvalidApproachThrows()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => CompactionStrategy.Create((CompactionApproach)99, CompactionSize.Moderate, CreateMockChatClient()));
    }

    [Fact]
    public void CreateInvalidSizeThrows()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => CompactionStrategy.Create(CompactionApproach.Gentle, (CompactionSize)99, CreateMockChatClient()));
    }

    // ── Size-threshold behavioral verification ────────────────────────────────

    /// <summary>
    /// Verifies that <see cref="CompactionSize.Compact"/> and <see cref="CompactionSize.Moderate"/>
    /// configure different message thresholds.
    /// </summary>
    [Fact]
    public async Task CreateGentleSizeDifferentiatesMessageThresholdsAsync()
    {
        // Arrange: 1 tool-call group + 99 (User, Assistant) groups = 100 groups / 200 messages.
        //   Compact ToolResult triggers at MessagesExceed(50)  → 200 > 50  → fires.
        //   Moderate ToolResult triggers at MessagesExceed(500) → 200 < 500 → does not fire.
        //
        //   The configuration preserves a number of most-recent groups, leaving the oldest
        //   tool-call group eligible for collapsing, which makes the behavioral difference
        //   between Compact and Moderate sizes observable in this test.
        CompactionStrategy compactPipeline = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Compact, CreateMockChatClient());
        CompactionStrategy moderatePipeline = CompactionStrategy.Create(CompactionApproach.Gentle, CompactionSize.Moderate, CreateMockChatClient());

        List<ChatMessage> messages =
        [
            // 1 tool-call group (assistant FunctionCall + tool result = 2 messages, 1 group)
            new(ChatRole.Assistant, [new FunctionCallContent("c1", "fetch")]),
            new(ChatRole.Tool, "data"),
        ];

        for (int index = 0; index < 99; ++index)
        {
            messages.Add(new(ChatRole.User, $"Q{index}"));
            messages.Add(new(ChatRole.Assistant, $"A{index}"));
        }

        // Two separate indexes so strategies run independently.
        CompactionMessageIndex compactIndex = CompactionMessageIndex.Create(messages);
        CompactionMessageIndex moderateIndex = CompactionMessageIndex.Create(messages);

        // Act
        bool compactCompacted = await compactPipeline.CompactAsync(compactIndex);
        bool moderateCompacted = await moderatePipeline.CompactAsync(moderateIndex);

        // Assert
        Assert.True(compactCompacted, "Compact size should trigger ToolResult compaction.");
        Assert.False(moderateCompacted, "Moderate size should NOT trigger ToolResult compaction.");
    }
}
