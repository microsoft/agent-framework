// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
            Converters = { new JsonStringEnumConverter() },
            TypeInfoResolver = AgentRuntimeAbstractionsJsonUtilities.JsonContext.Default
        };
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

    #region ActorResponse Tests

    [Fact]
    public void ActorResponse_SerializesAndDeserializes()
    {
        // Arrange
        var originalResponse = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg123",
            Status = RequestStatus.Completed,
            Data = JsonSerializer.SerializeToElement(new { result = "success" })
        };

        // Act - Serialize to JSON
        string json = JsonSerializer.Serialize(originalResponse, this._options);

        // Assert - JSON structure
        Assert.Contains("\"messageId\":\"msg123\"", json);
        Assert.Contains("\"status\":\"completed\"", json);

        // Act - Deserialize back
        var deserializedResponse = JsonSerializer.Deserialize<ActorResponse>(json, this._options);

        // Assert - Verify deserialization
        Assert.NotNull(deserializedResponse);
        Assert.Equal(originalResponse.MessageId, deserializedResponse.MessageId);
        Assert.Equal(originalResponse.Status, deserializedResponse.Status);
        Assert.Equal(originalResponse.ActorId.Type.Name, deserializedResponse.ActorId.Type.Name);
        Assert.Equal(originalResponse.ActorId.Key, deserializedResponse.ActorId.Key);
        Assert.Equal(originalResponse.Data.GetRawText(), deserializedResponse.Data.GetRawText());
    }

    [Fact]
    public void ActorResponse_ToString_OutputsExpectedFormat()
    {
        // Arrange
        var testData = JsonSerializer.SerializeToElement(new { result = "success" });
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg123",
            Status = RequestStatus.Completed,
            Data = testData
        };

        // Act
        string result = response.ToString();

        // Assert
        Assert.Equal($"ActorResponse(ActorId: TestActor/instance1, Status: Completed, MessageId: msg123, Data: {testData.GetRawText()})", result);
    }

    [Fact]
    public void ActorResponse_ToString_WithNullMessageId_OutputsExpectedFormat()
    {
        // Arrange
        var testData = JsonSerializer.SerializeToElement(new { error = "timeout" });
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = null,
            Status = RequestStatus.Pending,
            Data = testData
        };

        // Act
        string result = response.ToString();

        // Assert
        Assert.Equal($"ActorResponse(ActorId: TestActor/instance1, Status: Pending, MessageId: null, Data: {testData.GetRawText()})", result);
    }

    [Fact]
    public void ActorResponse_ToString_WithEmptyData_OutputsExpectedFormat()
    {
        // Arrange
        var emptyData = new JsonElement(); // Default JsonElement (empty)
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg456",
            Status = RequestStatus.Failed,
            Data = emptyData
        };

        // Act
        string result = response.ToString();

        // Assert
        Assert.Equal("ActorResponse(ActorId: TestActor/instance1, Status: Failed, MessageId: msg456, Data: undefined)", result);
    }

    [Fact]
    public void ActorResponse_ToString_WithLargeData_TruncatesAfter250Characters()
    {
        // Arrange
        // Create a large object that will serialize to more than 250 characters
        var largeArray = new List<object>();
        for (int i = 0; i < 20; i++)
        {
            largeArray.Add(new
            {
                id = $"item-{i:000}",
                name = $"This is item number {i} with a long description to make the JSON larger",
                properties = new
                {
                    prop1 = $"value1-{i}",
                    prop2 = $"value2-{i}",
                    prop3 = $"value3-{i}",
                    prop4 = $"value4-{i}",
                    prop5 = $"value5-{i}"
                }
            });
        }
        var largeData = JsonSerializer.SerializeToElement(largeArray);
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg789",
            Status = RequestStatus.Completed,
            Data = largeData
        };

        // Act
        string result = response.ToString();
        var rawText = largeData.GetRawText();

        // Assert
        // Verify that the raw JSON is indeed larger than 250 characters
        Assert.True(rawText.Length > 250, $"Test data should be larger than 250 characters, but was {rawText.Length}");

        // The ToString should truncate the data and add "..."
        Assert.EndsWith("...)", result);

        // Extract the data portion from the result
        var dataStartIndex = result.IndexOf("Data: ", System.StringComparison.Ordinal) + 6;
        var dataEndIndex = result.Length - 1; // Exclude the closing parenthesis
        var dataInResult = result.Substring(dataStartIndex, dataEndIndex - dataStartIndex);

        // Verify truncation: data should be 253 characters (250 + "...")
        Assert.Equal(253, dataInResult.Length);

        // Verify that the truncated data matches the first 250 characters of the original
        Assert.Equal(rawText.Substring(0, 250), dataInResult.Substring(0, 250));
    }

    [Fact]
    public void ActorResponse_ToString_WithSmallData_DoesNotTruncate()
    {
        // Arrange
        var smallObject = new
        {
            id = "test-id-123",
            name = "Small Test Object",
            value = 42
        };
        var smallData = JsonSerializer.SerializeToElement(smallObject);
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg789",
            Status = RequestStatus.Completed,
            Data = smallData
        };

        // Act
        string result = response.ToString();

        // Assert
        // The ToString should include the full JSON data without truncation
        Assert.Equal($"ActorResponse(ActorId: TestActor/instance1, Status: Completed, MessageId: msg789, Data: {smallData.GetRawText()})", result);
        // Verify no truncation occurred
        Assert.DoesNotContain("...", result);
    }

    [Fact]
    public void ActorResponse_ToString_WithNullData_OutputsExpectedFormat()
    {
        // Arrange
        var response = new ActorResponse
        {
            ActorId = new ActorId("TestActor", "instance1"),
            MessageId = "msg999",
            Status = RequestStatus.Completed,
            Data = JsonSerializer.SerializeToElement((object?)null)
        };

        // Act
        string result = response.ToString();

        // Assert
        Assert.Equal("ActorResponse(ActorId: TestActor/instance1, Status: Completed, MessageId: msg999, Data: null)", result);
    }

    #endregion
}
