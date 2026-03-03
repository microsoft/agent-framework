// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class ToolResultCompactionStrategyTests : CompactionStrategyTestBase
{
    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 100000);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task CollapsesOldToolGroupAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny, 72°F")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 4);

        // Assert
        Assert.Contains("[Tool calls: get_weather]", messages[1].Text);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
    }

    [Fact]
    public async Task ProtectsRecentGroupsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 10);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }

    [Fact]
    public async Task PreservesSystemMessagesAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Check weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.User, "Thanks"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 5);

        // Assert
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
    }

    [Fact]
    public async Task MultipleToolCalls_ListedInSummaryAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Do research"),
            new ChatMessage(ChatRole.Assistant, [
                new FunctionCallContent("c1", "search"),
                new FunctionCallContent("c2", "fetch_page"),
            ]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "results...")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c2", "page content...")]),
            new(ChatRole.User, "Summarize"),
            new(ChatRole.Assistant, "Here's the summary."),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 1, preserveRecentGroups: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 4);

        // Assert
        Assert.Contains("search", messages[1].Text);
        Assert.Contains("fetch_page", messages[1].Text);
    }

    [Fact]
    public async Task NoToolGroups_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there"),
        ];
        ToolResultCompactionStrategy strategy = new(maxTokens: 1);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);
    }
}
