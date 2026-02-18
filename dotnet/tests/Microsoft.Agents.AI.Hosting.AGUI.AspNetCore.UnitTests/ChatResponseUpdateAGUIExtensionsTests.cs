// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

public sealed class ChatResponseUpdateAGUIExtensionsTests
{
    [Fact]
    public async Task AsAGUIEventStreamAsync_YieldsRunStartedEvent_AtBeginningWithCorrectIdsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates = [];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);
        RunStartedEvent startEvent = Assert.IsType<RunStartedEvent>(events.First());
        Assert.Equal(ThreadId, startEvent.ThreadId);
        Assert.Equal(RunId, startEvent.RunId);
        Assert.Equal(AGUIEventTypes.RunStarted, startEvent.Type);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_YieldsRunFinishedEvent_AtEndWithCorrectIdsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates = [];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);
        RunFinishedEvent finishEvent = Assert.IsType<RunFinishedEvent>(events.Last());
        Assert.Equal(ThreadId, finishEvent.ThreadId);
        Assert.Equal(RunId, finishEvent.RunId);
        Assert.Equal(AGUIEventTypes.RunFinished, finishEvent.Type);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ConvertsTextContentUpdates_ToTextMessageEventsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, " World") { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.Contains(events, e => e is TextMessageStartEvent);
        Assert.Contains(events, e => e is TextMessageContentEvent);
        Assert.Contains(events, e => e is TextMessageEndEvent);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_GroupsConsecutiveUpdates_WithSameMessageIdAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        const string MessageId = "msg1";
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = MessageId },
            new ChatResponseUpdate(ChatRole.Assistant, " ") { MessageId = MessageId },
            new ChatResponseUpdate(ChatRole.Assistant, "World") { MessageId = MessageId }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageStartEvent> startEvents = events.OfType<TextMessageStartEvent>().ToList();
        List<TextMessageEndEvent> endEvents = events.OfType<TextMessageEndEvent>().ToList();
        Assert.Single(startEvents);
        Assert.Single(endEvents);
        Assert.Equal(MessageId, startEvents[0].MessageId);
        Assert.Equal(MessageId, endEvents[0].MessageId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithRoleChanges_EmitsProperTextMessageStartEventsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.User, "Hi") { MessageId = "msg2" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageStartEvent> startEvents = events.OfType<TextMessageStartEvent>().ToList();
        Assert.Equal(2, startEvents.Count);
        Assert.Equal("msg1", startEvents[0].MessageId);
        Assert.Equal("msg2", startEvents[1].MessageId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_EmitsTextMessageEndEvent_WhenMessageIdChangesAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "First") { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, "Second") { MessageId = "msg2" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageEndEvent> endEvents = events.OfType<TextMessageEndEvent>().ToList();
        Assert.NotEmpty(endEvents);
        Assert.Contains(endEvents, e => e.MessageId == "msg1");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithFunctionCallContent_EmitsToolCallEventsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        Dictionary<string, object?> arguments = new() { ["location"] = "Seattle", ["units"] = "fahrenheit" };
        FunctionCallContent functionCall = new("call_123", "GetWeather", arguments);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [functionCall]) { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        ToolCallStartEvent? startEvent = events.OfType<ToolCallStartEvent>().FirstOrDefault();
        Assert.NotNull(startEvent);
        Assert.Equal("call_123", startEvent.ToolCallId);
        Assert.Equal("GetWeather", startEvent.ToolCallName);
        Assert.Equal("msg1", startEvent.ParentMessageId);

        ToolCallArgsEvent? argsEvent = events.OfType<ToolCallArgsEvent>().FirstOrDefault();
        Assert.NotNull(argsEvent);
        Assert.Equal("call_123", argsEvent.ToolCallId);
        Assert.Contains("location", argsEvent.Delta);
        Assert.Contains("Seattle", argsEvent.Delta);

        ToolCallEndEvent? endEvent = events.OfType<ToolCallEndEvent>().FirstOrDefault();
        Assert.NotNull(endEvent);
        Assert.Equal("call_123", endEvent.ToolCallId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithMultipleFunctionCalls_EmitsAllToolCallEventsAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        FunctionCallContent call1 = new("call_1", "Tool1", new Dictionary<string, object?>());
        FunctionCallContent call2 = new("call_2", "Tool2", new Dictionary<string, object?>());
        ChatResponseUpdate response = new(ChatRole.Assistant, [call1, call2]) { MessageId = "msg1" };
        List<ChatResponseUpdate> updates = [response];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<ToolCallStartEvent> startEvents = events.OfType<ToolCallStartEvent>().ToList();
        Assert.Equal(2, startEvents.Count);
        Assert.Contains(startEvents, e => e.ToolCallId == "call_1" && e.ToolCallName == "Tool1");
        Assert.Contains(startEvents, e => e.ToolCallId == "call_2" && e.ToolCallName == "Tool2");

        List<ToolCallEndEvent> endEvents = events.OfType<ToolCallEndEvent>().ToList();
        Assert.Equal(2, endEvents.Count);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithFunctionCallWithNullArguments_EmitsEventsCorrectlyAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        FunctionCallContent functionCall = new("call_456", "NoArgsTool", null);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [functionCall]) { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.Contains(events, e => e is ToolCallStartEvent);
        Assert.Contains(events, e => e is ToolCallArgsEvent);
        Assert.Contains(events, e => e is ToolCallEndEvent);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithMixedContentTypes_EmitsAllEventTypesAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Text message") { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call_1", "Tool1", null)]) { MessageId = "msg2" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.Contains(events, e => e is RunStartedEvent);
        Assert.Contains(events, e => e is TextMessageStartEvent);
        Assert.Contains(events, e => e is TextMessageContentEvent);
        Assert.Contains(events, e => e is TextMessageEndEvent);
        Assert.Contains(events, e => e is ToolCallStartEvent);
        Assert.Contains(events, e => e is ToolCallArgsEvent);
        Assert.Contains(events, e => e is ToolCallEndEvent);
        Assert.Contains(events, e => e is RunFinishedEvent);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithFunctionResultContent_EmitsToolCallResultEventAsync()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        FunctionResultContent result = new("call_123", "Sunny, 72°F");
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [result]) { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        ToolCallResultEvent? resultEvent = events.OfType<ToolCallResultEvent>().FirstOrDefault();
        Assert.NotNull(resultEvent);
        Assert.Equal("call_123", resultEvent.ToolCallId);
        Assert.NotNull(resultEvent.MessageId);
        Assert.NotEmpty(resultEvent.MessageId);
        Assert.Equal(AGUIRoles.Tool, resultEvent.Role);
        Assert.Contains("Sunny", resultEvent.Content);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ConsecutiveToolCallResults_HaveDistinctMessageIdsAsync()
    {
        // Arrange — Issue #3962: MapAGUI reuses the same messageId for consecutive TOOL_CALL_RESULT SSE events
        // When an agent executes 2+ server-side tools, the FunctionResultContent items returned
        // in the same ChatResponseUpdate share the same MessageId. The AG-UI spec requires each
        // TOOL_CALL_RESULT event to have a distinct messageId.
        const string ThreadId = "thread1";
        const string RunId = "run1";
        const string SharedMessageId = "msg_shared";

        FunctionResultContent result1 = new("call_1", "Sunny, 72°F");
        FunctionResultContent result2 = new("call_2", "3:45 PM");

        // Both results come from the same ChatResponseUpdate with the same MessageId
        // (this is what happens when the LLM returns multiple tool results in one response)
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [result1, result2]) { MessageId = SharedMessageId }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<ToolCallResultEvent> toolCallResultEvents = events.OfType<ToolCallResultEvent>().ToList();
        Assert.Equal(2, toolCallResultEvents.Count);

        // Each TOOL_CALL_RESULT must have a distinct, non-null messageId
        Assert.All(toolCallResultEvents, e => Assert.NotNull(e.MessageId));
        Assert.All(toolCallResultEvents, e => Assert.NotEmpty(e.MessageId!));
        Assert.NotEqual(toolCallResultEvents[0].MessageId, toolCallResultEvents[1].MessageId);

        // Verify the tool call IDs are preserved correctly
        Assert.Contains(toolCallResultEvents, e => e.ToolCallId == "call_1");
        Assert.Contains(toolCallResultEvents, e => e.ToolCallId == "call_2");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ToolCallResultsFromSeparateUpdates_HaveDistinctMessageIdsAsync()
    {
        // Arrange — Variant of #3962: tool results arriving in separate ChatResponseUpdate objects
        // but with the same MessageId should still get distinct messageIds in the SSE events.
        const string ThreadId = "thread1";
        const string RunId = "run1";
        const string SharedMessageId = "msg_shared";

        FunctionResultContent result1 = new("call_1", "Sunny");
        FunctionResultContent result2 = new("call_2", "3:45 PM");

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [result1]) { MessageId = SharedMessageId },
            new ChatResponseUpdate(ChatRole.Tool, [result2]) { MessageId = SharedMessageId }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<ToolCallResultEvent> toolCallResultEvents = events.OfType<ToolCallResultEvent>().ToList();
        Assert.Equal(2, toolCallResultEvents.Count);

        Assert.All(toolCallResultEvents, e => Assert.NotNull(e.MessageId));
        Assert.All(toolCallResultEvents, e => Assert.NotEmpty(e.MessageId!));
        Assert.NotEqual(toolCallResultEvents[0].MessageId, toolCallResultEvents[1].MessageId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ThreeConsecutiveToolCallResults_AllHaveUniqueMessageIdsAsync()
    {
        // Arrange — Edge case: 3+ consecutive tool call results
        const string ThreadId = "thread1";
        const string RunId = "run1";

        FunctionResultContent result1 = new("call_1", "Result 1");
        FunctionResultContent result2 = new("call_2", "Result 2");
        FunctionResultContent result3 = new("call_3", "Result 3");

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [result1, result2, result3]) { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<ToolCallResultEvent> toolCallResultEvents = events.OfType<ToolCallResultEvent>().ToList();
        Assert.Equal(3, toolCallResultEvents.Count);

        // All messageIds must be distinct
        HashSet<string?> uniqueMessageIds = new(toolCallResultEvents.Select(e => e.MessageId));
        Assert.Equal(toolCallResultEvents.Count, uniqueMessageIds.Count);

        // All must be non-null/non-empty
        Assert.All(toolCallResultEvents, e =>
        {
            Assert.NotNull(e.MessageId);
            Assert.NotEmpty(e.MessageId!);
        });
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_SingleToolCallResult_HasValidMessageIdAsync()
    {
        // Arrange — Single tool call result should still get a valid messageId
        const string ThreadId = "thread1";
        const string RunId = "run1";

        FunctionResultContent result = new("call_1", "Result 1");
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [result]) { MessageId = "msg1" }
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        ToolCallResultEvent? resultEvent = events.OfType<ToolCallResultEvent>().Single();
        Assert.NotNull(resultEvent.MessageId);
        Assert.NotEmpty(resultEvent.MessageId);
    }
}
