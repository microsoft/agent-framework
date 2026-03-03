// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class TruncationCompactionStrategyTests : CompactionStrategyTestBase
{
    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
        ];
        TruncationCompactionStrategy strategy = new(maxTokens: 100000);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task OverLimit_RemovesOldestGroupsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First message"),
            new(ChatRole.Assistant, "First reply"),
            new(ChatRole.User, "Second message"),
            new(ChatRole.Assistant, "Second reply"),
        ];
        TruncationCompactionStrategy strategy = new(maxTokens: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 1);
    }

    [Fact]
    public async Task SystemOnlyMessages_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
        ];
        TruncationCompactionStrategy strategy = new(maxTokens: 1);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task SingleNonSystemGroup_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "System prompt"),
            new(ChatRole.User, "Only user message"),
        ];
        TruncationCompactionStrategy strategy = new(maxTokens: 1);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task PreserveRecentGroups_KeepsMultipleGroupsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
            new(ChatRole.User, "Turn 3"),
            new(ChatRole.Assistant, "Reply 3"),
        ];
        TruncationCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 2);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 2);

        // Assert
        Assert.Equal("Reply 3", messages[^1].Text);
    }
}
