// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

public sealed class AgentRunResponseUpdateAGUIExtensionsTests
{
    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunStartedEvent_ToResponseUpdateWithMetadataAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("run1", updates[0].ResponseId);
        Assert.NotNull(updates[0].CreatedAt);
        // ConversationId is stored in the underlying ChatResponseUpdate
        ChatResponseUpdate chatUpdate = Assert.IsType<ChatResponseUpdate>(updates[0].RawRepresentation);
        Assert.Equal("thread1", chatUpdate.ConversationId);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunFinishedEvent_ToResponseUpdateWithMetadataAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1", Result = JsonSerializer.SerializeToElement("Success") }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        // First update is RunStarted
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("run1", updates[0].ResponseId);
        // Second update is RunFinished
        Assert.Equal(ChatRole.Assistant, updates[1].Role);
        Assert.Equal("run1", updates[1].ResponseId);
        Assert.NotNull(updates[1].CreatedAt);
        TextContent content = Assert.IsType<TextContent>(updates[1].Contents[0]);
        Assert.Equal("\"Success\"", content.Text); // JSON string representation includes quotes
        // ConversationId is stored in the underlying ChatResponseUpdate
        ChatResponseUpdate chatUpdate = Assert.IsType<ChatResponseUpdate>(updates[1].RawRepresentation);
        Assert.Equal("thread1", chatUpdate.ConversationId);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunErrorEvent_ToErrorContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunErrorEvent { Message = "Error occurred", Code = "ERR001" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        ErrorContent content = Assert.IsType<ErrorContent>(updates[0].Contents[0]);
        Assert.Equal("Error occurred", content.Message);
        // Code is stored in ErrorCode property
        Assert.Equal("ERR001", content.ErrorCode);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsTextMessageSequence_ToTextUpdatesWithCorrectRoleAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " World" },
            new TextMessageEndEvent { MessageId = "msg1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));
        Assert.Equal("Hello", ((TextContent)updates[0].Contents[0]).Text);
        Assert.Equal(" World", ((TextContent)updates[1].Contents[0]).Text);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithTextMessageStartWhileMessageInProgress_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.User }
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Intentionally empty - consuming stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithTextMessageEndForWrongMessageId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg2" }
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Intentionally empty - consuming stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_MaintainsMessageContext_AcrossMultipleContentEventsAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " " },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "World" },
            new TextMessageEndEvent { MessageId = "msg1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, updates.Count);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));
        Assert.All(updates, u => Assert.Equal("msg1", u.MessageId));
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsToolCallEvents_ToFunctionCallContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "GetWeather", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"location\":" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "\"Seattle\"}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        AgentRunResponseUpdate toolCallUpdate = updates.First(u => u.Contents.Any(c => c is FunctionCallContent));
        FunctionCallContent functionCall = Assert.IsType<FunctionCallContent>(toolCallUpdate.Contents[0]);
        Assert.Equal("call_1", functionCall.CallId);
        Assert.Equal("GetWeather", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("Seattle", functionCall.Arguments!["location"]?.ToString());
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithMultipleToolCallArgsEvents_AccumulatesArgsCorrectlyAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "TestTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"par" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "t1\":\"val" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "ue1\",\"part2" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "\":\"value2\"}" },
            new ToolCallEndEvent { ToolCallId = "call_1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        FunctionCallContent functionCall = updates
            .SelectMany(u => u.Contents)
            .OfType<FunctionCallContent>()
            .Single();
        Assert.Equal("value1", functionCall.Arguments!["part1"]?.ToString());
        Assert.Equal("value2", functionCall.Arguments!["part2"]?.ToString());
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithEmptyToolCallArgs_HandlesGracefullyAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "NoArgsTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "" },
            new ToolCallEndEvent { ToolCallId = "call_1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        FunctionCallContent functionCall = updates
            .SelectMany(u => u.Contents)
            .OfType<FunctionCallContent>()
            .Single();
        Assert.Equal("call_1", functionCall.CallId);
        Assert.Equal("NoArgsTool", functionCall.Name);
        Assert.Null(functionCall.Arguments);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithOverlappingToolCalls_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "Tool2", ParentMessageId = "msg1" } // Second start before first ends
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithMismatchedToolCallId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{}" } // Wrong call ID
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithMismatchedToolCallEndId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_2" } // Wrong call ID
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithMultipleSequentialToolCalls_ProcessesAllCorrectlyAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"arg1\":\"val1\"}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "Tool2", ParentMessageId = "msg2" },
            new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{\"arg2\":\"val2\"}" },
            new ToolCallEndEvent { ToolCallId = "call_2" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        List<FunctionCallContent> functionCalls = updates
            .SelectMany(u => u.Contents)
            .OfType<FunctionCallContent>()
            .ToList();
        Assert.Equal(2, functionCalls.Count);
        Assert.Equal("call_1", functionCalls[0].CallId);
        Assert.Equal("Tool1", functionCalls[0].Name);
        Assert.Equal("call_2", functionCalls[1].CallId);
        Assert.Equal("Tool2", functionCalls[1].Name);
    }
}
