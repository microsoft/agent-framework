// Copyright (c) Microsoft. All rights reserved.

using System;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.UnitTests.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Tests for MicrosoftAgentAIHostingA2AEndpointRouteBuilderExtensions.MapA2A method.
/// </summary>
public sealed class EndpointRouteA2ABuilderExtensionsTests
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
    /// Verifies that MapA2A with IHostedAgentBuilder correctly maps the agent with default task manager configuration.
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
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_CustomTaskManagerConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder and agent card succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_WithAgentCard_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", agentCard);
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with IHostedAgentBuilder, agent card, and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_WithAgentCardAndCustomConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", agentCard, taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
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
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_CustomTaskManagerConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name and agent card succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_WithAgentCard_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", agentCard);
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with string agent name, agent card, and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentName_WithAgentCardAndCustomConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A("agent", "/a2a", agentCard, taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
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
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_CustomTaskManagerConfiguration_Succeeds()
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
        var result = app.MapA2A(agent, "/a2a", taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent and agent card succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_WithAgentCard_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", agentCard);
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A with AIAgent, agent card, and custom task manager configuration succeeds.
    /// </summary>
    [Fact]
    public void MapA2A_WithAIAgent_WithAgentCardAndCustomConfiguration_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A(agent, "/a2a", agentCard, taskManager => { });
        Assert.NotNull(result);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapA2A throws ArgumentNullException for null endpoints when using ITaskManager.
    /// </summary>
    [Fact]
    public void MapA2A_WithTaskManager_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;
        ITaskManager taskManager = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapA2A(taskManager, "/a2a"));

        Assert.Equal("endpoints", exception.ParamName);
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
    /// Verifies that task manager configuration callback is invoked correctly.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_TaskManagerConfigurationCallbackInvoked()
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
        app.MapA2A(agentBuilder, "/a2a", taskManager =>
        {
            configureCallbackInvoked = true;
            Assert.NotNull(taskManager);
        });

        // Assert
        Assert.True(configureCallbackInvoked);
    }

    /// <summary>
    /// Verifies that agent card with all properties is accepted.
    /// </summary>
    [Fact]
    public void MapA2A_WithAgentBuilder_FullAgentCard_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();
        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A comprehensive test agent"
        };

        // Act & Assert - Should not throw
        var result = app.MapA2A(agentBuilder, "/a2a", agentCard);
        Assert.NotNull(result);
    }
}
