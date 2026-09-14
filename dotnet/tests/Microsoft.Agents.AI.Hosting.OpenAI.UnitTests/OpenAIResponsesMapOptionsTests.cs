// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for default and custom Responses request mapping.
/// </summary>
public sealed class OpenAIResponsesMapOptionsTests
{
    [Fact]
    public void DefaultMapping_RejectsClientFunctions()
    {
        // Arrange
        var mapOptions = new OpenAIResponsesMapOptions();
        using JsonDocument body = CreateBody();

        // Act & Assert
#pragma warning disable MAAI001
        Assert.False(mapOptions.DangerouslyAllowClientFunctionTools);
#pragma warning restore MAAI001
        Assert.Throws<NotSupportedException>(() => OpenAIResponses.ToAgentRunRequest(body.RootElement, mapOptions));
    }

    [Fact]
    public void DefaultMapping_Enabled_ForwardsDuplicatesWithoutModifyingRequest()
    {
        // Arrange
        using JsonDocument body = CreateBody();
        var request = new OpenAIResponseRequestInfo
        {
            Tools = [body.RootElement.GetProperty("tools")[0], body.RootElement.GetProperty("tools")[1]]
        };
        var originalTools = request.Tools;
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions { DangerouslyAllowClientFunctionTools = true };
#pragma warning restore MAAI001

        // Act
        var result = Assert.IsType<ChatClientAgentRunOptions>(mapOptions.RunOptionsFactory(request));

        // Assert
        Assert.Same(originalTools, request.Tools);
        Assert.Equal(2, result.ChatOptions!.Tools!.Count);
        Assert.All(result.ChatOptions.Tools, tool =>
        {
            Assert.Equal("get_weather", tool.Name);
            Assert.IsAssignableFrom<AIFunctionDeclaration>(tool);
            Assert.False(tool is AIFunction);
        });
        Assert.Null(result.ChatOptions.ToolMode);
        Assert.Null(result.ChatOptions.AllowMultipleToolCalls);
        Assert.Null(result.ChatClientFactory);
    }

    [Theory]
    [InlineData(false, null)]
    [InlineData(true, null)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void CustomMapping_ReceivesAllToolsAndReturnsUnchangedOptions(bool allowClientFunctions, bool? allowMultipleToolCalls)
    {
        // Arrange
        using JsonDocument body = CreateBody();
        AIFunction hostedFunction = AIFunctionFactory.Create(() => "hosted", "get_weather");
        Func<IChatClient, IChatClient> factory = client => client;
        var configuredOptions = new ChatClientAgentRunOptions(new ChatOptions
        {
            Tools = [hostedFunction],
            ToolMode = ChatToolMode.Auto,
            AllowMultipleToolCalls = allowMultipleToolCalls
        })
        {
            ChatClientFactory = factory
        };
        OpenAIResponseRequestInfo? capturedRequest = null;
        int invocationCount = 0;
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions
        {
            DangerouslyAllowClientFunctionTools = allowClientFunctions,
            RunOptionsFactory = request =>
            {
                capturedRequest = request;
                invocationCount++;
                return configuredOptions;
            }
        };
#pragma warning restore MAAI001

        // Act
        var run = OpenAIResponses.ToAgentRunRequest(body.RootElement, mapOptions);

        // Assert
        Assert.Equal(1, invocationCount);
        Assert.NotNull(capturedRequest);
        Assert.Equal(2, capturedRequest.Tools!.Count);
        Assert.Equal("function", capturedRequest.Tools[0].GetProperty("type").GetString());
        Assert.Same(configuredOptions, run.Options);
        Assert.Same(factory, configuredOptions.ChatClientFactory);
        Assert.Equal(allowMultipleToolCalls, configuredOptions.ChatOptions!.AllowMultipleToolCalls);
        Assert.Equal(ChatToolMode.Auto, configuredOptions.ChatOptions.ToolMode);
        Assert.Same(hostedFunction, Assert.Single(configuredOptions.ChatOptions.Tools!));
    }

    [Fact]
    public void CustomMapping_ReturningNull_DoesNotAddClientFunctions()
    {
        // Arrange
        using JsonDocument body = CreateBody();
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions
        {
            DangerouslyAllowClientFunctionTools = true,
            RunOptionsFactory = _ => null
        };
#pragma warning restore MAAI001

        // Act
        var run = OpenAIResponses.ToAgentRunRequest(body.RootElement, mapOptions);

        // Assert
        Assert.Null(run.Options);
    }

    [Fact]
    public void ExplicitRejectFactory_OverridesOptInRegardlessOfAssignmentOrder()
    {
        // Arrange
        using JsonDocument body = CreateBody();
        var mapOptions = new OpenAIResponsesMapOptions
        {
            RunOptionsFactory = OpenAIResponsesMapOptions.RejectRequestSettings
        };
#pragma warning disable MAAI001
        mapOptions.DangerouslyAllowClientFunctionTools = true;
#pragma warning restore MAAI001

        // Act & Assert
        Assert.Throws<NotSupportedException>(() => OpenAIResponses.ToAgentRunRequest(body.RootElement, mapOptions));
    }

    [Fact]
    public void RunOptionsFactory_Null_ThrowsArgumentNullException()
    {
        // Arrange
        var mapOptions = new OpenAIResponsesMapOptions();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => mapOptions.RunOptionsFactory = null!);
    }

    private static JsonDocument CreateBody() => JsonDocument.Parse(
        """
        {
          "input": "hello",
          "tools": [
            {"type":"function","name":"get_weather","parameters":{"type":"object"}},
            {"type":"function","name":"get_weather","parameters":{"type":"object"}}
          ]
        }
        """);
}
