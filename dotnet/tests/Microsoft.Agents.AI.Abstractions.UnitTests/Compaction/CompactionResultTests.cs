// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Compaction;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class CompactionResultTests
{
    [Fact]
    public void Skipped_HasSameBeforeAndAfter()
    {
        // Arrange
        ChatHistoryMetric metrics = new() { MessageCount = 5, TokenCount = 100 };

        // Act
        CompactionResult result = CompactionResult.Skipped("Test", metrics);

        // Assert
        Assert.Equal("Test", result.StrategyName);
        Assert.False(result.Applied);
        Assert.Same(metrics, result.Before);
        Assert.Same(metrics, result.After);
    }
}
