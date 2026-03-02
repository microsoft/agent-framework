// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

using Microsoft.Agents.AI.Compaction;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class CompactionPipelineResultTests
{
    [Fact]
    public void Properties_AreReadable()
    {
        CompactionMetric before = new() { MessageCount = 10 };
        CompactionMetric after = new() { MessageCount = 5 };
        CompactionResult strategyResult = new("Test", applied: true, before, after);
        List<CompactionResult> results = [strategyResult];

        CompactionPipelineResult pipelineResult = new(before, after, results);

        Assert.Same(before, pipelineResult.Before);
        Assert.Same(after, pipelineResult.After);
        Assert.Single(pipelineResult.StrategyResults);
    }

    [Fact]
    public void AnyApplied_AllFalse_ReturnsFalse()
    {
        CompactionMetric metrics = new() { MessageCount = 5 };
        CompactionResult skipped = CompactionResult.Skipped("Skip", metrics);
        CompactionPipelineResult result = new(metrics, metrics, [skipped]);

        Assert.False(result.AnyApplied);
    }

    [Fact]
    public void AnyApplied_SomeTrue_ReturnsTrue()
    {
        CompactionMetric before = new() { MessageCount = 10 };
        CompactionMetric after = new() { MessageCount = 5 };
        CompactionResult applied = new("Applied", applied: true, before, after);
        CompactionPipelineResult result = new(before, after, [applied]);

        Assert.True(result.AnyApplied);
    }
}
