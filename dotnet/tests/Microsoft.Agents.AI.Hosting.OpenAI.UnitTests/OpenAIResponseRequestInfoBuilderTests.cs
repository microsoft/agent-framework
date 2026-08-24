// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for <see cref="OpenAIResponseRequestInfoBuilder"/>, in particular the mapping of the OpenAI
/// Responses <c>tool_choice</c> wire value onto its <see cref="ChatToolMode"/> equivalent.
/// </summary>
public sealed class OpenAIResponseRequestInfoBuilderTests
{
    [Fact]
    public void ToRequestInfo_MapsToolChoiceNone_ToChatToolModeNone()
    {
        // Arrange
        CreateResponse request = CreateRequestWithToolChoice("\"none\"");

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Equal(ChatToolMode.None, info.ToolChoice);
    }

    [Fact]
    public void ToRequestInfo_MapsToolChoiceAuto_ToChatToolModeAuto()
    {
        // Arrange
        CreateResponse request = CreateRequestWithToolChoice("\"auto\"");

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Equal(ChatToolMode.Auto, info.ToolChoice);
    }

    [Fact]
    public void ToRequestInfo_MapsToolChoiceRequired_ToRequireAny()
    {
        // Arrange
        CreateResponse request = CreateRequestWithToolChoice("\"required\"");

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Equal(ChatToolMode.RequireAny, info.ToolChoice);
    }

    [Fact]
    public void ToRequestInfo_MapsSpecificFunctionToolChoice_ToRequireSpecific()
    {
        // Arrange
        CreateResponse request = CreateRequestWithToolChoice("""{"type":"function","name":"get_weather"}""");

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        RequiredChatToolMode required = Assert.IsType<RequiredChatToolMode>(info.ToolChoice);
        Assert.Equal("get_weather", required.RequiredFunctionName);
    }

    [Fact]
    public void ToRequestInfo_MapsUnrecognizedToolChoice_ToNull()
    {
        // Arrange
        CreateResponse request = CreateRequestWithToolChoice("\"something_else\"");

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Null(info.ToolChoice);
    }

    [Fact]
    public void ToRequestInfo_NoToolChoice_MapsToNull()
    {
        // Arrange
        CreateResponse request = new() { Input = "hello" };

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Null(info.ToolChoice);
    }

    [Fact]
    public void ToRequestInfo_MapsFunctionToolToDeclaration()
    {
        // Arrange
        CreateResponse request = new()
        {
            Input = "hello",
            Tools =
            [
                ParseElement(
                    """
                    {
                      "type": "function",
                      "name": "get_weather",
                      "description": "Retrieves current weather.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "location": { "type": "string" }
                        },
                        "required": [ "location" ]
                      },
                      "strict": true
                    }
                    """)
            ]
        };

        // Act
        OpenAIResponseRequestInfo info = request.ToRequestInfo();

        // Assert
        Assert.Single(info.Tools!);
        AIFunctionDeclaration function = Assert.IsAssignableFrom<AIFunctionDeclaration>(Assert.Single(info.FunctionTools!));
        Assert.Equal("get_weather", function.Name);
        Assert.Equal("Retrieves current weather.", function.Description);
        Assert.True(function.JsonSchema.GetProperty("properties").TryGetProperty("location", out _));
        Assert.True(Assert.IsType<bool>(function.AdditionalProperties["strict"]));
    }

    private static CreateResponse CreateRequestWithToolChoice(string toolChoiceJson)
    {
        using JsonDocument document = JsonDocument.Parse(toolChoiceJson);
        return new()
        {
            Input = "hello",
            ToolChoice = document.RootElement.Clone(),
        };
    }

    private static JsonElement ParseElement(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
