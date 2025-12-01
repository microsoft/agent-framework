// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the MapAGUI extension methods.
/// </summary>
public sealed class MapAGUIEndpointRouteBuilderExtensionsTests
{
    /// <summary>
    /// Verifies that MapAGUI throws ArgumentNullException for null endpoints when using IHostedAgentBuilder.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapAGUI(agentBuilder));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapAGUI throws ArgumentNullException for null agentBuilder.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_NullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        IHostedAgentBuilder agentBuilder = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapAGUI(agentBuilder));

        Assert.Equal("agentBuilder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapAGUI with IHostedAgentBuilder correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI(agentBuilder);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapAGUI with IHostedAgentBuilder and custom path works correctly.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_CustomPath_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("my-agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI(agentBuilder, path: "/agents/my-agent/agui");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped using IHostedAgentBuilder.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI(agent1Builder);
        app.MapAGUI(agent2Builder);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that IHostedAgentBuilder overload validates agent name characters.
    /// </summary>
    [Theory]
    [InlineData("agent with spaces")]
    [InlineData("agent<script>")]
    [InlineData("agent?query")]
    [InlineData("agent#fragment")]
    public void MapAGUI_WithAgentBuilder_InvalidAgentNameCharacters_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(invalidName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapAGUI(agentBuilder));

        Assert.Contains("invalid for URL routes", exception.Message);
    }

    /// <summary>
    /// Verifies that IHostedAgentBuilder overload accepts valid agent names.
    /// </summary>
    [Theory]
    [InlineData("agent-name")]
    [InlineData("agent_name")]
    [InlineData("agent.name")]
    [InlineData("agent123")]
    [InlineData("my-agent_v1.0")]
    public void MapAGUI_WithAgentBuilder_ValidAgentNameCharacters_DoesNotThrow(string validName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(validName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI(agentBuilder);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that IHostedAgentBuilder overload with custom paths can be specified.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentBuilder_MultipleAgentsWithCustomPaths_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI(agent1Builder, path: "/api/v1/agent1/agui");
        app.MapAGUI(agent2Builder, path: "/api/v1/agent2/agui");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapAGUI throws ArgumentNullException for null endpoints when using string agent name.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentName_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapAGUI("agent"));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapAGUI throws ArgumentException for null or whitespace agent name.
    /// </summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void MapAGUI_WithAgentName_NullOrWhitespaceAgentName_ThrowsArgumentException(string? agentName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            app.MapAGUI(agentName!));
    }

    /// <summary>
    /// Verifies that MapAGUI with string agent name correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentName_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI("agent");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapAGUI with string agent name and custom path works correctly.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAgentName_CustomPath_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("my-agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapAGUI("my-agent", path: "/agents/my-agent/agui");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that string agent name overload validates agent name characters.
    /// </summary>
    [Theory]
    [InlineData("agent with spaces")]
    [InlineData("agent<script>")]
    [InlineData("agent?query")]
    [InlineData("agent#fragment")]
    public void MapAGUI_WithAgentName_InvalidAgentNameCharacters_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(invalidName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapAGUI(invalidName));

        Assert.Contains("invalid for URL routes", exception.Message);
    }

    /// <summary>
    /// Verifies that MapAGUI throws ArgumentNullException for null endpoints when using AIAgent.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        IEndpointRouteBuilder endpoints = null!;
        AIAgent agent = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapAGUI(agent));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapAGUI throws ArgumentNullException for null agent.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();

        // Act & Assert
        AIAgent agent = null!;
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapAGUI(agent));

        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapAGUI with AIAgent correctly maps the agent.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        app.MapAGUI(agent);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapAGUI with AIAgent and custom path works correctly.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_CustomPath_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        app.MapAGUI(agent, path: "/custom/agui");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapAGUI validates agent name characters for URL safety.
    /// </summary>
    [Theory]
    [InlineData("agent with spaces")]
    [InlineData("agent<script>")]
    [InlineData("agent\nwith\nnewlines")]
    [InlineData("agent\twith\ttabs")]
    [InlineData("agent?query")]
    [InlineData("agent#fragment")]
    public void MapAGUI_WithAIAgent_InvalidAgentNameCharacters_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(invalidName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(invalidName);

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapAGUI(agent));

        Assert.Contains("invalid for URL routes", exception.Message);
    }

    /// <summary>
    /// Verifies that MapAGUI accepts valid agent names with special characters.
    /// </summary>
    [Theory]
    [InlineData("agent-name")]
    [InlineData("agent_name")]
    [InlineData("agent.name")]
    [InlineData("agent123")]
    [InlineData("123agent")]
    [InlineData("AGENT")]
    [InlineData("my-agent_v1.0")]
    public void MapAGUI_WithAIAgent_ValidAgentNameCharacters_DoesNotThrow(string validName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(validName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(validName);

        // Act & Assert - Should not throw
        app.MapAGUI(agent);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped to different paths.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent1 = app.Services.GetRequiredKeyedService<AIAgent>("agent1");
        AIAgent agent2 = app.Services.GetRequiredKeyedService<AIAgent>("agent2");

        // Act & Assert - Should not throw
        app.MapAGUI(agent1);
        app.MapAGUI(agent2);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that long agent names are accepted.
    /// </summary>
    [Fact]
    public void MapAGUI_WithAIAgent_LongAgentName_Succeeds()
    {
        // Arrange
        string longName = new('a', 100);
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(longName, "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(longName);

        // Act & Assert - Should not throw
        app.MapAGUI(agent);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that custom paths can be specified for AGUI endpoints.
    /// </summary>
    [Fact]
    public void MapAGUI_WithCustomPath_AcceptsValidPath()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddAGUI();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        app.MapAGUI(agent, path: "/custom/agui/path");
        Assert.NotNull(app);
    }
}
