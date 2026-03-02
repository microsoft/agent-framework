// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Compaction;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class CompactionMetricTests
{
    [Fact]
    public void DefaultValues_AreZero()
    {
        CompactionMetric metrics = new();
        Assert.Equal(0, metrics.TokenCount);
        Assert.Equal(0L, metrics.ByteCount);
        Assert.Equal(0, metrics.MessageCount);
        Assert.Equal(0, metrics.ToolCallCount);
        Assert.Equal(0, metrics.UserTurnCount);
        Assert.Empty(metrics.Groups);
    }

    [Fact]
    public void InitProperties_SetCorrectly()
    {
        CompactionMetric metrics = new()
        {
            TokenCount = 100,
            ByteCount = 500,
            MessageCount = 5,
            ToolCallCount = 2,
            UserTurnCount = 3
        };

        Assert.Equal(100, metrics.TokenCount);
        Assert.Equal(500L, metrics.ByteCount);
        Assert.Equal(5, metrics.MessageCount);
        Assert.Equal(2, metrics.ToolCallCount);
        Assert.Equal(3, metrics.UserTurnCount);
    }
}
