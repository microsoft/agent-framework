// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

using Microsoft.Agents.AI.Compaction;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class CompactionPipelineResultTests
{
    [Fact]
    public void Properties_AreReadable()
    {
        // Arrange
        ChatHistoryMetric before = new() { MessageCount = 10 };
        ChatHistoryMetric after = new() { MessageCount = 5 };
        CompactionResult strategyResult = new("Test", applied: true, before, after);
        List<CompactionResult> results = [strategyResult];

        // Act
        CompactionPipelineResult pipelineResult = new(before, after, results);

        // Assert
        Assert.Same(before, pipelineResult.Before);
        Assert.Same(after, pipelineResult.After);
        Assert.Single(pipelineResult.StrategyResults);
    }

    [Fact]
    public void AnyApplied_AllFalse_ReturnsFalse()
    {
        // Arrange
        ChatHistoryMetric metrics = new() { MessageCount = 5 };
        CompactionResult skipped = CompactionResult.Skipped("Skip", metrics);

        // Act
        CompactionPipelineResult result = new(metrics, metrics, [skipped]);

        // Assert
        Assert.False(result.AnyApplied);
    }

    [Fact]
    public void AnyApplied_SomeTrue_ReturnsTrue()
    {
        // Arrange
        ChatHistoryMetric before = new() { MessageCount = 10 };
        ChatHistoryMetric after = new() { MessageCount = 5 };
        CompactionResult applied = new("Applied", applied: true, before, after);

        // Act
        CompactionPipelineResult result = new(before, after, [applied]);

        // Assert
        Assert.True(result.AnyApplied);
    }
}
