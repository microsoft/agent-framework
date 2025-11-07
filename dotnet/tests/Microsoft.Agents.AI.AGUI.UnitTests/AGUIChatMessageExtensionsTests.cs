// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

// Custom complex type for testing tool call parameters
public sealed class WeatherRequest
{
    public string Location { get; set; } = string.Empty;
    public string Units { get; set; } = "celsius";
    public bool IncludeForecast { get; set; }
}

// Custom complex type for testing tool call results
public sealed class WeatherResponse
{
    public double Temperature { get; set; }
    public string Conditions { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
}

// Custom JsonSerializerContext for the custom types
[JsonSerializable(typeof(WeatherRequest))]
[JsonSerializable(typeof(WeatherResponse))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
internal sealed partial class CustomTypesContext : JsonSerializerContext
{
}

/// <summary>
/// Unit tests for the <see cref="AGUIChatMessageExtensions"/> class.
/// </summary>
public sealed class AGUIChatMessageExtensionsTests
{
    [Fact]
    public void AsChatMessages_WithEmptyCollection_ReturnsEmptyList()
    {
        // Arrange
        List<AGUIMessage> aguiMessages = [];

        // Act
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);

        // Assert
        Assert.NotNull(chatMessages);
        Assert.Empty(chatMessages);
    }

    [Fact]
    public void AsChatMessages_WithSingleMessage_ConvertsToChatMessageCorrectly()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIUserMessage
            {
                Id = "msg1",
                Content = "Hello"
            }
        ];

        // Act
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello", message.Text);
    }

    [Fact]
    public void AsChatMessages_WithMultipleMessages_PreservesOrder()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIUserMessage { Id = "msg1", Content = "First" },
            new AGUIAssistantMessage { Id = "msg2", Content = "Second" },
            new AGUIUserMessage { Id = "msg3", Content = "Third" }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        Assert.Equal(3, chatMessages.Count);
        Assert.Equal("First", chatMessages[0].Text);
        Assert.Equal("Second", chatMessages[1].Text);
        Assert.Equal("Third", chatMessages[2].Text);
    }

    [Fact]
    public void AsChatMessages_MapsAllSupportedRoleTypes_Correctly()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUISystemMessage { Id = "msg1", Content = "System message" },
            new AGUIUserMessage { Id = "msg2", Content = "User message" },
            new AGUIAssistantMessage { Id = "msg3", Content = "Assistant message" },
            new AGUIDeveloperMessage { Id = "msg4", Content = "Developer message" }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        Assert.Equal(4, chatMessages.Count);
        Assert.Equal(ChatRole.System, chatMessages[0].Role);
        Assert.Equal(ChatRole.User, chatMessages[1].Role);
        Assert.Equal(ChatRole.Assistant, chatMessages[2].Role);
        Assert.Equal("developer", chatMessages[3].Role.Value);
    }

    [Fact]
    public void AsAGUIMessages_WithEmptyCollection_ReturnsEmptyList()
    {
        // Arrange
        List<ChatMessage> chatMessages = [];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

        // Assert
        Assert.NotNull(aguiMessages);
        Assert.Empty(aguiMessages);
    }

    [Fact]
    public void AsAGUIMessages_WithSingleMessage_ConvertsToAGUIMessageCorrectly()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "Hello") { MessageId = "msg1" }
        ];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        Assert.Equal("msg1", message.Id);
        Assert.Equal(AGUIRoles.User, message.Role);
        Assert.Equal("Hello", ((AGUIUserMessage)message).Content);
    }

    [Fact]
    public void AsAGUIMessages_WithMultipleMessages_PreservesOrder()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Second"),
            new ChatMessage(ChatRole.User, "Third")
        ];

        // Act
        List<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        Assert.Equal(3, aguiMessages.Count);
        Assert.Equal("First", ((AGUIUserMessage)aguiMessages[0]).Content);
        Assert.Equal("Second", ((AGUIAssistantMessage)aguiMessages[1]).Content);
        Assert.Equal("Third", ((AGUIUserMessage)aguiMessages[2]).Content);
    }

    [Fact]
    public void AsAGUIMessages_PreservesMessageId_WhenPresent()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "Hello") { MessageId = "msg123" }
        ];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        Assert.Equal("msg123", message.Id);
    }

    [Theory]
    [InlineData(AGUIRoles.System, "system")]
    [InlineData(AGUIRoles.User, "user")]
    [InlineData(AGUIRoles.Assistant, "assistant")]
    [InlineData(AGUIRoles.Developer, "developer")]
    public void MapChatRole_WithValidRole_ReturnsCorrectChatRole(string aguiRole, string expectedRoleValue)
    {
        // Arrange & Act
        ChatRole role = AGUIChatMessageExtensions.MapChatRole(aguiRole);

        // Assert
        Assert.Equal(expectedRoleValue, role.Value);
    }

    [Fact]
    public void MapChatRole_WithUnknownRole_ThrowsInvalidOperationException()
    {
        // Arrange & Act & Assert
        Assert.Throws<InvalidOperationException>(() => AGUIChatMessageExtensions.MapChatRole("unknown"));
    }

    [Fact]
    public void AsAGUIMessages_WithToolResultMessage_SerializesResultCorrectly()
    {
        // Arrange
        var result = new Dictionary<string, object?> { ["temperature"] = 72, ["condition"] = "Sunny" };
        FunctionResultContent toolResult = new("call_123", result);
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];

        // Act
        List<AGUIMessage> aguiMessages = messages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        AGUIMessage aguiMessage = Assert.Single(aguiMessages);
        Assert.Equal(AGUIRoles.Tool, aguiMessage.Role);
        Assert.Equal("call_123", ((AGUIToolMessage)aguiMessage).ToolCallId);
        Assert.NotEmpty(((AGUIToolMessage)aguiMessage).Content);
        // Content should be serialized JSON
        Assert.Contains("temperature", ((AGUIToolMessage)aguiMessage).Content);
        Assert.Contains("72", ((AGUIToolMessage)aguiMessage).Content);
    }

    [Fact]
    public void AsAGUIMessages_WithNullToolResult_HandlesGracefully()
    {
        // Arrange
        FunctionResultContent toolResult = new("call_456", null);
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];

        // Act
        List<AGUIMessage> aguiMessages = messages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        AGUIMessage aguiMessage = Assert.Single(aguiMessages);
        Assert.Equal(AGUIRoles.Tool, aguiMessage.Role);
        Assert.Equal("call_456", ((AGUIToolMessage)aguiMessage).ToolCallId);
        Assert.Equal(string.Empty, ((AGUIToolMessage)aguiMessage).Content);
    }

    [Fact]
    public void AsAGUIMessages_WithoutTypeInfoResolver_ThrowsInvalidOperationException()
    {
        // Arrange
        FunctionResultContent toolResult = new("call_789", "Result");
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];
        System.Text.Json.JsonSerializerOptions optionsWithoutResolver = new();

        // Act & Assert
        NotSupportedException ex = Assert.Throws<NotSupportedException>(() => messages.AsAGUIMessages(optionsWithoutResolver).ToList());
        Assert.Contains("JsonTypeInfo", ex.Message);
    }

    [Fact]
    public void AsChatMessages_WithToolMessage_DeserializesResultCorrectly()
    {
        // Arrange
        const string JsonContent = "{\"status\":\"success\",\"value\":42}";
        List<AGUIMessage> aguiMessages =
        [
            new AGUIToolMessage
            {
                Id = "msg1",
                Content = JsonContent,
                ToolCallId = "call_abc"
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.Tool, message.Role);
        FunctionResultContent result = Assert.IsType<FunctionResultContent>(message.Contents[0]);
        Assert.Equal("call_abc", result.CallId);
        Assert.NotNull(result.Result);
    }

    [Fact]
    public void AsChatMessages_WithEmptyToolContent_CreatesNullResult()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIToolMessage
            {
                Id = "msg1",
                Content = string.Empty,
                ToolCallId = "call_def"
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        FunctionResultContent result = Assert.IsType<FunctionResultContent>(message.Contents[0]);
        Assert.Equal("call_def", result.CallId);
        Assert.Equal(string.Empty, result.Result);
    }

    [Fact]
    public void AsChatMessages_WithToolMessageWithoutCallId_TreatsAsRegularMessage()
    {
        // Arrange - use valid JSON for Content
        List<AGUIMessage> aguiMessages =
        [
            new AGUIToolMessage
            {
                Id = "msg1",
                Content = "{\"result\":\"Some content\"}",
                ToolCallId = string.Empty
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.Tool, message.Role);
        var resultContent = Assert.IsType<FunctionResultContent>(message.Contents.First());
        Assert.Equal(string.Empty, resultContent.CallId);
    }

    [Fact]
    public void RoundTrip_ToolResultMessage_PreservesData()
    {
        // Arrange
        var resultData = new Dictionary<string, object?> { ["location"] = "Seattle", ["temperature"] = 68, ["forecast"] = "Partly cloudy" };
        FunctionResultContent originalResult = new("call_roundtrip", resultData);
        ChatMessage originalMessage = new(ChatRole.Tool, [originalResult]);

        // Act - Convert to AGUI and back
        List<ChatMessage> originalList = [originalMessage];
        AGUIMessage aguiMessage = originalList.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).Single();
        List<AGUIMessage> aguiList = [aguiMessage];
        ChatMessage reconstructedMessage = aguiList.AsChatMessages(AGUIJsonSerializerContext.Default.Options).Single();

        // Assert
        Assert.Equal(ChatRole.Tool, reconstructedMessage.Role);
        FunctionResultContent reconstructedResult = Assert.IsType<FunctionResultContent>(reconstructedMessage.Contents[0]);
        Assert.Equal("call_roundtrip", reconstructedResult.CallId);
        Assert.NotNull(reconstructedResult.Result);
    }

    [Fact]
    public void MapChatRole_WithToolRole_ReturnsToolChatRole()
    {
        // Arrange & Act
        ChatRole role = AGUIChatMessageExtensions.MapChatRole(AGUIRoles.Tool);

        // Assert
        Assert.Equal(ChatRole.Tool, role);
    }

    #region Custom Type Serialization Tests

    [Fact]
    public void AsChatMessages_WithFunctionCallContainingCustomType_SerializesCorrectly()
    {
        // Arrange
        var customRequest = new WeatherRequest { Location = "Seattle", Units = "fahrenheit", IncludeForecast = true };
        var parameters = new Dictionary<string, object?>
        {
            ["location"] = customRequest.Location,
            ["units"] = customRequest.Units,
            ["includeForecast"] = customRequest.IncludeForecast
        };

        List<AGUIMessage> aguiMessages =
        [
            new AGUIAssistantMessage
            {
                Id = "msg1",
                ToolCalls =
                [
                    new AGUIToolCall
                    {
                        Id = "call_1",
                        Function = new AGUIFunctionCall
                        {
                            Name = "GetWeather",
                            Arguments = System.Text.Json.JsonSerializer.Serialize(parameters, AGUIJsonSerializerContext.Default.Options)
                        }
                    }
                ]
            }
        ];

        // Combine contexts for serialization
        var combinedOptions = new System.Text.Json.JsonSerializerOptions
        {
            TypeInfoResolver = System.Text.Json.Serialization.Metadata.JsonTypeInfoResolver.Combine(
                AGUIJsonSerializerContext.Default,
                CustomTypesContext.Default)
        };

        // Act
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages(combinedOptions);

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.Assistant, message.Role);
        var toolCallContent = Assert.IsType<FunctionCallContent>(message.Contents.First());
        Assert.Equal("call_1", toolCallContent.CallId);
        Assert.Equal("GetWeather", toolCallContent.Name);
        Assert.NotNull(toolCallContent.Arguments);
        // Compare as strings since deserialization produces JsonElement objects
        Assert.Equal("Seattle", ((System.Text.Json.JsonElement)toolCallContent.Arguments["location"]!).GetString());
        Assert.Equal("fahrenheit", ((System.Text.Json.JsonElement)toolCallContent.Arguments["units"]!).GetString());
        Assert.True(toolCallContent.Arguments["includeForecast"] is System.Text.Json.JsonElement j && j.GetBoolean());
    }

    [Fact]
    public void AsAGUIMessages_WithFunctionResultContainingCustomType_SerializesCorrectly()
    {
        // Arrange
        var customResponse = new WeatherResponse { Temperature = 72.5, Conditions = "Sunny", Timestamp = DateTime.UtcNow };
        var resultObject = new Dictionary<string, object?>
        {
            ["temperature"] = customResponse.Temperature,
            ["conditions"] = customResponse.Conditions,
            ["timestamp"] = customResponse.Timestamp.ToString("O")
        };

        var resultJson = System.Text.Json.JsonSerializer.Serialize(resultObject, AGUIJsonSerializerContext.Default.Options);
        var functionResult = new FunctionResultContent("call_1", System.Text.Json.JsonSerializer.Deserialize<System.Text.Json.JsonElement>(resultJson, AGUIJsonSerializerContext.Default.Options));
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.Tool, [functionResult])
        ];

        // Combine contexts for serialization
        var combinedOptions = new System.Text.Json.JsonSerializerOptions
        {
            TypeInfoResolver = System.Text.Json.Serialization.Metadata.JsonTypeInfoResolver.Combine(
                AGUIJsonSerializerContext.Default,
                CustomTypesContext.Default)
        };

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(combinedOptions);

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        var toolMessage = Assert.IsType<AGUIToolMessage>(message);
        Assert.Equal("call_1", toolMessage.ToolCallId);
        Assert.NotNull(toolMessage.Content);

        // Verify the content can be deserialized back
        var deserializedResult = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, System.Text.Json.JsonElement>>(
            toolMessage.Content,
            combinedOptions);
        Assert.NotNull(deserializedResult);
        Assert.Equal(72.5, deserializedResult["temperature"].GetDouble());
        Assert.Equal("Sunny", deserializedResult["conditions"].GetString());
    }

    [Fact]
    public void RoundTrip_WithCustomTypesInFunctionCallAndResult_PreservesData()
    {
        // Arrange
        var customRequest = new WeatherRequest { Location = "New York", Units = "celsius", IncludeForecast = false };
        var parameters = new Dictionary<string, object?>
        {
            ["location"] = customRequest.Location,
            ["units"] = customRequest.Units,
            ["includeForecast"] = customRequest.IncludeForecast
        };

        var customResponse = new WeatherResponse { Temperature = 22.3, Conditions = "Cloudy", Timestamp = DateTime.UtcNow };
        var resultObject = new Dictionary<string, object?>
        {
            ["temperature"] = customResponse.Temperature,
            ["conditions"] = customResponse.Conditions,
            ["timestamp"] = customResponse.Timestamp.ToString("O")
        };

        var resultJson = System.Text.Json.JsonSerializer.Serialize(resultObject, AGUIJsonSerializerContext.Default.Options);
        var resultElement = System.Text.Json.JsonSerializer.Deserialize<System.Text.Json.JsonElement>(resultJson, AGUIJsonSerializerContext.Default.Options);

        List<ChatMessage> originalChatMessages =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_1", "GetWeather", parameters)]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call_1", resultElement)])
        ];

        // Combine contexts for serialization
        var combinedOptions = new System.Text.Json.JsonSerializerOptions
        {
            TypeInfoResolver = System.Text.Json.Serialization.Metadata.JsonTypeInfoResolver.Combine(
                AGUIJsonSerializerContext.Default,
                CustomTypesContext.Default)
        };

        // Act - Convert to AGUI messages and back
        IEnumerable<AGUIMessage> aguiMessages = originalChatMessages.AsAGUIMessages(combinedOptions);
        List<ChatMessage> roundTrippedChatMessages = aguiMessages.AsChatMessages(combinedOptions).ToList();

        // Assert
        Assert.Equal(2, roundTrippedChatMessages.Count);

        // Verify function call
        ChatMessage callMessage = roundTrippedChatMessages[0];
        Assert.Equal(ChatRole.Assistant, callMessage.Role);
        var functionCall = Assert.IsType<FunctionCallContent>(callMessage.Contents.First());
        Assert.Equal("call_1", functionCall.CallId);
        Assert.Equal("GetWeather", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        // Compare string values from JsonElement
        Assert.Equal(customRequest.Location, functionCall.Arguments["location"]?.ToString());
        Assert.Equal(customRequest.Units, functionCall.Arguments["units"]?.ToString());

        // Verify function result
        ChatMessage resultMessage = roundTrippedChatMessages[1];
        Assert.Equal(ChatRole.Tool, resultMessage.Role);
        var functionResultContent = Assert.IsType<FunctionResultContent>(resultMessage.Contents.First());
        Assert.Equal("call_1", functionResultContent.CallId);
        Assert.NotNull(functionResultContent.Result);
    }

    [Fact]
    public void AsAGUIMessages_WithNestedCustomObjects_HandlesComplexSerialization()
    {
        // Arrange - nested custom types
        var nestedParameters = new Dictionary<string, object?>
        {
            ["request"] = new Dictionary<string, object?>
            {
                ["location"] = "Boston",
                ["options"] = new Dictionary<string, object?>
                {
                    ["units"] = "fahrenheit",
                    ["includeHumidity"] = true,
                    ["daysAhead"] = 5
                }
            }
        };

        var functionCall = new FunctionCallContent("call_nested", "GetDetailedWeather", nestedParameters);
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.Assistant, [functionCall])
        ];

        // Combine contexts for serialization
        var combinedOptions = new System.Text.Json.JsonSerializerOptions
        {
            TypeInfoResolver = System.Text.Json.Serialization.Metadata.JsonTypeInfoResolver.Combine(
                AGUIJsonSerializerContext.Default,
                CustomTypesContext.Default)
        };

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(combinedOptions);

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        var assistantMessage = Assert.IsType<AGUIAssistantMessage>(message);
        Assert.NotNull(assistantMessage.ToolCalls);
        var toolCall = Assert.Single(assistantMessage.ToolCalls);
        Assert.Equal("call_nested", toolCall.Id);
        Assert.Equal("GetDetailedWeather", toolCall.Function?.Name);

        // Verify nested structure is preserved
        var deserializedArgs = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, System.Text.Json.JsonElement>>(
            toolCall.Function?.Arguments ?? "{}",
            combinedOptions);
        Assert.NotNull(deserializedArgs);
        Assert.True(deserializedArgs.ContainsKey("request"));
    }

    [Fact]
    public void AsAGUIMessages_WithDictionaryContainingCustomTypes_SerializesDirectly()
    {
        // Arrange - Create a dictionary with custom type values (not flattened)
        var customRequest = new WeatherRequest { Location = "Tokyo", Units = "celsius", IncludeForecast = true };
        var parameters = new Dictionary<string, object?>
        {
            ["customRequest"] = customRequest, // Custom type as value
            ["simpleString"] = "test",
            ["simpleNumber"] = 42
        };

        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_custom", "ProcessWeather", parameters)])
        ];

        // Combine contexts for serialization
        var combinedOptions = new System.Text.Json.JsonSerializerOptions
        {
            TypeInfoResolver = System.Text.Json.Serialization.Metadata.JsonTypeInfoResolver.Combine(
                AGUIJsonSerializerContext.Default,
                CustomTypesContext.Default)
        };

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(combinedOptions);

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        var assistantMessage = Assert.IsType<AGUIAssistantMessage>(message);
        Assert.NotNull(assistantMessage.ToolCalls);
        var toolCall = Assert.Single(assistantMessage.ToolCalls);
        Assert.Equal("call_custom", toolCall.Id);
        Assert.Equal("ProcessWeather", toolCall.Function?.Name);

        // Verify custom type was serialized correctly without flattening
        var deserializedArgs = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, System.Text.Json.JsonElement>>(
            toolCall.Function?.Arguments ?? "{}",
            combinedOptions);
        Assert.NotNull(deserializedArgs);
        Assert.True(deserializedArgs.ContainsKey("customRequest"));
        Assert.True(deserializedArgs.ContainsKey("simpleString"));
        Assert.True(deserializedArgs.ContainsKey("simpleNumber"));

        // Verify the custom type properties are accessible
        var customRequestElement = deserializedArgs["customRequest"];
        Assert.Equal("Tokyo", customRequestElement.GetProperty("Location").GetString());
        Assert.Equal("celsius", customRequestElement.GetProperty("Units").GetString());
        Assert.True(customRequestElement.GetProperty("IncludeForecast").GetBoolean());

        // Verify simple types
        Assert.Equal("test", deserializedArgs["simpleString"].GetString());
        Assert.Equal(42, deserializedArgs["simpleNumber"].GetInt32());
    }

    #endregion
}
