// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

public sealed class ChatResponseUpdateAGUIExtensionsTests
{
    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsRunStartedEvent_ToResponseUpdateWithMetadataAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("run1", updates[0].ResponseId);
        Assert.NotNull(updates[0].CreatedAt);
        Assert.Equal("thread1", updates[0].ConversationId);
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsRunFinishedEvent_ToResponseUpdateWithMetadataAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1", Result = JsonSerializer.SerializeToElement("Success") }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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
        // ConversationId is stored in the ChatResponseUpdate
        Assert.Equal("thread1", updates[1].ConversationId);
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsRunErrorEvent_ToErrorContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunErrorEvent { Message = "Error occurred", Code = "ERR001" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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
    public async Task AsChatResponseUpdatesAsync_ConvertsTextMessageSequence_ToTextUpdatesWithCorrectRoleAsync()
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
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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
    public async Task AsChatResponseUpdatesAsync_WithTextMessageStartWhileMessageInProgress_ThrowsInvalidOperationExceptionAsync()
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
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Intentionally empty - consuming stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithTextMessageEndForWrongMessageId_ThrowsInvalidOperationExceptionAsync()
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
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Intentionally empty - consuming stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_MaintainsMessageContext_AcrossMultipleContentEventsAsync()
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
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, updates.Count);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));
        Assert.All(updates, u => Assert.Equal("msg1", u.MessageId));
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsToolCallEvents_ToFunctionCallContentAsync()
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
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate toolCallUpdate = updates.First(u => u.Contents.Any(c => c is FunctionCallContent));
        FunctionCallContent functionCall = Assert.IsType<FunctionCallContent>(toolCallUpdate.Contents[0]);
        Assert.Equal("call_1", functionCall.CallId);
        Assert.Equal("GetWeather", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("Seattle", functionCall.Arguments!["location"]?.ToString());
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithMultipleToolCallArgsEvents_AccumulatesArgsCorrectlyAsync()
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
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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
    public async Task AsChatResponseUpdatesAsync_WithEmptyToolCallArgs_HandlesGracefullyAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "NoArgsTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "" },
            new ToolCallEndEvent { ToolCallId = "call_1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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
    public async Task AsChatResponseUpdatesAsync_WithOverlappingToolCalls_ThrowsInvalidOperationExceptionAsync()
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
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Consume stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithMismatchedToolCallId_ThrowsInvalidOperationExceptionAsync()
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
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Consume stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithMismatchedToolCallEndId_ThrowsInvalidOperationExceptionAsync()
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
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
            {
                // Consume stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithMultipleSequentialToolCalls_ProcessesAllCorrectlyAsync()
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
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
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

    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsStateSnapshotEvent_ToDataContentWithJsonAsync()
    {
        // Arrange
        JsonElement stateSnapshot = JsonSerializer.SerializeToElement(new { counter = 42, status = "active" });
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateSnapshotEvent { Snapshot = stateSnapshot },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate stateUpdate = updates.First(u => u.Contents.Any(c => c is DataContent));
        Assert.Equal(ChatRole.Assistant, stateUpdate.Role);
        Assert.Equal("thread1", stateUpdate.ConversationId);
        Assert.Equal("run1", stateUpdate.ResponseId);

        DataContent dataContent = Assert.IsType<DataContent>(stateUpdate.Contents[0]);
        Assert.Equal("application/json", dataContent.MediaType);

        // Verify the JSON content
        string jsonText = System.Text.Encoding.UTF8.GetString(dataContent.Data.ToArray());
        JsonElement deserializedState = JsonElement.Parse(jsonText);
        Assert.Equal(42, deserializedState.GetProperty("counter").GetInt32());
        Assert.Equal("active", deserializedState.GetProperty("status").GetString());

        // Verify additional properties
        Assert.NotNull(stateUpdate.AdditionalProperties);
        Assert.True((bool)stateUpdate.AdditionalProperties["is_state_snapshot"]!);
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithNullStateSnapshot_DoesNotEmitUpdateAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateSnapshotEvent { Snapshot = null },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.DoesNotContain(updates, u => u.Contents.Any(c => c is DataContent));
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithEmptyObjectStateSnapshot_EmitsDataContentAsync()
    {
        // Arrange
        JsonElement emptyState = JsonSerializer.SerializeToElement(new { });
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateSnapshotEvent { Snapshot = emptyState },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate stateUpdate = updates.First(u => u.Contents.Any(c => c is DataContent));
        DataContent dataContent = Assert.IsType<DataContent>(stateUpdate.Contents[0]);
        string jsonText = System.Text.Encoding.UTF8.GetString(dataContent.Data.ToArray());
        Assert.Equal("{}", jsonText);
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithComplexStateSnapshot_PreservesJsonStructureAsync()
    {
        // Arrange
        var complexState = new
        {
            user = new { name = "Alice", age = 30 },
            items = new[] { "item1", "item2", "item3" },
            metadata = new { timestamp = "2024-01-01T00:00:00Z", version = 2 }
        };
        JsonElement stateSnapshot = JsonSerializer.SerializeToElement(complexState);
        List<BaseEvent> events =
        [
            new StateSnapshotEvent { Snapshot = stateSnapshot }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate stateUpdate = updates.First();
        DataContent dataContent = Assert.IsType<DataContent>(stateUpdate.Contents[0]);
        string jsonText = System.Text.Encoding.UTF8.GetString(dataContent.Data.ToArray());
        JsonElement roundTrippedState = JsonElement.Parse(jsonText);

        Assert.Equal("Alice", roundTrippedState.GetProperty("user").GetProperty("name").GetString());
        Assert.Equal(30, roundTrippedState.GetProperty("user").GetProperty("age").GetInt32());
        Assert.Equal(3, roundTrippedState.GetProperty("items").GetArrayLength());
        Assert.Equal("item1", roundTrippedState.GetProperty("items")[0].GetString());
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithStateSnapshotAndTextMessages_EmitsBothAsync()
    {
        // Arrange
        JsonElement state = JsonSerializer.SerializeToElement(new { step = 1 });
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Processing..." },
            new TextMessageEndEvent { MessageId = "msg1" },
            new StateSnapshotEvent { Snapshot = state },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Contains(updates, u => u.Contents.Any(c => c is TextContent));
        Assert.Contains(updates, u => u.Contents.Any(c => c is DataContent));
    }

    #region State Delta Tests

    [Fact]
    public async Task AsChatResponseUpdatesAsync_ConvertsStateDeltaEvent_ToDataContentWithJsonPatchAsync()
    {
        // Arrange - Create JSON Patch operations (RFC 6902)
        JsonElement stateDelta = JsonSerializer.SerializeToElement(new object[]
        {
            new { op = "replace", path = "/counter", value = 43 },
            new { op = "add", path = "/newField", value = "test" }
        });
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateDeltaEvent { Delta = stateDelta },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate deltaUpdate = updates.First(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json-patch+json"));
        Assert.Equal(ChatRole.Assistant, deltaUpdate.Role);
        Assert.Equal("thread1", deltaUpdate.ConversationId);
        Assert.Equal("run1", deltaUpdate.ResponseId);

        DataContent dataContent = Assert.IsType<DataContent>(deltaUpdate.Contents[0]);
        Assert.Equal("application/json-patch+json", dataContent.MediaType);

        // Verify the JSON Patch content
        string jsonText = System.Text.Encoding.UTF8.GetString(dataContent.Data.ToArray());
        JsonElement deserializedDelta = JsonElement.Parse(jsonText);
        Assert.Equal(JsonValueKind.Array, deserializedDelta.ValueKind);
        Assert.Equal(2, deserializedDelta.GetArrayLength());

        // Verify first operation
        JsonElement firstOp = deserializedDelta[0];
        Assert.Equal("replace", firstOp.GetProperty("op").GetString());
        Assert.Equal("/counter", firstOp.GetProperty("path").GetString());
        Assert.Equal(43, firstOp.GetProperty("value").GetInt32());

        // Verify second operation
        JsonElement secondOp = deserializedDelta[1];
        Assert.Equal("add", secondOp.GetProperty("op").GetString());
        Assert.Equal("/newField", secondOp.GetProperty("path").GetString());
        Assert.Equal("test", secondOp.GetProperty("value").GetString());

        // Verify additional properties
        Assert.NotNull(deltaUpdate.AdditionalProperties);
        Assert.True((bool)deltaUpdate.AdditionalProperties["is_state_delta"]!);
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithNullStateDelta_DoesNotEmitUpdateAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateDeltaEvent { Delta = null },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert - Only run started and finished should be present
        Assert.Equal(2, updates.Count);
        Assert.IsType<ChatResponseUpdate>(updates[0]); // Run started
        Assert.IsType<ChatResponseUpdate>(updates[1]); // Run finished
        Assert.DoesNotContain(updates, u => u.Contents.Any(c => c is DataContent));
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithEmptyStateDelta_EmitsUpdateAsync()
    {
        // Arrange - Empty JSON Patch array is valid
        JsonElement emptyDelta = JsonSerializer.SerializeToElement(Array.Empty<object>());
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateDeltaEvent { Delta = emptyDelta },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Contains(updates, u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json-patch+json"));
    }

    [Fact]
    public async Task AsChatResponseUpdatesAsync_WithMultipleStateDeltaEvents_ConvertsAllAsync()
    {
        // Arrange
        JsonElement delta1 = JsonSerializer.SerializeToElement(new[] { new { op = "replace", path = "/counter", value = 1 } });
        JsonElement delta2 = JsonSerializer.SerializeToElement(new[] { new { op = "replace", path = "/counter", value = 2 } });
        JsonElement delta3 = JsonSerializer.SerializeToElement(new[] { new { op = "replace", path = "/counter", value = 3 } });

        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateDeltaEvent { Delta = delta1 },
            new StateDeltaEvent { Delta = delta2 },
            new StateDeltaEvent { Delta = delta3 },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        // Assert
        var deltaUpdates = updates.Where(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json-patch+json")).ToList();
        Assert.Equal(3, deltaUpdates.Count);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ConvertsDataContentWithJsonPatch_ToStateDeltaEventAsync()
    {
        // Arrange - Create a ChatResponseUpdate with JSON Patch DataContent
        JsonElement patchOps = JsonSerializer.SerializeToElement(new object[]
        {
            new { op = "remove", path = "/oldField" },
            new { op = "add", path = "/newField", value = "newValue" }
        });
        byte[] jsonBytes = JsonSerializer.SerializeToUtf8Bytes(patchOps);
        DataContent dataContent = new(jsonBytes, "application/json-patch+json");

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [dataContent])
            {
                MessageId = "msg1"
            }
        ];

        // Act
        List<BaseEvent> outputEvents = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync("thread1", "run1", AGUIJsonSerializerContext.Default.Options))
        {
            outputEvents.Add(evt);
        }

        // Assert
        StateDeltaEvent? deltaEvent = outputEvents.OfType<StateDeltaEvent>().FirstOrDefault();
        Assert.NotNull(deltaEvent);
        Assert.NotNull(deltaEvent.Delta);
        Assert.Equal(JsonValueKind.Array, deltaEvent.Delta.Value.ValueKind);

        // Verify patch operations
        JsonElement delta = deltaEvent.Delta.Value;
        Assert.Equal(2, delta.GetArrayLength());
        Assert.Equal("remove", delta[0].GetProperty("op").GetString());
        Assert.Equal("/oldField", delta[0].GetProperty("path").GetString());
        Assert.Equal("add", delta[1].GetProperty("op").GetString());
        Assert.Equal("/newField", delta[1].GetProperty("path").GetString());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithBothSnapshotAndDelta_EmitsBothEventsAsync()
    {
        // Arrange
        JsonElement snapshot = JsonSerializer.SerializeToElement(new { counter = 0 });
        byte[] snapshotBytes = JsonSerializer.SerializeToUtf8Bytes(snapshot);
        DataContent snapshotContent = new(snapshotBytes, "application/json");

        JsonElement delta = JsonSerializer.SerializeToElement(new[] { new { op = "replace", path = "/counter", value = 1 } });
        byte[] deltaBytes = JsonSerializer.SerializeToUtf8Bytes(delta);
        DataContent deltaContent = new(deltaBytes, "application/json-patch+json");

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [snapshotContent]) { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, [deltaContent]) { MessageId = "msg2" }
        ];

        // Act
        List<BaseEvent> outputEvents = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync("thread1", "run1", AGUIJsonSerializerContext.Default.Options))
        {
            outputEvents.Add(evt);
        }

        // Assert
        Assert.Contains(outputEvents, e => e is StateSnapshotEvent);
        Assert.Contains(outputEvents, e => e is StateDeltaEvent);
    }

    [Fact]
    public async Task StateDeltaEvent_RoundTrip_PreservesJsonPatchOperationsAsync()
    {
        // Arrange - Create complex JSON Patch with various operations
        JsonElement originalDelta = JsonSerializer.SerializeToElement(new object[]
        {
            new { op = "add", path = "/user/email", value = "test@example.com" },
            new { op = "remove", path = "/user/tempData" },
            new { op = "replace", path = "/user/lastLogin", value = "2025-11-09T12:00:00Z" },
            new { op = "move", from = "/user/oldAddress", path = "/user/previousAddress" },
            new { op = "copy", from = "/user/name", path = "/user/displayName" },
            new { op = "test", path = "/user/version", value = 2 }
        });

        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateDeltaEvent { Delta = originalDelta },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act - Convert to ChatResponseUpdate and back to events
        List<ChatResponseUpdate> updates = [];
        await foreach (ChatResponseUpdate update in events.ToAsyncEnumerableAsync().AsChatResponseUpdatesAsync(AGUIJsonSerializerContext.Default.Options))
        {
            updates.Add(update);
        }

        List<BaseEvent> roundTripEvents = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync("thread1", "run1", AGUIJsonSerializerContext.Default.Options))
        {
            roundTripEvents.Add(evt);
        }

        // Assert
        StateDeltaEvent? roundTripDelta = roundTripEvents.OfType<StateDeltaEvent>().FirstOrDefault();
        Assert.NotNull(roundTripDelta);
        Assert.NotNull(roundTripDelta.Delta);

        JsonElement delta = roundTripDelta.Delta.Value;
        Assert.Equal(6, delta.GetArrayLength());

        // Verify each operation type
        Assert.Equal("add", delta[0].GetProperty("op").GetString());
        Assert.Equal("remove", delta[1].GetProperty("op").GetString());
        Assert.Equal("replace", delta[2].GetProperty("op").GetString());
        Assert.Equal("move", delta[3].GetProperty("op").GetString());
        Assert.Equal("copy", delta[4].GetProperty("op").GetString());
        Assert.Equal("test", delta[5].GetProperty("op").GetString());
    }

    #endregion State Delta Tests

    #region AsAGUIEventStreamAsync Protocol Conformance Tests

    // ---- Helpers ----

    private static async Task<List<BaseEvent>> RunStreamAsync(
        IEnumerable<ChatResponseUpdate> updates,
        string threadId = "thread1",
        string runId = "run1")
    {
        var events = new List<BaseEvent>();
        await foreach (BaseEvent evt in updates
            .ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync(threadId, runId, AGUIJsonSerializerContext.Default.Options))
        {
            events.Add(evt);
        }
        return events;
    }

    /// <summary>Builds a tool-metadata JsonObject that points to a ui:// resource URI.</summary>
    private static JsonObject BuildToolMetadata(string resourceUri) =>
        new() { ["ui"] = new JsonObject { ["resourceUri"] = resourceUri } };

    // ---- Lifecycle ----

    [Fact]
    public async Task AsAGUIEventStreamAsync_FirstEvent_IsRunStartedAsync()
    {
        List<BaseEvent> events = await RunStreamAsync([]);
        Assert.IsType<RunStartedEvent>(events[0]);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_LastEvent_IsRunFinishedAsync()
    {
        List<BaseEvent> events = await RunStreamAsync([]);
        Assert.IsType<RunFinishedEvent>(events[^1]);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_RunStartedEvent_EchoesThreadIdAndRunIdAsync()
    {
        List<BaseEvent> events = await RunStreamAsync([], "my-thread", "my-run");
        var runStarted = Assert.IsType<RunStartedEvent>(events[0]);
        Assert.Equal("my-thread", runStarted.ThreadId);
        Assert.Equal("my-run", runStarted.RunId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_RunFinishedEvent_EchoesThreadIdAndRunIdAsync()
    {
        List<BaseEvent> events = await RunStreamAsync([], "my-thread", "my-run");
        var runFinished = Assert.IsType<RunFinishedEvent>(events[^1]);
        Assert.Equal("my-thread", runFinished.ThreadId);
        Assert.Equal("my-run", runFinished.RunId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_NormalFlow_ContainsNoRunErrorAsync()
    {
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("hi")]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);
        Assert.DoesNotContain(events, e => e is RunErrorEvent);
    }

    // ---- Tool call ordering ----

    [Fact]
    public async Task AsAGUIEventStreamAsync_FunctionCallContent_EmitsToolCallStartArgsDeltaEndInOrderAsync()
    {
        var functionCall = new FunctionCallContent("call_1", "get-time", null);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [functionCall]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        int startIdx = events.FindIndex(e => e is ToolCallStartEvent);
        int argsIdx = events.FindIndex(e => e is ToolCallArgsEvent);
        int endIdx = events.FindIndex(e => e is ToolCallEndEvent);

        Assert.True(startIdx >= 0, "Expected TOOL_CALL_START");
        Assert.True(argsIdx > startIdx, "TOOL_CALL_ARGS must follow TOOL_CALL_START");
        Assert.True(endIdx > argsIdx, "TOOL_CALL_END must follow TOOL_CALL_ARGS");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_FunctionCallContent_ToolCallIdIsConsistentAcrossStartArgsDeltaEndAsync()
    {
        var functionCall = new FunctionCallContent("call_1", "get-time", null);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [functionCall]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        var start = events.OfType<ToolCallStartEvent>().Single();
        var args = events.OfType<ToolCallArgsEvent>().Single();
        var end = events.OfType<ToolCallEndEvent>().Single();

        Assert.Equal(start.ToolCallId, args.ToolCallId);
        Assert.Equal(start.ToolCallId, end.ToolCallId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_FullToolCallSequence_ToolCallResultAppearsAfterToolCallEndAsync()
    {
        var functionCall = new FunctionCallContent("call_1", "get-time", null);
        var functionResult = new FunctionResultContent("call_1", new TextContent("2026-04-10T18:00:00Z"));
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [functionCall]) { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Tool, [functionResult]) { MessageId = "msg2" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        int endIdx = events.FindIndex(e => e is ToolCallEndEvent);
        int resultIdx = events.FindIndex(e => e is ToolCallResultEvent);

        Assert.True(endIdx >= 0, "Expected TOOL_CALL_END");
        Assert.True(resultIdx > endIdx, "TOOL_CALL_RESULT must come after TOOL_CALL_END");
    }

    // ---- TOOL_CALL_RESULT content format ----

    [Fact]
    public async Task AsAGUIEventStreamAsync_FunctionResultWithTextContent_ContentIsJsonEncodedStringAsync()
    {
        const string Timestamp = "2026-04-10T18:27:48Z";
        var functionResult = new FunctionResultContent("call_1", new TextContent(Timestamp));
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [functionResult]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        ToolCallResultEvent result = events.OfType<ToolCallResultEvent>().Single();
        // TextContent is serialized as a JSON-encoded string so Content is always valid JSON.
        using var doc = JsonDocument.Parse(result.Content!);
        Assert.Equal(JsonValueKind.String, doc.RootElement.ValueKind);
        Assert.Equal(Timestamp, doc.RootElement.GetString());
    }

    // ---- Activity snapshot ----

    [Fact]
    public async Task AsAGUIEventStreamAsync_FunctionResultWithToolMetadata_EmitsActivitySnapshotAfterResultAsync()
    {
        var textContent = new TextContent("2026-04-10T18:27:48Z")
        {
            AdditionalProperties = new() { ["ToolMetadata"] = BuildToolMetadata("ui://get-time.html") }
        };
        var functionResult = new FunctionResultContent("call_1", textContent);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [functionResult]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        int resultIdx = events.FindIndex(e => e is ToolCallResultEvent);
        int snapshotIdx = events.FindIndex(e => e is ActivitySnapshotEvent);

        Assert.True(resultIdx >= 0, "Expected TOOL_CALL_RESULT");
        Assert.True(snapshotIdx > resultIdx, "ACTIVITY_SNAPSHOT must follow TOOL_CALL_RESULT");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ActivitySnapshot_HasMcpAppsActivityTypeAndResourceUriAsync()
    {
        const string ResourceUri = "ui://get-time.html";
        var textContent = new TextContent("2026-04-10T18:27:48Z")
        {
            AdditionalProperties = new() { ["ToolMetadata"] = BuildToolMetadata(ResourceUri) }
        };
        var functionResult = new FunctionResultContent("call_1", textContent);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [functionResult]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        ActivitySnapshotEvent snapshot = Assert.IsType<ActivitySnapshotEvent>(
            events.Single(e => e is ActivitySnapshotEvent));

        Assert.Equal("mcp-apps", snapshot.ActivityType);
        Assert.True(snapshot.Replace);
        Assert.NotNull(snapshot.Content);
        Assert.Equal(ResourceUri, snapshot.Content.Value.GetProperty("resourceUri").GetString());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ActivitySnapshot_ResultContainsTextContentItemAsync()
    {
        const string Timestamp = "2026-04-10T18:27:48Z";
        const string ResourceUri = "ui://get-time.html";
        var textContent = new TextContent(Timestamp)
        {
            AdditionalProperties = new() { ["ToolMetadata"] = BuildToolMetadata(ResourceUri) }
        };
        var functionResult = new FunctionResultContent("call_1", textContent);
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Tool, [functionResult]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        ActivitySnapshotEvent snapshot = (ActivitySnapshotEvent)events.Single(e => e is ActivitySnapshotEvent);
        JsonElement resultContent = snapshot.Content!.Value
            .GetProperty("result")
            .GetProperty("content");

        Assert.Equal(JsonValueKind.Array, resultContent.ValueKind);
        JsonElement textItem = resultContent.EnumerateArray()
            .First(i => i.TryGetProperty("type", out var t) && t.GetString() == "text");
        Assert.Equal(Timestamp, textItem.GetProperty("text").GetString());
    }

    // ---- Text message nesting ----

    [Fact]
    public async Task AsAGUIEventStreamAsync_TextContent_EmitsProperlyNestedTextMessageEventsAsync()
    {
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("Hello")]) { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent(" World")]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        int startIdx = events.FindIndex(e => e is TextMessageStartEvent);
        int endIdx = events.FindLastIndex(e => e is TextMessageEndEvent);

        Assert.True(startIdx >= 0, "Expected TEXT_MESSAGE_START");
        Assert.True(endIdx > startIdx, "TEXT_MESSAGE_END must follow TEXT_MESSAGE_START");

        for (int i = 0; i < events.Count; i++)
        {
            if (events[i] is TextMessageContentEvent)
            {
                Assert.True(
                    i > startIdx && i < endIdx,
                    $"TEXT_MESSAGE_CONTENT at index {i} is outside START ({startIdx}) / END ({endIdx})");
            }
        }
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_TextContent_StartAndEndCountsMatchAsync()
    {
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("A")]) { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("B")]) { MessageId = "msg1" },
            new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("C")]) { MessageId = "msg1" }
        ];
        List<BaseEvent> events = await RunStreamAsync(updates);

        int starts = events.Count(e => e is TextMessageStartEvent);
        int ends = events.Count(e => e is TextMessageEndEvent);
        Assert.Equal(starts, ends);
    }

    #endregion AsAGUIEventStreamAsync Protocol Conformance Tests
}
