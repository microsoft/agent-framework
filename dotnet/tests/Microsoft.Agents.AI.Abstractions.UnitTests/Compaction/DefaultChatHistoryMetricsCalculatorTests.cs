// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class DefaultChatHistoryMetricsCalculatorTests
{
    [Fact]
    public void EmptyList_ReturnsZeroMetrics()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        CompactionMetric metrics = calculator.Calculate([]);

        Assert.Equal(0, metrics.TokenCount);
        Assert.Equal(0L, metrics.ByteCount);
        Assert.Equal(0, metrics.MessageCount);
        Assert.Equal(0, metrics.ToolCallCount);
        Assert.Equal(0, metrics.UserTurnCount);
    }

    [Fact]
    public void CountsMessages()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(2, metrics.MessageCount);
    }

    [Fact]
    public void CountsUserTurns()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi"),
            new(ChatRole.User, "How are you?"),
            new(ChatRole.Assistant, "Good"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(2, metrics.UserTurnCount);
    }

    [Fact]
    public void CountsToolCalls()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        ChatMessage assistantMsg = new(ChatRole.Assistant, [
            new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "NYC" }),
            new FunctionCallContent("call2", "get_time"),
        ]);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "What's the weather?"),
            assistantMsg,
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(2, metrics.ToolCallCount);
    }

    [Fact]
    public void ConsecutiveUserMessages_CountAsOneTurn()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "First"),
            new(ChatRole.User, "Second"),
            new(ChatRole.Assistant, "Reply"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(1, metrics.UserTurnCount);
    }

    [Fact]
    public void TokenCount_IsPositive()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello world"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.True(metrics.TokenCount > 0);
        Assert.True(metrics.ByteCount > 0);
    }

    [Fact]
    public void NullInput_ReturnsZeroMetrics()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        CompactionMetric metrics = calculator.Calculate(null!);

        Assert.Equal(0, metrics.TokenCount);
        Assert.Equal(0L, metrics.ByteCount);
        Assert.Equal(0, metrics.MessageCount);
        Assert.Empty(metrics.Groups);
    }

    [Fact]
    public void InvalidCharsPerToken_UsesDefault()
    {
        // A non-positive charsPerToken should fall back to the default (4)
        DefaultChatHistoryMetricsCalculator calculator = new(charsPerToken: 0);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Hello world"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        // With default 4 chars/token: "Hello world" = 11 chars → 11/4=2 + 4 overhead = 6 tokens
        Assert.True(metrics.TokenCount > 0);
    }

    [Fact]
    public void NullMessageText_HandledGracefully()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        // Message with no text content — Text returns null
        ChatMessage msg = new() { Role = ChatRole.User };
        List<ChatMessage> messages = [msg];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(1, metrics.MessageCount);
        // Null text → empty string → 0 bytes, only overhead tokens
        Assert.True(metrics.TokenCount > 0); // per-message overhead
        Assert.Equal(0L, metrics.ByteCount);
    }

    [Fact]
    public void NullContents_SkipsToolCounting()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        ChatMessage msg = new(ChatRole.User, "text");
        msg.Contents = null!;
        List<ChatMessage> messages = [msg];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(1, metrics.MessageCount);
        Assert.Equal(0, metrics.ToolCallCount);
    }

    [Fact]
    public void MessageWithOnlyNonTextContent_NullTextHandled()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        // FunctionCallContent-only message has null Text
        ChatMessage msg = new(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "func"),
        ]);
        List<ChatMessage> messages = [msg];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(1, metrics.MessageCount);
        Assert.Equal(1, metrics.ToolCallCount);
    }

    [Fact]
    public void Calculate_PopulatesGroupIndex()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "System prompt"),
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there"),
        ];

        CompactionMetric metrics = calculator.Calculate(messages);

        Assert.Equal(3, metrics.Groups.Count);
        Assert.Equal(ChatMessageGroupKind.System, metrics.Groups[0].Kind);
        Assert.Equal(ChatMessageGroupKind.UserTurn, metrics.Groups[1].Kind);
        Assert.Equal(ChatMessageGroupKind.AssistantPlain, metrics.Groups[2].Kind);
    }

    [Fact]
    public void EmptyList_GroupIndexIsEmpty()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        CompactionMetric metrics = calculator.Calculate([]);

        Assert.Empty(metrics.Groups);
    }

    [Fact]
    public void GroupIndex_SystemMessage_IdentifiedCorrectly()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helpful assistant"),
        ];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Single(groups);
        Assert.Equal(ChatMessageGroupKind.System, groups[0].Kind);
        Assert.Equal(0, groups[0].StartIndex);
        Assert.Equal(1, groups[0].Count);
    }

    [Fact]
    public void GroupIndex_AssistantWithToolCalls_GroupedWithResults()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        ChatMessage assistantMsg = new(ChatRole.Assistant, [
            new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "NYC" }),
        ]);
        ChatMessage toolResult = new(ChatRole.Tool, [
            new FunctionResultContent("call1", "Sunny, 72°F"),
        ]);
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "What's the weather?"),
            assistantMsg,
            toolResult,
        ];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Equal(2, groups.Count);
        Assert.Equal(ChatMessageGroupKind.UserTurn, groups[0].Kind);
        Assert.Equal(ChatMessageGroupKind.AssistantToolGroup, groups[1].Kind);
        Assert.Equal(1, groups[1].StartIndex);
        Assert.Equal(2, groups[1].Count); // assistant + tool result
    }

    [Fact]
    public void GroupIndex_MultipleToolResults_GroupedTogether()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        ChatMessage assistantMsg = new(ChatRole.Assistant, [
            new FunctionCallContent("c1", "func1"),
            new FunctionCallContent("c2", "func2"),
        ]);
        ChatMessage tool1 = new(ChatRole.Tool, [new FunctionResultContent("c1", "result1")]);
        ChatMessage tool2 = new(ChatRole.Tool, [new FunctionResultContent("c2", "result2")]);
        List<ChatMessage> messages = [assistantMsg, tool1, tool2];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Single(groups);
        Assert.Equal(ChatMessageGroupKind.AssistantToolGroup, groups[0].Kind);
        Assert.Equal(3, groups[0].Count);
    }

    [Fact]
    public void GroupIndex_ComplexConversation_CorrectGrouping()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a helper"),
            new(ChatRole.User, "Hi"),
            new(ChatRole.Assistant, "Hello!"),
            new(ChatRole.User, "Get weather"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new(ChatRole.Assistant, "It's sunny!"),
        ];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Equal(6, groups.Count);
        Assert.Equal(ChatMessageGroupKind.System, groups[0].Kind);
        Assert.Equal(ChatMessageGroupKind.UserTurn, groups[1].Kind);
        Assert.Equal(ChatMessageGroupKind.AssistantPlain, groups[2].Kind);
        Assert.Equal(ChatMessageGroupKind.UserTurn, groups[3].Kind);
        Assert.Equal(ChatMessageGroupKind.AssistantToolGroup, groups[4].Kind);
        Assert.Equal(2, groups[4].Count); // assistant + tool
        Assert.Equal(ChatMessageGroupKind.AssistantPlain, groups[5].Kind);
    }

    [Fact]
    public void GroupIndex_OrphanToolResult_IdentifiedCorrectly()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "orphan result")]),
        ];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Single(groups);
        Assert.Equal(ChatMessageGroupKind.ToolResult, groups[0].Kind);
    }

    [Fact]
    public void GroupIndex_UnknownRole_IdentifiedAsOther()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        List<ChatMessage> messages =
        [
            new(new ChatRole("custom"), "custom message"),
        ];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Single(groups);
        Assert.Equal(ChatMessageGroupKind.Other, groups[0].Kind);
    }

    [Fact]
    public void GroupIndex_AssistantWithNullContents_ClassifiedAsPlain()
    {
        DefaultChatHistoryMetricsCalculator calculator = new();
        ChatMessage msg = new(ChatRole.Assistant, "reply");
        msg.Contents = null!;
        List<ChatMessage> messages = [msg];

        IReadOnlyList<ChatMessageGroup> groups = calculator.Calculate(messages).Groups;

        Assert.Single(groups);
        Assert.Equal(ChatMessageGroupKind.AssistantPlain, groups[0].Kind);
    }
}
