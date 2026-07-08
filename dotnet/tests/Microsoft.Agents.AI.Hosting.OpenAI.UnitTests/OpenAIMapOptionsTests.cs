// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for <see cref="OpenAIResponsesMapOptions"/> and <see cref="OpenAIChatCompletionsMapOptions"/>,
/// including the default behavior that rejects request-supplied settings so that callers cannot
/// override the configuration of a self-contained agent.
/// </summary>
public sealed class OpenAIMapOptionsTests
{
    [Fact]
    public void Responses_DefaultRunOptionsFactory_IsRejectRequestSettings()
    {
        // Arrange & Act
        var options = new OpenAIResponsesMapOptions();

        // Assert
        Assert.Equal(OpenAIResponsesMapOptions.RejectRequestSettings, options.RunOptionsFactory);
    }

    [Fact]
    public void ChatCompletions_DefaultRunOptionsFactory_IsRejectRequestSettings()
    {
        // Arrange & Act
        var options = new OpenAIChatCompletionsMapOptions();

        // Assert
        Assert.Equal(OpenAIChatCompletionsMapOptions.RejectRequestSettings, options.RunOptionsFactory);
    }

    [Fact]
    public void Responses_RejectRequestSettings_ReturnsNull_WhenNoSettingsSpecified()
    {
        // Arrange
        var request = new OpenAIResponseRequestInfo { Model = "gpt-4o" };

        // Act
        AgentRunOptions? result = OpenAIResponsesMapOptions.RejectRequestSettings(request);

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData("temperature")]
    [InlineData("top_p")]
    [InlineData("max_output_tokens")]
    [InlineData("instructions")]
    [InlineData("tools")]
    [InlineData("tool_choice")]
    public void Responses_RejectRequestSettings_Throws_WhenSettingSpecified(string setting)
    {
        // Arrange
        var request = setting switch
        {
            "temperature" => new OpenAIResponseRequestInfo { Temperature = 0.5 },
            "top_p" => new OpenAIResponseRequestInfo { TopP = 0.5 },
            "max_output_tokens" => new OpenAIResponseRequestInfo { MaxOutputTokens = 100 },
            "instructions" => new OpenAIResponseRequestInfo { Instructions = "be brief" },
            "tools" => new OpenAIResponseRequestInfo { Tools = [ParseElement("{}")] },
            "tool_choice" => new OpenAIResponseRequestInfo { ToolChoice = ChatToolMode.None },
            _ => throw new ArgumentOutOfRangeException(nameof(setting))
        };

        // Act & Assert
        NotSupportedException ex = Assert.Throws<NotSupportedException>(() => OpenAIResponsesMapOptions.RejectRequestSettings(request));
        Assert.Contains(setting, ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ChatCompletions_RejectRequestSettings_ReturnsNull_WhenNoSettingsSpecified()
    {
        // Arrange
        var request = new OpenAIChatCompletionRequestInfo { Model = "gpt-4o" };

        // Act
        AgentRunOptions? result = OpenAIChatCompletionsMapOptions.RejectRequestSettings(request);

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData("temperature")]
    [InlineData("top_p")]
    [InlineData("max_completion_tokens")]
    [InlineData("frequency_penalty")]
    [InlineData("presence_penalty")]
    [InlineData("seed")]
    [InlineData("stop")]
    [InlineData("response_format")]
    [InlineData("tools")]
    [InlineData("tool_choice")]
    public void ChatCompletions_RejectRequestSettings_Throws_WhenSettingSpecified(string setting)
    {
        // Arrange
        var request = setting switch
        {
            "temperature" => new OpenAIChatCompletionRequestInfo { Temperature = 0.5f },
            "top_p" => new OpenAIChatCompletionRequestInfo { TopP = 0.5f },
            "max_completion_tokens" => new OpenAIChatCompletionRequestInfo { MaxOutputTokens = 100 },
            "frequency_penalty" => new OpenAIChatCompletionRequestInfo { FrequencyPenalty = 0.5f },
            "presence_penalty" => new OpenAIChatCompletionRequestInfo { PresencePenalty = 0.5f },
            "seed" => new OpenAIChatCompletionRequestInfo { Seed = 42 },
            "stop" => new OpenAIChatCompletionRequestInfo { StopSequences = ["stop"] },
            "response_format" => new OpenAIChatCompletionRequestInfo { ResponseFormat = ChatResponseFormat.Json },
            "tools" => new OpenAIChatCompletionRequestInfo { Tools = [AIFunctionFactory.Create(() => "x", "f")] },
            "tool_choice" => new OpenAIChatCompletionRequestInfo { ToolChoice = ChatToolMode.None },
            _ => throw new ArgumentOutOfRangeException(nameof(setting))
        };

        // Act & Assert
        NotSupportedException ex = Assert.Throws<NotSupportedException>(() => OpenAIChatCompletionsMapOptions.RejectRequestSettings(request));
        Assert.Contains(setting, ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Responses_DefaultEndpoint_RejectsRequestWithSettingsAsync()
    {
        // Arrange
        using var app = await CreateResponsesServerAsync("reject-agent", mapOptions: null);
        HttpClient client = GetClient(app);

        // Act
        HttpResponseMessage response = await client.PostAsync(
            new Uri("/reject-agent/v1/responses", UriKind.Relative),
            new StringContent("""{"input":"hello","temperature":0.5}""", Encoding.UTF8, "application/json"));

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        string body = await response.Content.ReadAsStringAsync();
        Assert.Contains("temperature", body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Responses_ConfiguredEndpoint_HonorsRequestSettingsAsync()
    {
        // Arrange
        using var app = await CreateResponsesServerAsync("map-agent", PermissiveMapOptions.Responses());
        HttpClient client = GetClient(app);

        // Act
        HttpResponseMessage response = await client.PostAsync(
            new Uri("/map-agent/v1/responses", UriKind.Relative),
            new StringContent("""{"input":"hello","temperature":0.5}""", Encoding.UTF8, "application/json"));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task ChatCompletions_DefaultEndpoint_RejectsRequestWithSettingsAsync()
    {
        // Arrange
        using var app = await CreateChatCompletionsServerAsync("reject-agent", mapOptions: null);
        HttpClient client = GetClient(app);

        // Act
        HttpResponseMessage response = await client.PostAsync(
            new Uri("/reject-agent/v1/chat/completions", UriKind.Relative),
            new StringContent("""{"model":"myModel","messages":[{"role":"user","content":"hello"}],"temperature":0.5}""", Encoding.UTF8, "application/json"));

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        string body = await response.Content.ReadAsStringAsync();
        Assert.Contains("temperature", body, StringComparison.Ordinal);
        Assert.Contains("invalid_request_error", body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ChatCompletions_ConfiguredEndpoint_HonorsRequestSettingsAsync()
    {
        // Arrange
        using var app = await CreateChatCompletionsServerAsync("map-agent", PermissiveMapOptions.ChatCompletions());
        HttpClient client = GetClient(app);

        // Act
        HttpResponseMessage response = await client.PostAsync(
            new Uri("/map-agent/v1/chat/completions", UriKind.Relative),
            new StringContent("""{"model":"myModel","messages":[{"role":"user","content":"hello"}],"temperature":0.5}""", Encoding.UTF8, "application/json"));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    private static async Task<WebApplication> CreateResponsesServerAsync(string agentName, OpenAIResponsesMapOptions? mapOptions)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient("Hello there.");
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(agentName, "You are a helpful assistant.", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();

        WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        app.MapOpenAIResponses(agent, responsesPath: null, mapOptions);

        await app.StartAsync();
        return app;
    }

    private static HttpClient GetClient(WebApplication app)
    {
        TestServer testServer = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");
        return testServer.CreateClient();
    }

    private static async Task<WebApplication> CreateChatCompletionsServerAsync(string agentName, OpenAIChatCompletionsMapOptions? mapOptions)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient("Hello there.");
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(agentName, "You are a helpful assistant.", chatClientServiceKey: "chat-client");
        builder.AddOpenAIChatCompletions();

        WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        app.MapOpenAIChatCompletions(agent, path: null, mapOptions);

        await app.StartAsync();
        return app;
    }

    private static JsonElement ParseElement(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
