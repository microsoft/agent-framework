// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the <see cref="ChatClientBuilderExtensions"/> class.
/// </summary>
public sealed class ChatClientBuilderExtensionsTests
{
    [Fact]
    public void BuildAIAgent_WithBasicParameters_CreatesAgent()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);

        // Act
        var agent = builder.BuildAIAgent(
            instructions: "Test instructions",
            name: "TestAgent",
            description: "Test description"
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("Test description", agent.Description);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    [Fact]
    public void BuildAIAgent_WithTools_SetsToolsInOptions()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);
        var tools = new List<AITool> { new Mock<AITool>().Object };

        // Act
        var agent = builder.BuildAIAgent(tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.ChatOptions);
        Assert.Equal(tools, agent.ChatOptions.Tools);
    }

    [Fact]
    public void BuildAIAgent_WithAllParameters_CreatesAgentCorrectly()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);
        var tools = new List<AITool> { new Mock<AITool>().Object };
        var loggerFactoryMock = new Mock<ILoggerFactory>();
        var serviceProviderMock = new Mock<IServiceProvider>();

        // Act
        var agent = builder.BuildAIAgent(
            instructions: "Complex instructions",
            name: "ComplexAgent",
            description: "Complex description",
            tools: tools,
            loggerFactory: loggerFactoryMock.Object,
            services: serviceProviderMock.Object
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("ComplexAgent", agent.Name);
        Assert.Equal("Complex description", agent.Description);
        Assert.Equal("Complex instructions", agent.Instructions);
        Assert.NotNull(agent.ChatOptions);
        Assert.Equal(tools, agent.ChatOptions.Tools);
    }

    [Fact]
    public void BuildAIAgent_WithOptions_CreatesAgentWithOptions()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);
        var options = new ChatClientAgentOptions
        {
            Name = "AgentWithOptions",
            Description = "Desc",
            Instructions = "Instr",
            UseProvidedChatClientAsIs = true
        };

        // Act
        var agent = builder.BuildAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("AgentWithOptions", agent.Name);
        Assert.Equal("Desc", agent.Description);
        Assert.Equal("Instr", agent.Instructions);
    }

    [Fact]
    public void BuildAIAgent_WithOptionsAndServices_CreatesAgentCorrectly()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);
        var loggerFactoryMock = new Mock<ILoggerFactory>();
        var serviceProviderMock = new Mock<IServiceProvider>();
        var options = new ChatClientAgentOptions
        {
            Name = "ServiceAgent",
            Instructions = "Service instructions"
        };

        // Act
        var agent = builder.BuildAIAgent(
            options: options,
            loggerFactory: loggerFactoryMock.Object,
            services: serviceProviderMock.Object
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("ServiceAgent", agent.Name);
        Assert.Equal("Service instructions", agent.Instructions);
    }

    [Fact]
    public void BuildAIAgent_WithNullBuilder_Throws()
    {
        // Arrange
        ChatClientBuilder builder = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.BuildAIAgent(instructions: "instructions"));
    }

    [Fact]
    public void BuildAIAgent_WithNullBuilderAndOptions_Throws()
    {
        // Arrange
        ChatClientBuilder builder = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.BuildAIAgent(options: new() { Instructions = "instructions" }));
    }

    [Fact]
    public void BuildAIAgent_WithMiddleware_BuildsCorrectPipeline()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var middlewareChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);

        // Add middleware that returns our mock
        builder.Use((client, services) => middlewareChatClientMock.Object);

        // Act
        var agent = builder.BuildAIAgent(
            new ChatClientAgentOptions
            {
                Instructions = "Middleware test",
                UseProvidedChatClientAsIs = true
            }
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Middleware test", agent.Instructions);
        // When UseProvidedChatClientAsIs is true, the agent should use the middleware chat client directly
        Assert.Same(middlewareChatClientMock.Object, agent.ChatClient);
    }

    [Fact]
    public void BuildAIAgent_WithNullOptions_CreatesAgentWithDefaults()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);

        // Act
        var agent = builder.BuildAIAgent(options: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
        Assert.Null(agent.Instructions);
    }

    [Fact]
    public void BuildAIAgent_WithEmptyParameters_CreatesMinimalAgent()
    {
        // Arrange
        var innerChatClientMock = new Mock<IChatClient>();
        var builder = new ChatClientBuilder(innerChatClientMock.Object);

        // Act
        var agent = builder.BuildAIAgent();

        // Assert
        Assert.NotNull(agent);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
        Assert.Null(agent.Instructions);
        Assert.Null(agent.ChatOptions);
    }
}
