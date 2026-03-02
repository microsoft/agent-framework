// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class SummarizationCompactionStrategyTests
{
    [Fact]
    public void ShouldCompact_UnderLimit_ReturnsFalse()
    {
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 100000);
        CompactionMetric metrics = new() { TokenCount = 500 };

        Assert.False(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public void ShouldCompact_OverLimit_ReturnsTrue()
    {
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 100);
        CompactionMetric metrics = new() { TokenCount = 500 };

        Assert.True(strategy.ShouldCompact(metrics));
    }

    [Fact]
    public async Task UnderLimit_NoChangeAsync()
    {
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 100000);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.False(result.Applied);
        Assert.Equal(2, messages.Count);
        chatClientMock.Verify(
            c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task SummarizesOldGroupsAsync()
    {
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "User asked about weather. It was sunny.")));

        // preserveRecentGroups=2 means keep last 2 non-system groups
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 2);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "What's the weather?"),
            new(ChatRole.Assistant, "The weather is sunny and 72°F."),
            new(ChatRole.User, "How about tomorrow?"),
            new(ChatRole.Assistant, "Tomorrow will be cloudy."),
            new(ChatRole.User, "Thanks!"),
            new(ChatRole.Assistant, "You're welcome!"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        // 6 groups (3 user + 3 assistant), protect last 2 → summarize first 4 groups
        // Result: summary + 2 protected groups = 3 messages
        Assert.Equal(3, messages.Count);
        Assert.Contains("[Summary]", messages[0].Text);
        Assert.Contains("sunny", messages[0].Text);
        Assert.Equal("Thanks!", messages[1].Text);
        Assert.Equal("You're welcome!", messages[2].Text);
    }

    [Fact]
    public async Task PreservesSystemMessagesAsync()
    {
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Summary of earlier discussion.")));

        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Turn 1"),
            new(ChatRole.Assistant, "Reply 1"),
            new(ChatRole.User, "Turn 2"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal("You are a helper", messages[0].Text);
        Assert.Contains("[Summary]", messages[1].Text);
    }

    [Fact]
    public async Task AllGroupsProtected_NoChangeAsync()
    {
        Mock<IChatClient> chatClientMock = new();
        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 10);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        // All groups protected → nothing to summarize → no change
        Assert.False(result.Applied);
        Assert.Equal(2, messages.Count);
        chatClientMock.Verify(
            c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task CustomPrompt_UsedInRequestAsync()
    {
        const string CustomPrompt = "Summarize briefly.";
        List<ChatMessage>? capturedMessages = null;

        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, _, _) => capturedMessages = [.. msgs])
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Brief summary.")));

        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1, summarizationPrompt: CustomPrompt);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.Assistant, "Reply"),
            new(ChatRole.User, "Second"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        await strategy.CompactAsync(messages, calculator);

        Assert.NotNull(capturedMessages);
        // First message in request should be the custom system prompt
        Assert.Equal(ChatRole.System, capturedMessages![0].Role);
        Assert.Equal(CustomPrompt, capturedMessages[0].Text);
    }

    [Fact]
    public async Task NullResponseText_UsesFallbackAsync()
    {
        Mock<IChatClient> chatClientMock = new();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, (string?)null)));

        SummarizationCompactionStrategy strategy = new(chatClientMock.Object, maxTokens: 1, preserveRecentGroups: 1);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.Assistant, "Reply"),
            new(ChatRole.User, "Second"),
            new(ChatRole.Assistant, "Reply 2"),
        ];
        DefaultChatHistoryMetricsCalculator calculator = new();

        CompactionResult result = await strategy.CompactAsync(messages, calculator);

        Assert.True(result.Applied);
        Assert.Contains("[Summary unavailable]", messages[0].Text);
    }
}
