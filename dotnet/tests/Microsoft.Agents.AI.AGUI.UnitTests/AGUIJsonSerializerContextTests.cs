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
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("threadId", out JsonElement threadIdProp));
        Assert.Equal("thread1", threadIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("runId", out JsonElement runIdProp));
        Assert.Equal("run1", runIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("messages", out JsonElement messagesProp));
        Assert.Equal(JsonValueKind.Array, messagesProp.ValueKind);
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
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }],
            State = JsonSerializer.SerializeToElement(new { key = "value" }),
            Context = [new AGUIContextItem { Description = "ctx1", Value = "value1" }],
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
                new AGUIUserMessage { Id = "m1", Content = "First" },
                new AGUIAssistantMessage { Id = "m2", Content = "Second" }
            ],
            Context = [
                new AGUIContextItem { Description = "key1", Value = "value1" },
                new AGUIContextItem { Description = "key2", Value = "value2" }
            ]
        };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunAgentInput);
        RunAgentInput? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunAgentInput);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.RunId, deserialized.RunId);
        Assert.Equal(2, deserialized.Messages.Count());
        Assert.Equal(2, deserialized.Context.Length);
    }

    [Fact]
    public void RunStartedEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        RunStartedEvent evt = new() { ThreadId = "thread1", RunId = "run1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunStartedEvent);

        // Assert
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.RunStarted, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void RunStartedEvent_Includes_ThreadIdAndRunIdInOutput()
    {
        // Arrange
        RunStartedEvent evt = new() { ThreadId = "thread1", RunId = "run1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunStartedEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("threadId", out JsonElement threadIdProp));
        Assert.Equal("thread1", threadIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("runId", out JsonElement runIdProp));
        Assert.Equal("run1", runIdProp.GetString());
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
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.RunFinished, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void RunFinishedEvent_Includes_ThreadIdRunIdAndOptionalResult()
    {
        // Arrange
        RunFinishedEvent evt = new() { ThreadId = "thread1", RunId = "run1", Result = JsonDocument.Parse("\"Success\"").RootElement.Clone() };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunFinishedEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("threadId", out JsonElement threadIdProp));
        Assert.Equal("thread1", threadIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("runId", out JsonElement runIdProp));
        Assert.Equal("run1", runIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("result", out JsonElement resultProp));
        Assert.Equal("Success", resultProp.GetString());
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
        Assert.Equal("Complete", evt.Result?.GetString());
    }

    [Fact]
    public void RunFinishedEvent_RoundTrip_PreservesData()
    {
        // Arrange
        RunFinishedEvent original = new() { ThreadId = "thread1", RunId = "run1", Result = JsonDocument.Parse("\"Done\"").RootElement.Clone() };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.RunFinishedEvent);
        RunFinishedEvent? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.RunFinishedEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.ThreadId, deserialized.ThreadId);
        Assert.Equal(original.RunId, deserialized.RunId);
        Assert.Equal(original.Result?.GetString(), deserialized.Result?.GetString());
    }

    [Fact]
    public void RunErrorEvent_Serializes_WithCorrectEventType()
    {
        // Arrange
        RunErrorEvent evt = new() { Message = "Error occurred" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunErrorEvent);

        // Assert
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.RunError, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void RunErrorEvent_Includes_MessageAndOptionalCode()
    {
        // Arrange
        RunErrorEvent evt = new() { Message = "Error occurred", Code = "ERR001" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.RunErrorEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("message", out JsonElement messageProp));
        Assert.Equal("Error occurred", messageProp.GetString());
        Assert.True(jsonElement.TryGetProperty("code", out JsonElement codeProp));
        Assert.Equal("ERR001", codeProp.GetString());
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
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.TextMessageStart, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void TextMessageStartEvent_Includes_MessageIdAndRole()
    {
        // Arrange
        TextMessageStartEvent evt = new() { MessageId = "msg1", Role = AGUIRoles.Assistant };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageStartEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("messageId", out JsonElement msgIdProp));
        Assert.Equal("msg1", msgIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("role", out JsonElement roleProp));
        Assert.Equal(AGUIRoles.Assistant, roleProp.GetString());
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
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.TextMessageContent, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void TextMessageContentEvent_Includes_MessageIdAndDelta()
    {
        // Arrange
        TextMessageContentEvent evt = new() { MessageId = "msg1", Delta = "Hello World" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageContentEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("messageId", out JsonElement msgIdProp));
        Assert.Equal("msg1", msgIdProp.GetString());
        Assert.True(jsonElement.TryGetProperty("delta", out JsonElement deltaProp));
        Assert.Equal("Hello World", deltaProp.GetString());
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
        var jsonElement = JsonDocument.Parse(json).RootElement;
        Assert.Equal(AGUIEventTypes.TextMessageEnd, jsonElement.GetProperty("type").GetString());
    }

    [Fact]
    public void TextMessageEndEvent_Includes_MessageId()
    {
        // Arrange
        TextMessageEndEvent evt = new() { MessageId = "msg1" };

        // Act
        string json = JsonSerializer.Serialize(evt, AGUIJsonSerializerContext.Default.TextMessageEndEvent);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("messageId", out JsonElement msgIdProp));
        Assert.Equal("msg1", msgIdProp.GetString());
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
        AGUIMessage message = new AGUIUserMessage() { Id = "m1", Content = "Hello" };

        // Act
        string json = JsonSerializer.Serialize(message, AGUIJsonSerializerContext.Default.AGUIMessage);
        JsonElement jsonElement = JsonSerializer.Deserialize<JsonElement>(json);

        // Assert
        Assert.True(jsonElement.TryGetProperty("id", out JsonElement idProp));
        Assert.Equal("m1", idProp.GetString());
        Assert.True(jsonElement.TryGetProperty("role", out JsonElement roleProp));
        Assert.Equal(AGUIRoles.User, roleProp.GetString());
        Assert.True(jsonElement.TryGetProperty("content", out JsonElement contentProp));
        Assert.Equal("Hello", contentProp.GetString());
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
        Assert.Equal("Test message", ((AGUIUserMessage)message).Content);
    }

    [Fact]
    public void AGUIMessage_RoundTrip_PreservesData()
    {
        // Arrange
        AGUIMessage original = new AGUIAssistantMessage() { Id = "msg123", Content = "Response text" };

        // Act
        string json = JsonSerializer.Serialize(original, AGUIJsonSerializerContext.Default.AGUIMessage);
        AGUIMessage? deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(original.Id, deserialized.Id);
        Assert.Equal(original.Role, deserialized.Role);
        Assert.Equal(((AGUIAssistantMessage)original).Content, ((AGUIAssistantMessage)deserialized).Content);
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
        Assert.NotNull(((AGUIUserMessage)message).Content);
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

    #region Comprehensive Message Serialization Tests

    [Fact]
    public void AGUIUserMessage_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalMessage = new AGUIUserMessage
        {
            Id = "user1",
            Content = "Hello, assistant!"
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUIUserMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIUserMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("user1", deserialized.Id);
        Assert.Equal("Hello, assistant!", deserialized.Content);
    }

    [Fact]
    public void AGUISystemMessage_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalMessage = new AGUISystemMessage
        {
            Id = "sys1",
            Content = "You are a helpful assistant."
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUISystemMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUISystemMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("sys1", deserialized.Id);
        Assert.Equal("You are a helpful assistant.", deserialized.Content);
    }

    [Fact]
    public void AGUIDeveloperMessage_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalMessage = new AGUIDeveloperMessage
        {
            Id = "dev1",
            Content = "Developer instructions here."
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUIDeveloperMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIDeveloperMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("dev1", deserialized.Id);
        Assert.Equal("Developer instructions here.", deserialized.Content);
    }

    [Fact]
    public void AGUIAssistantMessage_WithTextOnly_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalMessage = new AGUIAssistantMessage
        {
            Id = "asst1",
            Content = "I can help you with that."
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUIAssistantMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIAssistantMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("asst1", deserialized.Id);
        Assert.Equal("I can help you with that.", deserialized.Content);
        Assert.Null(deserialized.ToolCalls);
    }

    [Fact]
    public void AGUIAssistantMessage_WithToolCallsAndParameters_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var parameters = new Dictionary<string, object?>
        {
            ["location"] = "Seattle",
            ["units"] = "fahrenheit",
            ["days"] = 5
        };
        string argumentsJson = JsonSerializer.Serialize(parameters, AGUIJsonSerializerContext.Default.Options);

        var originalMessage = new AGUIAssistantMessage
        {
            Id = "asst2",
            Content = "Let me check the weather for you.",
            ToolCalls =
            [
                new AGUIToolCall
                {
                    Id = "call_123",
                    Type = "function",
                    Function = new AGUIFunctionCall
                    {
                        Name = "GetWeather",
                        Arguments = argumentsJson
                    }
                }
            ]
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUIAssistantMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIAssistantMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("asst2", deserialized.Id);
        Assert.Equal("Let me check the weather for you.", deserialized.Content);
        Assert.NotNull(deserialized.ToolCalls);
        Assert.Single(deserialized.ToolCalls);

        var toolCall = deserialized.ToolCalls[0];
        Assert.Equal("call_123", toolCall.Id);
        Assert.Equal("function", toolCall.Type);
        Assert.NotNull(toolCall.Function);
        Assert.Equal("GetWeather", toolCall.Function.Name);

        // Verify parameters can be deserialized
        var deserializedParams = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
            toolCall.Function.Arguments,
            AGUIJsonSerializerContext.Default.Options);
        Assert.NotNull(deserializedParams);
        Assert.Equal("Seattle", deserializedParams["location"].GetString());
        Assert.Equal("fahrenheit", deserializedParams["units"].GetString());
        Assert.Equal(5, deserializedParams["days"].GetInt32());
    }

    [Fact]
    public void AGUIToolMessage_WithResults_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var result = new Dictionary<string, object?>
        {
            ["temperature"] = 72.5,
            ["conditions"] = "Sunny",
            ["humidity"] = 45
        };
        string contentJson = JsonSerializer.Serialize(result, AGUIJsonSerializerContext.Default.Options);

        var originalMessage = new AGUIToolMessage
        {
            Id = "tool1",
            ToolCallId = "call_123",
            Content = contentJson
        };

        // Act
        string json = JsonSerializer.Serialize(originalMessage, AGUIJsonSerializerContext.Default.AGUIToolMessage);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIToolMessage);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("tool1", deserialized.Id);
        Assert.Equal("call_123", deserialized.ToolCallId);
        Assert.NotNull(deserialized.Content);

        // Verify result content can be deserialized
        var deserializedResult = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
            deserialized.Content,
            AGUIJsonSerializerContext.Default.Options);
        Assert.NotNull(deserializedResult);
        Assert.Equal(72.5, deserializedResult["temperature"].GetDouble());
        Assert.Equal("Sunny", deserializedResult["conditions"].GetString());
        Assert.Equal(45, deserializedResult["humidity"].GetInt32());
    }

    [Fact]
    public void AllFiveMessageTypes_SerializeAsPolymorphicArray_Correctly()
    {
        // Arrange
        AGUIMessage[] messages =
        [
            new AGUISystemMessage { Id = "1", Content = "System message" },
            new AGUIDeveloperMessage { Id = "2", Content = "Developer message" },
            new AGUIUserMessage { Id = "3", Content = "User message" },
            new AGUIAssistantMessage { Id = "4", Content = "Assistant message" },
            new AGUIToolMessage { Id = "5", ToolCallId = "call_1", Content = "{\"result\":\"success\"}" }
        ];

        // Act
        string json = JsonSerializer.Serialize(messages, AGUIJsonSerializerContext.Default.AGUIMessageArray);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.AGUIMessageArray);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(5, deserialized.Length);
        Assert.IsType<AGUISystemMessage>(deserialized[0]);
        Assert.IsType<AGUIDeveloperMessage>(deserialized[1]);
        Assert.IsType<AGUIUserMessage>(deserialized[2]);
        Assert.IsType<AGUIAssistantMessage>(deserialized[3]);
        Assert.IsType<AGUIToolMessage>(deserialized[4]);
    }

    #endregion

    #region Tool-Related Event Type Tests

    [Fact]
    public void ToolCallStartEvent_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalEvent = new ToolCallStartEvent
        {
            ParentMessageId = "msg1",
            ToolCallId = "call_123",
            ToolCallName = "GetWeather"
        };

        // Act
        string json = JsonSerializer.Serialize(originalEvent, AGUIJsonSerializerContext.Default.ToolCallStartEvent);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.ToolCallStartEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("msg1", deserialized.ParentMessageId);
        Assert.Equal("call_123", deserialized.ToolCallId);
        Assert.Equal("GetWeather", deserialized.ToolCallName);
        Assert.Equal(AGUIEventTypes.ToolCallStart, deserialized.Type);
    }

    [Fact]
    public void ToolCallArgsEvent_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalEvent = new ToolCallArgsEvent
        {
            ToolCallId = "call_123",
            Delta = "{\"location\":\"Seattle\",\"units\":\"fahrenheit\"}"
        };

        // Act
        string json = JsonSerializer.Serialize(originalEvent, AGUIJsonSerializerContext.Default.ToolCallArgsEvent);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.ToolCallArgsEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("call_123", deserialized.ToolCallId);
        Assert.Equal("{\"location\":\"Seattle\",\"units\":\"fahrenheit\"}", deserialized.Delta);
        Assert.Equal(AGUIEventTypes.ToolCallArgs, deserialized.Type);
    }

    [Fact]
    public void ToolCallEndEvent_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalEvent = new ToolCallEndEvent
        {
            ToolCallId = "call_123"
        };

        // Act
        string json = JsonSerializer.Serialize(originalEvent, AGUIJsonSerializerContext.Default.ToolCallEndEvent);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.ToolCallEndEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("call_123", deserialized.ToolCallId);
        Assert.Equal(AGUIEventTypes.ToolCallEnd, deserialized.Type);
    }

    [Fact]
    public void ToolCallResultEvent_SerializesAndDeserializes_Correctly()
    {
        // Arrange
        var originalEvent = new ToolCallResultEvent
        {
            MessageId = "msg1",
            ToolCallId = "call_123",
            Content = "{\"temperature\":72.5,\"conditions\":\"Sunny\"}",
            Role = "tool"
        };

        // Act
        string json = JsonSerializer.Serialize(originalEvent, AGUIJsonSerializerContext.Default.ToolCallResultEvent);
        var deserialized = JsonSerializer.Deserialize(json, AGUIJsonSerializerContext.Default.ToolCallResultEvent);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("msg1", deserialized.MessageId);
        Assert.Equal("call_123", deserialized.ToolCallId);
        Assert.Equal("{\"temperature\":72.5,\"conditions\":\"Sunny\"}", deserialized.Content);
        Assert.Equal("tool", deserialized.Role);
        Assert.Equal(AGUIEventTypes.ToolCallResult, deserialized.Type);
    }

    [Fact]
    public void AllToolEventTypes_SerializeAsPolymorphicBaseEvent_Correctly()
    {
        // Arrange
        BaseEvent[] events =
        [
            new RunStartedEvent { ThreadId = "t1", RunId = "r1" },
            new ToolCallStartEvent { ParentMessageId = "m1", ToolCallId = "c1", ToolCallName = "Tool1" },
            new ToolCallArgsEvent { ToolCallId = "c1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "c1" },
            new ToolCallResultEvent { MessageId = "m2", ToolCallId = "c1", Content = "{}", Role = "tool" },
            new RunFinishedEvent { ThreadId = "t1", RunId = "r1" }
        ];

        // Act
        string json = JsonSerializer.Serialize(events, AGUIJsonSerializerContext.Default.Options);
        var deserialized = JsonSerializer.Deserialize<BaseEvent[]>(json, AGUIJsonSerializerContext.Default.Options);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(6, deserialized.Length);
        Assert.IsType<RunStartedEvent>(deserialized[0]);
        Assert.IsType<ToolCallStartEvent>(deserialized[1]);
        Assert.IsType<ToolCallArgsEvent>(deserialized[2]);
        Assert.IsType<ToolCallEndEvent>(deserialized[3]);
        Assert.IsType<ToolCallResultEvent>(deserialized[4]);
        Assert.IsType<RunFinishedEvent>(deserialized[5]);
    }

    #endregion
}
