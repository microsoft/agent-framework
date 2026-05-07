// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.A2A.UnitTests.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Tests for A2AEndpointRouteBuilderExtensions and A2AServerServiceCollectionExtensions methods.
/// </summary>
public sealed class A2AEndpointRouteBuilderExtensionsTests
{
    /// <summary>
    /// Verifies that MapA2AHttpJson throws ArgumentNullException for null endpoints.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentBuilder_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;
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
    /// Verifies that MapA2AHttpJson with IHostedAgentBuilder correctly maps the agent with default configuration.
    /// </summary>
    [Fact]
    public void MapA2AHttpJson_WithAgentBuilder_DefaultConfiguration_Succeeds()
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
        var result = app.MapA2AHttpJson(agentBuilder, "/a2a");
        Assert.NotNull(result);
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
        agentBuilder.AddA2AServer(options => options.AgentRunMode = AgentRunMode.AllowBackgroundIfSupported);
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
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;

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
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;

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
}
