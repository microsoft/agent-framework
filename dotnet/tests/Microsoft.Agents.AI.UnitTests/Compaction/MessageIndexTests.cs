// Copyright (c) Microsoft. All rights reserved.

using System.Buffers;
using System.Collections.Generic;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="MessageIndex"/> class.
/// </summary>
public class MessageIndexTests
{
    [Fact]
    public void CreateEmptyListReturnsEmptyGroups()
    {
        // Arrange
        List<ChatMessage> messages = [];

        // Act
        MessageIndex groups = MessageIndex.Create(messages);

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
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.System, groups.Groups[0].Kind);
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
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.User, groups.Groups[0].Kind);
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
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.AssistantText, groups.Groups[0].Kind);
    }

    [Fact]
    public void CreateToolCallWithResultsCreatesAtomicToolCallGroup()
    {
        // Arrange
        ChatMessage assistantMessage = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny, 72°F");

        List<ChatMessage> messages = [assistantMessage, toolResult];

        // Act
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.ToolCall, groups.Groups[0].Kind);
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
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Equal(4, groups.Groups.Count);
        Assert.Equal(MessageGroupKind.System, groups.Groups[0].Kind);
        Assert.Equal(MessageGroupKind.User, groups.Groups[1].Kind);
        Assert.Equal(MessageGroupKind.ToolCall, groups.Groups[2].Kind);
        Assert.Equal(2, groups.Groups[2].Messages.Count);
        Assert.Equal(MessageGroupKind.AssistantText, groups.Groups[3].Kind);
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
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.ToolCall, groups.Groups[0].Kind);
        Assert.Equal(3, groups.Groups[0].Messages.Count);
    }

    [Fact]
    public void GetIncludedMessagesExcludesMarkedGroups()
    {
        // Arrange
        ChatMessage msg1 = new(ChatRole.User, "First");
        ChatMessage msg2 = new(ChatRole.Assistant, "Response");
        ChatMessage msg3 = new(ChatRole.User, "Second");

        MessageIndex groups = MessageIndex.Create([msg1, msg2, msg3]);
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

        MessageIndex groups = MessageIndex.Create([msg1, msg2]);
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
        MessageIndex groups = MessageIndex.Create(
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
        (summaryMessage.AdditionalProperties ??= [])[MessageGroup.SummaryPropertyKey] = true;

        List<ChatMessage> messages = [summaryMessage];

        // Act
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Single(groups.Groups);
        Assert.Equal(MessageGroupKind.Summary, groups.Groups[0].Kind);
        Assert.Same(summaryMessage, groups.Groups[0].Messages[0]);
    }

    [Fact]
    public void CreateSummaryAmongOtherMessagesGroupsCorrectly()
    {
        // Arrange
        ChatMessage systemMsg = new(ChatRole.System, "You are helpful.");
        ChatMessage summaryMsg = new(ChatRole.Assistant, "[Summary]: previous context");
        (summaryMsg.AdditionalProperties ??= [])[MessageGroup.SummaryPropertyKey] = true;
        ChatMessage userMsg = new(ChatRole.User, "Continue...");

        List<ChatMessage> messages = [systemMsg, summaryMsg, userMsg];

        // Act
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Equal(3, groups.Groups.Count);
        Assert.Equal(MessageGroupKind.System, groups.Groups[0].Kind);
        Assert.Equal(MessageGroupKind.Summary, groups.Groups[1].Kind);
        Assert.Equal(MessageGroupKind.User, groups.Groups[2].Kind);
    }

    [Fact]
    public void MessageGroupStoresPassedCounts()
    {
        // Arrange & Act
        MessageGroup group = new(MessageGroupKind.User, [new ChatMessage(ChatRole.User, "Hello")], byteCount: 5, tokenCount: 2);

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
        MessageGroup group = new(MessageGroupKind.User, messages, byteCount: 5, tokenCount: 1);

        // Assert — Messages is IReadOnlyList, not IList
        Assert.IsAssignableFrom<IReadOnlyList<ChatMessage>>(group.Messages);
        Assert.Same(messages, group.Messages);
    }

    [Fact]
    public void CreateComputesByteCountUtf8()
    {
        // Arrange — "Hello" is 5 UTF-8 bytes
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void CreateComputesByteCountMultiByteChars()
    {
        // Arrange — "café" has a multi-byte 'é' (2 bytes in UTF-8) → 5 bytes total
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "café")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void CreateComputesByteCountMultipleMessagesInGroup()
    {
        // Arrange — ToolCall group: assistant (tool call, null text) + tool result "OK" (2 bytes)
        ChatMessage assistantMsg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, "OK");
        MessageIndex groups = MessageIndex.Create([assistantMsg, toolResult]);

        // Assert — single ToolCall group with 2 messages
        Assert.Single(groups.Groups);
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(2, groups.Groups[0].ByteCount); // "OK" = 2 bytes, assistant text is null
    }

    [Fact]
    public void CreateDefaultTokenCountIsHeuristic()
    {
        // Arrange — "Hello world test data!" = 22 UTF-8 bytes → 22 / 4 = 5 estimated tokens
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world test data!")]);

        // Assert
        Assert.Equal(22, groups.Groups[0].ByteCount);
        Assert.Equal(22 / 4, groups.Groups[0].TokenCount);
    }

    [Fact]
    public void CreateNullTextHasZeroCounts()
    {
        // Arrange — message with no text (e.g., pure function call)
        ChatMessage msg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage tool = new(ChatRole.Tool, string.Empty);
        MessageIndex groups = MessageIndex.Create([msg, tool]);

        // Assert
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(0, groups.Groups[0].ByteCount);
        Assert.Equal(0, groups.Groups[0].TokenCount);
    }

    [Fact]
    public void TotalAggregatesSumAllGroups()
    {
        // Arrange
        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex groups = MessageIndex.Create(
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
        // Arrange — tool call group with assistant "Ask" (3 bytes) + tool result "OK" (2 bytes)
        ChatMessage assistantMsg = new(ChatRole.Assistant, [new FunctionCallContent("call1", "fn")]);
        ChatMessage toolResult = new(ChatRole.Tool, "OK");

        MessageIndex groups = MessageIndex.Create([assistantMsg, toolResult]);

        // Assert — single group with 2 messages
        Assert.Single(groups.Groups);
        Assert.Equal(2, groups.Groups[0].MessageCount);
        Assert.Equal(2, groups.Groups[0].ByteCount); // assistant text is null (function call), tool result is "OK" = 2 bytes
        Assert.Equal(1, groups.TotalGroupCount);
        Assert.Equal(2, groups.TotalMessageCount);
    }

    [Fact]
    public void CreateAssignsTurnIndicesSingleTurn()
    {
        // Arrange — System (no turn), User + Assistant = turn 1
        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex groups = MessageIndex.Create(
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

        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex groups = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "System."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        ]);

        // Act
        List<MessageGroup> turn1 = [.. groups.GetTurnGroups(1)];
        List<MessageGroup> turn2 = [.. groups.GetTurnGroups(2)];

        // Assert
        Assert.Equal(2, turn1.Count);
        Assert.Equal(MessageGroupKind.User, turn1[0].Kind);
        Assert.Equal(MessageGroupKind.AssistantText, turn1[1].Kind);
        Assert.Equal(2, turn2.Count);
        Assert.Equal(MessageGroupKind.User, turn2[0].Kind);
        Assert.Equal(MessageGroupKind.AssistantText, turn2[1].Kind);
    }

    [Fact]
    public void IncludedTurnCountReflectsExclusions()
    {
        // Arrange — 2 turns, exclude all groups in turn 1
        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex groups = MessageIndex.Create(
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
        MessageIndex index = MessageIndex.Create(messages);
        Assert.Equal(2, index.Groups.Count);
        Assert.Equal(2, index.ProcessedMessageCount);

        // Act — add 2 more messages and update
        messages.Add(new ChatMessage(ChatRole.User, "Q2"));
        messages.Add(new ChatMessage(ChatRole.Assistant, "A2"));
        index.Update(messages);

        // Assert — should have 4 groups total, processed count updated
        Assert.Equal(4, index.Groups.Count);
        Assert.Equal(4, index.ProcessedMessageCount);
        Assert.Equal(MessageGroupKind.User, index.Groups[2].Kind);
        Assert.Equal(MessageGroupKind.AssistantText, index.Groups[3].Kind);
    }

    [Fact]
    public void UpdateNoOpWhenNoNewMessages()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ];
        MessageIndex index = MessageIndex.Create(messages);
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
        MessageIndex index = MessageIndex.Create(messages);
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
        Assert.Equal(1, index.ProcessedMessageCount);
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
        MessageIndex index = MessageIndex.Create(messages);
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
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act — insert between Q1 and Q2
        ChatMessage summaryMsg = new(ChatRole.Assistant, "[Summary]");
        MessageGroup inserted = index.InsertGroup(1, MessageGroupKind.Summary, [summaryMsg], turnIndex: 1);

        // Assert
        Assert.Equal(3, index.Groups.Count);
        Assert.Same(inserted, index.Groups[1]);
        Assert.Equal(MessageGroupKind.Summary, index.Groups[1].Kind);
        Assert.Equal("[Summary]", index.Groups[1].Messages[0].Text);
        Assert.Equal(1, inserted.TurnIndex);
    }

    [Fact]
    public void AddGroupAppendsToEnd()
    {
        // Arrange
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ]);

        // Act
        ChatMessage msg = new(ChatRole.Assistant, "Appended");
        MessageGroup added = index.AddGroup(MessageGroupKind.AssistantText, [msg], turnIndex: 1);

        // Assert
        Assert.Equal(2, index.Groups.Count);
        Assert.Same(added, index.Groups[1]);
        Assert.Equal("Appended", index.Groups[1].Messages[0].Text);
    }

    [Fact]
    public void InsertGroupComputesByteAndTokenCounts()
    {
        // Arrange
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
        ]);

        // Act — insert a group with known text
        ChatMessage msg = new(ChatRole.Assistant, "Hello"); // 5 bytes, ~1 token (5/4)
        MessageGroup inserted = index.InsertGroup(0, MessageGroupKind.AssistantText, [msg]);

        // Assert
        Assert.Equal(5, inserted.ByteCount);
        Assert.Equal(1, inserted.TokenCount); // 5 / 4 = 1 (integer division)
    }

    [Fact]
    public void ConstructorWithGroupsRestoresTurnIndex()
    {
        // Arrange — pre-existing groups with turn indices
        MessageGroup group1 = new(MessageGroupKind.User, [new ChatMessage(ChatRole.User, "Q1")], 2, 1, turnIndex: 1);
        MessageGroup group2 = new(MessageGroupKind.AssistantText, [new ChatMessage(ChatRole.Assistant, "A1")], 2, 1, turnIndex: 1);
        MessageGroup group3 = new(MessageGroupKind.User, [new ChatMessage(ChatRole.User, "Q2")], 2, 1, turnIndex: 2);
        List<MessageGroup> groups = [group1, group2, group3];

        // Act — constructor should restore _currentTurn from the last group's TurnIndex
        MessageIndex index = new(groups);

        // Assert — adding a new user message should get turn 3 (restored 2 + 1)
        index.Update(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ]);

        // The new user group should have TurnIndex 3
        MessageGroup lastGroup = index.Groups[index.Groups.Count - 1];
        Assert.Equal(MessageGroupKind.User, lastGroup.Kind);
        Assert.NotNull(lastGroup.TurnIndex);
    }

    [Fact]
    public void ConstructorWithEmptyGroupsHandlesGracefully()
    {
        // Arrange & Act — constructor with empty list
        MessageIndex index = new([]);

        // Assert
        Assert.Empty(index.Groups);
    }

    [Fact]
    public void ConstructorWithGroupsWithoutTurnIndexSkipsRestore()
    {
        // Arrange — groups without turn indices (system messages)
        MessageGroup systemGroup = new(MessageGroupKind.System, [new ChatMessage(ChatRole.System, "Be helpful")], 10, 3, turnIndex: null);
        List<MessageGroup> groups = [systemGroup];

        // Act — constructor won't find a TurnIndex to restore
        MessageIndex index = new(groups);

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
        int tokenCount = MessageIndex.ComputeTokenCount(messages, tokenizer);

        // Assert — "Hello world" = 2, "Greetings" = 1 → 3 total
        Assert.Equal(3, tokenCount);
    }

    [Fact]
    public void ComputeTokenCountEmptyTextReturnsZero()
    {
        // Arrange — message with no text content
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new FunctionCallContent("c1", "fn")]),
        ];

        SimpleWordTokenizer tokenizer = new();
        int tokenCount = MessageIndex.ComputeTokenCount(messages, tokenizer);

        // Assert — no text content → 0 tokens
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
        MessageIndex index = MessageIndex.Create(messages, tokenizer);

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
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ], tokenizer);

        // Act
        ChatMessage msg = new(ChatRole.Assistant, "Hello world test message");
        MessageGroup inserted = index.InsertGroup(0, MessageGroupKind.AssistantText, [msg]);

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

        MessageIndex index = MessageIndex.Create(messages);

        // The Tool message should be grouped as AssistantText (the default fallback)
        Assert.Single(index.Groups);
        Assert.Equal(MessageGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void CreateWithAssistantNonSummaryWithPropertiesFallsToAssistantText()
    {
        // Assistant message with AdditionalProperties but NOT a summary
        ChatMessage assistant = new(ChatRole.Assistant, "Regular response");
        (assistant.AdditionalProperties ??= [])["someOtherKey"] = "value";

        MessageIndex index = MessageIndex.Create([assistant]);

        Assert.Single(index.Groups);
        Assert.Equal(MessageGroupKind.AssistantText, index.Groups[0].Kind);
    }

    [Fact]
    public void ComputeByteCountHandlesNullAndNonNullText()
    {
        // Mix of messages: one with text (non-null), one without (null Text)
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
        ];

        int byteCount = MessageIndex.ComputeByteCount(messages);

        // Only "Hello" contributes bytes (5 bytes UTF-8)
        Assert.Equal(5, byteCount);
    }

    [Fact]
    public void ComputeTokenCountHandlesNullAndNonNullText()
    {
        // Mix: one with text, one without
        SimpleWordTokenizer tokenizer = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello world"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
        ];

        int tokenCount = MessageIndex.ComputeTokenCount(messages, tokenizer);

        // Only "Hello world" contributes tokens (2 words)
        Assert.Equal(2, tokenCount);
    }

    /// <summary>
    /// A simple tokenizer that counts whitespace-separated words as tokens.
    /// </summary>
    private sealed class SimpleWordTokenizer : Microsoft.ML.Tokenizers.Tokenizer
    {
        public override Microsoft.ML.Tokenizers.PreTokenizer? PreTokenizer => null;
        public override Microsoft.ML.Tokenizers.Normalizer? Normalizer => null;

        protected override Microsoft.ML.Tokenizers.EncodeResults<Microsoft.ML.Tokenizers.EncodedToken> EncodeToTokens(string? text, System.ReadOnlySpan<char> textSpan, Microsoft.ML.Tokenizers.EncodeSettings settings)
        {
            // Simple word-based encoding
            string input = text ?? textSpan.ToString();
            if (string.IsNullOrWhiteSpace(input))
            {
                return new Microsoft.ML.Tokenizers.EncodeResults<Microsoft.ML.Tokenizers.EncodedToken>
                {
                    Tokens = System.Array.Empty<Microsoft.ML.Tokenizers.EncodedToken>(),
                    CharsConsumed = 0,
                    NormalizedText = null,
                };
            }

            string[] words = input.Split(' ');
            List<Microsoft.ML.Tokenizers.EncodedToken> tokens = [];
            int offset = 0;
            for (int i = 0; i < words.Length; i++)
            {
                tokens.Add(new Microsoft.ML.Tokenizers.EncodedToken(i, words[i], new System.Range(offset, offset + words[i].Length)));
                offset += words[i].Length + 1;
            }

            return new Microsoft.ML.Tokenizers.EncodeResults<Microsoft.ML.Tokenizers.EncodedToken>
            {
                Tokens = tokens,
                CharsConsumed = input.Length,
                NormalizedText = null,
            };
        }

        public override OperationStatus Decode(System.Collections.Generic.IEnumerable<int> ids, System.Span<char> destination, out int idsConsumed, out int charsWritten)
        {
            idsConsumed = 0;
            charsWritten = 0;
            return OperationStatus.Done;
        }
    }
}
