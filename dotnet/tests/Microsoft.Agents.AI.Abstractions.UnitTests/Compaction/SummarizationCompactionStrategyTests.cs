// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class SummarizationCompactionStrategyTests : CompactionStrategyTestBase
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
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 100000);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);

        // Assert
        chatClientMock.Verify(
            c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task SummarizesOldGroupsAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "What's the weather?"),
            new(ChatRole.Assistant, "The weather is sunny and 72°F."),
            new(ChatRole.User, "How about tomorrow?"),
            new(ChatRole.Assistant, "Tomorrow will be cloudy."),
            new(ChatRole.User, "Thanks!"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "User asked about weather. It was sunny.")));
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 2);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 3);

        // Assert
        Assert.Contains("[Summary]", messages[0].Text);
        Assert.Contains("sunny", messages[0].Text);
        Assert.Equal("Thanks!", messages[1].Text);
        Assert.Equal("You're welcome!", messages[2].Text);
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
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Summary of earlier discussion.")));
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 3);

        // Assert
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
        Assert.Contains("[Summary]", messages[1].Text);
    }

    [Fact]
    public async Task AllGroupsProtected_NoChangeAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 10);

        // Act & Assert
        await RunCompactionStrategySkippedAsync(strategy, messages);

        // Assert
        chatClientMock.Verify(
            c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task CustomPrompt_UsedInRequestAsync()
    {
        // Arrange
        const string CustomPrompt = "Summarize briefly.";
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.Assistant, "Reply"),
            new(ChatRole.User, "Second"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        List<ChatMessage>? capturedMessages = null;
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, _, _) => capturedMessages = [.. msgs])
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Brief summary.")));
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1, summarizationPrompt: CustomPrompt);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 2);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Equal(ChatRole.System, capturedMessages![0].Role);
        Assert.Equal(CustomPrompt, capturedMessages[0].Text);
    }

    [Fact]
    public async Task NullResponseText_UsesFallbackAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.Assistant, "Reply"),
            new(ChatRole.User, "Second"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, (string?)null)));
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1);

        // Act & Assert
        await RunCompactionStrategyReducedAsync(strategy, messages, expectedCount: 2);

        // Assert
        Assert.Contains("[Summary unavailable]", messages[0].Text);
    }
}
