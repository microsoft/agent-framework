// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class SlidingWindowCompactionStrategyTests : CompactionStrategyTestBase
{
    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 10);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task KeepsLastNTurnsAsync()
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
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 2);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 4);

        // Assert
        Assert.Equal("Turn 2", messages[0].Text);
        Assert.Equal("Reply 2", messages[1].Text);
        Assert.Equal("Turn 3", messages[2].Text);
        Assert.Equal("Reply 3", messages[3].Text);
    }

    [Fact]
    public async Task PreservesSystemMessagesAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 3);

        // Assert
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
        Assert.Equal("Turn 2", messages[1].Text);
        Assert.Equal("Reply 2", messages[2].Text);
    }

    [Fact]
    public async Task PreservesToolGroupsWithinKeptTurnsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Get weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.Assistant, "It's sunny!"),
        ];
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 4);

        // Assert
        Assert.Equal("Get weather", messages[0].Text);
    }

    [Fact]
    public async Task SingleTurn_AtLimit_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task DropsResponseGroupsFromOldTurnsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Turn 1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "search")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "result")]),
            new(ChatRole.Assistant, "Here's what I found"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        SlidingWindowCompactionStrategy strategy = new(maxTurns: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 2);

        // Assert
        Assert.Equal("Turn 2", messages[0].Text);
        Assert.Equal("Reply 2", messages[1].Text);
    }
}
