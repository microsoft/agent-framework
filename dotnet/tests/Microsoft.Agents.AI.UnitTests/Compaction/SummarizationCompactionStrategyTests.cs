// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
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
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System prompt."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — summary should be inserted after system, before preserved group
        CompactionMessageGroup summaryGroup = index.Groups.First(g => g.Kind == CompactionGroupKind.Summary);
        Assert.NotNull(summaryGroup);
        Assert.Contains("[Summary]", summaryGroup.Messages[0].Text);
        Assert.True(summaryGroup.Messages[0].AdditionalProperties!.ContainsKey(CompactionMessageGroup.SummaryPropertyKey));
    }

    [Fact]
    public async Task CompactAsyncHandlesEmptyLlmResponseAsync()
    {
        // Arrange — LLM returns whitespace
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("   "),
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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
            CompactionTriggers.Always,
            minimumPreservedGroups: 5);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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

        const string CustomPrompt = "Summarize in bullet points only.";
        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1,
            summarizationPrompt: CustomPrompt);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — the custom prompt should be the system message, followed by the original messages
        Assert.NotNull(capturedMessages);
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal(ChatRole.System, capturedMessages![0].Role);
        Assert.Equal(CustomPrompt, capturedMessages[0].Text);
        Assert.Equal(ChatRole.User, capturedMessages[1].Role);
        Assert.Equal("Q1", capturedMessages[1].Text);
    }

    [Fact]
    public async Task CompactAsyncSetsExcludeReasonAsync()
    {
        // Arrange
        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient(),
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Old"),
            new ChatMessage(ChatRole.User, "New"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert
        CompactionMessageGroup excluded = index.Groups.First(g => g.IsExcluded);
        Assert.NotNull(excluded.ExcludeReason);
        Assert.Contains("SummarizationCompactionStrategy", excluded.ExcludeReason);
    }

    [Fact]
    public async Task CompactAsyncTargetStopsMarkingEarlyAsync()
    {
        // Arrange — 4 non-system groups, preserve 1, target met after 1 exclusion
        int exclusionCount = 0;
        bool TargetAfterOne(CompactionMessageIndex _) => ++exclusionCount >= 1;

        SummarizationCompactionStrategy strategy = new(
            CreateMockChatClient("Partial summary."),
            CompactionTriggers.Always,
            minimumPreservedGroups: 1,
            target: TargetAfterOne);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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
            CompactionTriggers.Always,
            minimumPreservedGroups: 2);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
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

    [Fact]
    public async Task CompactAsyncWithSystemBetweenSummarizableGroupsAsync()
    {
        // Arrange — system group between user/assistant groups to exercise skip logic in loop
        IChatClient mockClient = CreateMockChatClient("[Summary]");
        SummarizationCompactionStrategy strategy = new(
            mockClient,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.System, "System note"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — summary inserted at 0, system group shifted to index 2
        Assert.True(result);
        Assert.Equal(CompactionGroupKind.Summary, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.System, index.Groups[2].Kind);
        Assert.False(index.Groups[2].IsExcluded); // System never excluded
    }

    [Fact]
    public async Task CompactAsyncMaxSummarizableBoundsLoopExitAsync()
    {
        // Arrange — large MinimumPreserved so maxSummarizable is small, target never stops
        IChatClient mockClient = CreateMockChatClient("[Summary]");
        SummarizationCompactionStrategy strategy = new(
            mockClient,
            CompactionTriggers.Always,
            minimumPreservedGroups: 3,
            target: _ => false);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
            new ChatMessage(ChatRole.Assistant, "A3"),
        ]);

        // Act — should only summarize 6-3 = 3 groups (not all 6)
        bool result = await strategy.CompactAsync(index);

        // Assert — 3 preserved + 1 summary = 4 included
        Assert.True(result);
        Assert.Equal(4, index.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncWithPreExcludedGroupAsync()
    {
        // Arrange — pre-exclude a group so the count and loop both must skip it
        IChatClient mockClient = CreateMockChatClient("[Summary]");
        SummarizationCompactionStrategy strategy = new(
            mockClient,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);
        index.Groups[0].IsExcluded = true; // Pre-exclude Q1

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);
        Assert.True(index.Groups[0].IsExcluded); // Still excluded
    }

    [Fact]
    public async Task CompactAsyncWithEmptyTextMessageInGroupAsync()
    {
        // Arrange — a message with null text (FunctionCallContent) in a summarized group
        IChatClient mockClient = CreateMockChatClient("[Summary]");
        SummarizationCompactionStrategy strategy = new(
            mockClient,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ];

        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Act — the tool-call group's message has null text
        bool result = await strategy.CompactAsync(index);

        // Assert — compaction succeeded despite null text
        Assert.True(result);
    }

    #region Error resilience

    [Fact]
    public async Task CompactAsyncLlmFailureRestoresGroupsAsync()
    {
        // Arrange — chat client throws a non-cancellation exception
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Service unavailable"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        int originalGroupCount = index.Groups.Count;

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — returns false, all groups restored to non-excluded
        Assert.False(result);
        Assert.Equal(originalGroupCount, index.Groups.Count);
        Assert.All(index.Groups, g => Assert.False(g.IsExcluded));
        Assert.All(index.Groups, g => Assert.Null(g.ExcludeReason));
    }

    [Fact]
    public async Task CompactAsyncLlmFailurePreservesAllOriginalMessagesAsync()
    {
        // Arrange — verify that after failure, GetIncludedMessages returns all original messages
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new HttpRequestException("Timeout"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        List<ChatMessage> originalIncluded = [.. index.GetIncludedMessages()];

        // Act
        await strategy.CompactAsync(index);

        // Assert — all original messages still included
        List<ChatMessage> afterIncluded = [.. index.GetIncludedMessages()];
        Assert.Equal(originalIncluded.Count, afterIncluded.Count);
        for (int i = 0; i < originalIncluded.Count; i++)
        {
            Assert.Same(originalIncluded[i], afterIncluded[i]);
        }
    }

    [Fact]
    public async Task CompactAsyncLlmFailureDoesNotInsertSummaryGroupAsync()
    {
        // Arrange
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("API error"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — no Summary group was inserted
        Assert.DoesNotContain(index.Groups, g => g.Kind == CompactionGroupKind.Summary);
    }

    [Fact]
    public async Task CompactAsyncCancellationPropagatesAsync()
    {
        // Arrange — OperationCanceledException should NOT be caught
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException("Cancelled"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act & Assert — OperationCanceledException propagates
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => strategy.CompactAsync(index).AsTask());
    }

    [Fact]
    public async Task CompactAsyncTaskCancellationPropagatesAsync()
    {
        // Arrange — TaskCanceledException (subclass of OperationCanceledException) should also propagate
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new TaskCanceledException("Task cancelled"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act & Assert — TaskCanceledException propagates (inherits from OperationCanceledException)
        await Assert.ThrowsAsync<TaskCanceledException>(
            () => strategy.CompactAsync(index).AsTask());
    }

    [Fact]
    public async Task CompactAsyncLlmFailureWithMultipleExcludedGroupsRestoresAllAsync()
    {
        // Arrange — multiple groups excluded before failure, all must be restored
        Mock<IChatClient> mockClient = new();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Rate limited"));

        SummarizationCompactionStrategy strategy = new(
            mockClient.Object,
            CompactionTriggers.Always,
            minimumPreservedGroups: 1,
            target: _ => false); // Never stop — exclude as many as possible

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System prompt"),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — all non-system groups restored
        Assert.False(result);
        Assert.All(index.Groups, g => Assert.False(g.IsExcluded));
        Assert.All(index.Groups, g => Assert.Null(g.ExcludeReason));
        Assert.Equal(6, index.IncludedGroupCount);
    }

    #endregion
}
