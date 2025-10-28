// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.AGUI.Shared;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIJsonSerializerContext"/> class and JSON serialization.
/// </summary>
public sealed class AGUIJsonSerializerContextTests
{
    [Fact]
    public void RunAgentInput_Serializes_WithAllRequiredFields()
    {
        // Arrange
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "Test" }]
        };

        // Act
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.Contains("\"threadId\":\"thread1\"", json);
        Assert.Contains("\"runId\":\"run1\"", json);
        Assert.Contains("\"messages\"", json);
    }

    [Fact]
    public void RunAgentInput_Deserializes_FromJsonWithRequiredFields()
    {
        // Arrange
        const string Json = """
            {
                "threadId": "thread1",
                "runId": "run1",
                "messages": [
                    {
                        "id": "m1",
                        "role": "user",
                        "content": "Test"
                    }
                ]
            }
            """;

        // Act
        RunAgentInput? input = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.NotNull(input);
        Assert.Equal("thread1", input.ThreadId);
        Assert.Equal("run1", input.RunId);
        Assert.Single(input.Messages);
    }

    [Fact]
    public void RunAgentInput_HandlesOptionalFields_StateContextAndForwardedProperties()
    {
        // Arrange
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "Test" }],
            State = JsonSerializer.SerializeToElement(new { key = "value" }),
            Context = new Dictionary<string, string> { ["ctx1"] = "value1" },
            ForwardedProperties = JsonSerializer.SerializeToElement(new { prop1 = "val1" })
        };

        // Act
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        RunAgentInput? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.NotNull(deserialized);
        Assert.NotEqual(JsonValueKind.Undefined, deserialized.State.ValueKind);
        Assert.Single(deserialized.Context);
        Assert.NotEqual(JsonValueKind.Undefined, deserialized.ForwardedProperties.ValueKind);
    }

    [Fact]
    public void RunAgentInput_ValidatesMinimumMessageCount_MinLengthOne()
    {
        // Arrange
        const string Json = """
            {
                "threadId": "thread1",
                "runId": "run1",
                "messages": []
            }
            """;

        // Act
        RunAgentInput? input = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.NotNull(input);
        Assert.Empty(input.Messages);
    }

    [Fact]
    public void RunAgentInput_RoundTrip_PreservesAllData()
    {
        // Arrange
        RunAgentInput original = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages =
            [
                new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "First" },
                new AGUIMessage { Id = "m2", Role = AGUIRoles.Assistant, Content = "Second" }
            ],
            Context = new Dictionary<string, string> { ["key1"] = "value1", ["key2"] = "value2" }
        };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunAgentInput);
        RunAgentInput? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.RunId, deserialized.RunId);
        Assert.Equal(2, deserialized.Messages.Count());
        Assert.Equal(2, deserialized.Context.Count);
    }

    [Fact]
    public void RunStartedEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        RunStartedEvent evt = new() { ThreadId = "thread1", RunId = "run1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunStartedEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.RunStarted}\"", json);
    }

    [Fact]
    public void RunStartedEvent_Includes_ThreadIdAndRunIdInOutput()
    {
        // Arrange
        RunStartedEvent evt = new() { ThreadId = "thread1", RunId = "run1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunStartedEvent);

        // Assert
        Assert.Contains("\"threadId\":\"thread1\"", json);
        Assert.Contains("\"runId\":\"run1\"", json);
    }

    [Fact]
    public void RunStartedEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_STARTED",
                "threadId": "thread1",
                "runId": "run1"
            }
            """;

        // Act
        RunStartedEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.RunStartedEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("thread1", evt.ThreadId);
        Assert.Equal("run1", evt.RunId);
    }

    [Fact]
    public void RunStartedEvent_RoundTrip_PreservesData()
    {
        // Arrange
        RunStartedEvent original = new() { ThreadId = "thread123", RunId = "run456" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunStartedEvent);
        RunStartedEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunStartedEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.RunId, deserialized.RunId);
        Assert.Equal(original.Type, deserialized.Type);
    }

    [Fact]
    public void RunFinishedEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        RunFinishedEvent evt = new() { ThreadId = "thread1", RunId = "run1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunFinishedEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.RunFinished}\"", json);
    }

    [Fact]
    public void RunFinishedEvent_Includes_ThreadIdRunIdAndOptionalResult()
    {
        // Arrange
        RunFinishedEvent evt = new() { ThreadId = "thread1", RunId = "run1", Result = "Success" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunFinishedEvent);

        // Assert
        Assert.Contains("\"threadId\":\"thread1\"", json);
        Assert.Contains("\"runId\":\"run1\"", json);
        Assert.Contains("\"result\":\"Success\"", json);
    }

    [Fact]
    public void RunFinishedEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_FINISHED",
                "threadId": "thread1",
                "runId": "run1",
                "result": "Complete"
            }
            """;

        // Act
        RunFinishedEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.RunFinishedEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("thread1", evt.ThreadId);
        Assert.Equal("run1", evt.RunId);
        Assert.Equal("Complete", evt.Result);
    }

    [Fact]
    public void RunFinishedEvent_RoundTrip_PreservesData()
    {
        // Arrange
        RunFinishedEvent original = new() { ThreadId = "thread1", RunId = "run1", Result = "Done" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunFinishedEvent);
        RunFinishedEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunFinishedEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.RunId, deserialized.RunId);
        Assert.Equal(original.Result, deserialized.Result);
    }

    [Fact]
    public void RunErrorEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        RunErrorEvent evt = new() { Message = "Error occurred" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunErrorEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.RunError}\"", json);
    }

    [Fact]
    public void RunErrorEvent_Includes_MessageAndOptionalCode()
    {
        // Arrange
        RunErrorEvent evt = new() { Message = "Error occurred", Code = "ERR001" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunErrorEvent);

        // Assert
        Assert.Contains("\"message\":\"Error occurred\"", json);
        Assert.Contains("\"code\":\"ERR001\"", json);
    }

    [Fact]
    public void RunErrorEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_ERROR",
                "message": "Something went wrong",
                "code": "ERR123"
            }
            """;

        // Act
        RunErrorEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.RunErrorEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("Something went wrong", evt.Message);
        Assert.Equal("ERR123", evt.Code);
    }

    [Fact]
    public void RunErrorEvent_RoundTrip_PreservesData()
    {
        // Arrange
        RunErrorEvent original = new() { Message = "Test error", Code = "TEST001" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunErrorEvent);
        RunErrorEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunErrorEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.Message, deserialized.Message);
        Assert.Equal(original.Code, deserialized.Code);
    }

    [Fact]
    public void TextMessageStartEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        TextMessageStartEvent evt = new() { MessageId = "msg1", Role = AGUIRoles.Assistant };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageStartEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.TextMessageStart}\"", json);
    }

    [Fact]
    public void TextMessageStartEvent_Includes_MessageIdAndRole()
    {
        // Arrange
        TextMessageStartEvent evt = new() { MessageId = "msg1", Role = AGUIRoles.Assistant };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageStartEvent);

        // Assert
        Assert.Contains("\"messageId\":\"msg1\"", json);
        Assert.Contains($"\"role\":\"{AGUIRoles.Assistant}\"", json);
    }

    [Fact]
    public void TextMessageStartEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_START",
                "messageId": "msg1",
                "role": "assistant"
            }
            """;

        // Act
        TextMessageStartEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.TextMessageStartEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("msg1", evt.MessageId);
        Assert.Equal(AGUIRoles.Assistant, evt.Role);
    }

    [Fact]
    public void TextMessageStartEvent_RoundTrip_PreservesData()
    {
        // Arrange
        TextMessageStartEvent original = new() { MessageId = "msg123", Role = AGUIRoles.User };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.TextMessageStartEvent);
        TextMessageStartEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.TextMessageStartEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.MessageId, deserialized.MessageId);
        Assert.Equal(original.Role, deserialized.Role);
    }

    [Fact]
    public void TextMessageContentEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        TextMessageContentEvent evt = new() { MessageId = "msg1", Delta = "Hello" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageContentEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.TextMessageContent}\"", json);
    }

    [Fact]
    public void TextMessageContentEvent_Includes_MessageIdAndDelta()
    {
        // Arrange
        TextMessageContentEvent evt = new() { MessageId = "msg1", Delta = "Hello World" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageContentEvent);

        // Assert
        Assert.Contains("\"messageId\":\"msg1\"", json);
        Assert.Contains("\"delta\":\"Hello World\"", json);
    }

    [Fact]
    public void TextMessageContentEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": "msg1",
                "delta": "Test content"
            }
            """;

        // Act
        TextMessageContentEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.TextMessageContentEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("msg1", evt.MessageId);
        Assert.Equal("Test content", evt.Delta);
    }

    [Fact]
    public void TextMessageContentEvent_RoundTrip_PreservesData()
    {
        // Arrange
        TextMessageContentEvent original = new() { MessageId = "msg456", Delta = "Sample text" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.TextMessageContentEvent);
        TextMessageContentEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.TextMessageContentEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.MessageId, deserialized.MessageId);
        Assert.Equal(original.Delta, deserialized.Delta);
    }

    [Fact]
    public void TextMessageEndEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        TextMessageEndEvent evt = new() { MessageId = "msg1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageEndEvent);

        // Assert
        Assert.Contains($"\"type\":\"{AGUIEventTypes.TextMessageEnd}\"", json);
    }

    [Fact]
    public void TextMessageEndEvent_Includes_MessageId()
    {
        // Arrange
        TextMessageEndEvent evt = new() { MessageId = "msg1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageEndEvent);

        // Assert
        Assert.Contains("\"messageId\":\"msg1\"", json);
    }

    [Fact]
    public void TextMessageEndEvent_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_END",
                "messageId": "msg1"
            }
            """;

        // Act
        TextMessageEndEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.TextMessageEndEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.Equal("msg1", evt.MessageId);
    }

    [Fact]
    public void TextMessageEndEvent_RoundTrip_PreservesData()
    {
        // Arrange
        TextMessageEndEvent original = new() { MessageId = "msg789" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.TextMessageEndEvent);
        TextMessageEndEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.TextMessageEndEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.MessageId, deserialized.MessageId);
    }

    [Fact]
    public void AGUIMessage_Serializes_WithIdRoleAndContent()
    {
        // Arrange
        AGUIMessage message = new() { Id = "m1", Role = AGUIRoles.User, Content = "Hello" };

        // Act
        string json = JsonSerializer.Serialize(message, AGUIJsonSerializerContext.Default.AGUIMessage);

        // Assert
        Assert.Contains("\"id\":\"m1\"", json);
        Assert.Contains($"\"role\":\"{AGUIRoles.User}\"", json);
        Assert.Contains("\"content\":\"Hello\"", json);
    }

    [Fact]
    public void AGUIMessage_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "id": "m1",
                "role": "user",
                "content": "Test message"
            }
            """;

        // Act
        AGUIMessage? message = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.AGUIMessage);

        // Assert
        Assert.NotNull(message);
        Assert.Equal("m1", message.Id);
        Assert.Equal(AGUIRoles.User, message.Role);
        Assert.Equal("Test message", message.Content);
    }

    [Fact]
    public void AGUIMessage_RoundTrip_PreservesData()
    {
        // Arrange
        AGUIMessage original = new() { Id = "msg123", Role = AGUIRoles.Assistant, Content = "Response text" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.AGUIMessage);
        AGUIMessage? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.Id, deserialized.Id);
        Assert.Equal(original.Role, deserialized.Role);
        Assert.Equal(original.Content, deserialized.Content);
    }

    [Fact]
    public void AGUIMessage_Validates_RequiredFields()
    {
        // Arrange
        const string Json = """
            {
                "id": "m1",
                "role": "user",
                "content": "Test"
            }
            """;

        // Act
        AGUIMessage? message = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.AGUIMessage);

        // Assert
        Assert.NotNull(message);
        Assert.NotNull(message.Id);
        Assert.NotNull(message.Role);
        Assert.NotNull(message.Content);
    }

    [Fact]
    public void BaseEvent_Deserializes_RunStartedEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_STARTED",
                "threadId": "thread1",
                "runId": "run1"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<RunStartedEvent>(evt);
    }

    [Fact]
    public void BaseEvent_Deserializes_RunFinishedEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_FINISHED",
                "threadId": "thread1",
                "runId": "run1"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<RunFinishedEvent>(evt);
    }

    [Fact]
    public void BaseEvent_Deserializes_RunErrorEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "RUN_ERROR",
                "message": "Error"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<RunErrorEvent>(evt);
    }

    [Fact]
    public void BaseEvent_Deserializes_TextMessageStartEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_START",
                "messageId": "msg1",
                "role": "assistant"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<TextMessageStartEvent>(evt);
    }

    [Fact]
    public void BaseEvent_Deserializes_TextMessageContentEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": "msg1",
                "delta": "Hello"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<TextMessageContentEvent>(evt);
    }

    [Fact]
    public void BaseEvent_Deserializes_TextMessageEndEventAsBaseEvent()
    {
        // Arrange
        const string Json = """
            {
                "type": "TEXT_MESSAGE_END",
                "messageId": "msg1"
            }
            """;

        // Act
        BaseEvent? evt = JsonSerializer.Deserialize(Json, AGUIJsonSerializerContext.Default.BaseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<TextMessageEndEvent>(evt);
    }

    [Fact]
    public void BaseEvent_DistinguishesEventTypes_BasedOnTypeField()
    {
        // Arrange
        string[] jsonEvents =
        [
            "{\"type\":\"RUN_STARTED\",\"threadId\":\"t1\",\"runId\":\"r1\"}",
            "{\"type\":\"RUN_FINISHED\",\"threadId\":\"t1\",\"runId\":\"r1\"}",
            "{\"type\":\"RUN_ERROR\",\"message\":\"err\"}",
            "{\"type\":\"TEXT_MESSAGE_START\",\"messageId\":\"m1\",\"role\":\"user\"}",
            "{\"type\":\"TEXT_MESSAGE_CONTENT\",\"messageId\":\"m1\",\"delta\":\"hi\"}",
            "{\"type\":\"TEXT_MESSAGE_END\",\"messageId\":\"m1\"}"
        ];

        // Act
        List<BaseEvent> events = [];
        foreach (string json in jsonEvents)
        {
            BaseEvent? evt = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.BaseEvent);
            if (evt != null)
            {
                events.Add(evt);
            }
        }

        // Assert
        Assert.Equal(6, events.Count);
        Assert.IsType<RunStartedEvent>(events[0]);
        Assert.IsType<RunFinishedEvent>(events[1]);
        Assert.IsType<RunErrorEvent>(events[2]);
        Assert.IsType<TextMessageStartEvent>(events[3]);
        Assert.IsType<TextMessageContentEvent>(events[4]);
        Assert.IsType<TextMessageEndEvent>(events[5]);
    }

    [Fact]
    public void AGUIAgentThreadState_Serializes_WithThreadIdAndWrappedState()
    {
        // Arrange
        AGUIAgentThread.AGUIAgentThreadState state = new()
        {
            ThreadId = "thread1",
            WrappedState = JsonSerializer.SerializeToElement(new { test = "data" })
        };

        // Act
        string json = JsonSerializer.Serialize(state, AGUIJsonSerializerContext.Default.AGUIAgentThreadState);

        // Assert
        Assert.Contains("\"ThreadId\":\"thread1\"", json);
        Assert.Contains("\"WrappedState\"", json);
    }

    [Fact]
    public void AGUIAgentThreadState_Deserializes_FromJsonCorrectly()
    {
        // Arrange
        const string Json = """
            {
                "ThreadId": "thread1",
                "WrappedState": {"test": "data"}
            }
            """;

        // Act
        AGUIAgentThread.AGUIAgentThreadState? state = JsonSerializer.Deserialize(
            Json,
            AGUIJsonSerializerContext.Default.AGUIAgentThreadState);

        // Assert
        Assert.NotNull(state);
        Assert.Equal("thread1", state.ThreadId);
        Assert.NotEqual(JsonValueKind.Undefined, state.WrappedState.ValueKind);
    }

    [Fact]
    public void AGUIAgentThreadState_RoundTrip_PreservesThreadIdAndNestedState()
    {
        // Arrange
        AGUIAgentThread.AGUIAgentThreadState original = new()
        {
            ThreadId = "thread123",
            WrappedState = JsonSerializer.SerializeToElement(new { key1 = "value1", key2 = 42 })
        };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.AGUIAgentThreadState);
        AGUIAgentThread.AGUIAgentThreadState? deserialized = JsonSerializer.Deserialize(
            json,
            AGUIJsonSerializerContext.Default.AGUIAgentThreadState);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.WrappedState.GetProperty("key1").GetString(),
                     deserialized.WrappedState.GetProperty("key1").GetString());
        Assert.Equal(original.WrappedState.GetProperty("key2").GetInt32(),
                     deserialized.WrappedState.GetProperty("key2").GetInt32());
    }
}
