// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class HarnessAgentTests
{
    private const int TestMaxContextWindowTokens = 100_000;
    private const int TestMaxOutputTokens = 10_000;

    #region Constructor Validation

    /// <summary>
    /// Verify that the constructor throws when chatClient is null.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenChatClientIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new HarnessAgent(null!, TestMaxContextWindowTokens, TestMaxOutputTokens));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxContextWindowTokens is invalid (zero).
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxContextWindowTokensIsZero()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, 0, TestMaxOutputTokens));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxOutputTokens equals MaxContextWindowTokens.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxOutputTokensEqualsContextWindow()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, 100_000, 100_000));
    }

    /// <summary>
    /// Verify that the constructor succeeds when options is null.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWhenOptionsIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region Agent Identity

    /// <summary>
    /// Verify that Name and Description are passed through to the inner agent.
    /// </summary>
    [Fact]
    public void NameAndDescription_ArePassedThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            Name = "TestAgent",
            Description = "A test agent",
        });

        // Assert
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("A test agent", agent.Description);
    }

    /// <summary>
    /// Verify that Id is passed through to the inner agent.
    /// </summary>
    [Fact]
    public void Id_IsPassedThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            Id = "my-agent-id",
        });

        // Assert
        Assert.Equal("my-agent-id", agent.Id);
    }

    #endregion

    #region Instructions

    /// <summary>
    /// Verify that default instructions are used when none are provided.
    /// </summary>
    [Fact]
    public void Instructions_DefaultsToBuiltInInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal(HarnessAgent.DefaultInstructions, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that default instructions are used when options is provided but ChatOptions.Instructions is null.
    /// </summary>
    [Fact]
    public void Instructions_DefaultsWhenChatOptionsInstructionsIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatOptions = new ChatOptions { Temperature = 0.5f },
        });
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal(HarnessAgent.DefaultInstructions, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions.Instructions overrides the defaults.
    /// </summary>
    [Fact]
    public void Instructions_CanBeOverriddenViaChatOptions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatOptions = new ChatOptions { Instructions = "You are a custom assistant." },
        });
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal("You are a custom assistant.", innerAgent!.Instructions);
    }

    #endregion

    #region ChatHistoryProvider

    /// <summary>
    /// Verify that the default ChatHistoryProvider is InMemoryChatHistoryProvider when none is specified.
    /// </summary>
    [Fact]
    public void ChatHistoryProvider_DefaultsToInMemory()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.IsType<InMemoryChatHistoryProvider>(innerAgent!.ChatHistoryProvider);
    }

    /// <summary>
    /// Verify that a custom ChatHistoryProvider is used when provided.
    /// </summary>
    [Fact]
    public void ChatHistoryProvider_UsesCustomProviderWhenSpecified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customProvider = new InMemoryChatHistoryProvider();

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatHistoryProvider = customProvider,
        });
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Same(customProvider, innerAgent!.ChatHistoryProvider);
    }

    #endregion

    #region ChatClient Pipeline

    /// <summary>
    /// Verify that the inner agent's ChatClient includes FunctionInvokingChatClient in the pipeline.
    /// </summary>
    [Fact]
    public void Pipeline_IncludesFunctionInvokingChatClient()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        var ficc = innerAgent!.ChatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(ficc);
    }

    /// <summary>
    /// Verify that the inner agent's ChatClient pipeline includes more than just the raw chat client,
    /// confirming that per-service-call persistence and other decorators have been applied.
    /// </summary>
    [Fact]
    public void Pipeline_HasDecoratedChatClient()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        var rawClient = mockClient.Object;

        // Act
        var agent = new HarnessAgent(rawClient, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — the pipeline wraps the raw client, so the outer client is not the same object.
        Assert.NotNull(innerAgent);
        Assert.NotSame(rawClient, innerAgent!.ChatClient);
    }

    #endregion

    #region AIContextProviders

    /// <summary>
    /// Verify that additional AIContextProviders from options are passed to the inner ChatClientAgent,
    /// not merged into the chat client builder pipeline.
    /// </summary>
    [Fact]
    public void AIContextProviders_ArePassedToInnerAgent()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var todoProvider = new TodoProvider();

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            AIContextProviders = [todoProvider],
        });
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — the TodoProvider should appear in the inner agent's AIContextProviders.
        Assert.NotNull(innerAgent);
        Assert.NotNull(innerAgent!.AIContextProviders);
        Assert.Contains(todoProvider, innerAgent.AIContextProviders!);
    }

    /// <summary>
    /// Verify that when no AIContextProviders are specified, the inner agent has no additional providers.
    /// </summary>
    [Fact]
    public void AIContextProviders_IsNullWhenNoneSpecified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Null(innerAgent!.AIContextProviders);
    }

    #endregion

    #region ChatOptions and Tools

    /// <summary>
    /// Verify that tools from ChatOptions are passed to the model during invocation.
    /// </summary>
    [Fact]
    public async Task ChatOptions_ToolsArePreservedAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "test", "TestTool");
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                Tools = [tool],
            },
        });
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — verify the tool was included in the ChatOptions passed to the model.
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions!.Tools);
        Assert.Contains(capturedOptions.Tools, t => t == tool);
    }

    /// <summary>
    /// Verify that the source ChatOptions are cloned and not modified.
    /// </summary>
    [Fact]
    public void ChatOptions_SourceIsNotModified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var sourceChatOptions = new ChatOptions
        {
            Instructions = "original instructions",
            Temperature = 0.7f,
        };

        // Act
        _ = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatOptions = sourceChatOptions,
        });

        // Assert — source ChatOptions should not be mutated.
        Assert.Equal("original instructions", sourceChatOptions.Instructions);
        Assert.Equal(0.7f, sourceChatOptions.Temperature);
    }

    #endregion

    #region GetService

    /// <summary>
    /// Verify that GetService returns the HarnessAgent for its own type.
    /// </summary>
    [Fact]
    public void GetService_ReturnsSelfForHarnessAgentType()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.Same(agent, agent.GetService<HarnessAgent>());
    }

    /// <summary>
    /// Verify that GetService returns the inner ChatClientAgent.
    /// </summary>
    [Fact]
    public void GetService_ReturnsInnerChatClientAgent()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.NotNull(agent.GetService<ChatClientAgent>());
    }

    #endregion

    #region RunAsync Delegation

    /// <summary>
    /// Verify that RunAsync delegates to the inner ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task RunAsync_DelegatesToInnerAgentAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello!")));

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            session);

        // Assert
        Assert.NotNull(response);
        Assert.True(response.Messages.Any());
    }

    #endregion

    #region DefaultInstructions

    /// <summary>
    /// Verify that DefaultInstructions is a non-empty public constant.
    /// </summary>
    [Fact]
    public void DefaultInstructions_IsNonEmpty()
    {
        // Assert
        Assert.False(string.IsNullOrWhiteSpace(HarnessAgent.DefaultInstructions));
    }

    #endregion

    #region AsHarnessAgent Extension Method

    /// <summary>
    /// Verify that AsHarnessAgent creates a HarnessAgent with default options.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_CreatesAgentWithDefaults()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = chatClient.AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<HarnessAgent>(agent);
        Assert.Equal(HarnessAgent.DefaultInstructions, agent.GetService<ChatClientAgent>()!.Instructions);
    }

    /// <summary>
    /// Verify that AsHarnessAgent passes options through to the HarnessAgent.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_PassesOptionsThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = chatClient.AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            Name = "ExtensionAgent",
            ChatOptions = new ChatOptions { Instructions = "Custom instructions" },
        });
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.Equal("ExtensionAgent", agent.Name);
        Assert.NotNull(innerAgent);
        Assert.Equal("Custom instructions", innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that AsHarnessAgent throws when chatClient is null.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_ThrowsWhenChatClientIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((IChatClient)null!).AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens));
    }

    #endregion
}
