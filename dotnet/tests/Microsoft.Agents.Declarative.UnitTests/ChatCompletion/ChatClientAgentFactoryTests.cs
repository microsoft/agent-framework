// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.Declarative.UnitTests.ChatCompletion;

/// <summary>
/// Unit tests for <see cref="ChatClientAgentFactory"/>.
/// </summary>
public class ChatClientAgentFactoryTests
{
    private readonly Mock<IChatClient> _mockChatClient;
    private readonly Mock<IServiceProvider> _mockServiceProvider;
    private readonly Mock<ILoggerFactory> _mockLoggerFactory;

    public ChatClientAgentFactoryTests()
    {
        this._mockChatClient = new Mock<IChatClient>();
        this._mockServiceProvider = new Mock<IServiceProvider>();
        this._mockLoggerFactory = new Mock<ILoggerFactory>();
    }

    #region Constructor Tests

    [Fact]
    public void Constructor_InitializesWithCorrectSupportedTypes()
    {
        // Act
        var factory = new ChatClientAgentFactory();

        // Assert
        Assert.Contains(ChatClientAgentFactory.ChatClientAgentType, factory.Types);
    }

    #endregion

    #region TryCreateAsync Tests

    [Fact]
    public async Task TryCreateAsync_WithNullAgentDefinition_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            factory.TryCreateAsync(null!, options, CancellationToken.None));
    }

    [Fact]
    public async Task TryCreateAsync_WithUnsupportedAgentType_ReturnsNullAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: unsupported_type
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions();

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, CancellationToken.None);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_WithSupportedTypeAndChatClientInOptions_CreatesAgentAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions
        {
            ChatClient = this._mockChatClient.Object,
            LoggerFactory = this._mockLoggerFactory.Object
        };

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ChatClientAgent>(result);
    }

    [Fact]
    public async Task TryCreateAsync_WithSupportedTypeAndChatClientFromServiceProvider_CreatesAgentAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

        this._mockServiceProvider
            .Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(this._mockChatClient.Object);

        var options = new AgentCreationOptions
        {
            ServiceProvider = this._mockServiceProvider.Object,
            LoggerFactory = this._mockLoggerFactory.Object
        };

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ChatClientAgent>(result);
        this._mockServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.Once);
    }

    [Fact]
    public async Task TryCreateAsync_WithSupportedTypeButNoChatClient_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            factory.TryCreateAsync(agentDefinition, options, CancellationToken.None));

        Assert.Equal("agentCreationOptions", exception.ParamName);
        Assert.Contains("A chat client must be provided via the AgentCreationOptions.", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_WithSupportedTypeButServiceProviderReturnsNull_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

#pragma warning disable CS8603 // Possible null reference return.
        this._mockServiceProvider
            .Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(() => null);
#pragma warning restore CS8603 // Possible null reference return.

        var options = new AgentCreationOptions
        {
            ServiceProvider = this._mockServiceProvider.Object
        };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            factory.TryCreateAsync(agentDefinition, options, CancellationToken.None));

        Assert.Equal("agentCreationOptions", exception.ParamName);
        Assert.Contains("A chat client must be provided via the AgentCreationOptions.", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_WithChatClientInOptionsAndServiceProvider_PrefersChatClientInOptionsAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();
        var optionsChatClient = new Mock<IChatClient>().Object;
        var serviceProviderChatClient = new Mock<IChatClient>().Object;

        this._mockServiceProvider
            .Setup(sp => sp.GetService(typeof(IChatClient)))
            .Returns(serviceProviderChatClient);

        var options = new AgentCreationOptions
        {
            ChatClient = optionsChatClient,
            ServiceProvider = this._mockServiceProvider.Object,
            LoggerFactory = this._mockLoggerFactory.Object
        };

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ChatClientAgent>(result);
        var chatClientAgent = (ChatClientAgent)result;

        // Verify that the service provider was not called since ChatClient was provided directly
        this._mockServiceProvider.Verify(sp => sp.GetService(typeof(IChatClient)), Times.Never);
    }

    [Fact]
    public async Task TryCreateAsync_WithCancellationToken_CompletesSuccessfullyAsync()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions
        {
            ChatClient = this._mockChatClient.Object,
            LoggerFactory = this._mockLoggerFactory.Object
        };
        using var cts = new CancellationTokenSource();

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, cts.Token);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ChatClientAgent>(result);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("chat_client_agent")]
    public async Task TryCreateAsync_WithVariousAgentTypes_HandlesCorrectlyAsync(string? agentType)
    {
        // Arrange
        var yaml =
            $"""
            kind: GptComponentMetadata
            type: {agentType}
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(yaml);
        var factory = new ChatClientAgentFactory();
        var options = new AgentCreationOptions
        {
            ChatClient = this._mockChatClient.Object,
            LoggerFactory = this._mockLoggerFactory.Object
        };

        // Act
        var result = await factory.TryCreateAsync(agentDefinition, options, CancellationToken.None);

        // Assert
        if (agentType == ChatClientAgentFactory.ChatClientAgentType)
        {
            Assert.NotNull(result);
            Assert.IsType<ChatClientAgent>(result);
        }
        else
        {
            Assert.Null(result);
        }
    }

    #endregion

    #region IsSupported Tests

    [Fact]
    public void IsSupported_WithSupportedType_ReturnsTrue()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: chat_client_agent
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

        // Act
        var result = factory.IsSupported(agentDefinition);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void IsSupported_WithUnsupportedType_ReturnsFalse()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: unsupported_type
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

        // Act
        var result = factory.IsSupported(agentDefinition);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void IsSupported_WithNullType_ReturnsFalse()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

        // Act
        var result = factory.IsSupported(agentDefinition);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void IsSupported_WithEmptyType_ReturnsFalse()
    {
        // Arrange
        const string Yaml =
            """
            kind: GptComponentMetadata
            type: 
            name: JokerAgent
            instructions: You are good at telling jokes.
            """;
        var agentDefinition = AgentBotElementYaml.FromYaml(Yaml);
        var factory = new ChatClientAgentFactory();

        // Act
        var result = factory.IsSupported(agentDefinition);

        // Assert
        Assert.False(result);
    }

    #endregion

    #region Constant Tests

    [Fact]
    public void ChatClientAgentType_HasExpectedValue()
    {
        // Assert
        Assert.Equal("chat_client_agent", ChatClientAgentFactory.ChatClientAgentType);
    }

    #endregion
}
