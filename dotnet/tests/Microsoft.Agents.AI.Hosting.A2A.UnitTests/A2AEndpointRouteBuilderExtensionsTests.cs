// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI.Hosting.A2A.UnitTests.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Tests for A2AEndpointRouteBuilderExtensions and A2AServerServiceCollectionExtensions methods.
/// </summary>
public sealed class A2AEndpointRouteBuilderExtensionsTests
{
    [Theory]
    [InlineData(false, false, false)]
    [InlineData(true, false, false)]
    [InlineData(false, true, false)]
    [InlineData(true, true, false)]
    [InlineData(false, true, true)]
    [InlineData(true, true, true)]
    public async Task MapA2A_WithServerOptions_RejectsUnsupportedRequestsBeforeInvokingHandlerAsync(
        bool jsonRpc, bool streaming, bool supportsStreaming)
    {
        // Arrange
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var (app, handler) = await CreateServerOptionsTestHostAsync(supportsStreaming, cts.Token);
        await using var appScope = app;
        using var client = app.GetTestClient();
        bool streamingDisabled = streaming && !supportsStreaming;
        Part part = streamingDisabled ? Part.FromText("Hello") : Part.FromRaw([1, 2, 3], "image/png");

        // Act
        using var response = await SendServerOptionsTestRequestAsync(client, jsonRpc, streaming, part, cts.Token);
        string body = await response.Content.ReadAsStringAsync(cts.Token);

        // Assert
        Assert.Equal(jsonRpc ? "application/json" : "application/a2a+json", response.Content.Headers.ContentType?.MediaType);
        using var document = JsonDocument.Parse(body);
        JsonElement error = document.RootElement.GetProperty("error");
        if (jsonRpc)
        {
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            Assert.Equal(
                (int)(streamingDisabled ? A2AErrorCode.UnsupportedOperation : A2AErrorCode.ContentTypeNotSupported),
                error.GetProperty("code").GetInt32());
        }
        else
        {
            Assert.False(response.IsSuccessStatusCode);
            Assert.Contains(error.GetProperty("details").EnumerateArray(), detail =>
                string.Equals(detail.GetProperty("reason").GetString(),
                    streamingDisabled ? "UNSUPPORTED_OPERATION" : "CONTENT_TYPE_NOT_SUPPORTED", StringComparison.Ordinal));
        }

        handler.Verify(h => h.ExecuteAsync(
            It.IsAny<RequestContext>(), It.IsAny<AgentEventQueue>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task MapA2A_WithServerOptions_AcceptsTextAndExplicitlyEnabledStreamingAsync(bool jsonRpc, bool streaming)
    {
        // Arrange
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var (app, handler) = await CreateServerOptionsTestHostAsync(supportsStreaming: streaming, cts.Token);
        await using var appScope = app;
        using var client = app.GetTestClient();

        // Act
        using var response = await SendServerOptionsTestRequestAsync(client, jsonRpc, streaming, Part.FromText("Hello"), cts.Token);
        string body = await response.Content.ReadAsStringAsync(cts.Token);
        using var cardResponse = await client.GetAsync(new Uri("/.well-known/agent-card.json", UriKind.Relative), cts.Token);
        string cardJson = await cardResponse.Content.ReadAsStringAsync(cts.Token);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("Reply", body);
        Assert.Equal(
            streaming ? "text/event-stream" : jsonRpc ? "application/json" : "application/a2a+json",
            response.Content.Headers.ContentType?.MediaType);
        cardResponse.EnsureSuccessStatusCode();
        using var cardDocument = JsonDocument.Parse(cardJson);
        Assert.Equal(streaming, cardDocument.RootElement.GetProperty("capabilities").GetProperty("streaming").GetBoolean());
        Assert.Equal("text/plain", Assert.Single(cardDocument.RootElement.GetProperty("defaultInputModes").EnumerateArray()).GetString());
        handler.Verify(h => h.ExecuteAsync(
            It.IsAny<RequestContext>(), It.IsAny<AgentEventQueue>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public void MapA2AJsonRpc_MarksFeatureUsed()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient chatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", chatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act
        _ = app.MapA2AJsonRpc(agentBuilder, "/a2a");

        // Assert
        AssertFeatureUsed(73);
    }

    private static void AssertFeatureUsed(int featureIndex)
    {
#pragma warning disable MAAI001
        string userAgent = FeatureUsage.ApplyToUserAgent(string.Empty);
#pragma warning restore MAAI001
        const string Prefix = "(feat=v1.";
        Assert.StartsWith(Prefix, userAgent);
        Assert.EndsWith(")", userAgent);

        string hexMask = userAgent[Prefix.Length..^1];
        int digitOffset = featureIndex / 4;
        Assert.True(hexMask.Length > digitOffset);
        char digit = char.ToLowerInvariant(hexMask[hexMask.Length - digitOffset - 1]);
        int nibble = digit <= '9' ? digit - '0' : digit - 'a' + 10;
        Assert.NotEqual(0, nibble & (1 << (featureIndex & 3)));
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null endpoints.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentBuilder_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2AHttpJson(agentBuilder, "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null agentBuilder.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentBuilder_NullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        IHostedAgentBuilder agentBuilder = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AHttpJson(agentBuilder, "/a2a"));

        Assert.Equal("agentBuilder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson maps protocol endpoints without exposing a stub agent card.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentBuilder_MapsProtocolEndpoints()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act
        var result = app.MapA2AHttpJson(agentBuilder, "/a2a");
        RouteEndpoint[] endpoints = ((IEndpointRouteBuilder)app).DataSources
            .SelectMany(source => source.Endpoints)
            .OfType<RouteEndpoint>()
            .ToArray();

        // Assert
        Assert.NotNull(result);
        Assert.Contains(endpoints, endpoint => endpoint.RoutePattern.RawText == "/a2a/message:send");
        Assert.Contains(endpoints, endpoint => endpoint.RoutePattern.RawText == "/a2a/message:stream");
        Assert.Contains(endpoints, endpoint => endpoint.RoutePattern.RawText == "/a2a/tasks/{id}");
        Assert.DoesNotContain(endpoints, endpoint => endpoint.RoutePattern.RawText == "/a2a/card");
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson with string agent name correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentName_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddA2AServer("agent");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2AHttpJson("agent", "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc with IHostedAgentBuilder correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAgentBuilder_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2AJsonRpc(agentBuilder, "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc with string agent name correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAgentName_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddA2AServer("agent");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2AJsonRpc("agent", "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that both MapA2AHttpJson and MapA2AJsonRpc can be called for the same agent.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_And_MapA2AJsonRpc_SameAgent_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var httpResult = app.MapA2AHttpJson(agentBuilder, "/a2a");
        var rpcResult = app.MapA2AJsonRpc(agentBuilder, "/a2a");
        Assert.NotNull(httpResult);
        Assert.NotNull(rpcResult);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped to different paths.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        agent1Builder.AddA2AServer();
        agent2Builder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapA2AHttpJson(agent1Builder, "/a2a/agent1");
        app.MapA2AHttpJson(agent2Builder, "/a2a/agent2");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that custom paths can be specified for A2A endpoints.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithCustomPath_AcceptsValidPath()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapA2AHttpJson(agentBuilder, "/custom/a2a/path");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that AddA2AServer with custom A2AServerRegistrationOptions succeeds.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithCustomOptions_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer(options => options.AgentRunMode = AgentRunMode.ReturnTask);
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2AHttpJson(agentBuilder, "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null endpoints when using string agent name.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentName_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2AHttpJson("agent", "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc throws ArgumentNullException for null endpoints when using string agent name.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAgentName_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2AJsonRpc("agent", "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null agentName.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentName_NullAgentName_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AHttpJson((string)null!, "/a2a"));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentException for empty agentName.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentName_EmptyAgentName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapA2AHttpJson(string.Empty, "/a2a"));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null path.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_NullPath_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AHttpJson(agentBuilder, null!));
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentException for whitespace-only path.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WhitespacePath_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        agentBuilder.AddA2AServer();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            app.MapA2AHttpJson(agentBuilder, "   "));
    }

    /// <summary>
    /// Verifies that AddA2AServer throws ArgumentNullException for null services.
    /// </summary>
    [Fact]
    public void AddA2AServer_NullServices_ThrowsArgumentNullException()
    {
        // Arrange
        IServiceCollection services = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            services.AddA2AServer("agent"));

        Assert.Equal("services", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddA2AServer throws ArgumentNullException for null agentName.
    /// </summary>
    [Fact]
    public void AddA2AServer_NullAgentName_ThrowsArgumentNullException()
    {
        // Arrange
        IServiceCollection services = new ServiceCollection();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            services.AddA2AServer((string)null!));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddA2AServer throws ArgumentException for empty agentName.
    /// </summary>
    [Fact]
    public void AddA2AServer_EmptyAgentName_ThrowsArgumentException()
    {
        // Arrange
        IServiceCollection services = new ServiceCollection();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            services.AddA2AServer(string.Empty));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddA2AServer on IHostedAgentBuilder throws ArgumentNullException for null builder.
    /// </summary>
    [Fact]
    public void AddA2AServer_NullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        IHostedAgentBuilder agentBuilder = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            agentBuilder.AddA2AServer());

        Assert.Equal("agentBuilder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null AIAgent.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAIAgent_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AHttpJson(agent, "/a2a"));

        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for AIAgent with null Name.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAIAgent_NullName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns((string?)null);

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AHttpJson(agentMock.Object, "/a2a"));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentException for AIAgent with whitespace Name.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAIAgent_WhitespaceName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns("   ");

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapA2AHttpJson(agentMock.Object, "/a2a"));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc throws ArgumentNullException for null AIAgent.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAIAgent_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AJsonRpc(agent, "/a2a"));

        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc throws ArgumentNullException for AIAgent with null Name.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAIAgent_NullName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns((string?)null);

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2AJsonRpc(agentMock.Object, "/a2a"));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc throws ArgumentException for AIAgent with whitespace Name.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithAIAgent_WhitespaceName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns("   ");

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapA2AJsonRpc(agentMock.Object, "/a2a"));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2AHttpJson throws InvalidOperationException when no A2AServer has been
    /// registered for the specified agent via AddA2AServer.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithoutAddA2AServer_ThrowsInvalidOperationException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            app.MapA2AHttpJson("agent", "/a2a"));

        Assert.Contains("agent", exception.Message);
        Assert.Contains("AddA2AServer", exception.Message);
    }

    /// <summary>
    /// Verifies that MapA2AJsonRpc throws InvalidOperationException when no A2AServer has been
    /// registered for the specified agent via AddA2AServer.
    /// </summary>
    [Fact]
    public void MapA2AJsonRpc_WithoutAddA2AServer_ThrowsInvalidOperationException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            app.MapA2AJsonRpc("agent", "/a2a"));

        Assert.Contains("agent", exception.Message);
        Assert.Contains("AddA2AServer", exception.Message);
    }

    private static async Task<(WebApplication App, Mock<IAgentHandler> Handler)> CreateServerOptionsTestHostAsync(
        bool supportsStreaming, CancellationToken cancellationToken)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        var agent = new Mock<AIAgent>();
        agent.SetupGet(a => a.Name).Returns("policy-agent");
        var handler = new Mock<IAgentHandler>();
        handler.Setup(h => h.ExecuteAsync(It.IsAny<RequestContext>(), It.IsAny<AgentEventQueue>(), It.IsAny<CancellationToken>()))
            .Returns((RequestContext _, AgentEventQueue queue, CancellationToken ct) => queue.EnqueueMessageAsync(
                new Message { MessageId = "reply", Role = Role.Agent, Parts = [Part.FromText("Reply")] }, ct).AsTask());
        builder.Services.AddKeyedSingleton(agent.Object.Name, handler.Object);
        builder.AddA2AServer(agent.Object, options => options.ServerOptions = new A2AServerOptions
        {
            SupportsStreaming = supportsStreaming,
            SupportedInputModes = ["text/plain"]
        });
        var app = builder.Build();
        app.MapA2AHttpJson(agent.Object, "/a2a");
        app.MapA2AJsonRpc(agent.Object, "/a2a");
        app.MapWellKnownAgentCard(new AgentCard
        {
            Name = "policy-agent",
            Description = "Test agent",
            Version = "1.0.0",
            Capabilities = new() { Streaming = supportsStreaming },
            DefaultInputModes = ["text/plain"],
            DefaultOutputModes = ["text/plain"],
            Skills = [],
            SupportedInterfaces = []
        });
        await app.StartAsync(cancellationToken);
        return (app, handler);
    }

    private static async Task<HttpResponseMessage> SendServerOptionsTestRequestAsync(
        HttpClient client, bool jsonRpc, bool streaming, Part part, CancellationToken cancellationToken)
    {
        var request = new SendMessageRequest
        {
            Message = new Message { MessageId = "request", Role = Role.User, Parts = [part] }
        };
        string json = jsonRpc
            ? JsonSerializer.Serialize(new JsonRpcRequest
            {
                Id = "request",
                Method = streaming ? "SendStreamingMessage" : "SendMessage",
                Params = JsonSerializer.SerializeToElement(request, A2AJsonUtilities.DefaultOptions)
            }, A2AJsonUtilities.DefaultOptions)
            : JsonSerializer.Serialize(request, A2AJsonUtilities.DefaultOptions);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        var uri = new Uri(jsonRpc ? "/a2a" : streaming ? "/a2a/message:stream" : "/a2a/message:send", UriKind.Relative);
        return await client.PostAsync(uri, content, cancellationToken);
    }
}
