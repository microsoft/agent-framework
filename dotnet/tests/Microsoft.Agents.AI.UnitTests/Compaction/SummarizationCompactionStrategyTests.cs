// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="SummarizationCompactionStrategy"/> class.
/// </summary>
public class SummarizationCompactionStrategyTests
{
    private static readonly CompactionTrigger AlwaysTrigger = _ => true;

    /// <summary>
    /// Creates a mock <see cref="IChatClient"/> that returns the specified summary text.
    /// </summary>
    private static IChatClient CreateMockChatClient(string summaryText = "Summary of conversation.")
    {
        Mock<IChatClient> mock = new();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, summaryText)]));
        return mock.Object;
    }

    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger requires > 100000 tokens
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient(),
            CompactionTriggers.TokensExceed(100000),
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(2, index.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncSummarizesOldGroupsAsync()
    {
        // Arrange — always trigger, preserve 1 recent group
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("Key facts from earlier."),
            AlwaysTrigger,
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First question"),
            new ChatMessage(ChatRole.Assistant, "First answer"),
            new ChatMessage(ChatRole.User, "Second question"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);

        List<ChatMessage> included = [.. index.GetIncludedMessages()];

        // Should have: summary + preserved recent group (Second question)
        Assert.Equal(2, included.Count);
        Assert.Contains("[Summary]", included[0].Text);
        Assert.Contains("Key facts from earlier.", included[0].Text);
        Assert.Equal("Second question", included[1].Text);
    }

    [Fact]
    public async Task CompactAsyncPreservesSystemMessagesAsync()
    {
        // Arrange
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient(),
            AlwaysTrigger,
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Old question"),
            new ChatMessage(ChatRole.Assistant, "Old answer"),
            new ChatMessage(ChatRole.User, "Recent question"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert
        List<ChatMessage> included = [.. index.GetIncludedMessages()];

        Assert.Equal("You are helpful.", included[0].Text);
        Assert.Equal(ChatRole.System, included[0].Role);
    }

    [Fact]
    public async Task CompactAsyncInsertsSummaryGroupAtCorrectPositionAsync()
    {
        // Arrange
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("Summary text."),
            AlwaysTrigger,
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System prompt."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — summary should be inserted after system, before preserved group
        MessageGroup summaryGroup = index.Groups.First(g => g.Kind == MessageGroupKind.Summary);
        Assert.NotNull(summaryGroup);
        Assert.Contains("[Summary]", summaryGroup.Messages[0].Text);
        Assert.True(summaryGroup.Messages[0].AdditionalProperties!.ContainsKey(MessageGroup.SummaryPropertyKey));
    }

    [Fact]
    public async Task CompactAsyncHandlesEmptyLlmResponseAsync()
    {
        // Arrange — LLM returns whitespace
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("   "),
            AlwaysTrigger,
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — should use fallback text
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Contains("[Summary unavailable]", included[0].Text);
    }

    [Fact]
    public async Task CompactAsyncNothingToSummarizeReturnsFalseAsync()
    {
        // Arrange — preserve 5 but only 2 non-system groups
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient(),
            AlwaysTrigger,
            minimumPreserved: 5);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncUsesCustomPromptAsync()
    {
        // Arrange — capture the messages sent to the chat client
        List<ChatMessage>? capturedMessages = null;
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) =>
                capturedMessages = [.. msgs])
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Custom summary.")]));

        const string customPrompt = "Summarize in bullet points only.";
        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            AlwaysTrigger,
            minimumPreserved: 1,
            summarizationPrompt: customPrompt);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — the custom prompt should be the first message sent to the LLM
        Assert.NotNull(capturedMessages);
        Assert.Equal(customPrompt, capturedMessages![0].Text);
    }

    [Fact]
    public async Task CompactAsyncSetsExcludeReasonAsync()
    {
        // Arrange
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient(),
            AlwaysTrigger,
            minimumPreserved: 1);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Old"),
            new ChatMessage(ChatRole.User, "New"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert
        MessageGroup excluded = index.Groups.First(g => g.IsExcluded);
        Assert.NotNull(excluded.ExcludeReason);
        Assert.Contains("SummarizationCompactionStrategy", excluded.ExcludeReason);
    }

    [Fact]
    public async Task CompactAsyncTargetStopsMarkingEarlyAsync()
    {
        // Arrange — 4 non-system groups, preserve 1, target met after 1 exclusion
        int exclusionCount = 0;
        CompactionTrigger targetAfterOne = _ => ++exclusionCount >= 1;

        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("Partial summary."),
            AlwaysTrigger,
            minimumPreserved: 1,
            target: targetAfterOne);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — only 1 group should have been summarized (target met after first exclusion)
        int excludedCount = index.Groups.Count(g => g.IsExcluded);
        Assert.Equal(1, excludedCount);
    }

    [Fact]
    public async Task CompactAsyncPreservesMultipleRecentGroupsAsync()
    {
        // Arrange — preserve 2
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("Summary."),
            AlwaysTrigger,
            minimumPreserved: 2);

        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — 2 oldest excluded, 2 newest preserved + 1 summary inserted
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(3, included.Count); // summary + Q2 + A2
        Assert.Contains("[Summary]", included[0].Text);
        Assert.Equal("Q2", included[1].Text);
        Assert.Equal("A2", included[2].Text);
    }
}
