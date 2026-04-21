// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.A2A.UnitTests.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Tests for A2AEndpointRouteBuilderExtensions.MapA2A method.
/// </summary>
public sealed class A2AEndpointRouteBuilderExtensionsTests
{
    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null endpoints.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2A(agentBuilder, "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null agentBuilder.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_NullAgentBuilder_ThrowsArgumentNullException()
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
            app.MapA2A(agentBuilder, "/a2a"));

        Assert.Equal("agentBuilder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder correctly maps the agent with default configuration.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and custom A2AHostingOptions succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_CustomA2AHostingOptionsConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", options => { });
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null endpoints when using string agent name.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2A("agent", "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name and custom A2AHostingOptions succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_CustomA2AHostingOptionsConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", options => { });
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null endpoints when using AIAgent.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2A((AIAgent)null!, "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_DefaultConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent and custom A2AHostingOptions succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_CustomA2AHostingOptionsConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", options => { });
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and A2AHostingOptions with AgentRunMode succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_CustomOptionsAndRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", options => options.AgentRunMode = AgentRunMode.DisallowBackground);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with string agentName and A2AHostingOptions with AgentRunMode succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_CustomOptionsAndRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", options => options.AgentRunMode = AgentRunMode.DisallowBackground);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped to different paths.
    /// </summary>
    [Fact]
    public void MapA2A_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapA2A(agent1Builder, "/a2a/agent1");
        app.MapA2A(agent2Builder, "/a2a/agent2");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that custom paths can be specified for A2A endpoints.
    /// </summary>
    [Fact]
    public void MapA2A_WithCustomPath_AcceptsValidPath()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapA2A(agentBuilder, "/custom/a2a/path");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that A2AHostingOptions configuration callback is invoked correctly.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_A2AHostingOptionsConfigurationCallbackInvoked()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        bool configureCallbackInvoked = false;

        // Act
        app.MapA2A(agentBuilder, "/a2a", options =>
        {
            configureCallbackInvoked = true;
            Assert.NotNull(options);
        });

        // Assert
        Assert.True(configureCallbackInvoked);
    }

    /// <summary>
    /// Verifies that MapA2A with JsonRpc protocolBindings succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithJsonRpcProtocol_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", options => options.ProtocolBindings = A2AProtocolBinding.JsonRpc);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with both protocols succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithBothProtocols_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", options => options.ProtocolBindings = A2AProtocolBinding.HttpJson | A2AProtocolBinding.JsonRpc);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and direct protocolBindings parameter succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_DirectProtocol_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", A2AProtocolBinding.HttpJson);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and direct protocolBindings and run mode parameters succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_DirectProtocolAndRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", A2AProtocolBinding.HttpJson, AgentRunMode.AllowBackgroundIfSupported);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder, null protocolBindings, and direct run mode parameter succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_NullProtocolAndDirectRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", protocolBindings: null, agentRunMode: AgentRunMode.DisallowBackground);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name and direct protocolBindings parameter succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_DirectProtocol_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", A2AProtocolBinding.JsonRpc);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name and direct protocolBindings and run mode parameters succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_DirectProtocolAndRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", A2AProtocolBinding.HttpJson, AgentRunMode.AllowBackgroundIfSupported);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent and direct protocolBindings parameter succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_DirectProtocol_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", A2AProtocolBinding.HttpJson);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent and direct protocolBindings and run mode parameters succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_DirectProtocolAndRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", A2AProtocolBinding.HttpJson, AgentRunMode.AllowBackgroundIfSupported);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent, null protocolBindings, and direct run mode defaults correctly.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_NullProtocolAndDirectRunMode_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", protocolBindings: null, agentRunMode: AgentRunMode.DisallowBackground);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null agentName (string overload with configureOptions).
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_NullAgentName_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2A((string)null!, "/a2a"));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null agentName (string overload with protocolBindings).
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_NullAgentName_ProtocolOverload_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapA2A((string)null!, "/a2a", A2AProtocolBinding.HttpJson));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentException for empty agentName (string overload with configureOptions).
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_EmptyAgentName_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapA2A(string.Empty, "/a2a"));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentException for empty agentName (string overload with protocolBindings).
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_EmptyAgentName_ProtocolOverload_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapA2A(string.Empty, "/a2a", A2AProtocolBinding.HttpJson));

        Assert.Equal("agentName", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentException for null path.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_NullPath_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            app.MapA2A(agent, null!));
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentException for whitespace-only path.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_WhitespacePath_ThrowsArgumentException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            app.MapA2A(agent, "   "));
    }
}
