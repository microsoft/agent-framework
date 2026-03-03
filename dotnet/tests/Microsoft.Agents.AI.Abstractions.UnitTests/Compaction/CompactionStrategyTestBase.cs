// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public abstract class CompactionStrategyTestBase
{
    public static async ValueTask<CompactionResult> RunCompactionStrategyReducedAsync(ChatHistoryCompactionStrategy strategy, List<ChatMessage> messages, int expectedCount)
    {
        // Act
        ChatHistoryCompactionStrategy.s_currentMetrics.Value = DefaultChatHistoryMetricsCalculator.Instance.Calculate(messages);
        CompactionResult result = await strategy.CompactAsync(messages, DefaultChatHistoryMetricsCalculator.Instance);

        // Assert
        Assert.True(result.Applied);
        Assert.NotEqual(result.Before, result.After);
        Assert.Equal(expectedCount, messages.Count);

        return result;
    }

    public static async ValueTask<CompactionResult> RunCompactionStrategySkippedAsync(ChatHistoryCompactionStrategy strategy, List<ChatMessage> messages)
    {
        // Act
        int initialCount = messages.Count;
        ChatHistoryCompactionStrategy.s_currentMetrics.Value = DefaultChatHistoryMetricsCalculator.Instance.Calculate(messages);
        CompactionResult result = await strategy.CompactAsync(messages, DefaultChatHistoryMetricsCalculator.Instance);

        // Assert
        Assert.False(result.Applied);
        Assert.Equal(result.Before, result.After);
        Assert.Equal(initialCount, messages.Count);

        return result;
    }
}
