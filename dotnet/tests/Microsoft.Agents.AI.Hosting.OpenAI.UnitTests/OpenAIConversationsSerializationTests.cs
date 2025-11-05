// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for OpenAI Conversations API model serialization and deserialization.
/// These tests verify that our models correctly serialize to and deserialize from JSON
/// matching the OpenAI wire format, without testing actual API implementation behavior.
/// </summary>
public sealed class OpenAIConversationsSerializationTests
{
    private const string TracesBasePath = "ConformanceTraces/Conversations";

    /// <summary>
    /// Loads a JSON file from the conformance traces directory.
    /// </summary>
    private static string LoadTraceFile(string relativePath)
    {
        var fullPath = System.IO.Path.Combine(TracesBasePath, relativePath);

        if (!System.IO.File.Exists(fullPath))
        {
            throw new System.IO.FileNotFoundException($"Conformance trace file not found: {fullPath}");
        }

        return System.IO.File.ReadAllText(fullPath);
    }

    #region Request Serialization Tests

    [Fact]
    public void Deserialize_CreateConversationRequest_Success()
    {
        // Arrange
        string json = LoadTraceFile("basic/create_conversation_request.json");

        // Act
        CreateConversationRequest? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateConversationRequest);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Metadata);
    }

    [Fact]
    public void Deserialize_CreateConversationWithItems_Success()
    {
        // Arrange
        string json = LoadTraceFile("create_with_items/create_request.json");

        // Act
        CreateConversationRequest? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateConversationRequest);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Items);
        Assert.True(request.Items.Count > 0);
    }

    [Fact]
    public void Deserialize_CreateItemsRequest_Success()
    {
        // Arrange
        string json = LoadTraceFile("add_items/request.json");

        // Act
        CreateItemsRequest? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.CreateItemsRequest);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Items);
        Assert.True(request.Items.Count > 0);
    }

    [Fact]
    public void Deserialize_UpdateConversationRequest_Success()
    {
        // Arrange
        string json = LoadTraceFile("update_conversation/request.json");

        // Act
        UpdateConversationRequest? request = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.UpdateConversationRequest);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Metadata);
    }

    [Fact]
    public void Serialize_CreateConversationRequest_MatchesFormat()
    {
        // Arrange
        var request = new CreateConversationRequest
        {
            Metadata = new System.Collections.Generic.Dictionary<string, string>
            {
                ["test_key"] = "test_value"
            }
        };

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateConversationRequest);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.True(root.TryGetProperty("metadata", out var metadata));
        Assert.Equal(JsonValueKind.Object, metadata.ValueKind);
        Assert.Equal("test_value", metadata.GetProperty("test_key").GetString());
    }

    [Fact]
    public void Serialize_CreateConversationRequestWithItems_IncludesItems()
    {
        // Arrange
        var request = new CreateConversationRequest
        {
            Items =
            [
                new ResponsesUserMessageItemParam
                {
                    Content = InputMessageContent.FromContents(new ItemContentInputText { Text = "test" })
                }
            ],
            Metadata = []
        };

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateConversationRequest);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.True(root.TryGetProperty("items", out var items));
        Assert.Equal(JsonValueKind.Array, items.ValueKind);
        Assert.Equal(1, items.GetArrayLength());
    }

    [Fact]
    public void Serialize_NullableFields_AreOmittedWhenNull()
    {
        // Arrange
        var request = new CreateConversationRequest();

        // Act
        string json = JsonSerializer.Serialize(request, OpenAIHostingJsonContext.Default.CreateConversationRequest);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Optional fields should not be present when null or use null value
        // Either the property doesn't exist or it's explicitly null
        bool hasItems = root.TryGetProperty("items", out var itemsProp);
        if (hasItems)
        {
            Assert.Equal(JsonValueKind.Null, itemsProp.ValueKind);
        }
    }

    #endregion

    #region Response Deserialization Tests

    [Fact]
    public void Deserialize_Conversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("basic/create_conversation_response.json");

        // Act
        Conversation? conversation = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Conversation);

        // Assert
        Assert.NotNull(conversation);
        Assert.StartsWith("conv_", conversation.Id);
        Assert.Equal("conversation", conversation.Object);
        Assert.True(conversation.CreatedAt > 0);
        Assert.NotNull(conversation.Metadata);
    }

    [Fact]
    public void Deserialize_ConversationRoundTrip_PreservesData()
    {
        // Arrange
        string originalJson = LoadTraceFile("basic/create_conversation_response.json");

        // Act - Deserialize and re-serialize
        Conversation? conversation = JsonSerializer.Deserialize(originalJson, OpenAIHostingJsonContext.Default.Conversation);
        string reserializedJson = JsonSerializer.Serialize(conversation, OpenAIHostingJsonContext.Default.Conversation);
        Conversation? roundtripped = JsonSerializer.Deserialize(reserializedJson, OpenAIHostingJsonContext.Default.Conversation);

        // Assert
        Assert.NotNull(conversation);
        Assert.NotNull(roundtripped);
        Assert.Equal(conversation.Id, roundtripped.Id);
        Assert.Equal(conversation.CreatedAt, roundtripped.CreatedAt);
        Assert.Equal(conversation.Object, roundtripped.Object);
    }

    [Fact]
    public void Deserialize_ItemListResponse_Success()
    {
        // Arrange
        string json = LoadTraceFile("list_items/response.json");

        // Act - The list_items response uses ListResponse<ItemResource>, not ConversationListResponse
        ListResponse<ItemResource>? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ListResponseItemResource);

        // Assert
        Assert.NotNull(response);
        Assert.Equal("list", response.Object);
        Assert.NotNull(response.Data);
        Assert.NotNull(response.FirstId);
        Assert.NotNull(response.LastId);
        Assert.False(response.HasMore);
    }

    [Fact]
    public void Deserialize_ItemResource_Success()
    {
        // Arrange
        string json = LoadTraceFile("retrieve_item/response.json");

        // Act
        ItemResource? item = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ItemResource);

        // Assert
        Assert.NotNull(item);
        Assert.StartsWith("msg_", item.Id);
        Assert.Equal("message", item.Type);
        var messageItem = Assert.IsType<ResponsesAssistantMessageItemResource>(item);
        Assert.NotNull(messageItem.Content);
        Assert.NotEmpty(messageItem.Content);
    }

    [Fact]
    public void Deserialize_DeleteResponse_Success()
    {
        // Arrange
        string json = LoadTraceFile("delete_conversation/response.json");

        // Act
        DeleteResponse? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.DeleteResponse);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Id);
        Assert.Equal("conversation.deleted", response.Object);
        Assert.True(response.Deleted);
    }

    [Fact]
    public void Deserialize_DeleteItemResponse_Success()
    {
        // Arrange
        string json = LoadTraceFile("delete_item/response.json");

        // Act
        DeleteResponse? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.DeleteResponse);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Id);
        Assert.Equal("conversation.item.deleted", response.Object);
        Assert.True(response.Deleted);
    }

    [Fact]
    public void Deserialize_ErrorResponse_Success()
    {
        // Arrange
        string json = LoadTraceFile("error_conversation_not_found/response.json");

        // Act
        ErrorResponse? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ErrorResponse);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Error);
        Assert.NotNull(response.Error.Message);
        Assert.NotNull(response.Error.Type);
    }

    [Fact]
    public void Deserialize_AllConversationResponses_HaveRequiredFields()
    {
        // Arrange
        string[] responsePaths =
        [
            "basic/create_conversation_response.json",
            "create_with_items/create_response.json",
            "retrieve_conversation/response.json",
            "update_conversation/response.json"
        ];

        foreach (var path in responsePaths)
        {
            string json = LoadTraceFile(path);

            // Act
            Conversation? conversation = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.Conversation);

            // Assert
            Assert.NotNull(conversation);
            Assert.NotNull(conversation.Id);
            Assert.Equal("conversation", conversation.Object);
            Assert.True(conversation.CreatedAt > 0, $"Conversation from {path} should have created_at");
        }
    }

    [Fact]
    public void Deserialize_AllItemResponses_HaveRequiredFields()
    {
        // Arrange - Use list_items response which has multiple items
        string json = LoadTraceFile("list_items/response.json");
        ListResponse<ItemResource>? response = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ListResponseItemResource);
        Assert.NotNull(response);
        Assert.NotNull(response.Data);

        // Act & Assert
        foreach (var item in response.Data)
        {
            Assert.NotNull(item);
            Assert.NotNull(item.Id);
            Assert.Equal("message", item.Type);
            var messageItem = Assert.IsAssignableFrom<ResponsesMessageItemResource>(item);
            // Content is on concrete message types (ResponsesAssistantMessageItemResource, etc.)
            // For this test, we just verify the type is correct
            Assert.NotNull(messageItem);
        }
    }

    [Fact]
    public void Serialize_Conversation_MatchesFormat()
    {
        // Arrange
        var conversation = new Conversation
        {
            Id = "conv_test123",
            CreatedAt = 1234567890,
            Metadata = new System.Collections.Generic.Dictionary<string, string>
            {
                ["test_key"] = "test_value"
            }
        };

        // Act
        string json = JsonSerializer.Serialize(conversation, OpenAIHostingJsonContext.Default.Conversation);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.Equal("conv_test123", root.GetProperty("id").GetString());
        Assert.Equal("conversation", root.GetProperty("object").GetString());
        Assert.Equal(1234567890, root.GetProperty("created_at").GetInt64());
        var metadata = root.GetProperty("metadata");
        Assert.Equal("test_value", metadata.GetProperty("test_key").GetString());
    }

    [Fact]
    public void Serialize_ConversationListResponse_MatchesFormat()
    {
        // Arrange
        var response = new ListResponse<Conversation>
        {
            Data =
            [
                new()
                {
                    Id = "conv_1",
                    CreatedAt = 1234567890,
                    Metadata = []
                }
            ],
            HasMore = false
        };

        // Act
        string json = JsonSerializer.Serialize(response, OpenAIHostingJsonUtilities.DefaultOptions);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.Equal("list", root.GetProperty("object").GetString());
        var data = root.GetProperty("data");
        Assert.Equal(JsonValueKind.Array, data.ValueKind);
        Assert.Equal(1, data.GetArrayLength());
        Assert.False(root.GetProperty("has_more").GetBoolean());
    }

    [Fact]
    public void Serialize_DeleteResponse_MatchesFormat()
    {
        // Arrange
        var response = new DeleteResponse
        {
            Id = "conv_test123",
            Object = "conversation.deleted",
            Deleted = true
        };

        // Act
        string json = JsonSerializer.Serialize(response, OpenAIHostingJsonContext.Default.DeleteResponse);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        Assert.Equal("conv_test123", root.GetProperty("id").GetString());
        Assert.Equal("conversation.deleted", root.GetProperty("object").GetString());
        Assert.True(root.GetProperty("deleted").GetBoolean());
    }

    [Fact]
    public void Serialize_ErrorResponse_MatchesFormat()
    {
        // Arrange
        var response = new ErrorResponse
        {
            Error = new ErrorDetails
            {
                Message = "Conversation not found",
                Type = "invalid_request_error"
            }
        };

        // Act
        string json = JsonSerializer.Serialize(response, OpenAIHostingJsonContext.Default.ErrorResponse);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert
        var error = root.GetProperty("error");
        Assert.Equal("Conversation not found", error.GetProperty("message").GetString());
        Assert.Equal("invalid_request_error", error.GetProperty("type").GetString());
    }

    #endregion

    #region Integration with Responses API Tests

    [Fact]
    public void Deserialize_ResponsesAPIRequestWithConversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("basic/first_message_request.json");

        // Act
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Verify the request has conversation field
        Assert.True(root.TryGetProperty("conversation", out var conversation));
        var conversationId = conversation.GetString();
        Assert.NotNull(conversationId);
        Assert.StartsWith("conv_", conversationId);

        // Assert - Has standard Responses API fields
        Assert.True(root.TryGetProperty("model", out var model));
        Assert.True(root.TryGetProperty("input", out var input));
        Assert.True(root.TryGetProperty("max_output_tokens", out var maxTokens));
    }

    [Fact]
    public void Deserialize_ResponsesAPIResponseWithConversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("basic/first_message_response.json");

        // Act
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Verify the response has conversation field
        Assert.True(root.TryGetProperty("conversation", out var conversation));
        Assert.Equal(JsonValueKind.Object, conversation.ValueKind);
        Assert.True(conversation.TryGetProperty("id", out var conversationId));
        Assert.NotNull(conversationId.GetString());

        // Assert - Has standard Responses API fields
        Assert.True(root.TryGetProperty("id", out var responseId));
        Assert.True(root.TryGetProperty("object", out var obj));
        Assert.Equal("response", obj.GetString());
        Assert.True(root.TryGetProperty("status", out var status));
        Assert.True(root.TryGetProperty("output", out var output));
    }

    [Fact]
    public void Deserialize_StreamingResponseWithConversation_Success()
    {
        // Arrange
        string sseContent = LoadTraceFile("basic_streaming/first_message_response.txt");

        // Act
        var events = ParseSseEventsFromContent(sseContent);

        // Assert - At least one event should be present
        Assert.NotEmpty(events);

        // Assert - Check if any event has conversation reference
        var createdEvent = events.FirstOrDefault(e =>
            e.TryGetProperty("type", out var type) &&
            type.GetString() == "response.created");

        if (!createdEvent.Equals(default(JsonElement)))
        {
            Assert.True(createdEvent.TryGetProperty("response", out var response));
            // Conversation field may be in the response object
        }
    }

    [Fact]
    public void Deserialize_ImageInputWithConversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("image_input/first_message_request.json");

        // Act
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Verify has conversation and image input
        Assert.True(root.TryGetProperty("conversation", out var conversation));
        Assert.True(root.TryGetProperty("input", out var input));
        Assert.Equal(JsonValueKind.Array, input.ValueKind);
    }

    [Fact]
    public void Deserialize_ToolCallWithConversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("tool_call/first_message_request.json");

        // Act
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Verify has conversation and tools
        Assert.True(root.TryGetProperty("conversation", out var conversation));
        Assert.True(root.TryGetProperty("tools", out var tools));
        Assert.Equal(JsonValueKind.Array, tools.ValueKind);
    }

    [Fact]
    public void Deserialize_RefusalWithConversation_Success()
    {
        // Arrange
        string json = LoadTraceFile("refusal/first_message_request.json");

        // Act
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Assert - Verify has conversation
        Assert.True(root.TryGetProperty("conversation", out var conversation));
        Assert.NotNull(conversation.GetString());
    }

    /// <summary>
    /// Helper to parse SSE events from a streaming response content string.
    /// </summary>
    private static System.Collections.Generic.List<JsonElement> ParseSseEventsFromContent(string sseContent)
    {
        var events = new System.Collections.Generic.List<JsonElement>();
        var lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            var line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal) && i + 1 < lines.Length)
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

        return events;
    }

    #endregion
}
