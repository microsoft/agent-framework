// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.UnitTests;

/// <summary>
/// Tests for JSON serialization and deserialization of all JSON-serializable types.
/// </summary>
public class JsonSerializationTests
{
    private readonly JsonSerializerOptions _options;

    public JsonSerializationTests()
    {
        this._options = new JsonSerializerOptions
        {
            WriteIndented = false, // Use compact JSON for easier testing
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            Converters = { new JsonStringEnumConverter() }
        };
        this._options.TypeInfoResolver = ActorJsonContext.Default;
    }

    #region ActorMessage Tests

    [Fact]
    public void ActorRequestMessage_SerializesAndDeserializes()
    {
        // Arrange
        var originalMessage = new ActorRequestMessage("msg123")
        {
            SenderId = new ActorId("TestActor", "instance1"),
            Method = "TestMethod",
            Params = JsonSerializer.SerializeToElement(new { param = "value" })
        };

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorMessage>(originalMessage, this._options);

        // Assert - JSON structure
        Assert.Contains("\"type\":\"request\"", json);
        Assert.Contains("\"messageId\":\"msg123\"", json);
        Assert.Contains("\"method\":\"TestMethod\"", json);

        // Act - Deserialize back
        var deserializedMessage = JsonSerializer.Deserialize<ActorMessage>(json, this._options) as ActorRequestMessage;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedMessage);
        Assert.Equal(originalMessage.MessageId, deserializedMessage.MessageId);
        Assert.Equal(originalMessage.Method, deserializedMessage.Method);
        Assert.Equal(originalMessage.SenderId?.Type.Name, deserializedMessage.SenderId?.Type.Name);
        Assert.Equal(originalMessage.SenderId?.Key, deserializedMessage.SenderId?.Key);
        Assert.Equal(originalMessage.Params.GetRawText(), deserializedMessage.Params.GetRawText());
    }

    #endregion

    #region ActorWriteOperation Tests

    [Fact]
    public void SetValueOperation_SerializesAndDeserializes()
    {
        // Arrange
        var originalOperation = new SetValueOperation("testKey", JsonSerializer.SerializeToElement(new { value = "testValue" }));

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorWriteOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"set_value\"", json);
        Assert.Contains("\"key\":\"testKey\"", json);
        Assert.Contains("\"value\":", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorWriteOperation>(json, this._options) as SetValueOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.Key, deserializedOperation.Key);
        Assert.Equal(originalOperation.Value.GetRawText(), deserializedOperation.Value.GetRawText());
    }

    [Fact]
    public void RemoveKeyOperation_SerializesAndDeserializes()
    {
        // Arrange
        var originalOperation = new RemoveKeyOperation("keyToRemove");

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorWriteOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"remove_key\"", json);
        Assert.Contains("\"key\":\"keyToRemove\"", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorWriteOperation>(json, this._options) as RemoveKeyOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.Key, deserializedOperation.Key);
    }

    [Fact]
    public void ActorSendRequestOperation_SerializesAndDeserializes()
    {
        // Arrange
        var request = new ActorRequestMessage("msg456")
        {
            SenderId = new ActorId("TargetActor", "instance1"),
            Method = "ProcessData",
            Params = JsonSerializer.SerializeToElement(new { data = "payload" })
        };
        var originalOperation = new SendRequestOperation(request);

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorWriteOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"send_request\"", json);
        Assert.Contains("\"message\":", json);
        Assert.Contains("\"messageId\":\"msg456\"", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorWriteOperation>(json, this._options) as SendRequestOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.Message.MessageId, deserializedOperation.Message.MessageId);
        Assert.Equal(originalOperation.Message.Method, deserializedOperation.Message.Method);
    }

    [Fact]
    public void ActorUpdateRequestOperation_SerializesAndDeserializes()
    {
        // Arrange
        var originalOperation = new UpdateRequestOperation("msg789", RequestStatus.Failed, JsonSerializer.SerializeToElement(new { error = "timeout" }));

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorWriteOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"update_request\"", json);
        Assert.Contains("\"messageId\":\"msg789\"", json);
        Assert.Contains("\"status\":\"failed\"", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorWriteOperation>(json, this._options) as UpdateRequestOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.MessageId, deserializedOperation.MessageId);
        Assert.Equal(originalOperation.Status, deserializedOperation.Status);
        Assert.Equal(originalOperation.Data.GetRawText(), deserializedOperation.Data.GetRawText());
    }

    #endregion

    #region ActorReadOperation Tests

    [Fact]
    public void ListKeysOperation_SerializesAndDeserializes()
    {
        // Arrange
        var originalOperation = new ListKeysOperation("continuationToken123", "prefix_");

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorReadOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"list_keys\"", json);
        Assert.Contains("\"continuationToken\":\"continuationToken123\"", json);
        Assert.Contains("\"keyPrefix\":\"prefix_\"", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorReadOperation>(json, this._options) as ListKeysOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.ContinuationToken, deserializedOperation.ContinuationToken);
        Assert.Equal(originalOperation.KeyPrefix, deserializedOperation.KeyPrefix);
    }

    [Fact]
    public void GetValueOperation_SerializesAndDeserializes()
    {
        // Arrange
        var originalOperation = new GetValueOperation("myKey");

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize<ActorReadOperation>(originalOperation, this._options);

        // Assert - JSON structure (uses snake_case)
        Assert.Contains("\"type\":\"get_value\"", json);
        Assert.Contains("\"key\":\"myKey\"", json);

        // Act - Deserialize back
        var deserializedOperation = JsonSerializer.Deserialize<ActorReadOperation>(json, this._options) as GetValueOperation;

        // Assert - Verify deserialization
        Assert.NotNull(deserializedOperation);
        Assert.Equal(originalOperation.Key, deserializedOperation.Key);
    }

    #endregion

    #region Enum Serialization Tests

    [Fact]
    public void ActorMessageType_SerializesAsString()
    {
        // Test that enums serialize as strings
        Assert.Equal("\"request\"", JsonSerializer.Serialize(ActorMessageType.Request, this._options));
        Assert.Equal("\"response\"", JsonSerializer.Serialize(ActorMessageType.Response, this._options));
    }

    [Fact]
    public void RequestStatus_SerializesAsString()
    {
        // Test that enums serialize as strings
        Assert.Equal("\"pending\"", JsonSerializer.Serialize(RequestStatus.Pending, this._options));
        Assert.Equal("\"completed\"", JsonSerializer.Serialize(RequestStatus.Completed, this._options));
        Assert.Equal("\"failed\"", JsonSerializer.Serialize(RequestStatus.Failed, this._options));
        Assert.Equal("\"not_found\"", JsonSerializer.Serialize(RequestStatus.NotFound, this._options));
    }

    [Fact]
    public void ActorWriteOperationType_SerializesAsString()
    {
        // Test that enums serialize as strings (snake_case)
        Assert.Equal("\"set_value\"", JsonSerializer.Serialize(ActorWriteOperationType.SetValue, this._options));
        Assert.Equal("\"remove_key\"", JsonSerializer.Serialize(ActorWriteOperationType.RemoveKey, this._options));
        Assert.Equal("\"send_request\"", JsonSerializer.Serialize(ActorWriteOperationType.SendRequest, this._options));
        Assert.Equal("\"update_request\"", JsonSerializer.Serialize(ActorWriteOperationType.UpdateRequest, this._options));
    }

    [Fact]
    public void ActorReadOperationType_SerializesAsString()
    {
        // Test that enums serialize as strings (snake_case)
        Assert.Equal("\"list_keys\"", JsonSerializer.Serialize(ActorReadOperationType.ListKeys, this._options));
        Assert.Equal("\"get_value\"", JsonSerializer.Serialize(ActorReadOperationType.GetValue, this._options));
    }

    [Fact]
    public void ActorReadResultType_SerializesAsString()
    {
        // Test that enums serialize as strings (snake_case)
        Assert.Equal("\"list_keys\"", JsonSerializer.Serialize(ActorReadResultType.ListKeys, this._options));
        Assert.Equal("\"get_value\"", JsonSerializer.Serialize(ActorReadResultType.GetValue, this._options));
    }

    #endregion

    #region ActorId Tests

    [Fact]
    public void ActorId_SerializesAndDeserializes()
    {
        // Arrange
        var actorId = new ActorId("UserActor", "user123");

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize(actorId, this._options);

        // Assert - JSON structure
        Assert.Contains("UserActor/user123", json);

        // Act - Deserialize back
        var deserializedActorId = JsonSerializer.Deserialize<ActorId>(json, this._options);

        // Assert - Verify deserialization
        Assert.Equal(actorId.Type.Name, deserializedActorId.Type.Name);
        Assert.Equal(actorId.Key, deserializedActorId.Key);
    }

    #endregion

    #region Non-message types Tests

    [Fact]
    public void ActorRequest_SerializesAndDeserializes()
    {
        // Arrange
        var originalRequest = new ActorRequest(
            new ActorId("TestActor", "instance1"),
            "msg123",
            "TestMethod",
            JsonSerializer.SerializeToElement(new { param = "value" }));

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize(originalRequest, this._options);

        // Assert - JSON structure
        Assert.Contains("\"messageId\":\"msg123\"", json);
        Assert.Contains("\"method\":\"TestMethod\"", json);

        // Act - Deserialize back
        var deserializedRequest = JsonSerializer.Deserialize<ActorRequest>(json, this._options);

        // Assert - Verify deserialization
        Assert.NotNull(deserializedRequest);
        Assert.Equal(originalRequest.MessageId, deserializedRequest.MessageId);
        Assert.Equal(originalRequest.Method, deserializedRequest.Method);
        Assert.Equal(originalRequest.ActorId.Type.Name, deserializedRequest.ActorId.Type.Name);
        Assert.Equal(originalRequest.ActorId.Key, deserializedRequest.ActorId.Key);
        Assert.Equal(originalRequest.Params.GetRawText(), deserializedRequest.Params.GetRawText());
    }

    [Fact]
    public void ActorRequestUpdate_SerializesAndDeserializes()
    {
        // Arrange
        var originalUpdate = new ActorRequestUpdate(RequestStatus.Completed, JsonSerializer.SerializeToElement(new { result = "done" }));

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize(originalUpdate, this._options);

        // Assert - JSON structure
        Assert.Contains("\"status\":\"completed\"", json);

        // Act - Deserialize back
        var deserializedUpdate = JsonSerializer.Deserialize<ActorRequestUpdate>(json, this._options);

        // Assert - Verify deserialization
        Assert.NotNull(deserializedUpdate);
        Assert.Equal(originalUpdate.Status, deserializedUpdate.Status);
        Assert.Equal(originalUpdate.Data.GetRawText(), deserializedUpdate.Data.GetRawText());
    }

    #endregion
}
