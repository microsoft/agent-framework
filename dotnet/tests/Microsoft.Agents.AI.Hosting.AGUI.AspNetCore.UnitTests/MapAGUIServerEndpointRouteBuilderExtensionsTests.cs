// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the agent-name-derived <c>MapAGUIServer</c> overloads.
/// </summary>
public sealed class MapAGUIServerEndpointRouteBuilderExtensionsTests
{
    [Fact]
    public void MapAGUIServer_WithAgentBuilder_MapsNameDerivedRoute()
    {
        // Arrange
        using WebApplication app = CreateApp("test-agent");
        Mock<IHostedAgentBuilder> agentBuilder = new();
        agentBuilder.SetupGet(builder => builder.Name).Returns("test-agent");

        // Act
        app.MapAGUIServer(agentBuilder.Object);

        // Assert
        Assert.Contains(GetRoutePatterns(app), pattern => pattern == "/test-agent/agui");
    }

    [Fact]
    public void MapAGUIServer_WithAgentName_MapsNameDerivedRoute()
    {
        // Arrange
        using WebApplication app = CreateApp("test-agent");

        // Act
        app.MapAGUIServer("test-agent");

        // Assert
        Assert.Contains(GetRoutePatterns(app), pattern => pattern == "/test-agent/agui");
    }

    [Fact]
    public void MapAGUIServer_WithAgent_MapsNameDerivedRoute()
    {
        // Arrange
        using WebApplication app = CreateApp();
        AIAgent agent = new TestAgent("test-agent");

        // Act
        app.MapAGUIServer(agent);

        // Assert
        Assert.Contains(GetRoutePatterns(app), pattern => pattern == "/test-agent/agui");
    }

    [Fact]
    public void MapAGUIServer_WithNullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;
        AIAgent agent = new TestAgent("test-agent");

        // Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() => endpoints.MapAGUIServer(agent));

        // Assert
        Assert.Equal("endpoints", exception.ParamName);
    }

    [Fact]
    public void MapAGUIServer_WithNullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        using WebApplication app = CreateApp();

        // Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() => app.MapAGUIServer((IHostedAgentBuilder)null!));

        // Assert
        Assert.Equal("agentBuilder", exception.ParamName);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void MapAGUIServer_WithNullOrWhitespaceAgentName_ThrowsArgumentException(string? agentName)
    {
        // Arrange
        using WebApplication app = CreateApp();

        // Act
        ArgumentException exception = Assert.ThrowsAny<ArgumentException>(() => app.MapAGUIServer(agentName!));

        // Assert
        Assert.Equal("agentName", exception.ParamName);
    }

    [Fact]
    public void MapAGUIServer_WithNullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        using WebApplication app = CreateApp();

        // Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() => app.MapAGUIServer((AIAgent)null!));

        // Assert
        Assert.Equal("aiAgent", exception.ParamName);
    }

    [Theory]
    [InlineData("agent with spaces")]
    [InlineData("agent<script>")]
    [InlineData("agent?query")]
    [InlineData("agent#fragment")]
    public void MapAGUIServer_WithInvalidAgentName_ThrowsArgumentException(string agentName)
    {
        // Arrange
        using WebApplication app = CreateApp();
        AIAgent agent = new TestAgent(agentName);

        // Act
        ArgumentException exception = Assert.Throws<ArgumentException>(() => app.MapAGUIServer(agent));

        // Assert
        Assert.Equal("agentName", exception.ParamName);
    }

    [Theory]
    [InlineData("agent-name")]
    [InlineData("agent_name")]
    [InlineData("agent.name")]
    [InlineData("agent123")]
    public void MapAGUIServer_WithValidAgentName_MapsNameDerivedRoute(string agentName)
    {
        // Arrange
        using WebApplication app = CreateApp();
        AIAgent agent = new TestAgent(agentName);

        // Act
        app.MapAGUIServer(agent);

        // Assert
        Assert.Contains(GetRoutePatterns(app), pattern => pattern == $"/{agentName}/agui");
    }

    private static WebApplication CreateApp(string? keyedAgentName = null)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUIServer();

        if (keyedAgentName is not null)
        {
            builder.Services.AddKeyedSingleton<AIAgent>(keyedAgentName, new TestAgent(keyedAgentName));
        }

        return builder.Build();
    }

    private static IEnumerable<string?> GetRoutePatterns(WebApplication app) =>
        ((IEndpointRouteBuilder)app).DataSources
            .SelectMany(dataSource => dataSource.Endpoints)
            .OfType<RouteEndpoint>()
            .Select(endpoint => endpoint.RoutePattern.RawText);

    private sealed class TestAgent(string? name) : AIAgent
    {
        protected override string? IdCore => name;

        public override string? Name => name;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }
}
