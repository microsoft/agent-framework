// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.ML.Tokenizers;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="CompactionMessageIndex"/> class.
/// </summary>
public class CompactionMessageIndexTests
{
    [Fact]
    public void CreateEmptyListReturnsEmptyGroups()
    {
        // Arrange
        List<ChatMessage> messages = [];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Empty(groups.Groups);
    }

    [Fact]
    public void CreateSystemMessageCreatesSystemGroup()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
        ];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.System, groups.Groups[0].Kind);
        Assert.Single(groups.Groups[0].Messages);
    }

    [Fact]
    public void CreateUserMessageCreatesUserGroup()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.User, groups.Groups[0].Kind);
    }

    [Fact]
    public void CreateAssistantTextMessageCreatesAssistantTextGroup()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, "Hi there!"),
        ];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, groups.Groups[0].Kind);
    }

    [Fact]
    public void CreateToolCallWithResultsCreatesAtomicGroup()
    {
        // Arrange
        ChatMessage assistantMessage = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("call1", "Sunny, 72°F")]);

        List<ChatMessage> messages = [assistantMessage, toolResult];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(2, groups.Groups[0].Messages.Count);
        Assert.Same(assistantMessage, groups.Groups[0].Messages[0]);
        Assert.Same(toolResult, groups.Groups[0].Messages[1]);
    }

    [Fact]
    public void CreateToolCallWithTextCreatesAtomicGroup()
    {
        // Arrange
        ChatMessage assistantMessage = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]);
        ChatMessage toolResult = new(ChatRole.Tool, [new TextContent("Sunny, 72°F"), new FunctionResultContent("call1", "Sunny, 72°F")]);

        List<ChatMessage> messages = [assistantMessage, toolResult];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(2, groups.Groups[0].Messages.Count);
        Assert.Same(assistantMessage, groups.Groups[0].Messages[0]);
        Assert.Same(toolResult, groups.Groups[0].Messages[1]);
    }

    [Fact]
    public void CreateMixedConversationGroupsCorrectly()
    {
        // Arrange
        ChatMessage systemMsg = new(ChatRole.System, "You are helpful.");
        ChatMessage userMsg = new(ChatRole.User, "What's the weather?");
        ChatMessage assistantToolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");
        ChatMessage assistantText = new(ChatRole.Assistant, "The weather is sunny!");

        List<ChatMessage> messages = [systemMsg, userMsg, assistantToolCall, toolResult, assistantText];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Equal(4, groups.Groups.Count);
        Assert.Equal(CompactionGroupKind.System, groups.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.User, groups.Groups[1].Kind);
        Assert.Equal(CompactionGroupKind.ToolCall, groups.Groups[2].Kind);
        Assert.Equal(2, groups.Groups[2].Messages.Count);
        Assert.Equal(CompactionGroupKind.AssistantText, groups.Groups[3].Kind);
    }

    [Fact]
    public void CreateMultipleToolResultsGroupsAllWithAssistant()
    {
        // Arrange
        ChatMessage assistantToolCall = new(ChatRole.Assistant, [
            new FunctionCallContent("call1", "get_weather"),
            new FunctionCallContent("call2", "get_time"),
        ]);
        ChatMessage toolResult1 = new(ChatRole.Tool, "Sunny");
        ChatMessage toolResult2 = new(ChatRole.Tool, "3:00 PM");

        List<ChatMessage> messages = [assistantToolCall, toolResult1, toolResult2];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(3, groups.Groups[0].Messages.Count);
    }

    [Fact]
    public void GetIncludedMessagesExcludesMarkedGroups()
    {
        // Arrange
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response");
        ChatMessage msg3 = new(ChatRole.User, "Second");

        CompactionMessageIndex groups = CompactionMessageIndex.Create([msg1, msg2, msg3]);
        groups.Groups[1].IsExcluded = true;

        // Act
        List<ChatMessage> included = [.. groups.GetIncludedMessages()];

        // Assert
        Assert.Equal(2, included.Count);
        Assert.Same(msg1, included[0]);
        Assert.Same(msg3, included[1]);
    }

    [Fact]
    public void GetAllMessagesIncludesExcludedGroups()
    {
        // Arrange
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response");

        CompactionMessageIndex groups = CompactionMessageIndex.Create([msg1, msg2]);
        groups.Groups[0].IsExcluded = true;

        // Act
        List<ChatMessage> all = [.. groups.GetAllMessages()];

        // Assert
        Assert.Equal(2, all.Count);
    }

    [Fact]
    public void IncludedGroupCountReflectsExclusions()
    {
        // Arrange
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
        ]);

        groups.Groups[1].IsExcluded = true;

        // Act & Assert
        Assert.Equal(2, groups.IncludedGroupCount);
        Assert.Equal(2, groups.IncludedMessageCount);
    }

    [Fact]
    public void CreateSummaryMessageCreatesSummaryGroup()
    {
        // Arrange
        ChatMessage summaryMessage = new(ChatRole.Assistant, "[Summary of earlier conversation]: key facts...");
        (summaryMessage.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;

        List<ChatMessage> messages = [summaryMessage];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(CompactionGroupKind.Summary, groups.Groups[0].Kind);
        Assert.Same(summaryMessage, groups.Groups[0].Messages[0]);
    }

    [Fact]
    public void CreateSummaryAmongOtherMessagesGroupsCorrectly()
    {
        // Arrange
        ChatMessage systemMsg = new(ChatRole.System, "You are helpful.");
        ChatMessage summaryMsg = new(ChatRole.Assistant, "[Summary]: previous context");
        (summaryMsg.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;
        ChatMessage userMsg = new(ChatRole.User, "Continue...");

        List<ChatMessage> messages = [systemMsg, summaryMsg, userMsg];

        // Act
        CompactionMessageIndex groups = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Equal(3, groups.Groups.Count);
        Assert.Equal(CompactionGroupKind.System, groups.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.Summary, groups.Groups[1].Kind);
        Assert.Equal(CompactionGroupKind.User, groups.Groups[2].Kind);
    }

    [Fact]
    public void MessageGroupStoresPassedCounts()
    {
        // Arrange & Act
        CompactionMessageGroup group = new(CompactionGroupKind.User, [new ChatMessage(ChatRole.User, "Hello")], byteCount: 5, tokenCount: 2);

        // Assert
        Assert.Equal(1, group.MessageCount);
        Assert.Equal(5, group.ByteCount);
        Assert.Equal(2, group.TokenCount);
    }

    [Fact]
    public void MessageGroupMessagesAreImmutable()
    {
        // Arrange
        IReadOnlyList<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];
        CompactionMessageGroup group = new(CompactionGroupKind.User, messages, byteCount: 5, tokenCount: 1);

        // Assert — Messages is IReadOnlyList, not IList
        Assert.IsType<IReadOnlyList<ChatMessage>>(group.Messages, exactMatch: false);
        Assert.Same(messages, group.Messages);
    }

    [Fact]
    public void CreateComputesByteCountUtf8()
    {
        // Arrange — "Hello" is 5 UTF-8 bytes
        CompactionMessageIndex groups = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void CreateComputesByteCountMultiByteChars()
    {
        // Arrange — "café" has a multi-byte 'é' (2 bytes in UTF-8) → 5 bytes total
        CompactionMessageIndex groups = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "café")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void CreateComputesByteCountMultipleMessagesInGroup()
    {
        // Arrange — ToolCall group: assistant (tool call) + tool result "OK" (2 bytes)
        ChatMessage assistantMsg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, "OK");
        CompactionMessageIndex groups = CompactionMessageIndex.Create([assistantMsg, toolResult]);

        // Assert — single ToolCall group with 2 messages
        Assert.Single(groups.Groups);
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(9, groups.Groups[0].ByteCount); // FunctionCallContent: "call1" (5) + "fn" (2) = 7, "OK" = 2 → 9 total
    }

    [Fact]
    public void CreateDefaultTokenCountIsHeuristic()
    {
        // Arrange — "Hello world test data!" = 22 UTF-8 bytes → 22 / 4 = 5 estimated tokens
        CompactionMessageIndex groups = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world test data!")]);

        // Assert
        Assert.Equal(22, groups.Groups[0].ByteCount);
        Assert.Equal(22 / 4, groups.Groups[0].TokenCount);
    }

    [Fact]
    public void CreateNonTextContentHasAccurateCounts()
    {
        // Arrange — message with pure function call (no text)
        ChatMessage msg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage tool = new(ChatRole.Tool, string.Empty);
        CompactionMessageIndex groups = CompactionMessageIndex.Create([msg, tool]);

        // Assert — FunctionCallContent: "call1" (5) + "get_weather" (11) = 16 bytes
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(16, groups.Groups[0].ByteCount);
        Assert.Equal(4, groups.Groups[0].TokenCount); // 16 / 4 = 4 estimated tokens
    }

    [Fact]
    public void TotalAggregatesSumAllGroups()
    {
        // Arrange
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "AAAA"),       // 4 bytes
            new ChatMessage(ChatRole.Assistant, "BBBB"),   // 4 bytes
        ]);

        groups.Groups[0].IsExcluded = true;

        // Act & Assert — totals include excluded groups
        Assert.Equal(2, groups.TotalGroupCount);
        Assert.Equal(2, groups.TotalMessageCount);
        Assert.Equal(8, groups.TotalByteCount);
        Assert.Equal(2, groups.TotalTokenCount); // Each group: 4 bytes / 4 = 1 token, 2 groups = 2
    }

    [Fact]
    public void IncludedAggregatesExcludeMarkedGroups()
    {
        // Arrange
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "AAAA"),       // 4 bytes
            new ChatMessage(ChatRole.Assistant, "BBBB"),   // 4 bytes
            new ChatMessage(ChatRole.User, "CCCC"),       // 4 bytes
        ]);

        groups.Groups[0].IsExcluded = true;

        // Act & Assert
        Assert.Equal(3, groups.TotalGroupCount);
        Assert.Equal(2, groups.IncludedGroupCount);
        Assert.Equal(3, groups.TotalMessageCount);
        Assert.Equal(2, groups.IncludedMessageCount);
        Assert.Equal(12, groups.TotalByteCount);
        Assert.Equal(8, groups.IncludedByteCount);
        Assert.Equal(3, groups.TotalTokenCount);  // 12 / 4 = 3 (across 3 groups of 4 bytes each = 1+1+1)
        Assert.Equal(2, groups.IncludedTokenCount); // 8 / 4 = 2 (2 included groups of 4 bytes = 1+1)
    }

    [Fact]
    public void ToolCallGroupAggregatesAcrossMessages()
    {
        // Arrange — tool call group with FunctionCallContent + tool result "OK" (2 bytes)
        ChatMessage assistantMsg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, "OK");

        CompactionMessageIndex groups = CompactionMessageIndex.Create([assistantMsg, toolResult]);

        // Assert — single group with 2 messages
        Assert.Single(groups.Groups);
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(9, groups.Groups[0].ByteCount); // FunctionCallContent: "call1" (5) + "fn" (2) = 7, "OK" = 2 → 9 total
        Assert.Equal(1, groups.TotalGroupCount);
        Assert.Equal(2, groups.TotalMessageCount);
    }

    [Fact]
    public void CreateAssignsTurnIndicesSingleTurn()
    {
        // Arrange — System (no turn), User + Assistant = turn 1
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Assert
        Assert.Null(groups.Groups[0].TurnIndex);   // System
        Assert.Equal(1, groups.Groups[1].TurnIndex); // User
        Assert.Equal(1, groups.Groups[2].TurnIndex); // Assistant
        Assert.Equal(1, groups.TotalTurnCount);
        Assert.Equal(1, groups.IncludedTurnCount);
    }

    [Fact]
    public void CreateAssignsTurnIndicesMultiTurn()
    {
        // Arrange — 3 user turns
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System prompt."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // Assert — 6 groups: System(null), User(1), Assistant(1), User(2), Assistant(2), User(3)
        Assert.Null(groups.Groups[0].TurnIndex);
        Assert.Equal(1, groups.Groups[1].TurnIndex);
        Assert.Equal(1, groups.Groups[2].TurnIndex);
        Assert.Equal(2, groups.Groups[3].TurnIndex);
        Assert.Equal(2, groups.Groups[4].TurnIndex);
        Assert.Equal(3, groups.Groups[5].TurnIndex);
        Assert.Equal(3, groups.TotalTurnCount);
    }

    [Fact]
    public void CreateTurnSpansToolCallGroups()
    {
        // Arrange — turn 1 includes User, ToolCall, AssistantText
        ChatMessage assistantToolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");

        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "What's the weather?"),
            assistantToolCall,
            toolResult,
            new ChatMessage(ChatRole.Assistant, "The weather is sunny!"),
        ]);

        // Assert — all 3 groups belong to turn 1
        Assert.Equal(3, groups.Groups.Count);
        Assert.Equal(1, groups.Groups[0].TurnIndex); // User
        Assert.Equal(1, groups.Groups[1].TurnIndex); // ToolCall
        Assert.Equal(1, groups.Groups[2].TurnIndex); // AssistantText
        Assert.Equal(1, groups.TotalTurnCount);
    }

    [Fact]
    public void GetTurnGroupsReturnsGroupsForSpecificTurn()
    {
        // Arrange
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        List<CompactionMessageGroup> turn1 = [.. groups.GetTurnGroups(1)];
        List<CompactionMessageGroup> turn2 = [.. groups.GetTurnGroups(2)];

        // Assert
        Assert.Equal(2, turn1.Count);
        Assert.Equal(CompactionGroupKind.User, turn1[0].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, turn1[1].Kind);
        Assert.Equal(2, turn2.Count);
        Assert.Equal(CompactionGroupKind.User, turn2[0].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, turn2[1].Kind);
    }

    [Fact]
    public void IncludedTurnCountReflectsExclusions()
    {
        // Arrange — 2 turns, exclude all groups in turn 1
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        groups.Groups[0].IsExcluded = true; // User Q1 (turn 1)
        groups.Groups[1].IsExcluded = true; // Assistant A1 (turn 1)

        // Assert
        Assert.Equal(2, groups.TotalTurnCount);
        Assert.Equal(1, groups.IncludedTurnCount); // Only turn 2 has included groups
    }

    [Fact]
    public void TotalTurnCountZeroWhenNoUserMessages()
    {
        // Arrange — only system messages
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System."),
        ]);

        // Assert
        Assert.Equal(0, groups.TotalTurnCount);
        Assert.Equal(0, groups.IncludedTurnCount);
    }

    [Fact]
    public void IncludedTurnCountPartialExclusionStillCountsTurn()
    {
        // Arrange — turn 1 has 2 groups, only one excluded
        CompactionMessageIndex groups = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ]);

        groups.Groups[1].IsExcluded = true; // Exclude assistant but user is still included

        // Assert — turn 1 still has one included group
        Assert.Equal(1, groups.TotalTurnCount);
        Assert.Equal(1, groups.IncludedTurnCount);
    }

    [Fact]
    public void UpdateAppendsNewMessagesIncrementally()
    {
        // Arrange — create with 2 messages
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(2, index.RawMessageCount);

        // Act — add 2 more messages and update
        messages.Add(new ChatMessage(ChatRole.User, "Q2"));
        messages.Add(new ChatMessage(ChatRole.Assistant, "A2"));
        index.Update(messages);

        // Assert — should have 4 groups total, processed count updated
        Assert.Equal(4, index.Groups.Count);
        Assert.Equal(4, index.RawMessageCount);
        Assert.Equal(CompactionGroupKind.User, index.Groups[2].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[3].Kind);
    }

    [Fact]
    public void UpdateNoOpWhenNoNewMessages()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        int originalCount = index.Groups.Count;

        // Act — update with same count
        index.Update(messages);

        // Assert — nothing changed
        Assert.Equal(originalCount, index.Groups.Count);
    }

    [Fact]
    public void UpdateRebuildsWhenMessagesShrink()
    {
        // Arrange — create with 3 messages
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        Assert.Equal(3, index.Groups.Count);

        // Exclude a group to verify rebuild clears state
        index.Groups[0].IsExcluded = true;

        // Act — update with fewer messages (simulates storage compaction)
        List<ChatMessage> shortened =
        [
            new ChatMessage(ChatRole.User, "Q2"),
        ];
        index.Update(shortened);

        // Assert — rebuilt from scratch
        Assert.Single(index.Groups);
        Assert.False(index.Groups[0].IsExcluded);
        Assert.Equal(1, index.RawMessageCount);
    }

    [Fact]
    public void UpdateWithEmptyListClearsGroups()
    {
        // Arrange — create with messages
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        Assert.Equal(2, index.Groups.Count);

        // Act — update with empty list
        index.Update([]);

        // Assert — fully cleared
        Assert.Empty(index.Groups);
        Assert.Equal(0, index.TotalTurnCount);
        Assert.Equal(0, index.RawMessageCount);
    }

    [Fact]
    public void UpdateRebuildsWhenLastProcessedMessageNotFound()
    {
        // Arrange — create with messages
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        Assert.Equal(2, index.Groups.Count);
        index.Groups[0].IsExcluded = true;

        // Act — update with completely different messages (last processed "A1" is absent)
        List<ChatMessage> replaced =
        [
            new ChatMessage(ChatRole.User, "X1"),
            new ChatMessage(ChatRole.Assistant, "X2"),
            new ChatMessage(ChatRole.User, "X3"),
        ];
        index.Update(replaced);

        // Assert — rebuilt from scratch, exclusion state gone
        Assert.Equal(3, index.Groups.Count);
        Assert.All(index.Groups, g => Assert.False(g.IsExcluded));
        Assert.Equal(3, index.RawMessageCount);
    }

    [Fact]
    public void UpdatePreservesExistingGroupExclusionState()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        index.Groups[0].IsExcluded = true;
        index.Groups[0].ExcludeReason = "Test exclusion";

        // Act — append new messages
        messages.Add(new ChatMessage(ChatRole.User, "Q2"));
        index.Update(messages);

        // Assert — original exclusion state preserved
        Assert.True(index.Groups[0].IsExcluded);
        Assert.Equal("Test exclusion", index.Groups[0].ExcludeReason);
        Assert.Equal(3, index.Groups.Count);
    }

    [Fact]
    public void InsertGroupInsertsAtSpecifiedIndex()
    {
        // Arrange
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act — insert between Q1 and Q2
        ChatMessage summaryMsg = new(ChatRole.Assistant, "[Summary]");
        CompactionMessageGroup inserted = index.InsertGroup(1, CompactionGroupKind.Summary, [summaryMsg], turnIndex: 1);

        // Assert
        Assert.Equal(3, index.Groups.Count);
        Assert.Same(inserted, index.Groups[1]);
        Assert.Equal(CompactionGroupKind.Summary, index.Groups[1].Kind);
        Assert.Equal("[Summary]", index.Groups[1].Messages[0].Text);
        Assert.Equal(1, inserted.TurnIndex);
    }

    [Fact]
    public void AddGroupAppendsToEnd()
    {
        // Arrange
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ]);

        // Act
        ChatMessage msg = new(ChatRole.Assistant, "Appended");
        CompactionMessageGroup added = index.AddGroup(CompactionGroupKind.AssistantText, [msg], turnIndex: 1);

        // Assert
        Assert.Equal(2, index.Groups.Count);
        Assert.Same(added, index.Groups[1]);
        Assert.Equal("Appended", index.Groups[1].Messages[0].Text);
    }

    [Fact]
    public void InsertGroupComputesByteAndTokenCounts()
    {
        // Arrange
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ]);

        // Act — insert a group with known text
        ChatMessage msg = new(ChatRole.Assistant, "Hello"); // 5 bytes, ~1 token (5/4)
        CompactionMessageGroup inserted = index.InsertGroup(0, CompactionGroupKind.AssistantText, [msg]);

        // Assert
        Assert.Equal(5, inserted.ByteCount);
        Assert.Equal(1, inserted.TokenCount); // 5 / 4 = 1 (integer division)
    }

    [Fact]
    public void ConstructorWithGroupsRestoresTurnIndex()
    {
        // Arrange — pre-existing groups with turn indices
        CompactionMessageGroup group1 = new(CompactionGroupKind.User, [new ChatMessage(ChatRole.User, "Q1")], 2, 1, turnIndex: 1);
        CompactionMessageGroup group2 = new(CompactionGroupKind.AssistantText, [new ChatMessage(ChatRole.Assistant, "A1")], 2, 1, turnIndex: 1);
        CompactionMessageGroup group3 = new(CompactionGroupKind.User, [new ChatMessage(ChatRole.User, "Q2")], 2, 1, turnIndex: 2);
        List<CompactionMessageGroup> groups = [group1, group2, group3];

        // Act — constructor should restore _currentTurn from the last group's TurnIndex
        CompactionMessageIndex index = new(groups);

        // Assert — adding a new user message should get turn 3 (restored 2 + 1)
        index.Update(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // The new user group should have TurnIndex 3
        CompactionMessageGroup lastGroup = index.Groups[index.Groups.Count - 1];
        Assert.Equal(CompactionGroupKind.User, lastGroup.Kind);
        Assert.NotNull(lastGroup.TurnIndex);
    }

    [Fact]
    public void ConstructorWithEmptyGroupsHandlesGracefully()
    {
        // Arrange & Act — constructor with empty list
        CompactionMessageIndex index = new([]);

        // Assert
        Assert.Empty(index.Groups);
    }

    [Fact]
    public void ConstructorWithGroupsWithoutTurnIndexSkipsRestore()
    {
        // Arrange — groups without turn indices (system messages)
        CompactionMessageGroup systemGroup = new(CompactionGroupKind.System, [new ChatMessage(ChatRole.System, "Be helpful")], 10, 3, turnIndex: null);
        List<CompactionMessageGroup> groups = [systemGroup];

        // Act — constructor won't find a TurnIndex to restore
        CompactionMessageIndex index = new(groups);

        // Assert
        Assert.Single(index.Groups);
    }

    [Fact]
    public void ComputeTokenCountReturnsTokenCount()
    {
        // Arrange — call the public static method directly
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello world"),
            new ChatMessage(ChatRole.Assistant, "Greetings"),
        ];

        // Act — use a simple tokenizer that counts words (each word = 1 token)
        SimpleWordTokenizer tokenizer = new();
        int tokenCount = CompactionMessageIndex.ComputeTokenCount(messages, tokenizer);

        // Assert — "Hello world" = 2, "Greetings" = 1 → 3 total
        Assert.Equal(3, tokenCount);
    }

    [Fact]
    public void ComputeTokenCountEmptyContentsReturnsZero()
    {
        // Arrange — message with empty contents
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, []),
        ];

        SimpleWordTokenizer tokenizer = new();
        int tokenCount = CompactionMessageIndex.ComputeTokenCount(messages, tokenizer);

        // Assert — no content → 0 tokens
        Assert.Equal(0, tokenCount);
    }

    [Fact]
    public void CreateWithTokenizerUsesTokenizerForCounts()
    {
        // Arrange
        SimpleWordTokenizer tokenizer = new();

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello world test"),
        ];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages, tokenizer);

        // Assert — tokenizer counts words: "Hello world test" = 3 tokens
        Assert.Single(index.Groups);
        Assert.Equal(3, index.Groups[0].TokenCount);
        Assert.NotNull(index.Tokenizer);
    }

    [Fact]
    public void InsertGroupWithTokenizerUsesTokenizer()
    {
        // Arrange
        SimpleWordTokenizer tokenizer = new();
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ], tokenizer);

        // Act
        ChatMessage msg = new(ChatRole.Assistant, "Hello world test message");
        CompactionMessageGroup inserted = index.InsertGroup(0, CompactionGroupKind.AssistantText, [msg]);

        // Assert — tokenizer counts words: "Hello world test message" = 4 tokens
        Assert.Equal(4, inserted.TokenCount);
    }

    [Fact]
    public void CreateWithStandaloneToolMessageGroupsAsAssistantText()
    {
        // A Tool message not preceded by an assistant tool-call falls through to the else branch
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Tool, "Orphaned tool result"),
        ];

        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // The Tool message should be grouped as AssistantText (the default fallback)
        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithAssistantNonSummaryWithPropertiesFallsToAssistantText()
    {
        // Assistant message with AdditionalProperties but NOT a summary
        ChatMessage assistant = new(ChatRole.Assistant, "Regular response");
        (assistant.AdditionalProperties ??= [])["someOtherKey"] = "value";

        CompactionMessageIndex index = CompactionMessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithSummaryPropertyFalseIsNotSummary()
    {
        // Summary property key present but value is false — not a summary
        ChatMessage assistant = new(ChatRole.Assistant, "Not a summary");
        (assistant.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = false;

        CompactionMessageIndex index = CompactionMessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithSummaryPropertyNonBoolIsNotSummary()
    {
        // Summary property key present but value is a string, not a bool
        ChatMessage assistant = new(ChatRole.Assistant, "Not a summary");
        (assistant.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = "true";

        CompactionMessageIndex index = CompactionMessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithSummaryPropertyNullValueIsNotSummary()
    {
        // Summary property key present but value is null
        ChatMessage assistant = new(ChatRole.Assistant, "Not a summary");
        (assistant.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = null!;

        CompactionMessageIndex index = CompactionMessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithNoAdditionalPropertiesIsNotSummary()
    {
        // Assistant message with no AdditionalProperties at all
        ChatMessage assistant = new(ChatRole.Assistant, "Plain response");

        CompactionMessageIndex index = CompactionMessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void ComputeByteCountHandlesTextAndNonTextContent()
    {
        // Mix of messages: one with text (non-null), one with FunctionCallContent
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
        ];

        int byteCount = CompactionMessageIndex.ComputeByteCount(messages);

        // "Hello" = 5 bytes, FunctionCallContent("c1", "fn") = "c1" (2) + "fn" (2) = 4 bytes
        Assert.Equal(9, byteCount);
    }

    [Fact]
    public void ComputeTokenCountHandlesTextAndNonTextContent()
    {
        // Mix: one with text, one with FunctionCallContent
        SimpleWordTokenizer tokenizer = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello world"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
        ];

        int tokenCount = CompactionMessageIndex.ComputeTokenCount(messages, tokenizer);

        // "Hello world" = 2 tokens (tokenized), FunctionCallContent("c1","fn") = 4 bytes → 1 token (estimated)
        Assert.Equal(3, tokenCount);
    }

    [Fact]
    public void ComputeByteCountTextContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new TextContent("Hello")]),
        ];

        Assert.Equal(5, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountTextReasoningContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new TextReasoningContent("think") { ProtectedData = "secret" }]),
        ];

        // "think" = 5 bytes, "secret" = 6 bytes
        Assert.Equal(11, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountDataContent()
    {
        byte[] payload = new byte[100];
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new DataContent(payload, "image/png") { Name = "pic" }]),
        ];

        // 100 (data) + 9 ("image/png") + 3 ("pic")
        Assert.Equal(112, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountUriContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new UriContent(new Uri("https://example.com/image.png"), "image/png")]),
        ];

        // "https://example.com/image.png" = 29 bytes, "image/png" = 9 bytes
        Assert.Equal(38, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountFunctionCallContentWithArguments()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" }),
            ]),
        ];

        // "call1" = 5, "get_weather" = 11, "city" = 4, "Seattle" = 7
        Assert.Equal(27, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountFunctionCallContentWithoutArguments()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
        ];

        // "c1" = 2, "fn" = 2
        Assert.Equal(4, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountFunctionResultContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call1", "Sunny, 72°F")]),
        ];

        // "call1" = 5, "Sunny, 72°F" = 13 bytes (° is 2 bytes in UTF-8)
        Assert.Equal(5 + System.Text.Encoding.UTF8.GetByteCount("Sunny, 72°F"), CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountErrorContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new ErrorContent("fail") { ErrorCode = "E001" }]),
        ];

        // "fail" = 4, "E001" = 4
        Assert.Equal(8, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountHostedFileContent()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new HostedFileContent("file-abc") { MediaType = "text/plain", Name = "readme.txt" }]),
        ];

        // "file-abc" = 8, "text/plain" = 10, "readme.txt" = 10
        Assert.Equal(28, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountMixedContentInSingleMessage()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User,
            [
                new TextContent("Hello"),
                new DataContent(new byte[50], "image/png"),
            ]),
        ];

        // TextContent: "Hello" = 5 bytes
        // DataContent: 50 (data) + 9 ("image/png") = 59 bytes
        Assert.Equal(64, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountEmptyContentsReturnsZero()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, []),
        ];

        Assert.Equal(0, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeByteCountUnknownContentTypeReturnsZero()
    {
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new UsageContent(new UsageDetails())]),
        ];

        Assert.Equal(0, CompactionMessageIndex.ComputeByteCount(messages));
    }

    [Fact]
    public void ComputeTokenCountTextReasoningContentUsesTokenizer()
    {
        SimpleWordTokenizer tokenizer = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, [new TextReasoningContent("deep thinking here") { ProtectedData = "hidden data" }]),
        ];

        // "deep thinking here" = 3 words, "hidden data" = 2 words → 5 tokens via tokenizer
        Assert.Equal(5, CompactionMessageIndex.ComputeTokenCount(messages, tokenizer));
    }

    [Fact]
    public void ComputeTokenCountNonTextContentEstimatesFromBytes()
    {
        SimpleWordTokenizer tokenizer = new();
        byte[] payload = new byte[40];
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new DataContent(payload, "image/png")]),
        ];

        // DataContent: 40 (data) + 9 ("image/png") = 49 bytes → 49/4 = 12 tokens (estimated)
        Assert.Equal(12, CompactionMessageIndex.ComputeTokenCount(messages, tokenizer));
    }

    [Fact]
    public void ComputeTokenCountMixedTextAndNonTextContent()
    {
        SimpleWordTokenizer tokenizer = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User,
            [
                new TextContent("Hello world"),
                new DataContent(new byte[40], "image/png"),
            ]),
        ];

        // TextContent: "Hello world" = 2 tokens (tokenized)
        // DataContent: 40 + 9 = 49 bytes → 12 tokens (estimated)
        Assert.Equal(14, CompactionMessageIndex.ComputeTokenCount(messages, tokenizer));
    }

    [Fact]
    public void CreateGroupByteCountIncludesAllContentTypes()
    {
        // Verify that CompactionMessageIndex.Create produces groups with accurate byte counts for non-text content
        ChatMessage assistantMessage = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("call1", "Sunny")]);
        List<ChatMessage> messages = [assistantMessage, toolResult];

        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // ToolCall group: FunctionCallContent("call1","get_weather",{city=Seattle}) + FunctionResultContent("call1","Sunny")
        // = (5 + 11 + 4 + 7) + (5 + 5) = 27 + 10 = 37
        Assert.Single(index.Groups);
        Assert.Equal(37, index.Groups[0].ByteCount);
        Assert.True(index.Groups[0].TokenCount > 0);
    }

    /// <summary>
    /// A simple tokenizer that counts whitespace-separated words as tokens.
    /// </summary>
    private sealed class SimpleWordTokenizer : Tokenizer
    {
        public override PreTokenizer? PreTokenizer => null;
        public override Normalizer? Normalizer => null;

        protected override EncodeResults<EncodedToken> EncodeToTokens(string? text, ReadOnlySpan<char> textSpan, EncodeSettings settings)
        {
            // Simple word-based encoding
            string input = text ?? textSpan.ToString();
            if (string.IsNullOrWhiteSpace(input))
            {
                return new EncodeResults<EncodedToken>
                {
                    Tokens = [],
                    CharsConsumed = 0,
                    NormalizedText = null,
                };
            }

            string[] words = input.Split(' ');
            List<EncodedToken> tokens = [];
            int offset = 0;
            for (int i = 0; i < words.Length; i++)
            {
                tokens.Add(new EncodedToken(i, words[i], new Range(offset, offset + words[i].Length)));
                offset += words[i].Length + 1;
            }

            return new EncodeResults<EncodedToken>
            {
                Tokens = tokens,
                CharsConsumed = input.Length,
                NormalizedText = null,
            };
        }

        public override OperationStatus Decode(IEnumerable<int> ids, Span<char> destination, out int idsConsumed, out int charsWritten)
        {
            idsConsumed = 0;
            charsWritten = 0;
            return OperationStatus.Done;
        }
    }

    [Fact]
    public void CreateReasoningBeforeToolCallGroupsAtomic()
    {
        // Arrange — reasoning-only assistant message immediately before a tool-call assistant message
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("I should look up the weather")]);
        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]);

        List<ChatMessage> messages = [reasoning, toolCall, toolResult];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — all three messages in a single ToolCall group
        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[0].Kind);
        Assert.Equal(3, index.Groups[0].MessageCount);
        Assert.Same(reasoning, index.Groups[0].Messages[0]);
        Assert.Same(toolCall, index.Groups[0].Messages[1]);
        Assert.Same(toolResult, index.Groups[0].Messages[2]);
    }

    [Fact]
    public void CreateMultipleReasoningBeforeToolCallGroupsAtomic()
    {
        // Arrange — multiple consecutive reasoning messages before a tool-call
        ChatMessage reasoning1 = new(ChatRole.Assistant, [new TextReasoningContent("First thought")]);
        ChatMessage reasoning2 = new(ChatRole.Assistant, [new TextReasoningContent("Second thought")]);
        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("c1", "search")]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("c1", "results")]);

        List<ChatMessage> messages = [reasoning1, reasoning2, toolCall, toolResult];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — all four messages in a single ToolCall group
        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[0].Kind);
        Assert.Equal(4, index.Groups[0].MessageCount);
    }

    [Fact]
    public void CreateReasoningNotFollowedByToolCallIsAssistantText()
    {
        // Arrange — reasoning-only message followed by a user message (no tool call)
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("Thinking...")]);
        ChatMessage user = new(ChatRole.User, "Hello");

        List<ChatMessage> messages = [reasoning, user];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — reasoning becomes AssistantText, user stays User
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.User, index.Groups[1].Kind);
    }

    [Fact]
    public void CreateReasoningAtEndOfConversationIsAssistantText()
    {
        // Arrange — reasoning-only message at the end with nothing following it
        ChatMessage user = new(ChatRole.User, "Hello");
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("Thinking...")]);

        List<ChatMessage> messages = [user, reasoning];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.User, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[1].Kind);
    }

    [Fact]
    public void CreateToolCallFollowedByReasoningInTail()
    {
        // Arrange — tool-call assistant followed by tool result and then reasoning-only messages
        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("c1", "data")]);
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("Analyzing result...")]);

        List<ChatMessage> messages = [toolCall, toolResult, reasoning];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — reasoning after tool result should be included in the same ToolCall group
        Assert.Single(index.Groups);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[0].Kind);
        Assert.Equal(3, index.Groups[0].MessageCount);
    }

    [Fact]
    public void CreateReasoningBetweenToolCallsGroupsCorrectly()
    {
        // Arrange — reasoning before first tool-call, then another reasoning+tool-call pair
        ChatMessage reasoning1 = new(ChatRole.Assistant, [new TextReasoningContent("Plan: call get_weather")]);
        ChatMessage toolCall1 = new(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]);
        ChatMessage toolResult1 = new(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]);
        ChatMessage user = new(ChatRole.User, "What else?");
        ChatMessage reasoning2 = new(ChatRole.Assistant, [new TextReasoningContent("Plan: call get_time")]);
        ChatMessage toolCall2 = new(ChatRole.Assistant, [new FunctionCallContent("c2", "get_time")]);
        ChatMessage toolResult2 = new(ChatRole.Tool, [new FunctionResultContent("c2", "3 PM")]);

        List<ChatMessage> messages = [reasoning1, toolCall1, toolResult1, user, reasoning2, toolCall2, toolResult2];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — two ToolCall groups with reasoning included, plus one User group
        Assert.Equal(3, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[0].Kind);
        Assert.Equal(3, index.Groups[0].MessageCount); // reasoning1 + toolCall1 + toolResult1
        Assert.Equal(CompactionGroupKind.User, index.Groups[1].Kind);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[2].Kind);
        Assert.Equal(3, index.Groups[2].MessageCount); // reasoning2 + toolCall2 + toolResult2
    }

    [Fact]
    public void CreateReasoningFollowedByNonReasoningAssistantNotGrouped()
    {
        // Arrange — reasoning-only followed by plain assistant text (not tool call)
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("Thinking...")]);
        ChatMessage plainAssistant = new(ChatRole.Assistant, "Here's my answer.");

        List<ChatMessage> messages = [reasoning, plainAssistant];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — each becomes its own AssistantText group
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[1].Kind);
    }

    [Fact]
    public void CreateMixedReasoningAndToolCallTurnIndex()
    {
        // Arrange — verify turn index is correctly assigned when reasoning precedes tool call
        ChatMessage system = new(ChatRole.System, "You are helpful.");
        ChatMessage user = new(ChatRole.User, "Help me");
        ChatMessage reasoning = new(ChatRole.Assistant, [new TextReasoningContent("Let me think")]);
        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("c1", "helper")]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("c1", "done")]);

        List<ChatMessage> messages = [system, user, reasoning, toolCall, toolResult];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert
        Assert.Equal(3, index.Groups.Count);
        Assert.Null(index.Groups[0].TurnIndex); // System
        Assert.Equal(1, index.Groups[1].TurnIndex); // User turn 1
        Assert.Equal(1, index.Groups[2].TurnIndex); // ToolCall inherits turn 1
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[2].Kind);
        Assert.Equal(3, index.Groups[2].MessageCount); // reasoning + toolCall + toolResult
    }

    [Fact]
    public void CreateAssistantWithMixedReasoningAndTextNotGroupedAsReasoning()
    {
        // Arrange — assistant with both reasoning and text content is NOT "only reasoning"
        ChatMessage mixedAssistant = new(ChatRole.Assistant, [
            new TextReasoningContent("Thinking"),
            new TextContent("And also speaking"),
        ]);
        ChatMessage toolCall = new(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, [new FunctionResultContent("c1", "data")]);

        List<ChatMessage> messages = [mixedAssistant, toolCall, toolResult];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — mixedAssistant has non-reasoning content, so it's AssistantText, not grouped with ToolCall
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[1].Kind);
    }

    [Fact]
    public void CreateEmptyContentsAssistantIsAssistantText()
    {
        // Arrange — assistant message with empty contents (edge case for HasOnlyReasoning)
        ChatMessage emptyAssistant = new(ChatRole.Assistant, []);
        ChatMessage user = new(ChatRole.User, "Hello");

        List<ChatMessage> messages = [emptyAssistant, user];

        // Act
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);

        // Assert — empty contents falls through to AssistantText
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void UpdateIncrementallyAppendsReasoningToolCallGroup()
    {
        // Arrange — create initial index, then add reasoning+tool-call messages
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        Assert.Equal(2, index.Groups.Count);

        // Add reasoning + tool-call
        messages.Add(new ChatMessage(ChatRole.Assistant, [new TextReasoningContent("Let me search")]));
        messages.Add(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "search")]));
        messages.Add(new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "found")]));

        // Act
        index.Update(messages);

        // Assert — new messages form a single ToolCall group (delta append)
        Assert.Equal(3, index.Groups.Count);
        Assert.Equal(CompactionGroupKind.User, index.Groups[0].Kind);
        Assert.Equal(CompactionGroupKind.AssistantText, index.Groups[1].Kind);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[2].Kind);
        Assert.Equal(3, index.Groups[2].MessageCount); // reasoning + toolCall + toolResult
    }
}
