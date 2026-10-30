// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Verifies how OpenAI Chat Completions endpoints resolve and select agents for each request.
/// </summary>
public sealed class OpenAIChatCompletionsAgentResolutionTests
{
    private const string RequestJson = """{"model":"test-model","messages":[{"role":"user","content":"hello"}]}""";

    [Fact]
    public async Task MapOpenAIChatCompletions_WithScopedHostedAgent_ResolvesAgentPerRequestAsync()
    {
        // Arrange
        int createdAgents = 0;
        WebApplicationBuilder builder = CreateBuilder();
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(
            "assistant",
            (_, name) =>
            {
                Interlocked.Increment(ref createdAgents);
                return new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Scoped response"), name: name);
            },
            ServiceLifetime.Scoped);

        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions(agentBuilder);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        string firstResponse = await PostAsync(client, "/assistant/v1/chat/completions");
        string secondResponse = await PostAsync(client, "/assistant/v1/chat/completions");

        // Assert
        Assert.Equal(2, createdAgents);
        Assert.Contains("Scoped response", firstResponse, StringComparison.Ordinal);
        Assert.Contains("Scoped response", secondResponse, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithSingletonHostedAgent_ResolvesAgentOnceAtMapTimeAsync()
    {
        // Arrange
        int createdAgents = 0;
        WebApplicationBuilder builder = CreateBuilder();
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(
            "assistant",
            (_, name) =>
            {
                Interlocked.Increment(ref createdAgents);
                return new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Singleton response"), name: name);
            });

        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions(agentBuilder);
        int createdAtMapTime = createdAgents;
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        await PostAsync(client, "/assistant/v1/chat/completions");
        string secondResponse = await PostAsync(client, "/assistant/v1/chat/completions");

        // Assert
        Assert.Equal(1, createdAtMapTime);
        Assert.Equal(1, createdAgents);
        Assert.Contains("Singleton response", secondResponse, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithUnregisteredHostedAgent_ThrowsAtMapTimeAsync()
    {
        // Arrange
        Mock<IHostedAgentBuilder> agentBuilder = new();
        agentBuilder.Setup(b => b.Name).Returns("missing");
        await using WebApplication app = CreateBuilder().Build();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => app.MapOpenAIChatCompletions(agentBuilder.Object));
        Assert.Contains("missing", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithAgentSelector_SelectsAgentFromRouteValueAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddAIAgent("alpha", (_, name) => new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Alpha response"), name: name), ServiceLifetime.Scoped);
        builder.AddAIAgent("beta", (_, name) => new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Beta response"), name: name), ServiceLifetime.Transient);

        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions("/agents/{agentId}/v1/chat/completions", SelectAgentFromRoute);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        string alphaResponse = await PostAsync(client, "/agents/alpha/v1/chat/completions");
        string betaResponse = await PostAsync(client, "/agents/beta/v1/chat/completions");

        // Assert
        Assert.Contains("Alpha response", alphaResponse, StringComparison.Ordinal);
        Assert.Contains("Beta response", betaResponse, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithAgentSelectorReturningNull_ReturnsNotFoundAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder();
        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions("/agents/{agentId}/v1/chat/completions", SelectAgentFromRoute);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await SendAsync(client, "/agents/unknown/v1/chat/completions");
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Contains("agent_not_found", responseBody, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithAgentSelectorReturningNullAndReflectionDisabled_ReturnsNotFoundErrorAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(disableReflectionSerialization: true);
        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions("/v1/chat/completions", _ => null);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await SendAsync(client, "/v1/chat/completions");
        JsonElement error = await ReadErrorAsync(response);

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("agent_not_found", error.GetProperty("code").GetString());
        Assert.Equal("invalid_request_error", error.GetProperty("type").GetString());
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithUnsupportedRunOptionAndReflectionDisabled_ReturnsBadRequestErrorAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(disableReflectionSerialization: true);
        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions(
            new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "assistant"),
            "/v1/chat/completions",
            new OpenAIChatCompletionsMapOptions { RunOptionsFactory = _ => throw new NotSupportedException("Unsupported setting.") });
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await SendAsync(client, "/v1/chat/completions");
        JsonElement error = await ReadErrorAsync(response);

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("unsupported_parameter", error.GetProperty("code").GetString());
        Assert.Equal("Unsupported setting.", error.GetProperty("message").GetString());
    }

    [Fact]
    public async Task MapOpenAIChatCompletions_WithAgentSelectorReturningUnnamedAgent_FailsRequestAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder();
        await using WebApplication app = builder.Build();
        app.MapOpenAIChatCompletions("/v1/chat/completions", _ => new ChatClientAgent(new TestHelpers.SimpleMockChatClient()));
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await SendAsync(client, "/v1/chat/completions");
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Contains("stable name", responseBody, StringComparison.Ordinal);
    }

    [Fact]
    public void MapOpenAIChatCompletions_WithNullAgentSelector_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpoints = new();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpoints.Object.MapOpenAIChatCompletions("/v1/chat/completions", null!));
    }

    private static AIAgent? SelectAgentFromRoute(HttpContext context) =>
        context.GetRouteValue("agentId") is string agentId
            ? context.RequestServices.GetKeyedService<AIAgent>(agentId)
            : null;

    private static WebApplicationBuilder CreateBuilder(bool disableReflectionSerialization = false)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = Environments.Development });
        builder.WebHost.UseTestServer();
        builder.AddOpenAIChatCompletions();
        if (disableReflectionSerialization)
        {
            // With reflection-based serialization disabled, the resolver registered by AddOpenAIChatCompletions only
            // provides the source-generated Chat Completions metadata. The test process has reflection enabled, which
            // that resolver would fall back to, so register the source-generated metadata alone.
            builder.Services.Configure<JsonOptions>(options =>
            {
                options.SerializerOptions.TypeInfoResolverChain.Clear();
                options.SerializerOptions.TypeInfoResolverChain.Add(ChatCompletionsJsonContext.Default);
            });
        }

        return builder;
    }

    private static async Task<JsonElement> ReadErrorAsync(HttpResponseMessage response)
    {
        string responseBody = await response.Content.ReadAsStringAsync();
        using JsonDocument document = JsonDocument.Parse(responseBody);
        return document.RootElement.GetProperty("error").Clone();
    }

    private static async Task<string> PostAsync(HttpClient client, string path)
    {
        using HttpResponseMessage response = await SendAsync(client, path);
        string responseBody = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, responseBody);
        return responseBody;
    }

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string path)
    {
        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");
        return await client.PostAsync(new Uri(path, UriKind.Relative), content);
    }
}
