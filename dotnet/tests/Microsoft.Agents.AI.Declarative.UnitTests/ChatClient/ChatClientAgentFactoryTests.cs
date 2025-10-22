// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for <see cref="ChatClientAgentFactory"/>.
/// </summary>
public sealed class ChatClientAgentFactoryTests
{
    private readonly Mock<IChatClient> _mockChatClient;
    private readonly Mock<ILoggerFactory> _mockLoggerFactory;

    public ChatClientAgentFactoryTests()
    {
        this._mockChatClient = new();
        this._mockLoggerFactory = new();
    }

    [Fact]
    public async Task TryCreateAsync_WithChatClientInConstructor_CreatesAgent()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        ChatClientAgentFactory factory = new(chatClient: this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, agentCreationOptions: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("Test Description", agent.Description);
    }

    [Fact]
    public async Task TryCreateAsync_WithServiceProviderInConstructor_ResolvesAndCreatesAgent()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IServiceProvider> mockServiceProvider = new();
        mockServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(this._mockChatClient.Object);
        mockServiceProvider.Setup(sp => sp.GetService(typeof(ILoggerFactory)))
            .Returns(this._mockLoggerFactory.Object);

        ChatClientAgentFactory factory = new(serviceProvider: mockServiceProvider.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, agentCreationOptions: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        mockServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.AtLeastOnce);
    }

    [Fact]
    public async Task TryCreateAsync_WithServiceProviderInConstructor_NoIChatClient_ThrowsArgumentException()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IServiceProvider> mockServiceProvider = new();
        mockServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(null);

        ChatClientAgentFactory factory = new(serviceProvider: mockServiceProvider.Object);

        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(
            () => factory.TryCreateAsync(promptAgent, agentCreationOptions: null));
        Assert.Contains("A chat client must be provided", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_WithChatClientInOptions_CreatesAgent()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        ChatClientAgentCreationOptions options = new()
        {
            ChatClient = this._mockChatClient.Object
        };
        ChatClientAgentFactory factory = new();

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    [Fact]
    public async Task TryCreateAsync_WithoutChatClientInOptions_ThrowsArgumentException()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        ChatClientAgentCreationOptions options = new();
        ChatClientAgentFactory factory = new();

        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(
            () => factory.TryCreateAsync(promptAgent, options));
        Assert.Contains("A chat client must be provided", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_WithServiceProviderInOptions_ResolvesAndCreatesAgent()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IServiceProvider> mockServiceProvider = new();
        mockServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(this._mockChatClient.Object);
        mockServiceProvider.Setup(sp => sp.GetService(typeof(ILoggerFactory)))
            .Returns(this._mockLoggerFactory.Object);

        ChatClientAgentCreationOptions options = new()
        {
            ServiceProvider = mockServiceProvider.Object
        };
        ChatClientAgentFactory factory = new();

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        mockServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.AtLeastOnce);
    }

    [Fact]
    public async Task TryCreateAsync_WithServiceProviderInOptions_NoIChatClient_ThrowsArgumentException()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IServiceProvider> mockServiceProvider = new();
        mockServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(null);

        ChatClientAgentCreationOptions options = new()
        {
            ServiceProvider = mockServiceProvider.Object
        };
        ChatClientAgentFactory factory = new();

        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(
            () => factory.TryCreateAsync(promptAgent, options));
        Assert.Contains("A chat client must be provided", exception.Message);
    }
    /*
    [Fact]
    public async Task TryCreateAsync_WithKeyedServiceInOptions_ResolvesKeyedClient()
    {
        // Arrange
        const string expectedPublisher = "TestPublisher";
        PromptAgent promptAgent = CreateTestPromptAgentWithPublisher(expectedPublisher);

        Mock<IChatClient> keyedChatClient = new();
        Mock<IServiceProvider> mockServiceProvider = new();

        mockServiceProvider.Setup(sp => sp.GetKeyedService(typeof(IChatClient), It.Is<object>(key => key.ToString() == expectedPublisher)))
            .Returns(keyedChatClient.Object);
        mockServiceProvider.Setup(sp => sp.GetService(typeof(ILoggerFactory)))
            .Returns(this._mockLoggerFactory.Object);

        ChatClientAgentCreationOptions options = new()
        {
            ServiceProvider = mockServiceProvider.Object
        };
        ChatClientAgentFactory factory = new();

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        mockServiceProvider.Verify(sp => sp.GetKeyedService(typeof(IChatClient), It.Is<object>(key => key.ToString() == expectedPublisher)), Times.Once);
    }

    [Fact]
    public async Task TryCreateAsync_WithKeyedServiceInOptions_FallsBackToNonKeyed()
    {
        // Arrange
        const string expectedPublisher = "TestPublisher";
        PromptAgent promptAgent = CreateTestPromptAgentWithPublisher(expectedPublisher);

        Mock<IServiceProvider> mockServiceProvider = new();

        mockServiceProvider.Setup(sp => sp.GetKeyedService(typeof(IChatClient), It.Is<object>(key => key.ToString() == expectedPublisher)))
            .Returns(null);
        mockServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(this._mockChatClient.Object);
        mockServiceProvider.Setup(sp => sp.GetService(typeof(ILoggerFactory)))
            .Returns(this._mockLoggerFactory.Object);

        ChatClientAgentCreationOptions options = new()
        {
            ServiceProvider = mockServiceProvider.Object
        };
        ChatClientAgentFactory factory = new();

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        mockServiceProvider.Verify(sp => sp.GetKeyedService(typeof(IChatClient), It.Is<object>(key => key.ToString() == expectedPublisher)), Times.Once);
        mockServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.AtLeastOnce);
    }
    */
    [Fact]
    public async Task TryCreateAsync_OptionsOverrideConstructor_UsesOptionsClient()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IChatClient> constructorClient = new();
        Mock<IChatClient> optionsClient = new();

        ChatClientAgentCreationOptions options = new()
        {
            ChatClient = optionsClient.Object
        };
        ChatClientAgentFactory factory = new(chatClient: constructorClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    [Fact]
    public async Task TryCreateAsync_OptionsServiceProviderOverridesConstructor_UsesOptionsServiceProvider()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        Mock<IServiceProvider> constructorServiceProvider = new();
        Mock<IServiceProvider> optionsServiceProvider = new();

        optionsServiceProvider.Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(this._mockChatClient.Object);

        ChatClientAgentCreationOptions options = new()
        {
            ServiceProvider = optionsServiceProvider.Object
        };
        ChatClientAgentFactory factory = new(serviceProvider: constructorServiceProvider.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, options);

        // Assert
        Assert.NotNull(agent);
        optionsServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.AtLeastOnce);
        constructorServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.Never);
    }

    [Fact]
    public async Task TryCreateAsync_WithNullPromptAgent_ThrowsArgumentNullException()
    {
        // Arrange
        ChatClientAgentFactory factory = new(chatClient: this._mockChatClient.Object);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => factory.TryCreateAsync(null!, agentCreationOptions: null));
    }

    [Fact]
    public async Task TryCreateAsync_SetsAgentPropertiesFromPromptAgent()
    {
        // Arrange
        PromptAgent promptAgent = CreateTestPromptAgent();
        ChatClientAgentFactory factory = new(chatClient: this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent, agentCreationOptions: null);

        // Assert
        Assert.NotNull(agent);
        ChatClientAgent chatClientAgent = Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal(promptAgent.Name, chatClientAgent.Name);
        Assert.Equal(promptAgent.Description, chatClientAgent.Description);
    }

    private static PromptAgent CreateTestPromptAgent(string? publisher = null)
    {
        string agentYaml =
            $"""
            kind: Prompt
            name: Test Agent
            description: Test Description
            instructions: You are a helpful assistant.
            model:
              kind: OpenAIResponsesModel
              id: gpt-4o
              publisher: {publisher}
              connection:
                kind: Key
                endpoint: https://my-azure-openai-endpoint.openai.azure.com/
                key: my-api-key
            """;

        return AgentBotElementYaml.FromYaml(agentYaml);
    }
}
