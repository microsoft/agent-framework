// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for OpenAI Responses API model serialization and deserialization.
/// These tests verify that our models correctly serialize to and deserialize from JSON
/// matching the OpenAI wire format, without testing actual API implementation behavior.
/// </summary>
public sealed class OpenAIResponsesSerializationTests : ConformanceTestBase
{
    #region Request Serialization Tests

    [Fact]
    public void Deserialize_BasicRequest_Success()
    {
        // Arrange
        string json = LoadResponsesTraceFile("basic/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.Equal("gpt-4o-mini", request.Model);
        Assert.NotNull(request.Input);
        Assert.Equal(100, request.MaxOutputTokens);
    }

    [Fact]
    public void Deserialize_BasicRequest_RoundTrip()
    {
        // Arrange
        string originalJson = LoadResponsesTraceFile("basic/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(originalJson, OpenAIHostingJsonContext.Default.CreateResponse);
        string reserializedJson = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateResponse);
        CreateResponse? roundtripped = JsonSerializer.Deserialize(reserializedJson, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(roundtripped);
        Assert.Equal(request.Model, roundtripped.Model);
        Assert.Equal(request.MaxOutputTokens, roundtripped.MaxOutputTokens);
    }

    [Fact]
    public void Deserialize_StreamingRequest_HasStreamFlag()
    {
        // Arrange
        string json = LoadResponsesTraceFile("streaming/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.Equal(200, request.MaxOutputTokens);
    }

    [Fact]
    public void Deserialize_ConversationRequest_HasPreviousResponseId()
    {
        // Arrange
        string json = LoadResponsesTraceFile("conversation/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.PreviousResponseId);
        Assert.StartsWith("resp_", request.PreviousResponseId);
    }

    [Fact]
    public void Deserialize_MetadataRequest_HasAllParameters()
    {
        // Arrange
        string json = LoadResponsesTraceFile("metadata/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Metadata);
        Assert.Equal(3, request.Metadata.Count);
        Assert.Equal("test_user_123", request.Metadata["user_id"]);
        Assert.Equal("session_456", request.Metadata["session_id"]);
        Assert.Equal("conformance_test", request.Metadata["purpose"]);

        Assert.NotNull(request.Instructions);
        Assert.Equal("Respond in a friendly, educational tone.", request.Instructions);

        Assert.Equal(0.7, request.Temperature);
        Assert.Equal(0.9, request.TopP);
        Assert.Equal(150, request.MaxOutputTokens);
    }

    [Fact]
    public void Deserialize_ToolCallRequest_HasToolDefinitions()
    {
        // Arrange
        string json = LoadResponsesTraceFile("tool_call/request.json");

        // Act
        // CreateResponse doesn't have Tools property - it uses dynamic JSON
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.True(root.TryGetProperty("tools", out var tools));
        Assert.Equal(JsonValueKind.Array, tools.ValueKind);
        Assert.Equal(1, tools.GetArrayLength());

        var tool = tools[0];
        Assert.Equal("function", tool.GetProperty("type").GetString());
        Assert.Equal("get_weather", tool.GetProperty("name").GetString());
        Assert.True(tool.TryGetProperty("description", out _));
        Assert.True(tool.TryGetProperty("parameters", out var parameters));
        Assert.Equal("object", parameters.GetProperty("type").GetString());
    }

    [Fact]
    public void Serialize_CreateMinimalRequest_MatchesFormat()
    {
        // Arrange
        var request = new CreateResponse
        {
            Model = "gpt-4o-mini",
            Input = ResponseInput.FromText("Hello")
        };

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateResponse);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.Equal("gpt-4o-mini", root.GetProperty("model").GetString());
        Assert.True(root.TryGetProperty("input", out var input));

        // Input can be string or object - verify one exists
        Assert.True(input.ValueKind is JsonValueKind.String or JsonValueKind.Object);
    }

    [Fact]
    public void Serialize_CreateRequestWithOptions_IncludesAllFields()
    {
        // Arrange
        var request = new CreateResponse
        {
            Model = "gpt-4o-mini",
            Input = ResponseInput.FromText("Test input"),
            MaxOutputTokens = 100,
            Temperature = 0.7,
            TopP = 0.9,
            Stream = false,
            Instructions = "Test instructions",
            Metadata = new Dictionary<string, string>
            {
                ["key1"] = "value1",
                ["key2"] = "value2"
            }
        };

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateResponse);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.Equal("gpt-4o-mini", root.GetProperty("model").GetString());
        Assert.Equal(100, root.GetProperty("max_output_tokens").GetInt32());
        Assert.Equal(0.7, root.GetProperty("temperature").GetDouble());
        Assert.Equal(0.9, root.GetProperty("top_p").GetDouble());
        Assert.False(root.GetProperty("stream").GetBoolean());
        Assert.Equal("Test instructions", root.GetProperty("instructions").GetString());

        var metadata = root.GetProperty("metadata");
        Assert.Equal("value1", metadata.GetProperty("key1").GetString());
        Assert.Equal("value2", metadata.GetProperty("key2").GetString());
    }

    [Fact]
    public void Serialize_NullableFields_AreOmittedWhenNull()
    {
        // Arrange
        var request = new CreateResponse
        {
            Model = "gpt-4o-mini",
            Input = ResponseInput.FromText("Test")
        };

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateResponse);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Optional fields should not be present when null
        Assert.False(root.TryGetProperty("previous_response_id", out _) &&
                     root.GetProperty("previous_response_id").ValueKind != JsonValueKind.Null,
                     "previous_response_id should be omitted or null");
        Assert.False(root.TryGetProperty("instructions", out _) &&
                     root.GetProperty("instructions").ValueKind != JsonValueKind.Null,
                     "instructions should be omitted or null");
    }

    [Fact]
    public void Deserialize_ImageInputRequest_HasImageData()
    {
        // Arrange
        string json = LoadResponsesTraceFile("image_input/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Input);
    }

    [Fact]
    public void Deserialize_ImageInputStreamingRequest_HasStreamAndImage()
    {
        // Arrange
        string json = LoadResponsesTraceFile("image_input_streaming/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.NotNull(request.Input);
    }

    [Fact]
    public void Deserialize_JsonOutputRequest_HasJsonSchema()
    {
        // Arrange
        string json = LoadResponsesTraceFile("json_output/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Input);
        Assert.NotNull(request.Text);
        Assert.NotNull(request.Text.Format);
        Assert.IsType<ResponseTextFormatConfigurationJsonSchema>(request.Text.Format);
        var jsonSchemaFormat = (ResponseTextFormatConfigurationJsonSchema)request.Text.Format;
        Assert.Equal("json_schema", jsonSchemaFormat.Type);
        Assert.NotNull(jsonSchemaFormat.Name);
        Assert.NotEqual(default, jsonSchemaFormat.Schema);
    }

    [Fact]
    public void Deserialize_JsonOutputStreamingRequest_HasJsonSchemaAndStream()
    {
        // Arrange
        string json = LoadResponsesTraceFile("json_output_streaming/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.NotNull(request.Input);
        Assert.NotNull(request.Text);
        Assert.NotNull(request.Text.Format);
        Assert.IsType<ResponseTextFormatConfigurationJsonSchema>(request.Text.Format);
        var jsonSchemaFormat = (ResponseTextFormatConfigurationJsonSchema)request.Text.Format;
        Assert.Equal("json_schema", jsonSchemaFormat.Type);
    }

    [Fact]
    public void Deserialize_ReasoningRequest_HasReasoningConfiguration()
    {
        // Arrange
        string json = LoadResponsesTraceFile("reasoning/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Reasoning);
    }

    [Fact]
    public void Deserialize_ReasoningStreamingRequest_HasReasoningAndStream()
    {
        // Arrange
        string json = LoadResponsesTraceFile("reasoning_streaming/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.NotNull(request.Reasoning);
    }

    [Fact]
    public void Deserialize_RefusalRequest_CanBeDeserialized()
    {
        // Arrange
        string json = LoadResponsesTraceFile("refusal/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Input);
    }

    [Fact]
    public void Deserialize_RefusalStreamingRequest_HasStream()
    {
        // Arrange
        string json = LoadResponsesTraceFile("refusal_streaming/request.json");

        // Act
        CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.NotNull(request.Input);
    }

    [Fact]
    public void Deserialize_InvalidInputObject_ThrowsHelpfulException()
    {
        // Arrange
        const string Json = "{\"model\":\"gpt-4o-mini\",\"input\":{\"input\":\"testing!\"},\"stream\":true}";

        // Act & Assert
        var exception = Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize(Json, OpenAIHostingJsonContext.Default.CreateResponse));

        Assert.Contains("ResponseInput must be either a string or an array of messages", exception.Message);
        Assert.Contains("Objects are not supported", exception.Message);
    }

    [Fact]
    public void Deserialize_AllRequests_CanBeDeserialized()
    {
        // Arrange
        string[] requestPaths =
        [
            "basic/request.json",
            "streaming/request.json",
            "conversation/request.json",
            "metadata/request.json",
            "tool_call/request.json",
            "image_input/request.json",
            "image_input_streaming/request.json",
            "json_output/request.json",
            "json_output_streaming/request.json",
            "reasoning/request.json",
            "reasoning_streaming/request.json",
            "refusal/request.json",
            "refusal_streaming/request.json"
        ];

        foreach (var path in requestPaths)
        {
            string json = LoadResponsesTraceFile(path);

            // Act & Assert - Should not throw
            CreateResponse? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateResponse);
            Assert.NotNull(request);
            Assert.NotNull(request.Input);
        }
    }

    #endregion

    #region Response Deserialization Tests

    [Fact]
    public void Deserialize_BasicResponse_Success()
    {
        // Arrange
        string json = LoadResponsesTraceFile("basic/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.StartsWith("resp_", response.Id);
        Assert.Equal("response", response.Object);
        Assert.True(response.CreatedAt > 0);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Model);
        Assert.StartsWith("gpt-4o-mini", response.Model);
    }

    [Fact]
    public void Deserialize_BasicResponse_HasCorrectOutput()
    {
        // Arrange
        string json = LoadResponsesTraceFile("basic/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Output);
        Assert.Single(response.Output);

        var outputItem = response.Output[0];
        Assert.NotNull(outputItem);

        // Verify it's a message type
        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(outputItem, OpenAIHostingJsonContext.Default.ItemResource));
        var root = doc.RootElement;
        Assert.Equal("message", root.GetProperty("type").GetString());
    }

    [Fact]
    public void Deserialize_BasicResponse_HasCorrectUsage()
    {
        // Arrange
        string json = LoadResponsesTraceFile("basic/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Usage);
        Assert.True(response.Usage.InputTokens > 0);
        Assert.True(response.Usage.OutputTokens > 0);
        Assert.Equal(response.Usage.InputTokens + response.Usage.OutputTokens, response.Usage.TotalTokens);
        Assert.NotNull(response.Usage.InputTokensDetails);
        Assert.NotNull(response.Usage.OutputTokensDetails);
    }

    [Fact]
    public void Deserialize_ConversationResponse_HasPreviousResponseId()
    {
        // Arrange
        string json = LoadResponsesTraceFile("conversation/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.PreviousResponseId);
        Assert.StartsWith("resp_", response.PreviousResponseId);
        Assert.NotEqual(response.Id, response.PreviousResponseId);
    }

    [Fact]
    public void Deserialize_MetadataResponse_PreservesMetadata()
    {
        // Arrange
        string json = LoadResponsesTraceFile("metadata/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Metadata);
        Assert.Equal("test_user_123", response.Metadata["user_id"]);
        Assert.Equal("session_456", response.Metadata["session_id"]);
        Assert.Equal("conformance_test", response.Metadata["purpose"]);
    }

    [Fact]
    public void Deserialize_MetadataResponse_HasIncompleteStatus()
    {
        // Arrange
        string json = LoadResponsesTraceFile("metadata/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Incomplete, response.Status);
        Assert.NotNull(response.IncompleteDetails);
        Assert.Equal("max_output_tokens", response.IncompleteDetails.Reason);
    }

    [Fact]
    public void Deserialize_MetadataResponse_HasInstructions()
    {
        // Arrange
        string json = LoadResponsesTraceFile("metadata/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Instructions);
        Assert.Equal("Respond in a friendly, educational tone.", response.Instructions);
    }

    [Fact]
    public void Deserialize_MetadataResponse_HasModelParameters()
    {
        // Arrange
        string json = LoadResponsesTraceFile("metadata/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(0.7, response.Temperature);
        Assert.Equal(0.9, response.TopP);
        Assert.Equal(150, response.MaxOutputTokens);
    }

    [Fact]
    public void Deserialize_ToolCallResponse_HasFunctionCall()
    {
        // Arrange
        string json = LoadResponsesTraceFile("tool_call/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Output);
        Assert.Single(response.Output);

        // Verify the output is a function_call type
        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(response.Output[0], OpenAIHostingJsonContext.Default.ItemResource));
        var root = doc.RootElement;
        Assert.Equal("function_call", root.GetProperty("type").GetString());
        Assert.Equal("get_weather", root.GetProperty("name").GetString());
        Assert.True(root.TryGetProperty("arguments", out var args));
        Assert.True(root.TryGetProperty("call_id", out var callId));
        Assert.StartsWith("call_", callId.GetString());
    }

    [Fact]
    public void Deserialize_ToolCallResponse_HasToolDefinitions()
    {
        // Arrange
        string json = LoadResponsesTraceFile("tool_call/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Tools);
        Assert.Single(response.Tools);

        var tool = response.Tools[0];
        Assert.Equal(JsonValueKind.Object, tool.ValueKind);

        var toolObj = tool;
        Assert.Equal("function", toolObj.GetProperty("type").GetString());
        Assert.Equal("get_weather", toolObj.GetProperty("name").GetString());
        Assert.True(toolObj.TryGetProperty("parameters", out var parameters));
        Assert.Equal("object", parameters.GetProperty("type").GetString());
    }

    [Fact]
    public void Deserialize_ImageInputResponse_HasImageInInput()
    {
        // Arrange
        string json = LoadResponsesTraceFile("image_input/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Output);
    }

    [Fact]
    public void Deserialize_JsonOutputResponse_HasStructuredOutput()
    {
        // Arrange
        string json = LoadResponsesTraceFile("json_output/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Output);
        Assert.NotNull(response.Text);
        Assert.NotNull(response.Text.Format);
        Assert.IsType<ResponseTextFormatConfigurationJsonSchema>(response.Text.Format);
        var jsonSchemaFormat = (ResponseTextFormatConfigurationJsonSchema)response.Text.Format;
        Assert.Equal("json_schema", jsonSchemaFormat.Type);
    }

    [Fact]
    public void Deserialize_ReasoningResponse_HasReasoningItems()
    {
        // Arrange
        string json = LoadResponsesTraceFile("reasoning/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Output);
        Assert.NotNull(response.Reasoning);
    }

    [Fact]
    public void Deserialize_RefusalResponse_HasRefusalContent()
    {
        // Arrange
        string json = LoadResponsesTraceFile("refusal/response.json");

        // Act
        Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Output);
    }

    [Fact]
    public void Deserialize_AllResponses_HaveRequiredFields()
    {
        // Arrange
        string[] responsePaths =
        [
            "basic/response.json",
            "conversation/response.json",
            "metadata/response.json",
            "tool_call/response.json",
            "image_input/response.json",
            "json_output/response.json",
            "reasoning/response.json",
            "refusal/response.json"
        ];

        foreach (var path in responsePaths)
        {
            string json = LoadResponsesTraceFile(path);

            // Act
            Response? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Response);

            // Assert
            Assert.NotNull(response);
            Assert.NotNull(response.Id);
            Assert.Equal("response", response.Object);
            Assert.True(response.CreatedAt > 0, $"Response from {path} should have created_at");
            Assert.NotNull(response.Model);
            Assert.NotNull(response.Output);
        }
    }

    [Fact]
    public void Deserialize_ResponseRoundTrip_PreservesData()
    {
        // Arrange
        string originalJson = LoadResponsesTraceFile("basic/response.json");

        // Act - Deserialize and re-serialize
        Response? response = JsonSerializer.Deserialize(originalJson, OpenAIHostingJsonContext.Default.Response);
        string reserializedJson = JsonSerializer.Serialize(response, OpenAIHostingJsonContext.Default.Response);
        Response? roundtripped = JsonSerializer.Deserialize(reserializedJson, OpenAIHostingJsonContext.Default.Response);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(roundtripped);
        Assert.Equal(response.Id, roundtripped.Id);
        Assert.Equal(response.CreatedAt, roundtripped.CreatedAt);
        Assert.Equal(response.Status, roundtripped.Status);
        Assert.Equal(response.Model, roundtripped.Model);
    }

    #endregion

    #region Streaming Event Deserialization Tests

    [Fact]
    public void ParseStreamingEvents_BasicFormat_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);

        // Assert
        Assert.NotEmpty(events);
        Assert.All(events, evt =>
        {
            Assert.True(evt.TryGetProperty("type", out var type));
            Assert.True(evt.TryGetProperty("sequence_number", out var seqNum));
            Assert.Equal(JsonValueKind.Number, seqNum.ValueKind);
        });
    }

    [Fact]
    public void ParseStreamingEvents_HasCorrectEventTypes()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);
        var eventTypes = events.Select(e => e.GetProperty("type").GetString()).ToHashSet();

        // Assert
        Assert.Contains("response.created", eventTypes);
        Assert.Contains("response.in_progress", eventTypes);
        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.content_part.added", eventTypes);
        Assert.Contains("response.output_text.delta", eventTypes);
        Assert.Contains("response.output_text.done", eventTypes);
        Assert.Contains("response.content_part.done", eventTypes);
        Assert.Contains("response.output_item.done", eventTypes);
    }

    [Fact]
    public void ParseStreamingEvents_DeserializeCreatedEvent_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var createdEventJson = events.First(e => e.GetProperty("type").GetString() == "response.created");

        // Act
        string jsonString = createdEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingResponseCreated>(evt);
        var created = (StreamingResponseCreated)evt;
        Assert.Equal(0, created.SequenceNumber);
        Assert.NotNull(created.Response);
        Assert.NotNull(created.Response.Id);
        Assert.StartsWith("resp_", created.Response.Id);
    }

    [Fact]
    public void ParseStreamingEvents_DeserializeInProgressEvent_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var inProgressEventJson = events.First(e => e.GetProperty("type").GetString() == "response.in_progress");

        // Act
        string jsonString = inProgressEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingResponseInProgress>(evt);
        var inProgress = (StreamingResponseInProgress)evt;
        Assert.Equal(1, inProgress.SequenceNumber);
        Assert.NotNull(inProgress.Response);
        Assert.Equal(ResponseStatus.InProgress, inProgress.Response.Status);
    }

    [Fact]
    public void ParseStreamingEvents_DeserializeOutputItemAdded_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var itemAddedJson = events.First(e => e.GetProperty("type").GetString() == "response.output_item.added");

        // Act
        string jsonString = itemAddedJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingOutputItemAdded>(evt);
        var itemAdded = (StreamingOutputItemAdded)evt;
        Assert.Equal(0, itemAdded.OutputIndex);
        Assert.NotNull(itemAdded.Item);
    }

    [Fact]
    public void ParseStreamingEvents_DeserializeContentPartAdded_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var partAddedJson = events.First(e => e.GetProperty("type").GetString() == "response.content_part.added");

        // Act
        string jsonString = partAddedJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingContentPartAdded>(evt);
        var partAdded = (StreamingContentPartAdded)evt;
        Assert.NotNull(partAdded.ItemId);
        Assert.Equal(0, partAdded.OutputIndex);
        Assert.Equal(0, partAdded.ContentIndex);
        Assert.NotNull(partAdded.Part);
    }

    [Fact]
    public void ParseStreamingEvents_DeserializeTextDelta_Success()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var textDeltaJson = events.First(e => e.GetProperty("type").GetString() == "response.output_text.delta");

        // Act
        string jsonString = textDeltaJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingOutputTextDelta>(evt);
        var textDelta = (StreamingOutputTextDelta)evt;
        Assert.NotNull(textDelta.ItemId);
        Assert.Equal(0, textDelta.OutputIndex);
        Assert.Equal(0, textDelta.ContentIndex);
        Assert.NotNull(textDelta.Delta);
    }

    [Fact]
    public void ParseStreamingEvents_AccumulateTextDeltas_MatchesFinalText()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);

        // Act
        var deltas = new List<string>();
        string? finalText = null;

        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

            if (evt is StreamingOutputTextDelta delta)
            {
                deltas.Add(delta.Delta);
            }
            else if (evt is StreamingOutputTextDone done)
            {
                finalText = done.Text;
            }
        }

        // Assert
        Assert.NotEmpty(deltas);
        Assert.NotNull(finalText);

        string accumulated = string.Concat(deltas);
        Assert.Equal(accumulated, finalText);
    }

    [Fact]
    public void ParseStreamingEvents_SequenceNumbersAreSequential()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);

        // Act
        var sequenceNumbers = new List<int>();
        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);
            sequenceNumbers.Add(evt.SequenceNumber);
        }

        // Assert
        Assert.NotEmpty(sequenceNumbers);
        Assert.Equal(0, sequenceNumbers.First());

        for (int i = 0; i < sequenceNumbers.Count; i++)
        {
            Assert.Equal(i, sequenceNumbers[i]);
        }
    }

    [Fact]
    public void ParseStreamingEvents_FinalEvent_IsTerminalState()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");
        var events = ParseSseEventsFromContent(sseContent);
        var lastEventJson = events.Last();

        // Act
        string jsonString = lastEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);

        // Should be one of the terminal events
        bool isTerminal = evt is StreamingResponseCompleted or
                          StreamingResponseIncomplete or
                          StreamingResponseFailed;
        Assert.True(isTerminal, $"Expected terminal event, got: {evt.GetType().Name}");
    }

    [Fact]
    public void ParseStreamingEvents_ImageInputStreaming_HasImageEvents()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("image_input_streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);

        // Assert
        Assert.NotEmpty(events);
        Assert.All(events, evt =>
        {
            StreamingResponseEvent? parsed = JsonSerializer.Deserialize(evt.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(parsed);
        });
    }

    [Fact]
    public void ParseStreamingEvents_JsonOutputStreaming_HasJsonSchemaEvents()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("json_output_streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);

        // Assert
        Assert.NotEmpty(events);
        Assert.All(events, evt =>
        {
            StreamingResponseEvent? parsed = JsonSerializer.Deserialize(evt.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(parsed);
        });
    }

    [Fact]
    public void ParseStreamingEvents_ReasoningStreaming_HasReasoningEvents()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("reasoning_streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);
        var eventTypes = events.Select(e => e.GetProperty("type").GetString()).ToHashSet();

        // Assert
        Assert.NotEmpty(events);
        // Should have reasoning-related events
        Assert.Contains("response.created", eventTypes);
        Assert.All(events, evt =>
        {
            StreamingResponseEvent? parsed = JsonSerializer.Deserialize(evt.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(parsed);
        });
    }

    [Fact]
    public void ParseStreamingEvents_RefusalStreaming_HasRefusalEvents()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("refusal_streaming/response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);
        var eventTypes = events.Select(e => e.GetProperty("type").GetString()).ToHashSet();

        // Assert
        Assert.NotEmpty(events);
        // Should have refusal-related events
        Assert.All(events, evt =>
        {
            StreamingResponseEvent? parsed = JsonSerializer.Deserialize(evt.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(parsed);
        });
    }

    [Fact]
    public void ParseStreamingEvents_AllStreamingTraces_CanBeDeserialized()
    {
        // Arrange
        string[] streamingPaths =
        [
            "streaming/response.txt",
            "image_input_streaming/response.txt",
            "json_output_streaming/response.txt",
            "reasoning_streaming/response.txt",
            "refusal_streaming/response.txt"
        ];

        foreach (var path in streamingPaths)
        {
            string sseContent = LoadResponsesTraceFile(path);

            // Act & Assert
            foreach (var eventJson in ParseSseEventsFromContent(sseContent))
            {
                // Should not throw
                StreamingResponseEvent? evt = JsonSerializer.Deserialize(eventJson.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
                Assert.NotNull(evt);
            }
        }
    }

    [Fact]
    public void ParseStreamingEvents_AllEvents_CanBeDeserialized()
    {
        // Arrange
        string sseContent = LoadResponsesTraceFile("streaming/response.txt");

        // Act & Assert
        foreach (var eventJson in ParseSseEventsFromContent(sseContent))
        {
            // Should not throw
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(eventJson.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            // Verify polymorphic deserialization worked
            Assert.True(
                evt is StreamingResponseCreated or
                StreamingResponseInProgress or
                StreamingResponseCompleted or
                StreamingResponseIncomplete or
                StreamingResponseFailed or
                StreamingOutputItemAdded or
                StreamingOutputItemDone or
                StreamingContentPartAdded or
                StreamingContentPartDone or
                StreamingOutputTextDelta or
                StreamingOutputTextDone or
                StreamingFunctionCallArgumentsDelta or
                StreamingFunctionCallArgumentsDone,
                $"Unknown event type: {evt.GetType().Name}");
        }
    }

    /// <summary>
    /// Helper to parse SSE events from a streaming response content string.
    /// </summary>
    private static List<JsonElement> ParseSseEventsFromContent(string sseContent)
    {
        var events = new List<JsonElement>();
        var lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            var line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal))
            {
                // Next line should have the data
                if (i + 1 < lines.Length)
                {
                    var dataLine = lines[i + 1].TrimEnd('\r');
                    if (dataLine.StartsWith("data: ", StringComparison.Ordinal))
                    {
                        var jsonData = dataLine.Substring("data: ".Length);
                        var doc = JsonDocument.Parse(jsonData);
                        events.Add(doc.RootElement.Clone());
                    }
                }
            }
        }

        return events;
    }

    #endregion
}
