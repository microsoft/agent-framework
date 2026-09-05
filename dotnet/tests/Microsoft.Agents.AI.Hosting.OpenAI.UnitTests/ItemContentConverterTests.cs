// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for converting between agent content and Responses API message content.
/// </summary>
public sealed class ItemContentConverterTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void FunctionApprovalResponse_RoundTripThroughJson_PreservesContent(bool approved)
    {
        // Arrange
        ToolApprovalResponseContent original = new(
            "request-1",
            approved,
            new FunctionCallContent("call-1", "get_weather", new Dictionary<string, object?>
            {
                ["location"] = "Seattle",
                ["options"] = new Dictionary<string, object?> { ["forecast"] = true }
            }));

        // Act
        ItemContentFunctionApprovalResponse item = Assert.IsType<ItemContentFunctionApprovalResponse>(
            ItemContentConverter.ToItemContent(original));
        string json = JsonSerializer.Serialize(item, OpenAIHostingJsonContext.Default.ItemContent);
        ItemContent deserialized = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ItemContent)!;
        ToolApprovalResponseContent result = Assert.IsType<ToolApprovalResponseContent>(ItemContentConverter.ToAIContent(deserialized));

        // Assert
        using JsonDocument document = JsonDocument.Parse(json);
        Assert.Equal("function_approval_response", document.RootElement.GetProperty("type").GetString());
        Assert.Equal("call-1", document.RootElement.GetProperty("function_call").GetProperty("id").GetString());
        Assert.Equal(original.RequestId, result.RequestId);
        Assert.Equal(approved, result.Approved);
        FunctionCallContent functionCall = Assert.IsType<FunctionCallContent>(result.ToolCall);
        Assert.Equal("call-1", functionCall.CallId);
        Assert.Equal("get_weather", functionCall.Name);
        Assert.Equal("Seattle", Assert.IsType<JsonElement>(functionCall.Arguments!["location"]).GetString());
        Assert.True(Assert.IsType<JsonElement>(functionCall.Arguments["options"]).GetProperty("forecast").GetBoolean());
        Assert.Same(original, item.RawRepresentation);
        Assert.Same(original, ItemContentConverter.ToAIContent(item));
        Assert.Same(deserialized, result.RawRepresentation);
        Assert.Same(deserialized, ItemContentConverter.ToItemContent(result));
    }

    [Fact]
    public void ToItemContent_FunctionApprovalResponse_WithNullArguments_RoundTrips()
    {
        // Arrange
        ToolApprovalResponseContent original = new("request-1", true, new FunctionCallContent("call-1", "get_time"));

        // Act
        ItemContent? item = ItemContentConverter.ToItemContent(original);
        string json = JsonSerializer.Serialize(item, OpenAIHostingJsonContext.Default.ItemContent);
        ItemContent deserialized = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.ItemContent)!;
        ToolApprovalResponseContent result = Assert.IsType<ToolApprovalResponseContent>(ItemContentConverter.ToAIContent(deserialized));

        // Assert
        Assert.Null(Assert.IsType<FunctionCallContent>(result.ToolCall).Arguments);
    }

    [Fact]
    public void ToItemContent_NonFunctionApprovalResponse_DoesNotMisrepresentToolCall()
    {
        // Arrange
        ToolApprovalResponseContent approval = new(
            "request-1", true, new McpServerToolCallContent("call-1", "search", "https://example.com/mcp"));

        // Act
        ItemContent? item = ItemContentConverter.ToItemContent(approval);

        // Assert
        Assert.Null(item);
    }
}
