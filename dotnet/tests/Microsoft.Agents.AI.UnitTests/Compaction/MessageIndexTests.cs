// Copyright (c) Microsoft. All rights reserved.

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
    public void Create_EmptyList_ReturnsEmptyGroups()
    {
        // Arrange
        List<ChatMessage> messages = [];

        // Act
        MessageIndex groups = MessageIndex.Create(messages);

        // Assert
        Assert.Empty(groups.Groups);
    }

    [Fact]
    public void Create_SystemMessage_CreatesSystemGroup()
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
    public void Create_UserMessage_CreatesUserGroup()
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
    public void Create_AssistantTextMessage_CreatesAssistantTextGroup()
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
    public void Create_ToolCallWithResults_CreatesAtomicToolCallGroup()
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
    public void Create_MixedConversation_GroupsCorrectly()
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
    public void Create_MultipleToolResults_GroupsAllWithAssistant()
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
    public void GetIncludedMessages_ExcludesMarkedGroups()
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
    public void GetAllMessages_IncludesExcludedGroups()
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
    public void IncludedGroupCount_ReflectsExclusions()
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
    public void Create_SummaryMessage_CreatesSummaryGroup()
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
    public void Create_SummaryAmongOtherMessages_GroupsCorrectly()
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
    public void MessageGroup_StoresPassedCounts()
    {
        // Arrange & Act
        MessageGroup group = new(MessageGroupKind.User, [new ChatMessage(ChatRole.User, "Hello")], byteCount: 5, tokenCount: 2);

        // Assert
        Assert.Equal(1, group.MessageCount);
        Assert.Equal(5, group.ByteCount);
        Assert.Equal(2, group.TokenCount);
    }

    [Fact]
    public void MessageGroup_MessagesAreImmutable()
    {
        // Arrange
        IReadOnlyList<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];
        MessageGroup group = new(MessageGroupKind.User, messages, byteCount: 5, tokenCount: 1);

        // Assert — Messages is IReadOnlyList, not IList
        Assert.IsAssignableFrom<IReadOnlyList<ChatMessage>>(group.Messages);
        Assert.Same(messages, group.Messages);
    }

    [Fact]
    public void Create_ComputesByteCount_Utf8()
    {
        // Arrange — "Hello" is 5 UTF-8 bytes
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hello")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void Create_ComputesByteCount_MultiByteChars()
    {
        // Arrange — "café" has a multi-byte 'é' (2 bytes in UTF-8) → 5 bytes total
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "café")]);

        // Assert
        Assert.Equal(5, groups.Groups[0].ByteCount);
    }

    [Fact]
    public void Create_ComputesByteCount_MultipleMessagesInGroup()
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
    public void Create_DefaultTokenCount_IsHeuristic()
    {
        // Arrange — "Hello world test data!" = 22 UTF-8 bytes → 22 / 4 = 5 estimated tokens
        MessageIndex groups = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world test data!")]);

        // Assert
        Assert.Equal(22, groups.Groups[0].ByteCount);
        Assert.Equal(22 / 4, groups.Groups[0].TokenCount);
    }

    [Fact]
    public void Create_NullText_HasZeroCounts()
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
    public void TotalAggregates_SumAllGroups()
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
    public void IncludedAggregates_ExcludeMarkedGroups()
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
    public void ToolCallGroup_AggregatesAcrossMessages()
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
    public void Create_AssignsTurnIndices_SingleTurn()
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
    public void Create_AssignsTurnIndices_MultiTurn()
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
    public void Create_TurnSpansToolCallGroups()
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
    public void GetTurnGroups_ReturnsGroupsForSpecificTurn()
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
    public void IncludedTurnCount_ReflectsExclusions()
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
    public void TotalTurnCount_ZeroWhenNoUserMessages()
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
    public void IncludedTurnCount_PartialExclusion_StillCountsTurn()
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
}
