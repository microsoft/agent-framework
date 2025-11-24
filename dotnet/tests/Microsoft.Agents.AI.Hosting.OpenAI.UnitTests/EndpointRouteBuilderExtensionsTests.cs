// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for EndpointRouteBuilderExtensions.MapOpenAIResponses method.
/// </summary>
public sealed class EndpointRouteBuilderExtensionsTests
{
    /// <summary>
    /// Verifies that MapOpenAIResponses throws ArgumentNullException for null endpoints.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;
        AIAgent agent = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapOpenAIResponses(agent));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses throws ArgumentNullException for null agent.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert
        AIAgent agent = null!;
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapOpenAIResponses(agent));

        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses validates agent name characters for URL safety.
    /// </summary>
    [Theory]
    [InlineData("agent with spaces")]
    [InlineData("agent<script>")]
    [InlineData("agent\nwith\nnewlines")]
    [InlineData("agent\twith\ttabs")]
    [InlineData("agent?query")]
    [InlineData("agent#fragment")]
    public void MapOpenAIResponses_InvalidAgentNameCharacters_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddOpenAIResponses();
        builder.AddAIAgent(invalidName, "Instructions", chatClientServiceKey: "chat-client");
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(invalidName);

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapOpenAIResponses(agent));

        Assert.Contains("invalid for URL routes", exception.Message);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses accepts valid agent names with special characters.
    /// </summary>
    [Theory]
    [InlineData("agent-name")]
    [InlineData("agent_name")]
    [InlineData("agent.name")]
    [InlineData("agent123")]
    [InlineData("123agent")]
    [InlineData("AGENT")]
    [InlineData("my-agent_v1.0")]
    public void MapOpenAIResponses_ValidAgentNameCharacters_DoesNotThrow(string validName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(validName, "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(validName);

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that custom paths can be specified for responses endpoints.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithCustomPath_AcceptsValidPath()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>("agent");

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent, responsesPath: "/custom/responses");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped to different paths.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();
        AIAgent agent1 = app.Services.GetRequiredKeyedService<AIAgent>("agent1");
        AIAgent agent2 = app.Services.GetRequiredKeyedService<AIAgent>("agent2");

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent1);
        app.MapOpenAIResponses(agent2);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that long agent names are accepted.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_LongAgentName_Succeeds()
    {
        // Arrange
        string longName = new('a', 100);
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(longName, "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();
        AIAgent agent = app.Services.GetRequiredKeyedService<AIAgent>(longName);

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses without agent parameter works correctly.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithoutAgent_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("test-agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses();
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses without agent parameter requires AddOpenAIResponses to be called.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithoutAgent_NoServiceRegistered_ThrowsInvalidOperationException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        using WebApplication app = builder.Build();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            app.MapOpenAIResponses());

        Assert.Contains("IResponsesService is not registered", exception.Message);
        Assert.Contains("AddOpenAIResponses()", exception.Message);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses without agent parameter with custom path works correctly.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithoutAgent_CustomPath_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent("test-agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(responsesPath: "/custom/path/responses");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses throws ArgumentNullException for null endpoints when using IHostedAgentBuilder.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_NullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AspNetCore.Routing.IEndpointRouteBuilder endpoints = null!;
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            endpoints.MapOpenAIResponses(agentBuilder));

        Assert.Equal("endpoints", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses throws ArgumentNullException for null agentBuilder.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_NullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();
        IHostedAgentBuilder agentBuilder = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            app.MapOpenAIResponses(agentBuilder));

        Assert.Equal("agentBuilder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses with IHostedAgentBuilder correctly resolves and maps the agent.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agentBuilder);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that MapOpenAIResponses with IHostedAgentBuilder and custom path works correctly.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_CustomPath_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("my-agent", "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agentBuilder, path: "/agents/my-agent/responses");
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that multiple agents can be mapped using IHostedAgentBuilder.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_MultipleAgents_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent1Builder);
        app.MapOpenAIResponses(agent2Builder);
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
    public void MapOpenAIResponses_WithAgentBuilder_InvalidAgentNameCharacters_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(invalidName, "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            app.MapOpenAIResponses(agentBuilder));

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
    public void MapOpenAIResponses_WithAgentBuilder_ValidAgentNameCharacters_DoesNotThrow(string validName)
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(validName, "Instructions", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agentBuilder);
        Assert.NotNull(app);
    }

    /// <summary>
    /// Verifies that IHostedAgentBuilder overload with custom paths can be specified.
    /// </summary>
    [Fact]
    public void MapOpenAIResponses_WithAgentBuilder_MultipleAgentsWithCustomPaths_Succeeds()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agent1Builder = builder.AddAIAgent("agent1", "Instructions1", chatClientServiceKey: "chat-client");
        IHostedAgentBuilder agent2Builder = builder.AddAIAgent("agent2", "Instructions2", chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();
        using WebApplication app = builder.Build();

        // Act & Assert - Should not throw
        app.MapOpenAIResponses(agent1Builder, path: "/api/v1/agent1/responses");
        app.MapOpenAIResponses(agent2Builder, path: "/api/v1/agent2/responses");
        Assert.NotNull(app);
    }
}
